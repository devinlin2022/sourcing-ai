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


@pytest.fixture(scope="session", autouse=True)
def loaded():
    out = []
    for name in SAMPLES:
        p = DATA / name
        if p.exists():
            out.append(ingest_file(p, name))
    return out
