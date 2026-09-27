"""Write Clay-ready CSV batches for the real-domain accounts.

Clay's free plan allows 100 data credits a month and 200 rows per table, so the
real accounts are split into batches of `clay.batch_size` rows. Import one batch
into a Clay table, enrich it, then export the result to data/clay_exports/.
See docs/clay_setup.md for the click-by-click steps.

Run:  python -m src.clay.export_for_clay
"""

from __future__ import annotations

import duckdb

from src.config import load_settings, path


def main() -> list[str]:
    cfg = load_settings()
    size = cfg["clay"]["batch_size"]
    con = duckdb.connect(str(path("warehouse")), read_only=True)
    df = con.execute(
        """
        select account_id as "Account ID", company_name as "Company Name", domain as "Domain"
        from raw.raw_accounts
        where is_real_domain = 'True'
        order by account_id
        """
    ).df()
    con.close()

    out_dir = path("clay_import_dir")
    written = []
    for i in range(0, len(df), size):
        f = out_dir / f"accounts_for_clay_batch_{i // size + 1:02d}.csv"
        df.iloc[i: i + size].to_csv(f, index=False)
        written.append(f.name)
        print(f"  {f.name}: {len(df.iloc[i: i + size])} rows")
    print(f"Wrote {len(written)} Clay import file(s) to {out_dir}")
    return written


if __name__ == "__main__":
    main()
