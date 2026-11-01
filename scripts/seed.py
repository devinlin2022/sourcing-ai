import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.ingest.xlsx import ingest_file

FILES = [
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


def main(data_dir: str):
    root = Path(data_dir)
    for name in FILES:
        p = root / name
        if not p.exists():
            print(f"skip (missing): {name}")
            continue
        try:
            r = ingest_file(p, name)
            print(
                f"{r['label']}: {r['status']} rows={r['rows_loaded']} "
                f"quarantined={r['rows_quarantined']} {r.get('note', '')}"
            )
        except Exception as e:
            print(f"{name}: FAILED {e}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).parent.parent / ".."))
