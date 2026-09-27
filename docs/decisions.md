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

## AI tooling notes

- _Add examples here: what Claude Code or Cursor produced, what you checked, and
  anything you had to fix._
