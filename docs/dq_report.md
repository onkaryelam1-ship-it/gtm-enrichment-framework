# Data-quality report

_Generated 2026-09-28 00:35 UTC by `make week2`. Simulated data._

## Headline

- **340 of 340** planted contact errors caught
  by the rule-based checks (100% recall on every check).
- Industry conflicts: **5 of 10** planted caught overall,
  **5 of 5** of the ones the enrichment could reveal.
  The rest had a blank or generic provider label (see "Trade-off" below).
- 2,101 raw contacts became **1,921** clean, deduplicated contacts in
  `marts.dim_contact`.
- 500 accounts: 100 enriched in Clay, 18 still waiting for enrichment,
  the rest by the mock provider.

## Planted vs caught

| Planted error | Check | Planted | Caught | Missed | Recall % | Detectable | Recall on detectable % |
| --- | --- | --- | --- | --- | --- | --- | --- |
| duplicate_contact | duplicate_contact | 100 | 100 | 0 | 100.0 | 100 | 100.0 |
| missing_title | missing_title | 100 | 100 | 0 | 100.0 | 100 | 100.0 |
| invalid_email | invalid_email | 60 | 60 | 0 | 100.0 | 60 | 100.0 |
| stale_record | stale_contact | 60 | 60 | 0 | 100.0 | 60 | 100.0 |
| orphan_contact | orphan_contact | 20 | 20 | 0 | 100.0 | 20 | 100.0 |
| conflicting_industry | industry_conflict | 10 | 5 | 5 | 50.0 | 5 | 100.0 |

## All checks

| Check | Entity | Severity | Action | Tested | Failed | Pass % |
| --- | --- | --- | --- | --- | --- | --- |
| missing_title | contact | warn | flag | 2101 | 100 | 95.2 |
| duplicate_contact | contact | warn | merge | 2101 | 100 | 95.2 |
| invalid_email | contact | error | quarantine | 2101 | 60 | 97.1 |
| stale_contact | contact | warn | refresh | 2101 | 60 | 97.1 |
| orphan_contact | contact | error | quarantine | 2101 | 20 | 99.0 |
| possible_duplicate | contact | - | - | 2101 | 0 | 100.0 |
| unmapped_title | contact | - | - | 2101 | 0 | 100.0 |
| missing_employee_count | account | warn | flag | 500 | 25 | 95.0 |
| missing_enrichment | account | warn | queue_for_enrichment | 500 | 18 | 96.4 |
| stale_enrichment | account | warn | re_enrich | 500 | 16 | 96.8 |
| headcount_band_mismatch | account | warn | flag | 500 | 13 | 97.4 |
| missing_industry | account | warn | flag | 500 | 6 | 98.8 |
| industry_conflict | account | warn | resolved_by_rule | 500 | 6 | 98.8 |
| country_conflict | account | warn | resolved_by_rule | 500 | 3 | 99.4 |
| suspected_wrong_entity | account | error | review | 500 | 1 | 99.8 |
| unmapped_industry_label | account | - | - | 500 | 0 | 100.0 |

## Findings in the real Clay data

These were not planted. They come from Clay's enrichment of real public companies.

| Check | Company | Detail |
| --- | --- | --- |
| suspected_wrong_entity | Chime | Chime Workplace: 14 employees vs "1,001-5,000 employees" |
| country_conflict | Collibra | BE vs US |
| country_conflict | JetBrains | CZ vs NL |
| country_conflict | Snowflake | US vs GB |
| industry_conflict | Loom | Software vs Online Audio and Video Media |
| headcount_band_mismatch | Airtable | 4613 employees vs "501-1,000 employees" |
| headcount_band_mismatch | Amplitude | 4421 employees vs "501-1,000 employees" |
| headcount_band_mismatch | Calendly | 4000 employees vs "201-500 employees" |
| headcount_band_mismatch | Canva | 19652 employees vs "1,001-5,000 employees" |
| headcount_band_mismatch | Datadog | 10209 employees vs "1,001-5,000 employees" |
| headcount_band_mismatch | Drata | 4198 employees vs "501-1,000 employees" |
| headcount_band_mismatch | Heap | 100 employees vs "201-500 employees" |
| headcount_band_mismatch | Monte Carlo | 553 employees vs "51-200 employees" |
| headcount_band_mismatch | Notion | 7124 employees vs "501-1,000 employees" |
| headcount_band_mismatch | Outreach | 5254 employees vs "501-1,000 employees" |
| headcount_band_mismatch | Plaid | 5110 employees vs "501-1,000 employees" |
| headcount_band_mismatch | Postman | 3582 employees vs "501-1,000 employees" |
| headcount_band_mismatch | Webflow | 5120 employees vs "501-1,000 employees" |

## How industry was resolved

| Enrichment | Industry rule | Accounts |
| --- | --- | --- |
| clay | seed_kept_generic_label | 77 |
| clay | seed_kept_compatible | 22 |
| clay | enrichment_overrides_conflict | 1 |
| missing | seed_only_no_enrichment | 18 |
| mock | seed_kept_compatible | 255 |
| mock | seed_kept_generic_label | 116 |
| mock | seed_only_provider_blank | 6 |
| mock | enrichment_overrides_conflict | 5 |

## Trade-off: industry conflicts

Clay labels most tech companies "Software Development", including security, fintech
and health companies. A strict mapping (where that label can only mean Software,
Developer Tools, Data, Sales, Marketing or HR) would catch 8 of
10 planted conflicts, but would also flag 9 real companies
whose seed industry is correct and overwrite it: Athenahealth, Bill.com, Doximity, Drata, Hinge Health, Plaid, Vanta, Veeva Systems, Zocdoc.

The pipeline instead treats generic labels as uninformative. It gives up the planted
conflicts that only a generic label could have revealed, in exchange for no false
overrides on real companies. Every conflict that a specific label reveals is caught.
