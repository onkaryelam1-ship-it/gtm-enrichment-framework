"""Load seed CSVs into the DuckDB `raw` schema exactly as they are.

Raw tables are loaded as text (all_varchar) so nothing is silently cleaned:
whitespace, casing and bad values survive for the staging layer to handle.

Run:  python -m src.load.load_raw
"""

from __future__ import annotations

import duckdb

from src.config import path

RAW_TABLES = {
    "raw_accounts": "accounts.csv",
    "raw_contacts": "contacts.csv",
    "raw_engagement": "engagement_events.csv",
    "planted_errors": "planted_errors.csv",
}


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(path("warehouse")))
    con.execute("create schema if not exists raw")
    return con


def main() -> dict:
    seed_dir = path("seed_dir")
    con = connect()
    counts = {}
    for table, filename in RAW_TABLES.items():
        f = seed_dir / filename
        if not f.exists():
            raise FileNotFoundError(f"{f} not found. Run `make seed` first.")
        con.execute(
            f"""
            create or replace table raw.{table} as
            select *, current_timestamp as _loaded_at
            from read_csv(?, header = true, all_varchar = true)
            """,
            [str(f)],
        )
        counts[table] = con.execute(f"select count(*) from raw.{table}").fetchone()[0]
    con.close()
    print("Loaded into", path("warehouse"))
    for t, n in counts.items():
        print(f"  raw.{t:<20} {n:>6} rows")
    return counts


if __name__ == "__main__":
    main()
