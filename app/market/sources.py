import io
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import openpyxl
import pandas as pd
from bs4 import BeautifulSoup

from app.config import DATA_DIR

CACHE_DIR = Path(DATA_DIR) / "cache"
UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
}
TE_URL = "https://tradingeconomics.com/commodities"
TE_SOURCE = "TradingEconomics"
WB_SOURCE = "World Bank Pink Sheet（月度）"
WB_URL = (
    "https://thedocs.worldbank.org/en/doc/"
    "18675f1d1639c7a34d463f59263ba0a2-0050012025/related/CMO-Historical-Data-Monthly.xlsx"
)
WB_PAGE = "https://www.worldbank.org/en/research/commodity-markets"
FRED_SOURCE = "FRED（圣路易斯联储）"

FRED_SERIES = {
    "Crude Oil": "DCOILWTICO",
    "Brent": "DCOILBRENTEU",
    "Natural gas": "DHHNGSP",
    "Copper": "PCOPPUSDM",
    "Aluminum": "PALUMUSDM",
    "Wheat": "PWHEAMTUSDM",
    "Soybeans": "PSOYBUSDM",
    "Cotton": "PCOTTINDUSDM",
    "Coffee": "PCOFFOTMUSDM",
    "Sugar": "PSUGAISAUSDM",
}

WB_SERIES = {
    "Crude Oil": "Crude oil, average",
    "Brent": "Crude oil, Brent",
    "Natural gas": "Natural gas, US",
    "Coal": "Coal, Australian",
    "Copper": "Copper",
    "Aluminum": "Aluminum",
    "Zinc": "Zinc",
    "Nickel": "Nickel",
    "Wheat": "Wheat, US SRW",
    "Soybeans": "Soybeans",
    "Cotton": "Cotton, A Index",
    "Sugar": "Sugar, world",
    "Coffee": "Coffee, Arabica",
    "Cocoa": "Cocoa",
    "Palm oil": "Palm oil",
}

_PCT = re.compile(r"^([+\-−]?)\s*([\d,]*\.?\d+)\s*%$")
_NUM = re.compile(r"^([+\-−]?)\s*([\d,]*\.?\d+)$")


def _num(text) -> float | None:
    t = str(text).strip().replace("−", "-").replace(" ", "").replace("\u2212", "-")
    if not t or t in ("…", "-", ".."):
        return None
    m = _PCT.match(t) or _NUM.match(t)
    if not m:
        return None
    sign = -1 if m.group(1) == "-" else 1
    try:
        return sign * float(m.group(2).replace(",", ""))
    except ValueError:
        return None


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def fetch_te_board() -> pd.DataFrame:
    r = httpx.get(TE_URL, headers=UA, timeout=25, follow_redirects=True)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    tables = [t for t in soup.find_all("table") if t.find("a", href=re.compile(r"^/commodity/"))]
    if not tables:
        raise RuntimeError("未找到商品表，页面结构可能已变化")

    seen, rows = set(), []
    for table in tables:
        ths = [th.get_text(" ", strip=True).lower() for th in table.find_all("th")]

        def idx(*words):
            for i, h in enumerate(ths):
                if any(w == h for w in words):
                    return i
            for i, h in enumerate(ths):
                if any(w in h for w in words):
                    return i
            return None

        i_price = idx("price")
        i_day = idx("%chg", "chg")
        i_week = idx("weekly")
        i_month = idx("monthly")
        i_ytd = idx("ytd")
        i_y1 = idx("yoy")
        i_date = idx("date")

        for tr in table.find_all("tr")[1:]:
            a = tr.find("a", href=re.compile(r"^/commodity/"))
            if a is None:
                continue
            tds = tr.find_all("td")
            if len(tds) < 4:
                continue
            name = a.get_text(strip=True)
            if not name or name in seen:
                continue

            def cell(i):
                if i is None or i >= len(tds):
                    return None
                return _num(tds[i].get_text(" ", strip=True))

            price = cell(i_price)
            if price is None:
                continue
            seen.add(name)
            rows.append(
                {
                    "commodity": name,
                    "price": price,
                    "day_pct": cell(i_day),
                    "week_pct": cell(i_week),
                    "month_pct": cell(i_month),
                    "ytd_pct": cell(i_ytd),
                    "y1_pct": cell(i_y1),
                    "data_date": tds[i_date].get_text(strip=True) if i_date is not None else "",
                }
            )
    if not rows:
        raise RuntimeError("商品表解析为空")
    df = pd.DataFrame(rows)
    df["source"] = TE_SOURCE
    df["fetched_at"] = _now()
    return df


def _resolve_wb_url() -> str:
    try:
        r = httpx.get(WB_PAGE, headers=UA, timeout=25, follow_redirects=True)
        hits = re.findall(
            r"https://thedocs\.worldbank\.org[^\"']*CMO-Historical-Data-Monthly\.xlsx", r.text
        )
        if hits:
            return hits[0]
    except Exception:
        pass
    return WB_URL


def _wb_cached_xlsx() -> bytes:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    p = CACHE_DIR / "wb_pink.xlsx"
    if p.exists() and time.time() - p.stat().st_mtime < 86400:
        return p.read_bytes()
    url = _resolve_wb_url()
    r = httpx.get(url, headers=UA, timeout=60, follow_redirects=True)
    r.raise_for_status()
    p.write_bytes(r.content)
    return r.content


def fetch_wb_monthly() -> pd.DataFrame:
    raw = _wb_cached_xlsx()
    wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True, read_only=True)
    ws = wb["Monthly Prices"]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    hdr, body = rows[4], rows[6:]
    want = {v: k for k, v in WB_SERIES.items()}
    colmap = {i: want[h] for i, h in enumerate(hdr) if h in want}
    out = []
    for r in body:
        code = str(r[0] or "")
        if "M" not in code or len(code) < 6:
            continue
        try:
            period = pd.Period(code.replace("M", "-"), freq="M")
        except Exception:
            continue
        for i, name in colmap.items():
            if i < len(r):
                v = _num(r[i])
                if v is not None:
                    out.append({"commodity": name, "date": period.to_timestamp(), "price": v})
    df = pd.DataFrame(out)
    if df.empty:
        raise RuntimeError("Pink Sheet 解析为空")
    df["source"] = WB_SOURCE
    return df


def wb_board() -> pd.DataFrame:
    hist = fetch_wb_monthly()
    rows = []
    now = _now()
    for name, g in hist.groupby("commodity"):
        g = g.sort_values("date")
        s = g.set_index("date")["price"]
        last_d = s.index[-1]
        price = float(s.iloc[-1])
        prev = float(s.iloc[-2]) if len(s) >= 2 else None
        yoy_base = s[s.index == last_d - pd.DateOffset(years=1)]
        dec = s[(s.index.year == last_d.year - 1) & (s.index.month == 12)]
        rows.append(
            {
                "commodity": name,
                "price": round(price, 2),
                "day_pct": None,
                "week_pct": None,
                "month_pct": round((price / prev - 1) * 100, 2) if prev else None,
                "ytd_pct": round((price / float(dec.iloc[-1]) - 1) * 100, 2) if len(dec) else None,
                "y1_pct": round((price / float(yoy_base.iloc[-1]) - 1) * 100, 2) if len(yoy_base) else None,
                "data_date": last_d.strftime("%Y-%m"),
                "source": WB_SOURCE,
                "fetched_at": now,
            }
        )
    return pd.DataFrame(rows)


def fetch_fred_history(commodity: str, timeout: float = 8.0) -> pd.DataFrame:
    symbol = FRED_SERIES.get(commodity)
    if not symbol:
        return pd.DataFrame(columns=["date", "price", "source"])
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={symbol}"
    r = httpx.get(url, headers=UA, timeout=timeout, follow_redirects=True)
    r.raise_for_status()
    df = pd.read_csv(io.StringIO(r.text))
    df.columns = ["date", "price"]
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna().reset_index(drop=True)
    df["source"] = f"{FRED_SOURCE} · {symbol}"
    return df


def source_status() -> dict:
    p = CACHE_DIR / "source_status.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_status(d: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / "source_status.json").write_text(
        json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8"
    )
