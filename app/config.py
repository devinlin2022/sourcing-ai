import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
DB_PATH = Path(os.getenv("DB_PATH") or DATA_DIR / "sourcing.duckdb")

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "")
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-ai/DeepSeek-V3")

NGROK_AUTHTOKEN = os.getenv("NGROK_AUTHTOKEN", "")
FTG_RESERVE = float(os.getenv("FTG_RESERVE", "0.25"))
MARKET_REFRESH_HOUR = int(os.getenv("MARKET_REFRESH_HOUR", "8"))

# Cost Exhibit 的价格列是「每 1000 计量单位」报价，用量列是计量单位本身。
# 实测 std_price * annual_qty / 1000 == annual_spend 精确成立，故一切「价差×用量」必须除以该系数。
PRICE_UNIT_DIVISOR = float(os.getenv("PRICE_UNIT_DIVISOR", "1000"))
