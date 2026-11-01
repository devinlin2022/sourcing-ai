from pathlib import Path

import pytest

from app.db import db
from app.ingest.pipeline import ingest_csv

DATA = Path(__file__).resolve().parent.parent.parent


def test_profile_detection(loaded):
    by_pid = {r["dataset"]: r for r in loaded}
    assert by_pid["cost_exhibit"]["status"] == "ok"
    assert by_pid["po_history"]["status"] == "ok"
    assert by_pid["icp"]["status"] == "ok"
    assert by_pid["logistics_rate"]["rows_loaded"] == 772
    assert by_pid["rapidratings"]["status"] == "ok"


def test_duplicate_upload_skipped(loaded):
    r = ingest_csv(DATA / "Cost Exhibit.csv", "Cost Exhibit.csv")
    assert r["status"] == "duplicate"
    n = db.scalar("SELECT count(*) FROM cost_exhibit")
    assert n > 0


def test_incremental_upsert_no_duplicates(loaded):
    n = db.scalar("SELECT count(*) FROM po_history")
    ingest_csv(DATA / "PO_HiSTORICAL_Procurement_2026-09-27-2006.csv", "delta.csv")
    n_after = db.scalar("SELECT count(*) FROM po_history")
    assert n_after == n
    dup = db.scalar(
        "SELECT count(*) FROM (SELECT * FROM po_history GROUP BY ALL HAVING count(*) > 1)"
    )
    assert dup == 0


def test_dedup_guard_7x(loaded):
    by_pid = {r["dataset"]: r for r in loaded}
    guard = [c for c in by_pid["cost_exhibit"]["checks"] if "取MAX" in c["check"]]
    assert guard, "缺少去重守卫检查项"
    value = guard[0]["value"]
    assert "27,850,612" in value
    assert "3,986,079" in value
    assert "6.9" in value


def test_annual_spend_deduped(loaded):
    naive = db.scalar("SELECT round(sum(annual_spend), 0) FROM cost_exhibit")
    dedup = db.scalar(
        "SELECT round(sum(v), 0) FROM "
        "(SELECT max(annual_spend) AS v FROM cost_exhibit GROUP BY material, plant)"
    )
    assert 5.5 < naive / dedup < 7.5


def test_price_anomaly_quarantined(loaded):
    bad = db.scalar("SELECT count(*) FROM quarantine WHERE reason LIKE '%单位口径不一致%'")
    assert bad >= 1
    in_table = db.scalar(
        "SELECT count(*) FROM cost_exhibit WHERE vendor_name LIKE '%LIANMENG%' "
        "AND order_price IS NOT NULL AND order_price < 0.5 * std_price"
    )
    assert in_table == 0
    kept = db.scalar("SELECT count(*) FROM cost_exhibit WHERE vendor_name LIKE '%LIANMENG%'")
    assert kept > 0


def test_zero_price_becomes_null(loaded):
    zeros = db.scalar("SELECT count(*) FROM cost_exhibit WHERE order_price = 0")
    assert zeros == 0


def test_rr_master_loaded(loaded):
    total = db.scalar("SELECT count(*) FROM rr_master")
    assert total == 168
    with_fhr = db.scalar("SELECT count(*) FROM rr_master WHERE fhr IS NOT NULL")
    assert with_fhr == 43


def test_vendor_options(loaded):
    from app.analysis.supplier360 import vendor_options

    opts = vendor_options()
    assert any("ROQUETTE" in v for v in opts)
    assert any("HUANFA" in v.upper() for v in opts)
