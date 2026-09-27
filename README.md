# GTM Enrichment & Outbound Automation Framework

A simulated B2B sales-operations pipeline: synthetic accounts and contacts are
enriched with **Clay**, standardized and validated with **Python + SQL (dbt, DuckDB)**,
scored and segmented, synced to **Attio** via its REST API, and used to draft
personalized outbound emails with an **LLM API**, with dashboards on top.

> **Simulated data. No real emails are sent.** Company names and domains for the
> Clay-eligible accounts are real and public; every contact is synthetic and uses
> a reserved `.test` email domain. Buying signals (`sim_*` columns) are simulated.
> Independent project, not affiliated with any employer.

## Status

| Week | Scope | Status |
| --- | --- | --- |
| 1 | Repo, synthetic data with planted errors, DuckDB raw load, Clay enrichment (100 real companies), mock enricher | Done |
| 2 | dbt staging and marts, dedup, conflict resolution, validation checks | Planned |
| 3 | Scoring and tiers, Attio API sync | Planned |
| 4 | LLM drafting and evaluation, dashboards, Airflow DAG | Planned |

## Architecture

```
generate (Python, Faker) -> raw (DuckDB) -> enrich (Clay CSV / mock) -> dbt staging + marts
   -> validate (dbt tests, Python) -> score + segment -> Attio (REST API)
   -> LLM drafts + eval -> dashboards (Streamlit)
```

## Quickstart

```bash
python3 -m venv .venv && source .venv/bin/activate
make setup
cp .env.example .env       # add keys later (Attio, Gemini)
make week1                 # seed, load, clay-export, mock-enrich, clay-load
make test
```

Then follow [docs/clay_setup.md](docs/clay_setup.md) to enrich the real accounts in Clay.

## Clay enrichment

100 real companies were enriched in Clay (two 50-row tables on the free plan) with the
**Enrich company** action, keyed on domain, at 0.5 credits per row. Results were
exported as CSV and loaded into `raw.raw_clay_enrichment` by `make clay-load`.

![Enriched Clay table](docs/img/clay_enriched_table.png)

| Enrichment setup (keyed on Domain, auto-run off) | Output fields |
| --- | --- |
| ![Enrichment setup](docs/img/clay_enrichment_setup.png) | ![Output fields](docs/img/clay_fields.png) |

What the real enrichment surfaced, before any cleaning:

- 100 of 100 companies matched back to the seed accounts by domain.
- Country disagrees with the seed for 3 companies (Snowflake, Collibra, JetBrains).
- 70 of 100 came back with the broad label "Software Development", so a mapping
  layer is needed to get useful industry segments.
- Founded year is missing for 26 of 100.
- `chime.com` resolved to "Chime Workplace" with 14 employees, a likely wrong-entity
  match that a sanity check on headcount vs. size band should flag.

## What Week 1 produces

| Output | Rows | Notes |
| --- | --- | --- |
| `raw.raw_accounts` | 500 | 118 real public domains, 382 synthetic `.example` domains |
| `raw.raw_contacts` | ~2,100 | includes planted duplicates and bad records |
| `raw.raw_engagement` | ~2,700 | opens, web visits, replies, meetings over 90 days |
| `raw.raw_clay_enrichment` | ~1,500 values | long format: one row per account and field |
| `raw.planted_errors` | 350 | manifest of every error injected on purpose |

### Planted data-quality errors

Every error is logged in `planted_errors.csv`, so Week 2 validation can report
**planted vs caught** for each check.

| Error | Rate | Example |
| --- | --- | --- |
| Duplicate contacts | 5% | same person with upper-cased email, swapped letters in name, stray whitespace |
| Missing titles | 5% | blank `title` |
| Invalid emails | 3% | missing `@`, double `@`, no TLD, space in local part |
| Stale records | 3% | `source_updated_at` 400 to 900 days old |
| Orphan contacts | 1% | `account_id` that doesn't exist |
| Conflicting industry | 2% of accounts | seed industry disagrees with enrichment |

The mock enricher also behaves like a real provider: LinkedIn-style industry labels,
some missing values, some stale enrichment dates, and noisy headcounts.

## Repo layout

```
config/settings.yaml     seeds, sizes, error rates, Clay column mapping
src/generate/            synthetic data + error injection
src/load/                raw loads into DuckDB
src/clay/                Clay export, mock enricher, Clay export loader
src/attio/  src/scoring/  src/llm/  src/validation/   (weeks 2 to 4)
dbt/                     staging, intermediate, marts (week 2)
tests/                   pytest
docs/                    Clay guide, sample data, decisions log
```

## Tools

Python, pandas, Faker, DuckDB, dbt Core, Clay, Attio API, Gemini or Claude API,
Streamlit, pytest, ruff. Built with Cursor and Claude Code; every output is checked
against the planted-error manifest and tests.
