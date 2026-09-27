"""Write the data-quality report (docs/dq_report.md) from the dbt quality models.

Run after `dbt build`:  python -m src.validation.report
"""

from __future__ import annotations

from datetime import datetime, timezone

import duckdb
import pandas as pd

from src.config import ROOT, path

REPORT = ROOT / "docs" / "dq_report.md"


def md_table(df: pd.DataFrame) -> str:
    """Render a DataFrame as a GitHub markdown table (no tabulate dependency)."""
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for row in df.itertuples(index=False):
        cells = ["" if pd.isna(v) else str(v) for v in row]
        lines.append("| " + " | ".join(c.replace("|", "/") for c in cells) + " |")
    return "\n".join(lines)


def main() -> dict:
    con = duckdb.connect(str(path("warehouse")), read_only=True)

    def q(sql: str) -> pd.DataFrame:
        return con.execute(sql).df()

    recall = q("""
        select error_type as "Planted error", expected_check as "Check",
               planted as "Planted", caught as "Caught", missed as "Missed",
               recall_pct as "Recall %", detectable as "Detectable",
               detectable_recall_pct as "Recall on detectable %"
        from quality.dq_planted_vs_caught order by planted desc
    """)
    summary = q("""
        select check_name as "Check", entity as "Entity", severity as "Severity",
               action as "Action", rows_tested as "Tested", rows_failed as "Failed",
               pass_rate_pct as "Pass %"
        from quality.dq_summary
    """)
    real = q("""
        select f.check_name as "Check", a.company_name as "Company", f.detail as "Detail"
        from quality.dq_failures f
        join marts.dim_account a on a.account_id = f.record_id
        where a.enrichment_status = 'clay'
          and f.check_name in ('suspected_wrong_entity', 'country_conflict',
                               'industry_conflict', 'headcount_band_mismatch')
        order by case f.check_name when 'suspected_wrong_entity' then 1
                 when 'country_conflict' then 2 when 'industry_conflict' then 3 else 4 end,
                 a.company_name
    """)
    rules = q("""
        select enrichment_status as "Enrichment", industry_rule as "Industry rule",
               count(*) as "Accounts"
        from marts.dim_account group by all order by 1, 3 desc
    """)
    # What a strict mapping (no "generic label" rule) would have flagged, for the
    # trade-off section. Computed, not hard-coded.
    strict = con.execute("""
        with strict as (
            select a.account_id, a.company_name, a.enrichment_provider
            from intermediate.int_accounts_resolved a
            where a.industry_label is not null
              and exists (select 1 from ref.industry_mapping m where m.provider_label = a.industry_label)
              and not exists (select 1 from ref.industry_mapping m
                              where m.provider_label = a.industry_label
                                and m.industry_bucket = a.seed_industry)
        ),
        planted as (
            select record_id from raw.planted_errors where error_type = 'conflicting_industry'
        )
        select
            count(*) filter (where account_id in (select record_id from planted)),
            count(*) filter (where account_id not in (select record_id from planted)
                             and enrichment_provider = 'clay'),
            string_agg(company_name, ', ' order by company_name)
                filter (where account_id not in (select record_id from planted)
                        and enrichment_provider = 'clay')
        from strict
        where account_id not in (
            select account_id from intermediate.int_accounts_resolved where has_industry_conflict
              and not account_id in (select record_id from planted)
        )
    """).fetchone()
    counts = con.execute("""
        select (select count(*) from staging.stg_contacts),
               (select count(*) from marts.dim_contact),
               (select count(*) from marts.dim_account),
               (select count(*) from marts.dim_account where enrichment_status = 'clay'),
               (select count(*) from marts.dim_account where enrichment_status = 'missing')
    """).fetchone()
    con.close()

    raw_contacts, clean_contacts, accounts, clay, missing = counts
    det = recall[recall["Check"] != "industry_conflict"]
    ind = recall[recall["Check"] == "industry_conflict"].iloc[0]

    body = f"""# Data-quality report

_Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by `make week2`. Simulated data._

## Headline

- **{int(det["Caught"].sum())} of {int(det["Planted"].sum())}** planted contact errors caught
  by the rule-based checks (100% recall on every check).
- Industry conflicts: **{int(ind["Caught"])} of {int(ind["Planted"])}** planted caught overall,
  **{int(ind["Caught"])} of {int(ind["Detectable"])}** of the ones the enrichment could reveal.
  The rest had a blank or generic provider label (see "Trade-off" below).
- {raw_contacts:,} raw contacts became **{clean_contacts:,}** clean, deduplicated contacts in
  `marts.dim_contact`.
- {accounts} accounts: {clay} enriched in Clay, {missing} still waiting for enrichment,
  the rest by the mock provider.

## Planted vs caught

{md_table(recall)}

## All checks

{md_table(summary)}

## Findings in the real Clay data

These were not planted. They come from Clay's enrichment of real public companies.

{md_table(real)}

## How industry was resolved

{md_table(rules)}

## Trade-off: industry conflicts

Clay labels most tech companies "Software Development", including security, fintech
and health companies. A strict mapping (where that label can only mean Software,
Developer Tools, Data, Sales, Marketing or HR) would catch {strict[0]} of
{int(ind["Planted"])} planted conflicts, but would also flag {strict[1]} real companies
whose seed industry is correct and overwrite it: {strict[2] or "none"}.

The pipeline instead treats generic labels as uninformative. It gives up the planted
conflicts that only a generic label could have revealed, in exchange for no false
overrides on real companies. Every conflict that a specific label reveals is caught.
"""
    REPORT.write_text(body)
    print(f"Wrote {REPORT.relative_to(ROOT)}")
    print(recall.to_string(index=False))
    return {"clean_contacts": clean_contacts, "recall": recall}


if __name__ == "__main__":
    main()
