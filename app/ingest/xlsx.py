import time
from pathlib import Path

import openpyxl

from app.db import db
from app.ingest.pipeline import _file_hash


def _rows(ws, header_row: int) -> list[dict]:
    hdr = [c for c in next(ws.iter_rows(min_row=header_row, max_row=header_row, values_only=True))]
    out = []
    for r in ws.iter_rows(min_row=header_row + 1, values_only=True):
        if all(v is None for v in r):
            continue
        out.append({hdr[i]: r[i] for i in range(min(len(hdr), len(r)))})
    return out


def _find_header(ws, tokens: list[str], limit: int = 10) -> int:
    for i, r in enumerate(ws.iter_rows(min_row=1, max_row=limit, values_only=True), start=1):
        vals = [str(v).strip().lower() for v in r if v is not None]
        if all(any(t == v or t in v for v in vals) for t in tokens):
            return i
    return 1


def _num(v):
    if v is None or v == "":
        return None
    try:
        return float(str(v).replace(",", "").replace("%", ""))
    except ValueError:
        return None


def ingest_rapidratings(path: str | Path, display_name: str = "") -> dict:
    t0 = time.perf_counter()
    path = Path(path)
    fhash = _file_hash(path)
    existing = db.df(
        "SELECT imported_at FROM meta_datasets WHERE file_hash = ? AND dataset_key = 'rapidratings'",
        [fhash],
    )
    if len(existing):
        return {
            "dataset": "rapidratings",
            "label": "RapidRatings 供应商风险",
            "status": "duplicate",
            "note": f"该文件已于 {existing.iloc[0]['imported_at']} 导入",
            "rows_loaded": 0,
            "rows_quarantined": 0,
            "checks": [],
            "seconds": round(time.perf_counter() - t0, 2),
        }

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    loaded = {}

    if "Master List" in wb.sheetnames:
        ws = wb["Master List"]
        hr = _find_header(ws, ["vendor name"])
        master = _rows(ws, hr)
        recs = []
        for r in master:
            name = r.get("Vendor Name")
            if not name:
                continue
            recs.append(
                [
                    str(name).strip(),
                    str(r.get("Vendor Contact Name") or "").strip(),
                    str(r.get("Vendor Contact E-mail") or "").strip(),
                    str(r.get("Vendor Contact Phone") or "").strip(),
                    str(r.get("Vendor Type") or "").strip(),
                    str(r.get("Division") or "").strip(),
                    str(r.get("Vendor Location") or "").strip(),
                    str(r.get("Is a Single Source Supplier?") or "").strip(),
                    str(r.get("RRID") or "").strip(),
                    _num(r.get("FHR")),
                ]
            )
        db.sql("BEGIN")
        db.sql("DELETE FROM rr_master")
        if recs:
            db.sql(
                "INSERT INTO rr_master(vendor_name, contact_name, contact_email, contact_phone,"
                "vendor_type, division, location, single_source, rr_id, fhr) VALUES "
                + ",".join(["(?,?,?,?,?,?,?,?,?,?)"] * len(recs)),
                [v for rec in recs for v in rec],
            )
        db.sql("COMMIT")
        loaded["master"] = len(recs)

    if "RRstatus - July 10 2024" in wb.sheetnames:
        ws = wb["RRstatus - July 10 2024"]
        hr = _find_header(ws, ["target company name", "current status"])
        status = _rows(ws, hr)
        recs = []
        for r in status:
            comp = r.get("Target Company Name")
            if not comp:
                continue
            recs.append(
                [
                    str(comp).strip(),
                    str(r.get("Current Status") or "").strip(),
                    _num(r.get("FHR Rating")),
                    str(r.get("Request Created Date") or "")[:10],
                    str(r.get("Submission Date (UTC)") or "")[:10],
                    str(r.get("Reason") or "").strip(),
                ]
            )
        db.sql("BEGIN")
        db.sql("DELETE FROM rr_status")
        if recs:
            db.sql(
                "INSERT INTO rr_status VALUES " + ",".join(["(?,?,?,?,?,?)"] * len(recs)),
                [v for rec in recs for v in rec],
            )
        db.sql("COMMIT")
        loaded["status"] = len(recs)

    if "RR Recommendations" in wb.sheetnames:
        ws = wb["RR Recommendations"]
        hr = _find_header(ws, ["company", "ticker"])
        year_row = list(ws.iter_rows(min_row=hr - 1, max_row=hr - 1, values_only=True))[0]
        hdr = list(next(ws.iter_rows(min_row=hr, max_row=hr, values_only=True)))
        recs = []
        hist = []
        for r in ws.iter_rows(min_row=hr + 1, values_only=True):
            if r[1] is None:
                continue
            company = str(r[1]).strip()
            cur = sim = epd = None
            for i, v in enumerate(r):
                s = str(v or "")
                if len(s) >= 8 and s[:4].isdigit() and "-" in s[4:8] and s[4] == "-":
                    cur, sim, epd = _num(r[i + 1]), _num(r[i + 2]), _num(r[i + 3])
                    break
            if cur is not None:
                recs.append([company, cur, epd if epd is not None else 0.0])
            for k in range(4, min(len(hdr), 22)):
                val = _num(r[k]) if k < len(r) else None
                if val is None or not (0 < val <= 100):
                    continue
                yr = year_row[k - 4] if k - 4 < len(year_row) else None
                label = hdr[k]
                if yr and label:
                    hist.append([company, f"{str(yr).split('.')[0]}-{str(label).strip()}", val])
        db.sql("BEGIN")
        db.sql("DELETE FROM rr_fhr_hist")
        if hist:
            db.sql(
                "INSERT INTO rr_fhr_hist VALUES " + ",".join(["(?,?,?)"] * len(hist)),
                [v for rec in hist for v in rec],
            )
        db.sql("COMMIT")
        loaded["fhr_hist"] = len(hist)
        loaded["fhr_current"] = len(recs)

    wb.close()
    db.sql(
        "INSERT INTO meta_datasets(dataset_key, file_name, label, rows_loaded, rows_quarantined,"
        " file_hash, status) VALUES ('rapidratings',?,?,?,?,?,'ok')",
        [
            display_name or path.name,
            "RapidRatings 供应商风险",
            sum(loaded.values()),
            0,
            fhash,
        ],
    )
    return {
        "dataset": "rapidratings",
        "label": "RapidRatings 供应商风险",
        "status": "ok",
        "note": f"Master {loaded.get('master', 0)} 家 / 状态 {loaded.get('status', 0)} 条 / "
        f"当前FHR {loaded.get('fhr_current', 0)} 家 / 历史序列 {loaded.get('fhr_hist', 0)} 条",
        "rows_loaded": sum(loaded.values()),
        "rows_quarantined": 0,
        "seconds": round(time.perf_counter() - t0, 2),
        "checks": [
            {
                "check": "FHR 覆盖率（Master List）",
                "value": db.scalar(
                    "SELECT round(100.0*count(fhr)/nullif(count(*),0),1) FROM rr_master"
                ),
                "note": "未评级供应商显示为无数据，不得当作低风险或高风险",
            }
        ],
    }


def ingest_file(path: str | Path, display_name: str = "") -> dict:
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xlsm") and "rapidratings" in path.name.lower():
        return ingest_rapidratings(path, display_name)
    from app.ingest.pipeline import ingest_csv

    return ingest_csv(path, display_name)
