import os
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="sourcing_test_")
os.environ["DB_PATH"] = os.path.join(_tmp, "test.duckdb")
os.environ.setdefault("ADMIN_PASSWORD", "admin123")

import pytest

from app.ingest.xlsx import ingest_file

DATA = Path(__file__).resolve().parent.parent.parent

SAMPLES = [
    "Cost Exhibit.csv",
    "PO_HiSTORICAL_Procurement.csv",
    "PO_HiSTORICAL_Procurement_2026-09-27-2006.csv",
    "ICP System Result.csv",
    "Vendor Master.csv",
    "MATERIAL_INFO_RECORD.csv",
    "Logistic RateCard.csv",
    "Spend Changes Statement.csv",
    "RapidRatings Vendor Outreach List 2024.xlsx",
]

if not (DATA / "Cost Exhibit.csv").exists() or not (
    DATA / "RapidRatings Vendor Outreach List 2024.xlsx"
).exists():
    pytest.skip(
        f"未找到样本数据（应位于 {DATA}）。这些用例校验真实数据的口径陷阱，"
        f"需把 Cost Exhibit / PO 等文件放到仓库上一级目录后再运行。",
        allow_module_level=True,
    )


@pytest.fixture(scope="session", autouse=True)
def loaded():
    out = []
    for name in SAMPLES:
        p = DATA / name
        if p.exists():
            out.append(ingest_file(p, name))
    return out
