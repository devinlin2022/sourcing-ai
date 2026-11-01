import pandas as pd

from app.analysis import consolidation, supplier360
from app.db import db


def test_cross_plant_rules():
    df = supplier360.cross_plant("M06526")
    assert not df.empty
    assert set(["工厂", "供应商", "参考结论"]).issubset(df.columns)
    notes = " ".join(df["参考结论"].tolist())
    assert "跨厂价差" in notes or "单厂" in notes


def test_supplier_profile():
    html = supplier360.profile_html("ZHAOQING HUANFA BIOTECHNOLOGY CO.,L")
    assert "ZHAOQING" in html
    po = supplier360.po_performance("ZHAOQING HUANFA BIOTECHNOLOGY CO.,L")
    assert not po.empty
    assert 0 <= float(po.iloc[0]["交付完整性pct"]) <= 100


def test_overview_spend_not_inflated():
    v = "ZHAOQING HUANFA BIOTECHNOLOGY CO.,L"
    covered = float(supplier360.overview(v).iloc[0]["覆盖年支出USD"])
    expected = db.scalar(
        "SELECT round(sum(v)) FROM (SELECT material, plant, max(annual_spend) AS v "
        "FROM cost_exhibit WHERE vendor_name = ? GROUP BY material, plant)",
        [v],
    )
    assert covered == pytest_approx(float(expected), rel=0.01)
    total = db.scalar(
        "SELECT round(sum(v)) FROM (SELECT material, plant, max(annual_spend) AS v "
        "FROM cost_exhibit GROUP BY material, plant)"
    )
    assert covered <= float(total) * 1.01


def test_rr_match_no_false_positive():
    assert supplier360.rr_lookup("ROQUETTE CHINA CO., LTD").empty
    assert supplier360.rr_lookup("PURE CHEM COMPANY LIMITED").empty
    hits = supplier360.rr_match("All4Labels Group")
    assert hits and hits[0]["匹配度"] >= 0.6


def test_fhr_bands():
    assert supplier360.fhr_band(89)[0] == "Very Low Risk"
    assert supplier360.fhr_band(65)[0] == "Low Risk"
    assert supplier360.fhr_band(41)[0] == "Medium Risk"
    assert supplier360.fhr_band(None)[0] == "无评级"


def test_consolidation_scan_math():
    df = consolidation.scan()
    assert not df.empty
    row = df.iloc[0]
    identified = float(row["识别FTG_USD"])
    validated = float(row["验证FTG_USD"])
    assert identified > 0
    assert validated < identified
    expected = db.scalar(
        """
        SELECT round(sum(greatest(std_price - leader_price, 0) * annual_qty / 1000), 0)
        FROM (SELECT material, plant, max(annual_qty) AS annual_qty,
                     max(std_price) AS std_price, max(leader_price) AS leader_price
              FROM cost_exhibit GROUP BY material, plant)
        """
    )
    assert identified == pytest_approx(float(expected))
    assert identified < 2_000_000


def pytest_approx(v, rel=1e-6):
    import pytest

    return pytest.approx(v, rel=rel)


def test_cbcs_evidence_bound():
    vendors = consolidation.vendors_in_segment("Sorbitol")
    assert vendors
    tbl = consolidation.cbcs_table(vendors)
    assert not tbl.empty
    for _, r in tbl.iterrows():
        assert isinstance(r["证据"], str) and r["证据"]
        score = r["CBCS得分"]
        assert score == "无数据" or 0 <= float(score) <= 105


def test_kpis_funnel():
    k = consolidation.kpis()
    assert k["validated"] <= k["identified"]
    assert k["realized"] >= 0
