# Attio setup (about 10 minutes)

The free Attio plan is enough: up to 3 seats, 50,000 records, API access.

## 1. Workspace and API key

1. Sign up at attio.com and create a workspace. Skip connecting email or calendar.
2. Workspace settings, then Developers, then create an access token.
3. Give it Read & Write on: Records, Object configuration, List entries,
   List configuration.
4. Copy the token into `.env` (never commit it):

```
ATTIO_API_KEY=your_token
```

## 2. Smoke test first

```bash
make all            # builds scores and does an Attio dry run (no API calls)
make attio-smoke    # creates the schema, then syncs 3 companies + 1 contact each
```

It prints links to the new records. Open one and check the `GTM ...` fields.

## 3. Full sync

```bash
make attio-sync     # about 3,100 writes, a few minutes at the paced rate
make attio-sync     # run again: every record should be "unchanged", 0 writes
make attio-verify   # one Attio record per GTM id, 0 duplicates
```

## 4. Screenshots for the README

Save in `docs/img/`:

- `attio_companies.png`: Companies view with GTM fit score and GTM industry columns
- `attio_prospects.png`: the "GTM Prospects (Tier A and B)" list, grouped or sorted by stage
- `attio_person.png`: one person record showing tier, persona and linked company

## If something fails

- `401` / `403`: the token is wrong or missing a scope from step 1.
- A value rejected (for example a `.example` domain on a synthetic company): the sync
  retries without that value, logs it, and carries on. See `attio.sync_errors`.
- Anything else: rerun is safe. Already-synced records are skipped.
