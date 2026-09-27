# Clay setup (about 20 minutes)

Clay's free plan gives 100 data credits a month, shows only 50 rows per table,
and has no HTTP API or webhooks. So data moves in and out of Clay as CSV files. This is the
one step you do by hand in the Clay UI.

Menu names in Clay change from time to time. If a label below doesn't match what
you see, look for the closest equivalent.

## 1. Create the import file

```bash
make seed load clay-export
```

This writes three files of up to 50 rows each (`accounts_for_clay_batch_01.csv`,
`_02`, `_03`). Import each one as its own Clay table, because the free plan only
shows 50 rows per table.

## 2. Build the Clay table

1. In Clay, create a new workbook named `GTM Enrichment Framework`.
2. Import `accounts_for_clay_batch_01.csv` as a new table. Keep all three columns:
   `Account ID`, `Company Name`, `Domain`.
3. **Test on 5 rows first.** Add a company enrichment column that takes a domain as
   input (search the enrichment list for "company" and pick one that accepts
   `Domain`). Run it on the first 5 rows only and check the credit cost per row.
4. From the enrichment result, add these as their own columns:
   `Industry`, `Employee Count`, `Headquarters Country`, `Founded Year`.
   If Clay only gives you HQ city/location, keep it anyway; we'll handle it in dbt.
5. Add one **formula column** (no credits) called `Domain Clean` that lowercases the
   domain and strips `www.`. This is a good talking point: you did light
   standardization inside Clay and the heavy lifting in SQL.
6. If the 5-row test looks right and you have credits left, run the enrichment on
   the rest of the rows.

## 3. Export back to the repo

1. Export the table as CSV.
2. Save it as `data/clay_exports/clay_batch_01.csv`.
3. Open `config/settings.yaml` and check `clay.column_map`. The left side must match
   the column headers in your export exactly. Edit it if Clay named them differently.
4. Load it:

```bash
make clay-load
```

You should see a `clay` provider line with the accounts you enriched next to the `mock`
line with 382. If you see "columns not found", fix `clay.column_map`.

## 4. Screenshots for the README

Take two screenshots and save them in `docs/img/`:

- `clay_table.png`: the Clay table with enrichment columns filled
- `clay_formula.png`: the `Domain Clean` formula column

## Credits budget

| Item | Rows | Notes |
| --- | --- | --- |
| 5-row test | 5 | confirm cost per row |
| Batch 01 | 50 | 25 credits at 0.5 per row |
| Batch 02 | 50 | 25 credits |
| Batch 03 | 18 | 9 credits |

Anything you can't enrich in Clay is covered by `src/clay/mock_enricher.py`, which
writes the same columns. In the README and in interviews, describe it as:
"Clay enrichment on a real-company sample, with a schema-matched mock enricher for
scale."
