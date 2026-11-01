import re

import pandas as pd

from app.config import PRICE_UNIT_DIVISOR
from app.db import db

DIV = PRICE_UNIT_DIVISOR

FHR_BANDS = [(80, "Very Low Risk", "#0F6E56"), (60, "Low Risk", "#1D9E75"),
             (40, "Medium Risk", "#BA7517"), (20, "High Risk", "#E24B4A"),
             (0, "Very High Risk", "#A32D2D")]


def fhr_band(score) -> tuple[str, str]:
    if score is None or pd.isna(score):
        return "无评级", "#888780"
    for cut, name, color in FHR_BANDS:
        if score >= cut:
            return name, color
    return "Very High Risk", "#A32D2D"


def vendor_options() -> list[str]:
    try:
        df = db.df(
            "SELECT vendor_name FROM cost_exhibit UNION SELECT vendor_name FROM po_history"
        )
    except Exception:
        return []
    return sorted({v for v in df["vendor_name"].dropna().tolist() if str(v).strip()})


def material_options() -> list[str]:
    try:
        df = db.df("SELECT DISTINCT material FROM cost_exhibit ORDER BY material")
    except Exception:
        return []
    return [v for v in df["material"].dropna().tolist() if str(v).strip()]


def _empty(cols: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=cols)


def overview(vendor: str) -> pd.DataFrame:
    q = """
    SELECT count(DISTINCT s.plant) AS 供应工厂数, count(DISTINCT s.plant_country) AS 国家数,
           count(DISTINCT s.material) AS 物料数,
           coalesce(round(sum(v.annual_spend)), 0) AS 覆盖年支出USD
    FROM (SELECT DISTINCT material, plant, plant_country FROM cost_exhibit WHERE vendor_name = ?) s
    LEFT JOIN (SELECT material, plant, max(annual_spend) AS annual_spend
               FROM cost_exhibit GROUP BY material, plant) v
      USING (material, plant)
    """
    try:
        return db.df(q, [vendor])
    except Exception:
        return _empty(["供应工厂数", "国家数", "物料数", "覆盖年支出USD"])


def price_position(vendor: str) -> pd.DataFrame:
    q = f"""
    SELECT material AS 物料, plant AS 工厂, plant_country AS 国家,
           round(std_price / {DIV}, 4) AS 标准单价USD,
           round(leader_price / {DIV}, 4) AS 最优厂单价USD,
           round(100 * std_price / nullif(leader_price, 0) - 100, 1) AS 相对最优价溢价pct
    FROM (SELECT DISTINCT material, plant, plant_country, std_price, leader_price
          FROM cost_exhibit WHERE vendor_name = ?)
    ORDER BY 相对最优价溢价pct DESC
    """
    try:
        return db.df(q, [vendor])
    except Exception:
        return _empty(["物料", "工厂", "国家", "标准单价USD", "最优厂单价USD", "相对最优价溢价pct"])


def po_performance(vendor: str) -> pd.DataFrame:
    q = """
    WITH lines AS (
      SELECT po_num, line_item,
             max(order_qty) AS order_qty,
             sum(history_qty) AS recv_qty,
             max(eff_unit_price) AS po_price,
             avg(ir_unit_fc) AS ir_price,
             max(net_value) AS net_value,
             max(completed) AS completed,
             min(posting_date) AS first_d,
             max(posting_date) AS last_d
      FROM po_history WHERE vendor_name = ? GROUP BY po_num, line_item
    )
    SELECT count(*) AS 行项目数, round(sum(recv_qty)) AS 累计收货量,
           round(sum(net_value)) AS 订单金额,
           round(100 * avg(least(coalesce(recv_qty, 0) / nullif(order_qty, 0), 1)), 1) AS 交付完整性pct,
           round(100 * avg(abs(ir_price - po_price) / nullif(po_price, 0)), 2) AS 价格漂移pct,
           round(100 * avg(CASE WHEN completed = 'X' THEN 1.0 ELSE 0 END), 1) AS 订单闭环率pct,
           CAST(min(first_d) AS VARCHAR) AS 首次收货, CAST(max(last_d) AS VARCHAR) AS 最近收货
    FROM lines
    """
    try:
        return db.df(q, [vendor])
    except Exception:
        return _empty(["行项目数", "累计收货量", "订单金额", "交付完整性pct", "价格漂移pct", "订单闭环率pct", "首次收货", "最近收货"])


RR_STOP = {
    "CO", "LTD", "LIMITED", "INC", "LLC", "PLC", "SA", "AG", "BV", "NV", "GMBH", "SPA",
    "COMPANY", "GROUP", "CORP", "CORPORATION", "INTERNATIONAL", "INDUSTRIES", "INDUSTRIAL",
    "PHARMACEUTICAL", "PHARMACEUTICALS", "PHARMA", "TECH", "TECHNOLOGY", "TECHNOLOGIES",
    "CHEM", "CHEMICAL", "CHEMICALS", "BIOTECHNOLOGY", "BIOTECH", "FOOD", "FOODS",
    "HOLDINGS", "TRADING", "PRODUCTS", "MANUFACTURING", "CHINA", "PRIVATE", "PUBLIC",
    "SERVICES", "SERVICE", "SOLUTIONS", "MATERIALS", "ENTERPRISE", "ENTERPRISES",
}


def _sig(name: str) -> set[str]:
    raw = re.split(r"[^0-9A-Za-z]+", str(name).upper())
    return {t for t in raw if len(t) >= 4 and t not in RR_STOP}


def _rr_rows() -> list[dict]:
    try:
        return db.df(
            "SELECT vendor_name, fhr, division, contact_name, contact_email, "
            "contact_phone, single_source FROM rr_master"
        ).to_dict("records")
    except Exception:
        return []


def rr_match(vendor: str, threshold: float = 0.6) -> list[dict]:
    sig = _sig(vendor)
    if not sig:
        return []
    scored = []
    for r in _rr_rows():
        other = _sig(r["vendor_name"])
        if not other:
            continue
        inter = sig & other
        if not inter:
            continue
        score = len(inter) / min(len(sig), len(other))
        if score >= threshold:
            scored.append((round(score, 2), r))
    scored.sort(key=lambda x: (-x[0], str(x[1]["vendor_name"])))
    return [{**r, "匹配度": s, "FHR": r["fhr"]} for s, r in scored[:5]]


def rr_lookup(vendor: str) -> pd.DataFrame:
    cols = ["RR供应商", "匹配度", "FHR", "风险档", "联系人", "邮箱", "电话", "区域", "单源"]
    hits = rr_match(vendor)
    if not hits:
        return _empty(cols)
    rows = [
        {
            "RR供应商": h["vendor_name"],
            "匹配度": h["匹配度"],
            "FHR": h["FHR"],
            "风险档": fhr_band(h["FHR"])[0],
            "联系人": h["contact_name"],
            "邮箱": h["contact_email"],
            "电话": h["contact_phone"],
            "区域": h["division"],
            "单源": h["single_source"],
        }
        for h in hits
    ]
    return pd.DataFrame(rows, columns=cols)


def cross_plant(material: str) -> pd.DataFrame:
    q = f"""
    SELECT plant AS 工厂, plant_country AS 国家, vendor_name AS 供应商,
           country_of_origin AS 原产国,
           round(std_price / {DIV}, 4) AS 标准单价USD,
           round(order_price / {DIV}, 4) AS 订单单价USD,
           moq AS MOQ, incoterms AS 贸易术语,
           round(100 * std_price / nullif(leader_price, 0) - 100, 1) AS 相对最优价溢价pct
    FROM (SELECT DISTINCT material, plant, plant_country, vendor_name, country_of_origin,
                 std_price, order_price, moq, incoterms, leader_price
          FROM cost_exhibit WHERE material = ?)
    ORDER BY plant, 标准单价USD NULLS LAST
    """
    try:
        df = db.df(q, [material])
    except Exception:
        return _empty(["工厂", "国家", "供应商", "原产国", "标准单价USD", "订单单价USD", "MOQ", "贸易术语", "相对最优价溢价pct", "参考结论"])
    notes = []
    by_vendor: dict[str, list[float]] = {}
    for _, r in df.iterrows():
        if pd.notna(r["标准单价USD"]):
            by_vendor.setdefault(str(r["供应商"]), []).append(float(r["标准单价USD"]))
    qty = {}
    try:
        for _, r in db.df(
            "SELECT plant, max(annual_qty) AS annual_qty FROM cost_exhibit "
            "WHERE material = ? GROUP BY plant", [material]
        ).iterrows():
            if pd.notna(r["annual_qty"]):
                qty[str(r["plant"])] = float(r["annual_qty"])
    except Exception:
        pass
    for _, r in df.iterrows():
        v = str(r["供应商"])
        prices = by_vendor.get(v, [])
        note = ""
        if len(prices) >= 2 and all(p > 0 for p in prices):
            spread = (max(prices) - min(prices)) / min(prices) * 100
            note = (
                f"同供应商跨厂价差 {spread:.1f}%，可直接参考"
                if spread <= 5
                else f"同供应商跨厂价差 {spread:.1f}%，可作谈判锚点"
            )
        else:
            note = "仅单厂供应记录，跨厂参考需询价确认"
        moq, plant = r["MOQ"], str(r["工厂"])
        if pd.notna(moq) and qty.get(plant) and float(moq) > 0.3 * qty[plant]:
            note += f"；MOQ {moq:,.0f} 超该厂年用量 {qty[plant]:,.0f} 的 30%，小批量切换不可行"
        notes.append(note)
    df["参考结论"] = notes
    return df


def profile_html(vendor: str) -> str:
    ov = overview(vendor)
    rr = rr_lookup(vendor)
    fhr = None
    contact = "无记录（RapidRatings 名录未匹配，需建映射或发起评级）"
    if not rr.empty:
        row = rr.iloc[0]
        fhr = row["FHR"]
        band, color = fhr_band(fhr)
        c = [str(row.get(k, "") or "") for k in ("联系人", "邮箱", "电话", "区域")]
        contact = f"{c[0]} · {c[1]} · {c[2]} · 区域 {c[3]}"
        fhr_txt = f"FHR {fhr:.0f} · {band}"
    else:
        color = "#888780"
        fhr_txt = "无 FHR 评级（显示为无数据，不等于低分）"
    if ov.empty:
        stats = "无成本基线数据"
    else:
        r = ov.iloc[0]
        stats = (
            f"供应工厂 {int(r['供应工厂数'])} · 国家 {int(r['国家数'])} · 物料 {int(r['物料数'])} · "
            f"覆盖年支出 ${float(r['覆盖年支出USD']):,.0f}"
        )
    return f"""
    <div style="display:flex;gap:14px;flex-wrap:wrap">
      <div style="flex:1;min-width:260px;background:#F8FAFC;border:1px solid #E2E8F0;
                  border-radius:12px;padding:16px">
        <div style="font-size:15px;font-weight:600;color:#0F172A">{vendor}</div>
        <div style="font-size:13px;color:#475569;margin-top:8px">{stats}</div>
        <div style="font-size:13px;color:#475569;margin-top:6px">触达：{contact}</div>
      </div>
      <div style="min-width:220px;background:#F8FAFC;border:1px solid #E2E8F0;border-radius:12px;
                  padding:16px;display:flex;flex-direction:column;justify-content:center">
        <div style="font-size:12px;color:#64748B">财务风险（RapidRatings）</div>
        <div style="font-size:20px;font-weight:700;color:{color};margin-top:6px">{fhr_txt}</div>
        <div style="font-size:11px;color:#94A3B8;margin-top:6px">分档：0-19 极高 / 20-39 高 /
        40-59 中 / 60-79 低 / 80-100 极低</div>
      </div>
    </div>
    """
