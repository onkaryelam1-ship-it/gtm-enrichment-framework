# Decisions and trade-offs

A running log. Add an entry whenever you choose between options, and note where
AI coding tools helped or got something wrong. These make strong interview stories.

## Week 1

- **Real domains for Clay, synthetic domains for scale.** Clay can only enrich real
  companies, and the free plan caps credits at 100 a month. So 118 public companies
  go through Clay and 382 synthetic `.example` companies go through a mock enricher
  that writes the same columns.
- **Fake people, reserved domains.** Contacts use `.test` email domains (reserved by
  RFC 2606) so nothing can reach a real inbox, even for real companies. No LinkedIn
  URLs are generated, to avoid pointing at real profiles.
- **Planted errors with a manifest.** Errors are injected at configured rates into
  disjoint sets of records and logged, so validation can be measured, not assumed.
- **Raw loaded as text.** `all_varchar` keeps whitespace and bad values intact so the
  staging layer, not the loader, owns cleaning.
- **Long-format enrichment table.** One row per (account, field, provider) makes it
  easy to compare providers and detect conflicts in SQL.

## Week 2

- **dbt on DuckDB.** Same SQL patterns as a Snowflake warehouse, runs locally with no
  cost. `dbt build` runs models and tests together, so a failing check stops the run.
- **Checks as models, not only tests.** Each check writes failing rows to
  `quality.dq_failures` with an action (quarantine, merge, flag, refresh, review).
  Tests say pass/fail; the failure table says what to do with each record.
- **Quarantine vs flag.** Invalid emails and orphan contacts can't be used, so they're
  removed from `dim_contact`. Missing titles and stale records are still usable, so
  they stay with a flag.
- **Exact dedup auto-merges, fuzzy dedup only flags.** Normalized-email matches are
  safe to merge. Name-similarity matches can be two different people, so they go to
  review.
- **Survivor rule.** In a duplicate group, keep the record with a title, then the most
  recently updated, then the lowest id.
- **Industry: generic labels don't count as evidence.** A strict mapping caught more
  planted conflicts but would have overwritten the correct industry of 9 real
  companies. Chose precision over recall and reported both numbers.
- **Country: seed wins.** The seed is a curated list; Clay said Snowflake is in GB.
  Conflicts are logged, not silently resolved.
- **Headcount vs size band: two thresholds.** 2-10x outside the band is a warning
  (bands are self-reported and lag). 10x or more suggests the wrong company was
  matched, which is how Chime / "Chime Workplace" was caught.
- **Recall measured, not assumed.** Every planted error is joined back to the checks,
  and a dbt test fails the build if a rule-based check misses one.

## Week 3

- **Scoring in SQL, weights as config.** The score is a dbt model, so it is versioned,
  tested (range and weight-sum tests) and visible in lineage. Weights and thresholds
  are dbt vars: tuning is a one-line change.
- **Thresholds set from the distribution.** With the first engagement settings only
  23 contacts (1%) reached tier A because engagement barely moved the score. Raised
  event points and lengthened the half-life from 14 to 30 days, then set A at 62 and
  B at 50 to get roughly 8% / 29% / 63%.
- **Match on our own IDs, not on email or domain.** `gtm_account_id` and
  `gtm_contact_id` are unique attributes in Attio and the upsert key. Emails and
  domains change and can collide; an external ID never does.
- **Fallback when unique attributes aren't allowed.** The first real run failed with
  "Cannot set attribute as unique": this workspace won't let the API create a unique
  custom attribute. The sync now detects that and switches to find-then-upsert
  (look up by external ID, then PATCH or POST). Tests run both modes, plus a test
  that wipes the local sync state and confirms no duplicates are created.
- **Emails Attio will accept.** Attio rejected the reserved `.test` addresses. The
  sync sends `jane.doe+acme@example.com` instead: example.com is also reserved and
  never delivers, but it's a valid address, stays unique per contact (checked: 1,921
  of 1,921), and keeps the source company visible. Configurable in settings.yaml.
- **Skip unchanged records.** Payload hashes make reruns cost nothing and make the
  "no duplicates on rerun" claim testable.
- **List membership follows the tier.** Only tier A and B go in the Prospects list;
  a contact that falls to C is removed, so the list is always the current working set.
- **Fake API for tests.** The real API can't be called from CI, so tests use an
  in-memory fake that enforces the behaviours the sync relies on (unique-attribute
  matching, list entries by parent, validation errors).

## AI tooling notes

- _Add examples here: what Claude Code or Cursor produced, what you checked, and
  anything you had to fix._
