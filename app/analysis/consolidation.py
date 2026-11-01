import pandas as pd

from app.config import FTG_RESERVE, PRICE_UNIT_DIVISOR
from app.db import db

DIV = PRICE_UNIT_DIVISOR


def _empty(cols):
    return pd.DataFrame(columns=cols)


def segment_options() -> list[str]:
    try:
        df = db.df(
            "SELECT DISTINCT spend_segment FROM cost_exhibit WHERE spend_segment IS NOT NULL"
        )
        return df["spend_segment"].tolist()
    except Exception:
        return []


BASE_CTE = """
WITH base AS (
  SELECT material, plant,
         any_value(spend_segment) AS spend_segment,
         any_value(plant_country) AS plant_country,
         max(annual_qty) AS annual_qty,
         max(std_price) AS std_price,
         max(leader_price) AS leader_price
  FROM cost_exhibit GROUP BY material, plant
)
"""


def scan() -> pd.DataFrame:
    q = (
        BASE_CTE
        + f"""
    SELECT b.spend_segment AS 支出段,
           count(DISTINCT b.material) AS 物料数,
           count(DISTINCT b.plant) AS 工厂数,
           count(DISTINCT b.plant_country) AS 国家数,
           (SELECT count(DISTINCT c.vendor_name) FROM cost_exhibit c
             WHERE c.spend_segment = b.spend_segment) AS 供应商数,
           round(100 * avg(b.std_price / nullif(b.leader_price, 0) - 1), 1) AS 平均溢价pct,
           round(sum(greatest(b.std_price - b.leader_price, 0) * b.annual_qty
                         / {DIV}), 0) AS 识别FTG_USD
    FROM base b WHERE b.spend_segment IS NOT NULL
    GROUP BY b.spend_segment ORDER BY 识别FTG_USD DESC
    """
    )
    try:
        df = db.df(q)
    except Exception:
        return _empty(["支出段", "物料数", "工厂数", "国家数", "供应商数", "平均溢价pct", "识别FTG_USD", "验证FTG_USD"])
    if df.empty:
        return df
    df["验证FTG_USD"] = (df["识别FTG_USD"] * (1 - FTG_RESERVE)).round(0)
    return df


def kpis() -> dict:
    try:
        df = scan()
        identified = float(df["识别FTG_USD"].sum()) if not df.empty else 0.0
        validated = float(df["验证FTG_USD"].sum()) if not df.empty else 0.0
    except Exception:
        identified = validated = 0.0
    try:
        realized = float(
            db.scalar("SELECT coalesce(sum(amount_usd), 0) FROM savings_realized") or 0
        )
    except Exception:
        realized = 0.0
    return {"identified": identified, "validated": validated, "realized": realized}


def kpis_html() -> str:
    k = kpis()
    return f"""
    <div style="display:flex;gap:14px;flex-wrap:wrap">
      <div style="flex:1;min-width:200px;background:#EFF6FF;border:1px solid #BFDBFE;border-radius:12px;padding:14px">
        <div style="font-size:12px;color:#1D4ED8">Identified 识别（毛差额）</div>
        <div style="font-size:20px;font-weight:700;color:#1E3A8A">${k['identified']:,.0f}</div>
      </div>
      <div style="flex:1;min-width:200px;background:#FFF7ED;border:1px solid #FED7AA;border-radius:12px;padding:14px">
        <div style="font-size:12px;color:#C2410C">Validated 验证（扣运费关税切换预留 {FTG_RESERVE*100:.0f}%，估算参数）</div>
        <div style="font-size:20px;font-weight:700;color:#7C2D12">${k['validated']:,.0f}</div>
      </div>
      <div style="flex:1;min-width:200px;background:#F0FDF4;border:1px solid #BBF7D0;border-radius:12px;padding:14px">
        <div style="font-size:12px;color:#15803D">Realized 实现（人工回填）</div>
        <div style="font-size:20px;font-weight:700;color:#14532D">${k['realized']:,.0f}</div>
      </div>
    </div>
    <div style="font-size:11px;color:#94A3B8;margin-top:6px">识别=（现标准价−最优厂价）×年用量；
    验证=识别扣跨境运费/关税/资金占用/切换成本预留；实现=实际进入合同。三级漏斗禁止只报第一级。</div>
    """


def detail(segment: str) -> pd.DataFrame:
    q = (
        BASE_CTE
        + f"""
    SELECT material AS 物料, plant AS 工厂, plant_country AS 国家,
           std_price AS 标准价, leader_price AS 最优厂价,
           round(100 * (std_price / nullif(leader_price, 0) - 1), 1) AS 溢价pct,
           round(annual_qty, 0) AS 年用量,
           round(greatest(std_price - leader_price, 0) * annual_qty / {DIV}, 0) AS 毛差额USD
    FROM base WHERE spend_segment = ? ORDER BY 毛差额USD DESC
    """
    )
    try:
        return db.df(q, [segment])
    except Exception:
        return _empty(["物料", "工厂", "国家", "标准价", "最优厂价", "溢价pct", "年用量", "毛差额USD"])


def vendors_in_segment(segment: str) -> list[str]:
    try:
        df = db.df(
            "SELECT DISTINCT vendor_name FROM cost_exhibit WHERE spend_segment = ? "
            "ORDER BY vendor_name",
            [segment],
        )
        return [v for v in df["vendor_name"].dropna().tolist()]
    except Exception:
        return []


def cbcs(vendor: str) -> dict:
    q = """
    SELECT count(DISTINCT plant_country) AS countries,
           count(*) FILTER (WHERE upper(incoterms) IN ('CIF','FOB','FCA','EXW')
                             AND country_of_origin IS NOT NULL
                             AND country_of_origin <> plant_country) AS export_lines,
           min(moq) AS min_moq
    FROM cost_exhibit WHERE vendor_name = ?
    """
    try:
        r = db.df(q, [vendor]).iloc[0]
    except Exception:
        return {"vendor": vendor, "score": None, "tier": "无数据", "evidence": []}
    try:
        from app.analysis.supplier360 import rr_match

        hits = [h for h in rr_match(vendor) if h.get("FHR") is not None]
        fhr_val = float(hits[0]["FHR"]) if hits else None
    except Exception:
        fhr_val = None
    try:
        target_qty = db.df(
            "SELECT max(annual_qty) AS q FROM (SELECT material, plant, "
            "max(annual_qty) AS annual_qty FROM cost_exhibit WHERE vendor_name = ? "
            "GROUP BY material, plant)",
            [vendor],
        ).iloc[0]["q"]
    except Exception:
        target_qty = None

    evidence = []
    geo = 30 if int(r["countries"] or 0) >= 2 else 0
    evidence.append(f"地理足迹 {geo}/30：已在 {int(r['countries'] or 0)} 个国家工厂供货")
    exp = 30 if int(r["export_lines"] or 0) > 0 else 0
    evidence.append(f"出口经验 {exp}/30：CIF/FOB/FCA/EXW 且原产国≠工厂国的记录 {int(r['export_lines'] or 0)} 条")
    moq = float(r["min_moq"]) if pd.notna(r["min_moq"]) else None
    if moq is not None and target_qty and float(target_qty) > 0 and moq <= 0.3 * float(target_qty):
        biz, moq_txt = 25, f"MOQ {moq:,.0f} ≤ 目标厂年用量 30%"
    elif moq is None:
        biz, moq_txt = 0, "MOQ 未知"
    else:
        biz, moq_txt = 0, f"MOQ {moq:,.0f} 超目标厂年用量 30%，小批量不可行"
    evidence.append(f"商务能力 {biz}/25：{moq_txt}")
    if fhr_val is None:
        risk, risk_txt = 0, "FHR 无评级（计入证据缺口，不按 0 分判为高风险）"
    else:
        risk = round(20 * fhr_val / 80, 1) if fhr_val < 80 else 20
        risk_txt = f"FHR {fhr_val:.0f}"
    evidence.append(f"合规风险 {risk}/20：{risk_txt}")

    score = round(geo + exp + biz + risk, 1)
    confidence = round(score / 105, 2)
    if fhr_val is None:
        tier = "B 需询价确认（缺财务评级，不得直接试点）" if score >= 60 else "C 证据不足"
    else:
        tier = "A 可直接试点" if score >= 75 else "B 需询价确认" if score >= 60 else "C 证据不足" if score >= 40 else "D 不建议"
    if confidence < 0.6 and not tier.startswith("C"):
        tier += "（置信度 <0.6，不进入 FTG 汇总，需人工核实）"
    return {"vendor": vendor, "score": score, "tier": tier, "confidence": confidence, "evidence": evidence}


def cbcs_table(vendors: list[str]) -> pd.DataFrame:
    rows = [cbcs(v) for v in vendors]
    return pd.DataFrame(
        [
            {
                "供应商": r["vendor"],
                "CBCS得分": r["score"] if r["score"] is not None else "无数据",
                "等级": r["tier"],
                "置信度": r.get("confidence"),
                "证据": "；".join(r["evidence"]),
            }
            for r in rows
        ]
    )
