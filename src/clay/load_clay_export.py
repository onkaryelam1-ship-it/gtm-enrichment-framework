"""Load Clay export CSVs (and the mock enricher's file) into raw.raw_clay_enrichment.

Every CSV in data/clay_exports/ is read, its columns renamed with
`clay.column_map`, joined to raw_accounts on a normalized domain, and stored in
long format: one row per (account, field). Files whose name starts with `mock_`
are tagged provider='mock', everything else provider='clay'.

Run:  python -m src.clay.load_clay_export
"""

from __future__ import annotations

from datetime import datetime, timezone

import duckdb
import pandas as pd

from src.config import load_settings, path

FIELDS = ["industry", "employee_count", "hq_country", "founded_year"]


def normalize_domain(d: str | float) -> str | None:
    if not isinstance(d, str) or not d.strip():
        return None
    d = d.strip().lower()
    for prefix in ("https://", "http://", "www."):
        d = d.removeprefix(prefix)
    return d.rstrip("/")


def read_export(f, column_map: dict) -> pd.DataFrame:
    df = pd.read_csv(f, dtype=str)
    missing = [c for c in column_map if c not in df.columns]
    if missing:
        print(f"  ! {f.name}: columns not found {missing}; edit clay.column_map in settings.yaml")
    df = df.rename(columns=column_map)
    if "Enriched At" in df.columns:
        df["enriched_at"] = df["Enriched At"]
    else:  # real Clay exports: use the file's modified time
        mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        df["enriched_at"] = mtime.date().isoformat()
    df["provider"] = "mock" if f.name.startswith("mock_") else "clay"
    df["source_file"] = f.name
    df["domain_norm"] = df["domain"].map(normalize_domain)
    keep = ["domain_norm", "provider", "source_file", "enriched_at"] + [c for c in FIELDS if c in df.columns]
    return df[keep]


def main() -> int:
    cfg = load_settings()
    files = sorted(path("clay_export_dir").glob("*.csv"))
    if not files:
        print("No files in data/clay_exports/. Run `make mock-enrich` and/or add Clay exports.")
        return 0

    wide = pd.concat([read_export(f, cfg["clay"]["column_map"]) for f in files], ignore_index=True)
    long = wide.melt(
        id_vars=["domain_norm", "provider", "source_file", "enriched_at"],
        value_vars=[c for c in FIELDS if c in wide.columns],
        var_name="field",
        value_name="value",
    )

    con = duckdb.connect(str(path("warehouse")))
    con.register("long_df", long)
    con.execute(
        """
        create or replace table raw.raw_clay_enrichment as
        select
            a.account_id as record_id,
            'account' as entity_type,
            l.field,
            l.value,
            l.provider,
            l.source_file,
            l.enriched_at,
            current_timestamp as _loaded_at
        from long_df l
        left join raw.raw_accounts a
          on lower(trim(a.domain)) = l.domain_norm
        """
    )
    n, unmatched = con.execute(
        "select count(*), count(*) filter (where record_id is null) from raw.raw_clay_enrichment"
    ).fetchone()
    by_provider = con.execute(
        "select provider, count(distinct record_id) from raw.raw_clay_enrichment group by 1 order by 1"
    ).fetchall()
    con.close()

    print(f"Loaded {n} enrichment values from {len(files)} file(s)")
    for provider, accounts in by_provider:
        print(f"  {provider:<5} {accounts:>4} accounts")
    if unmatched:
        print(f"  ! {unmatched} values did not match an account domain (kept with null record_id)")
    return n


if __name__ == "__main__":
    main()
