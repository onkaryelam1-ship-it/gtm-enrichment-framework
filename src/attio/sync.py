"""Sync scored accounts and contacts from the warehouse into Attio.

    python -m src.attio.sync --smoke      # 3 companies + 1 contact each, prints links
    python -m src.attio.sync              # full sync
    python -m src.attio.sync --dry-run    # no API calls; writes payloads to data/attio_payloads/
    python -m src.attio.sync --verify     # count what is in Attio and check for duplicates

How it stays idempotent:
  * Records are upserted ("asserted") on our own external IDs (gtm_account_id,
    gtm_contact_id), which are unique attributes in Attio. Running twice never
    creates a second record.
  * Each payload is hashed. If nothing changed since the last successful sync, the
    record is skipped, so a rerun sends zero writes.
  * Tier A and B contacts get an entry in the Prospects list. A contact that drops
    to tier C has its entry removed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

import duckdb
from dotenv import load_dotenv

from src.attio.client import AttioClient, AttioError
from src.attio.schema import LIST_SLUG, ensure_schema
from src.config import ROOT, path

# Values Attio may reject for simulated data (reserved .example / .test domains).
# If a write fails validation on one of these, it is retried once without it.
DROPPABLE = {"domains": "domain", "email_addresses": "email"}


# ---------------------------------------------------------------------------
# payloads
# ---------------------------------------------------------------------------

def _missing(v) -> bool:
    return v is None or v == "" or v == [] or (isinstance(v, float) and math.isnan(v))


def _clean(values: dict) -> dict:
    """Drop empty values and turn numpy scalars into plain Python for JSON."""
    out = {}
    for k, v in values.items():
        if hasattr(v, "item"):
            v = v.item()
        if not _missing(v):
            out[k] = v
    return out


def company_values(row: dict) -> dict:
    flags = [name for name, on in [
        ("suspected_wrong_entity", row.get("is_suspected_wrong_entity")),
        ("industry_conflict", row.get("has_industry_conflict")),
        ("country_conflict", row.get("has_country_conflict")),
        ("headcount_band_mismatch", row.get("has_headcount_band_mismatch")),
        ("stale_enrichment", row.get("is_stale_enrichment")),
        ("missing_enrichment", row.get("enrichment_status") == "missing"),
    ] if on]
    return _clean({
        "gtm_account_id": row["account_id"],
        "name": row["company_name"],
        "domains": [row["domain"]] if row.get("domain") else None,
        "gtm_fit_score": row.get("fit_score"),
        "gtm_industry": row.get("industry"),
        "gtm_enrichment_source": row.get("enrichment_status"),
        "gtm_dq_flags": ", ".join(flags) or None,
    })


def person_values(row: dict, company_record_id: str | None) -> dict:
    return _clean({
        "gtm_contact_id": row["contact_id"],
        "name": [{
            "first_name": row["first_name"],
            "last_name": row["last_name"],
            "full_name": row["full_name"],
        }],
        "email_addresses": [row["email"]],
        "job_title": row.get("title"),
        "company": [{"target_object": "companies", "target_record_id": company_record_id}]
        if company_record_id else None,
        "gtm_priority_score": row.get("priority_score"),
        "gtm_tier": row.get("tier"),
        "gtm_persona": row.get("persona"),
        "gtm_seniority": row.get("seniority"),
    })


def entry_values(row: dict) -> dict:
    return _clean({
        "gtm_stage": row["stage"],
        "gtm_tier": row["tier"],
        "gtm_priority_score": row["priority_score"],
        "gtm_segment": f"{row['tier']} / {row['persona']}",
    })


def payload_hash(values: dict) -> str:
    return hashlib.sha1(json.dumps(values, sort_keys=True, default=str).encode()).hexdigest()


# ---------------------------------------------------------------------------
# state (kept in the warehouse, so the sync is inspectable with SQL)
# ---------------------------------------------------------------------------

STATE_DDL = """
create schema if not exists attio;
create table if not exists attio.record_map (
    entity varchar, local_id varchar, attio_id varchar, payload_hash varchar,
    synced_at timestamp, primary key (entity, local_id));
create table if not exists attio.sync_runs (
    run_id varchar, entity varchar, sent integer, created integer, updated integer,
    unchanged integer, removed integer, failed integer, dropped_values integer,
    finished_at timestamp);
create table if not exists attio.sync_errors (
    run_id varchar, entity varchar, local_id varchar, status integer, message varchar,
    logged_at timestamp);
"""


@dataclass
class Stats:
    sent: int = 0
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0
    failed: int = 0
    dropped_values: int = 0
    errors: list = field(default_factory=list)


class State:
    def __init__(self, con: duckdb.DuckDBPyConnection, persist: bool = True):
        self.con = con
        self.persist = persist
        con.execute(STATE_DDL)
        self.map = {(e, i): (a, h) for e, i, a, h in con.execute(
            "select entity, local_id, attio_id, payload_hash from attio.record_map").fetchall()}

    def get(self, entity, local_id):
        return self.map.get((entity, local_id), (None, None))

    def put(self, entity, local_id, attio_id, h):
        self.map[(entity, local_id)] = (attio_id, h)
        if self.persist:
            self.con.execute(
                "insert or replace into attio.record_map values (?, ?, ?, ?, ?)",
                [entity, local_id, attio_id, h, datetime.now(timezone.utc)])

    def drop(self, entity, local_id):
        self.map.pop((entity, local_id), None)
        if self.persist:
            self.con.execute("delete from attio.record_map where entity = ? and local_id = ?",
                             [entity, local_id])


# ---------------------------------------------------------------------------
# transports
# ---------------------------------------------------------------------------

class DryRun:
    """Stands in for AttioClient: records every payload, returns stable fake ids."""

    def __init__(self):
        self.calls = []

    def request(self, method, path, params=None, json=None):
        self.calls.append({"method": method, "path": path, "params": params, "json": json})
        data = (json or {}).get("data", {})
        values = data.get("values", {})
        ext = values.get("gtm_contact_id") or values.get("gtm_account_id") or data.get("parent_record_id")
        rid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{path}|{ext}"))
        return {"data": {"id": {"record_id": rid, "entry_id": rid}, "web_url": None}}


# ---------------------------------------------------------------------------
# sync
# ---------------------------------------------------------------------------

def _write(client, method, path, params, values, stats, entity, local_id, log):
    """Send one record write, retrying once without a value Attio rejected
    (e.g. a reserved .example domain). Returns the response or None."""
    body = {"data": {"values": dict(values)}}
    for attempt in range(2):
        try:
            stats.sent += 1
            return client.request(method, path, params=params, json=body)
        except AttioError as e:
            droppable = [k for k, word in DROPPABLE.items()
                         if k in body["data"]["values"] and (k in e.message or word in e.message.lower())]
            if attempt == 0 and e.status == 400 and droppable:
                for k in droppable:
                    body["data"]["values"].pop(k)
                stats.dropped_values += len(droppable)
                log(f"  ! {entity} {local_id}: Attio rejected {droppable}, retrying without it")
                continue
            if e.status == 404:
                raise
            stats.failed += 1
            stats.errors.append((entity, local_id, e.status, e.message[:500]))
            return None
    return None


def _find(client, obj, key, value):
    """Look up a record by our external id (used when the id attribute isn't unique)."""
    data = client.request("POST", f"/objects/{obj}/records/query",
                          json={"filter": {key: value}, "limit": 1})["data"]
    return data[0]["id"]["record_id"] if data else None


def _upsert(client, obj, key, values, prev_id, unique, stats, entity, local_id, log):
    """Create or update one record. Returns (record_id, web_url, was_created).

    unique=True : PUT "assert" matched on the external id attribute (one call).
    unique=False: update the known record id; otherwise find by external id, then
                  update it or create it. Still one Attio record per external id.
    """
    if unique:
        resp = _write(client, "PUT", f"/objects/{obj}/records", {"matching_attribute": key},
                      values, stats, entity, local_id, log)
        if not resp:
            return None, None, False
        return resp["data"]["id"]["record_id"], resp["data"].get("web_url"), prev_id is None

    rid = prev_id
    if rid:
        try:
            resp = _write(client, "PATCH", f"/objects/{obj}/records/{rid}", None,
                          values, stats, entity, local_id, log)
            return (rid, resp["data"].get("web_url"), False) if resp else (None, None, False)
        except AttioError:          # 404: deleted in Attio since the last sync
            rid = None
    rid = _find(client, obj, key, values[key])
    if rid:
        resp = _write(client, "PATCH", f"/objects/{obj}/records/{rid}", None,
                      values, stats, entity, local_id, log)
        return (rid, resp["data"].get("web_url"), False) if resp else (None, None, False)
    resp = _write(client, "POST", f"/objects/{obj}/records", None, values, stats, entity, local_id, log)
    if not resp:
        return None, None, False
    return resp["data"]["id"]["record_id"], resp["data"].get("web_url"), True


def load_rows(con, limit: int | None, smoke: bool):
    accounts = con.execute("""
        select a.*, f.fit_score
        from marts.dim_account a join intermediate.int_account_fit f using (account_id)
        where a.account_id in (select account_id from marts.fct_prospect_scores)
        order by (a.enrichment_status = 'clay') desc, a.account_id
    """).df()
    if smoke:
        accounts = accounts.head(3)
    elif limit:
        accounts = accounts.head(limit)
    people = con.execute("""
        select * from marts.fct_prospect_scores
        where account_id = any(?)
        order by account_id, priority_rank
    """, [list(accounts["account_id"])]).df()
    if smoke:
        people = people.groupby("account_id").head(1)
    return accounts.to_dict("records"), people.to_dict("records")


def sync(client, con, *, limit=None, smoke=False, force=False, persist=True,
         unique_ids=None, log=print) -> dict:
    unique_ids = unique_ids or {"companies": True, "people": True}
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    state = State(con, persist=persist)
    accounts, people = load_rows(con, limit, smoke)
    results = {}
    links = []

    # companies ---------------------------------------------------------------
    s = Stats()
    for row in accounts:
        values = company_values(row)
        h = payload_hash(values)
        prev_id, prev_h = state.get("company", row["account_id"])
        if prev_id and prev_h == h and not force:
            s.unchanged += 1
            continue
        rid, url, created = _upsert(client, "companies", "gtm_account_id", values, prev_id,
                                    unique_ids["companies"], s, "company", row["account_id"], log)
        if rid:
            s.created += created
            s.updated += not created
            state.put("company", row["account_id"], rid, h)
            if url and len(links) < 3:
                links.append(url)
    results["companies"] = s
    log(f"companies: {_fmt(s)}")

    # people ------------------------------------------------------------------
    s = Stats()
    for row in people:
        company_id, _ = state.get("company", row["account_id"])
        values = person_values(row, company_id)
        h = payload_hash(values)
        prev_id, prev_h = state.get("person", row["contact_id"])
        if prev_id and prev_h == h and not force:
            s.unchanged += 1
            continue
        rid, url, created = _upsert(client, "people", "gtm_contact_id", values, prev_id,
                                    unique_ids["people"], s, "person", row["contact_id"], log)
        if rid:
            s.created += created
            s.updated += not created
            state.put("person", row["contact_id"], rid, h)
            if url and len(links) < 6:
                links.append(url)
    results["people"] = s
    log(f"people:    {_fmt(s)}")

    # prospects list (tier A and B) ------------------------------------------
    s = Stats()
    for row in people:
        person_id, _ = state.get("person", row["contact_id"])
        entry_id, prev_h = state.get("entry", row["contact_id"])
        if row["tier"] == "C":
            if entry_id:
                try:
                    s.sent += 1
                    client.request("DELETE", f"/lists/{LIST_SLUG}/entries/{entry_id}")
                    state.drop("entry", row["contact_id"])
                    s.removed += 1
                except AttioError as e:
                    s.failed += 1
                    s.errors.append(("entry", row["contact_id"], e.status, e.message[:500]))
            continue
        if not person_id:
            continue
        values = entry_values(row)
        h = payload_hash({**values, "_parent": person_id})
        if entry_id and prev_h == h and not force:
            s.unchanged += 1
            continue
        body = {"data": {"parent_record_id": person_id, "parent_object": "people",
                         "entry_values": values}}
        try:
            s.sent += 1
            resp = client.request("PUT", f"/lists/{LIST_SLUG}/entries", json=body)
            s.updated += bool(entry_id)
            s.created += not entry_id
            state.put("entry", row["contact_id"], resp["data"]["id"]["entry_id"], h)
        except AttioError as e:
            s.failed += 1
            s.errors.append(("entry", row["contact_id"], e.status, e.message[:500]))
    results["prospect_entries"] = s
    log(f"prospects: {_fmt(s)}")

    if persist:
        now = datetime.now(timezone.utc)
        for entity, st in results.items():
            con.execute("insert into attio.sync_runs values (?,?,?,?,?,?,?,?,?,?)",
                        [run_id, entity, st.sent, st.created, st.updated, st.unchanged,
                         st.removed, st.failed, st.dropped_values, now])
            for e, lid, status, msg in st.errors:
                con.execute("insert into attio.sync_errors values (?,?,?,?,?,?)",
                            [run_id, e, lid, status, msg, now])
    for entity, st in results.items():
        for e, lid, status, msg in st.errors[:3]:
            log(f"  error {e} {lid}: {status} {msg}")
    if links:
        log("Open in Attio:\n  " + "\n  ".join(links))
    return {"run_id": run_id, "results": results, "links": links}


def _fmt(s: Stats) -> str:
    return (f"{s.created} created, {s.updated} updated, {s.unchanged} unchanged, "
            f"{s.removed} removed, {s.failed} failed ({s.sent} API writes)")


def verify(client, con, log=print) -> dict:
    """Page through Attio and confirm one record per external id (no duplicates)."""
    out = {}
    for obj, key in [("companies", "gtm_account_id"), ("people", "gtm_contact_id")]:
        seen, offset = {}, 0
        while True:
            page = client.request("POST", f"/objects/{obj}/records/query",
                                  json={"limit": 500, "offset": offset})["data"]
            for rec in page:
                vals = rec.get("values", {}).get(key) or []
                if vals:
                    ext = vals[0].get("value")
                    seen[ext] = seen.get(ext, 0) + 1
            if len(page) < 500:
                break
            offset += 500
        dupes = {k: v for k, v in seen.items() if v > 1}
        expected = con.execute(
            "select count(*) from attio.record_map where entity = ?",
            ["company" if obj == "companies" else "person"]).fetchone()[0]
        out[obj] = {"in_attio": len(seen), "expected": expected, "duplicates": len(dupes)}
        log(f"{obj}: {len(seen)} in Attio with a GTM id, {expected} expected, "
            f"{len(dupes)} duplicated ids")
    return out


def main(argv=None) -> dict:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true", help="no API calls; write payloads to disk")
    p.add_argument("--smoke", action="store_true", help="sync 3 companies and 1 contact each")
    p.add_argument("--limit", type=int, help="only the first N companies (and their contacts)")
    p.add_argument("--force", action="store_true", help="resend even if nothing changed")
    p.add_argument("--verify", action="store_true", help="check Attio for missing or duplicate records")
    p.add_argument("--skip-schema", action="store_true")
    args = p.parse_args(argv)

    load_dotenv(ROOT / ".env")
    con = duckdb.connect(str(path("warehouse")))
    try:
        if args.dry_run:
            dry = DryRun()
            result = sync(dry, con, limit=args.limit, smoke=args.smoke, force=True, persist=False)
            out_dir = ROOT / "data" / "attio_payloads"
            out_dir.mkdir(parents=True, exist_ok=True)
            with open(out_dir / "requests.jsonl", "w") as f:
                f.writelines(json.dumps(c, default=str) + "\n" for c in dry.calls)
            print(f"Dry run: {len(dry.calls)} requests written to {out_dir / 'requests.jsonl'}")
            return result

        client = AttioClient(os.environ.get("ATTIO_API_KEY", "").strip())
        if args.verify:
            return verify(client, con)
        unique_ids = ensure_schema(client, create=not args.skip_schema)
        result = sync(client, con, limit=args.limit, smoke=args.smoke, force=args.force,
                      unique_ids=unique_ids)
        print(f"Done in {client.calls} API calls. Run id {result['run_id']}.")
        return result
    finally:
        con.close()


if __name__ == "__main__":
    main()
