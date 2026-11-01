import pandas as pd

from app.db import db
from app.market.sources import (
    TE_SOURCE,
    WB_SOURCE,
    _now,
    _save_status,
    fetch_te_board,
    fetch_wb_monthly,
    source_status,
    wb_board,
)

BOARD_COLS = [
    "commodity",
    "price",
    "day_pct",
    "week_pct",
    "month_pct",
    "ytd_pct",
    "y1_pct",
    "data_date",
    "source",
    "fetched_at",
]
CN = {
    "commodity": "商品",
    "price": "最新价",
    "day_pct": "日涨跌%",
    "week_pct": "周涨跌%",
    "month_pct": "月环比%",
    "ytd_pct": "年初至今%",
    "y1_pct": "同比%",
    "data_date": "数据日期",
    "source": "数据来源",
    "fetched_at": "抓取时间",
}


def refresh() -> tuple[pd.DataFrame, str]:
    df, err = None, ""
    try:
        df = fetch_te_board()
        _save_status({"primary": {"source": TE_SOURCE, "ok": True, "at": _now(), "error": ""}})
    except Exception as e:
        err = f"TradingEconomics 抓取失败（{type(e).__name__}: {e}），已切换世界银行兜底"
        _save_status(
            {"primary": {"source": TE_SOURCE, "ok": False, "at": _now(), "error": str(e)[:160]}}
        )
    if df is None or df.empty:
        try:
            df = wb_board()
            err = err or "当前使用世界银行 Pink Sheet 月度数据"
        except Exception as e:
            return board(), f"主源与兜底均失败：{e}"
    df = df.reindex(columns=BOARD_COLS)
    db.sql("BEGIN")
    db.sql("DELETE FROM market_snapshot WHERE fetched_at < now() - INTERVAL 400 DAY")
    recs = df.where(pd.notna(df), None).values.tolist()
    if recs:
        ph = ",".join(["?"] * len(BOARD_COLS))
        db.sql(
            f"INSERT INTO market_snapshot({','.join(BOARD_COLS)}) VALUES "
            + ",".join([f"({ph})"] * len(recs)),
            [v for rec in recs for v in rec],
        )
    db.sql("COMMIT")
    return board(), err


def board() -> pd.DataFrame:
    try:
        df = db.df(
            "SELECT * FROM market_snapshot WHERE fetched_at = "
            "(SELECT max(fetched_at) FROM market_snapshot) ORDER BY commodity"
        )
    except Exception:
        df = pd.DataFrame(columns=BOARD_COLS)
    if df.empty:
        return pd.DataFrame(columns=list(CN.values()))
    df = df.reindex(columns=BOARD_COLS).rename(columns=CN)
    for c in ["最新价", "日涨跌%", "周涨跌%", "月环比%", "年初至今%", "同比%"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").round(2)
    return df


def source_note() -> str:
    df = board()
    if df.empty:
        return "尚未抓取市场数据。点击「立即刷新」后写入来源与时间。"
    src = df["数据来源"].dropna().unique().tolist()
    at = df["抓取时间"].dropna().unique().tolist()
    dd = df["数据日期"].dropna().unique().tolist()
    st = source_status().get("primary", {})
    health = "主源正常" if st.get("ok") else f"主源异常，走兜底：{st.get('error','')[:60]}"
    return (
        f"来源：{'、'.join(src)}　|　数据日期：{'、'.join(map(str, dd[:3]))}　|　"
        f"抓取时间：{'、'.join(map(str, at))}　|　{health}"
    )


def alerts(board_df: pd.DataFrame | None = None) -> str:
    df = board_df if board_df is not None else board()
    if df.empty or "月环比%" not in df:
        return "暂无预警（无数据）。"
    hits = df[df["月环比%"].abs() > 5].sort_values("月环比%", key=lambda s: s.abs(), ascending=False)
    if hits.empty:
        return "当前无异动预警（阈值：月环比绝对值 > 5%）。"
    items = []
    for _, r in hits.iterrows():
        y1 = r["同比%"]
        y1_txt = f"{y1:+.1f}%" if pd.notna(y1) else "—"
        items.append(
            f"<li><b>{r['商品']}</b>：月环比 {r['月环比%']:+.1f}%，同比 {y1_txt}"
            f"　<span style='color:#94A3B8'>{r['数据来源']} · {r['数据日期']}</span></li>"
        )
    return (
        '<div style="background:#FEF2F2;border:1px solid #FECACA;border-radius:10px;'
        'padding:12px"><div style="font-weight:600;color:#991B1B;margin-bottom:6px">'
        "市场异动预警（月环比 &gt;5%）</div><ul style=\"margin:0;padding-left:18px;"
        'font-size:13px;color:#7F1D1D">' + "".join(items) + "</ul></div>"
    )


def commodity_options() -> list[str]:
    try:
        df = db.df("SELECT DISTINCT commodity FROM market_snapshot ORDER BY commodity")
        return df["commodity"].tolist()
    except Exception:
        return []


def history(commodity: str) -> pd.DataFrame:
    try:
        h = fetch_wb_monthly()
        h = h[h["commodity"] == commodity][["date", "price", "source"]]
        if not h.empty:
            return h.sort_values("date").reset_index(drop=True)
    except Exception:
        pass
    try:
        return db.df(
            "SELECT CAST(fetched_at AS DATE) AS date, price, 'TE 快照' AS source "
            "FROM market_snapshot WHERE commodity = ? ORDER BY fetched_at",
            [commodity],
        )
    except Exception:
        return pd.DataFrame(columns=["date", "price", "source"])


def history_stats(commodity: str) -> str:
    h = history(commodity)
    if h.empty:
        return f"{commodity}：暂无历史序列。"
    p = pd.to_numeric(h["price"], errors="coerce").dropna()
    if len(p) < 2:
        return f"{commodity}：历史数据不足。"
    mom = (p.iloc[-1] / p.iloc[-2] - 1) * 100
    yoy = (p.iloc[-1] / p.iloc[-13] - 1) * 100 if len(p) >= 13 else float("nan")
    d = pd.to_datetime(h["date"])
    pos = 100 * (p < p.iloc[-1]).mean()
    return (
        f"{commodity}｜{h['source'].iloc[0]}｜{d.min():%Y-%m} ~ {d.max():%Y-%m}："
        f"最新 {p.iloc[-1]:,.2f} · 月环比 {mom:+.1f}% · 同比 {yoy:+.1f}% · "
        f"历史分位 {pos:.0f}%（越高表示当前价处于历史高位）"
    )
