import threading
from pathlib import Path

import duckdb

from app.config import DB_PATH
from app.ingest.profiles import PROFILES

META_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta_datasets(
  dataset_key VARCHAR, file_name VARCHAR, label VARCHAR,
  rows_loaded BIGINT, rows_quarantined BIGINT,
  file_hash VARCHAR, imported_at TIMESTAMP DEFAULT now(), status VARCHAR
);
CREATE TABLE IF NOT EXISTS quarantine(
  dataset_key VARCHAR, table_name VARCHAR, reason VARCHAR,
  payload VARCHAR, created_at TIMESTAMP DEFAULT now()
);
CREATE TABLE IF NOT EXISTS savings_realized(
  segment VARCHAR, note VARCHAR, amount_usd DOUBLE,
  status VARCHAR, created_at TIMESTAMP DEFAULT now()
);
CREATE TABLE IF NOT EXISTS market_snapshot(
  commodity VARCHAR, price DOUBLE, day_pct DOUBLE, week_pct DOUBLE,
  month_pct DOUBLE, ytd_pct DOUBLE, y1_pct DOUBLE,
  data_date VARCHAR, source VARCHAR, fetched_at TIMESTAMP DEFAULT now()
);
CREATE TABLE IF NOT EXISTS market_history(
  commodity VARCHAR, date DATE, price DOUBLE, source VARCHAR
);
"""


def core_ddl() -> str:
    parts = []
    for p in PROFILES:
        cols = ", ".join(f"{c.dst} {c.typ}" for c in p.cols)
        parts.append(f"CREATE TABLE IF NOT EXISTS {p.table}({cols});")
    parts.append(
        "CREATE TABLE IF NOT EXISTS rr_master(vendor_name VARCHAR, contact_name VARCHAR, "
        "contact_email VARCHAR, contact_phone VARCHAR, vendor_type VARCHAR, division VARCHAR, "
        "location VARCHAR, single_source VARCHAR, rr_id VARCHAR, fhr DOUBLE);"
    )
    parts.append(
        "CREATE TABLE IF NOT EXISTS rr_status(target_company VARCHAR, status VARCHAR, "
        "fhr_rating DOUBLE, created VARCHAR, submitted VARCHAR, close_reason VARCHAR);"
    )
    parts.append(
        "CREATE TABLE IF NOT EXISTS rr_fhr_hist(company VARCHAR, period VARCHAR, fhr DOUBLE);"
    )
    return "\n".join(parts)


class Database:
    def __init__(self, path=None):
        self.path = str(path or DB_PATH)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = duckdb.connect(self.path)
        self._conn.execute(META_SCHEMA)
        self._conn.execute(
            "ALTER TABLE market_snapshot ADD COLUMN IF NOT EXISTS data_date VARCHAR"
        )
        self._conn.execute(core_ddl())

    def sql(self, query, params=None):
        with self._lock:
            if params:
                return self._conn.execute(query, params)
            return self._conn.execute(query)

    def df(self, query, params=None):
        return self.sql(query, params).fetchdf()

    def scalar(self, query, params=None):
        return self.sql(query, params).fetchone()[0]

    def close(self):
        with self._lock:
            self._conn.close()


db = Database()
