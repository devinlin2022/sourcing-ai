import hashlib
import time
from pathlib import Path

from app.db import db
from app.ingest.profiles import Profile, detect_profile
from app.ingest.reader import ensure_utf8, read_header


def _col_expr(src: str, typ: str, zero_null: bool) -> str:
    safe = src.replace('"', '""')
    if typ == "VARCHAR":
        return f'nullif(trim("{safe}"), \'\')'
    expr = f'try_cast(trim("{safe}") AS {typ})'
    if zero_null:
        expr = f"nullif({expr}, 0)"
    return expr


def _sql_literal(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def _file_hash(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _quality_checks(p: Profile) -> list[dict]:
    checks = []
    base = "stg_load" if p.table == "cost_exhibit" else p.table
    key_cols = ", ".join(p.keys)
    dup = db.scalar(
        f"SELECT count(*) FROM (SELECT {key_cols} FROM {p.table} "
        f"GROUP BY {key_cols} HAVING count(*) > 1)"
    )
    checks.append({"check": "主键重复行", "value": int(dup), "note": ""})
    for c in p.cols:
        if c.dst in p.keys:
            nulls = db.scalar(f"SELECT count(*) FROM {p.table} WHERE {c.dst} IS NULL")
            checks.append(
                {"check": f"关键列空值 {c.dst}", "value": int(nulls), "note": ""}
            )
    if p.table == "cost_exhibit":
        naive = db.scalar(f"SELECT round(sum(annual_spend), 0) FROM {base}")
        dedup = db.scalar(
            f"SELECT round(sum(v), 0) FROM "
            f"(SELECT max(annual_spend) AS v FROM {base} GROUP BY material, plant)"
        )
        ratio = (naive / dedup) if dedup else 0
        checks.append(
            {
                "check": "年支出：直接SUM vs 按(物料,工厂)取MAX",
                "value": f"{naive:,.0f} vs {dedup:,.0f}（{ratio:.2f}x）",
                "note": "金额与数量是工厂级字段，在多供应商行上重复；且同一(物料,工厂)存在主值+微量值两条，必须取MAX。直接SUM虚高约7倍",
            }
        )
    return checks


def ingest_csv(path: str | Path, display_name: str = "") -> dict:
    t0 = time.perf_counter()
    path = Path(path)
    utf8 = ensure_utf8(path)
    header = read_header(utf8)
    profile = detect_profile(header)
    if profile is None:
        raise ValueError(
            "无法识别文件类型。当前支持：Cost Exhibit / PO History / ICP / Vendor Master / "
            f"Info Record / Logistic RateCard / Spend Changes / RapidRatings(xlsx)。表头: {header[:6]}..."
        )
    fhash = _file_hash(path)

    existing = db.df(
        "SELECT imported_at FROM meta_datasets WHERE file_hash = ? AND dataset_key = ?",
        [fhash, profile.pid],
    )
    if len(existing):
        return {
            "dataset": profile.pid,
            "label": profile.label,
            "status": "duplicate",
            "note": f"该文件已于 {existing.iloc[0]['imported_at']} 导入，未重复处理",
            "rows_loaded": 0,
            "rows_quarantined": 0,
            "checks": [],
            "seconds": round(time.perf_counter() - t0, 2),
        }

    select_items = ", ".join(
        f"{_col_expr(c.src, c.typ, c.zero_null)} AS {c.dst}" for c in profile.cols
    )
    csv_path = _sql_literal(utf8.replace("\\", "/"))

    db.sql("DROP TABLE IF EXISTS stg_load")
    db.sql(
        f"CREATE TEMP TABLE stg_load AS SELECT {select_items} "
        f"FROM read_csv({csv_path}, header = true, all_varchar = true)"
    )
    db.sql("ALTER TABLE stg_load ADD COLUMN _bad BOOLEAN DEFAULT FALSE")
    total = db.scalar("SELECT count(*) FROM stg_load")

    if profile.anomaly:
        db.sql(f"UPDATE stg_load SET _bad = coalesce(({profile.anomaly}), false)")
        for col in profile.anomaly_null:
            db.sql(f"UPDATE stg_load SET {col} = NULL WHERE _bad")
    flagged = int(db.scalar("SELECT count(*) FROM stg_load WHERE _bad"))

    insert_cols = ", ".join(c.dst for c in profile.cols)
    db.sql("BEGIN")
    if flagged:
        db.sql(
            f"INSERT INTO quarantine(dataset_key, table_name, reason, payload) "
            f"SELECT {_sql_literal(profile.pid)}, {_sql_literal(profile.table)}, "
            f"{_sql_literal(profile.anomaly_note)}, json_remove(to_json(s), '$._bad') "
            f"FROM (SELECT DISTINCT * FROM stg_load WHERE _bad) s"
        )
    if profile.upsert == "row":
        full_join = " AND ".join(
            f"t.{c.dst} IS NOT DISTINCT FROM s.{c.dst}" for c in profile.cols
        )
        db.sql(
            f"INSERT INTO {profile.table} SELECT {insert_cols} FROM stg_load s "
            f"WHERE NOT EXISTS (SELECT 1 FROM {profile.table} t WHERE {full_join})"
        )
    else:
        delete_join = " AND ".join(
            f"{profile.table}.{k} IS NOT DISTINCT FROM s.{k}" for k in profile.keys
        )
        db.sql(f"DELETE FROM {profile.table} USING stg_load s WHERE {delete_join}")
        db.sql(f"INSERT INTO {profile.table} SELECT {insert_cols} FROM stg_load s")
    db.sql("COMMIT")

    loaded = int(total)
    checks = _quality_checks(profile)
    if flagged:
        checks.insert(
            0,
            {
                "check": "异常字段置空（行保留）",
                "value": f"{flagged} 行",
                "note": f"{profile.anomaly_note}；已置空 {', '.join(profile.anomaly_null)}，"
                f"金额与用量保留可用",
            },
        )
    db.sql(
        "INSERT INTO meta_datasets(dataset_key, file_name, label, rows_loaded, "
        "rows_quarantined, file_hash, status) VALUES (?,?,?,?,?,?,?)",
        [profile.pid, display_name or path.name, profile.label, loaded, flagged, fhash, "ok"],
    )
    db.sql("DROP TABLE IF EXISTS stg_load")

    return {
        "dataset": profile.pid,
        "label": profile.label,
        "status": "ok",
        "note": "",
        "rows_loaded": loaded,
        "rows_quarantined": flagged,
        "checks": checks,
        "seconds": round(time.perf_counter() - t0, 2),
    }


def datasets_overview() -> list[dict]:
    df = db.df(
        "SELECT dataset_key, label, file_name, rows_loaded, rows_quarantined, "
        "CAST(imported_at AS VARCHAR) AS imported_at, status FROM meta_datasets "
        "QUALIFY row_number() OVER (PARTITION BY dataset_key ORDER BY imported_at DESC) = 1 "
        "ORDER BY imported_at DESC"
    )
    return df.to_dict("records")


def quarantine_rows(dataset_key: str | None = None) -> list[dict]:
    q = "SELECT table_name, reason, payload, CAST(created_at AS VARCHAR) AS created_at FROM quarantine"
    if dataset_key:
        return db.df(q + " WHERE dataset_key = ?", [dataset_key]).to_dict("records")
    return db.df(q).to_dict("records")
