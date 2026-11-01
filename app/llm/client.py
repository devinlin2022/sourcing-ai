import httpx

from app.config import LLM_MODEL, SILICONFLOW_API_KEY, SILICONFLOW_BASE_URL
from app.db import db

SYSTEM_PROMPT = (
    "你是 Sourcing AI 的采购顾问。只用下方提供的【数据上下文】回答，禁止编造任何数字。"
    "数据里没有的信息要明确说'当前数据不含该信息'。涉及切换供应商的建议必须提示需人工审批。"
    "回答用简体中文，简洁分点。"
)


def enabled() -> bool:
    return bool(SILICONFLOW_API_KEY)


def _context() -> str:
    parts = []
    try:
        df = db.df(
            "SELECT commodity, price, month_pct, y1_pct, data_date, source FROM "
            "market_snapshot WHERE fetched_at = (SELECT max(fetched_at) FROM market_snapshot) "
            "ORDER BY commodity"
        )
        if len(df):
            parts.append("【大宗商品最新行情（price 为页面报价单位）】\n" + df.to_string(index=False))
    except Exception:
        pass
    try:
        df = db.df(
            "SELECT vendor_name, count(DISTINCT plant) AS plants, "
            "count(DISTINCT material) AS materials FROM cost_exhibit "
            "GROUP BY 1 ORDER BY plants DESC LIMIT 30"
        )
        if len(df):
            parts.append("【供应商覆盖概况】\n" + df.to_string(index=False))
    except Exception:
        pass
    try:
        df = db.df(
            "SELECT material, plant, plant_country, "
            "round(max(std_price)/1000, 4) AS std_usd_per_unit, "
            "round(max(leader_price)/1000, 4) AS leader_usd_per_unit, "
            "round(100*max(std_price)/nullif(max(leader_price),0)-100, 1) AS premium_pct, "
            "round(max(annual_qty)) AS annual_qty "
            "FROM cost_exhibit GROUP BY 1,2,3 ORDER BY premium_pct DESC LIMIT 60"
        )
        if len(df):
            parts.append(
                "【成本基线：单价已换算为 USD/单位（原表为每 1000 单位报价）】\n"
                + df.to_string(index=False)
            )
    except Exception:
        pass
    try:
        from app.analysis import consolidation

        s = consolidation.scan()
        if not s.empty:
            parts.append("【FTG 整合机会（识别口径）】\n" + s.to_string(index=False))
    except Exception:
        pass
    return "\n\n".join(parts) or "（数据库暂无数据）"


def chat(user_message: str, history: list) -> str:
    if not enabled():
        return "未配置 SILICONFLOW_API_KEY，AI 助手不可用。请在 .env 或环境变量中填写后重启。"
    messages = [{"role": "system", "content": SYSTEM_PROMPT + "\n\n" + _context()}]
    for h in history[-8:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": user_message})
    r = httpx.post(
        f"{SILICONFLOW_BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {SILICONFLOW_API_KEY}"},
        json={"model": LLM_MODEL, "messages": messages, "temperature": 0.2, "max_tokens": 1500},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]
