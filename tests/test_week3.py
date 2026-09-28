"""Week 3 tests: scoring and tiers, and the Attio sync against an in-memory fake of
the Attio API (no network, no key needed)."""

from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import duckdb
import pytest

from src.attio import sync as attio_sync
from src.attio.client import AttioClient, AttioError, retry_after_seconds
from src.attio.schema import COMPANY_ATTRS, LIST_SLUG, PEOPLE_ATTRS, ensure_schema

# ---------------------------------------------------------------------------
# fake Attio
# ---------------------------------------------------------------------------

class FakeAttio:
    """Just enough of the Attio v2 API for the sync: attributes, options, lists,
    asserting records on a unique attribute, list entries, and record queries."""

    def __init__(self, reject_domain_suffix: str | None = None, allow_unique: bool = True):
        self.allow_unique = allow_unique
        self.attrs = {"objects/companies": {}, "objects/people": {}}
        self.lists = {}
        self.records = {"companies": {}, "people": {}}
        self.entries = {}
        self.writes = 0
        self.reject_domain_suffix = reject_domain_suffix

    def _err(self, status, msg, method, path):
        raise AttioError(status, {"status_code": status, "message": msg}, method, path)

    def request(self, method, path, params=None, json=None):
        parts = path.strip("/").split("/")
        if method in ("PUT", "POST", "DELETE") and not path.endswith("/query"):
            self.writes += 1
        # attributes and options
        if len(parts) >= 3 and parts[2] == "attributes":
            key = f"{parts[0]}/{parts[1]}"
            attrs = self.attrs.setdefault(key, {})
            if len(parts) == 3:
                if method == "GET":
                    return {"data": [{"api_slug": s, "is_unique": a["meta"]["is_unique"]}
                                     for s, a in attrs.items()]}
                slug = json["data"]["api_slug"]
                if slug in attrs:
                    self._err(409, "slug_conflict", method, path)
                if json["data"]["is_unique"] and not self.allow_unique:
                    self._err(400, "Cannot set attribute as unique.", method, path)
                attrs[slug] = {"meta": json["data"], "options": set()}
                return {"data": {"api_slug": slug}}
            opts = attrs[parts[3]]["options"]
            if method == "GET":
                return {"data": [{"title": o} for o in opts]}
            opts.add(json["data"]["title"])
            return {"data": {}}
        if path == "/lists":
            if method == "GET":
                return {"data": [{"api_slug": s} for s in self.lists]}
            self.lists[json["data"]["api_slug"]] = json["data"]
            self.attrs[f"lists/{json['data']['api_slug']}"] = {}
            return {"data": {}}
        # records
        if parts[0] == "objects" and parts[2] == "records":
            obj = parts[1]
            if path.endswith("/query"):
                recs = list(self.records[obj].items())
                for k, v in (json.get("filter") or {}).items():
                    recs = [(rid, r) for rid, r in recs if r["values"].get(k) == v]
                off = json.get("offset", 0)
                page = recs[off: off + json["limit"]]
                return {"data": [{"id": {"record_id": rid},
                                  "values": {k: [{"value": v}] for k, v in r["values"].items()}}
                                 for rid, r in page]}
            values = json["data"]["values"]
            if self.reject_domain_suffix and any(
                    d.endswith(self.reject_domain_suffix) for d in values.get("domains", [])):
                self._err(400, "Invalid value was passed to attribute with slug \"domains\".",
                          method, path)
            if method == "PATCH":
                if parts[3] not in self.records[obj]:
                    self._err(404, "Record not found", method, path)
                self.records[obj][parts[3]]["values"].update(values)
                return {"data": {"id": {"record_id": parts[3]}, "web_url": f"https://fake/{parts[3]}"}}
            if method == "POST":
                rid = str(uuid.uuid4())
                self.records[obj][rid] = {"values": dict(values)}
                return {"data": {"id": {"record_id": rid}, "web_url": f"https://fake/{rid}"}}
            match = params["matching_attribute"]
            assert self.attrs[f"objects/{obj}"][match]["meta"]["is_unique"], "must match on a unique attr"
            for rid, rec in self.records[obj].items():
                if rec["values"].get(match) == values[match]:
                    rec["values"].update(values)
                    return {"data": {"id": {"record_id": rid}, "web_url": f"https://fake/{rid}"}}
            rid = str(uuid.uuid4())
            self.records[obj][rid] = {"values": dict(values)}
            return {"data": {"id": {"record_id": rid}, "web_url": f"https://fake/{rid}"}}
        # list entries
        if parts[0] == "lists" and parts[2] == "entries":
            if method == "DELETE":
                self.entries.pop(parts[3])
                return {}
            parent = json["data"]["parent_record_id"]
            for eid, e in self.entries.items():
                if e["parent"] == parent:
                    e["values"] = json["data"]["entry_values"]
                    return {"data": {"id": {"entry_id": eid}}}
            eid = str(uuid.uuid4())
            self.entries[eid] = {"parent": parent, "values": json["data"]["entry_values"]}
            return {"data": {"id": {"entry_id": eid}}}
        raise AssertionError(f"unexpected call {method} {path}")


@pytest.fixture()
def con(built_warehouse, tmp_path):
    """A private read-write copy of the built warehouse (sync writes its state there)."""
    db = tmp_path / "sync.duckdb"
    shutil.copy(built_warehouse, db)
    c = duckdb.connect(str(db))
    yield c
    c.close()


def quiet(*_a, **_k):
    pass


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------

def test_every_clean_contact_is_scored(con):
    n_contacts, n_scored = con.execute(
        "select (select count(*) from marts.dim_contact), (select count(*) from marts.fct_prospect_scores)"
    ).fetchone()
    assert n_contacts == n_scored


def test_tier_sizes_are_sensible(con):
    shares = dict(con.execute("""
        select tier, count(*) * 1.0 / sum(count(*)) over () from marts.fct_prospect_scores group by 1
    """).fetchall())
    assert 0.03 <= shares["A"] <= 0.20
    assert shares["A"] < shares["B"] < shares["C"]


def test_tiers_follow_thresholds(con):
    bad = con.execute("""
        select count(*) from marts.fct_prospect_scores
        where (tier = 'A' and priority_score < 62) or (tier = 'C' and priority_score >= 50)
           or (tier = 'B' and (priority_score < 50 or priority_score >= 62))
    """).fetchone()[0]
    assert bad == 0


def test_data_leaders_outrank_individual_contributors(con):
    leader, ic = con.execute("""
        select avg(role_score) filter (where persona = 'Data/RevOps leader'),
               avg(role_score) filter (where seniority = 'IC')
        from marts.fct_prospect_scores
    """).fetchone()
    assert leader > ic


# ---------------------------------------------------------------------------
# attio client
# ---------------------------------------------------------------------------

def test_retry_after_parses_seconds_and_dates():
    assert retry_after_seconds("2") == 2.0
    future = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=3), usegmt=True)
    assert 1.5 < retry_after_seconds(future) <= 3.5
    assert retry_after_seconds(None) == 1.0


class _Resp:
    def __init__(self, status, body=None, headers=None):
        self.status_code = status
        self._body = body or {}
        self.headers = headers or {}
        self.content = b"x"
        self.text = str(self._body)

    def json(self):
        return self._body


class _Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.headers = {}
        self.calls = 0

    def request(self, *a, **k):
        self.calls += 1
        return self.responses.pop(0)


def test_client_retries_429_then_succeeds():
    s = _Session([_Resp(429, headers={"Retry-After": "0"}), _Resp(200, {"data": {"ok": True}})])
    c = AttioClient("k", writes_per_sec=1000, session=s)
    assert c.request("GET", "/self") == {"data": {"ok": True}}
    assert s.calls == 2


def test_client_raises_readable_error_on_400():
    s = _Session([_Resp(400, {"message": "bad value", "code": "validation_type"})])
    c = AttioClient("k", writes_per_sec=1000, session=s)
    with pytest.raises(AttioError) as e:
        c.request("PUT", "/objects/people/records")
    assert e.value.status == 400 and "bad value" in str(e.value)


def test_client_requires_a_key():
    with pytest.raises(ValueError):
        AttioClient("")


# ---------------------------------------------------------------------------
# attio sync
# ---------------------------------------------------------------------------

def test_schema_setup_is_idempotent():
    fake = FakeAttio()
    ensure_schema(fake, log=quiet)
    first = fake.writes
    ensure_schema(fake, log=quiet)
    assert fake.writes == first
    assert {a.slug for a in COMPANY_ATTRS} <= set(fake.attrs["objects/companies"])
    assert {a.slug for a in PEOPLE_ATTRS} <= set(fake.attrs["objects/people"])
    assert LIST_SLUG in fake.lists


BOTH_MODES = pytest.mark.parametrize("allow_unique", [True, False], ids=["unique-ids", "find-then-upsert"])


def _setup(allow_unique=True, **kw):
    fake = FakeAttio(allow_unique=allow_unique, **kw)
    unique_ids = ensure_schema(fake, log=quiet)
    assert all(unique_ids.values()) == allow_unique
    return fake, unique_ids


def test_lost_state_does_not_create_duplicates(con):
    """If the local sync state is wiped, find-then-upsert still finds existing records."""
    fake, u = _setup(allow_unique=False)
    attio_sync.sync(fake, con, limit=5, unique_ids=u, log=quiet)
    n = len(fake.records["people"])
    con.execute("delete from attio.record_map")
    attio_sync.sync(fake, con, limit=5, unique_ids=u, log=quiet)
    assert len(fake.records["people"]) == n


@BOTH_MODES
def test_full_sync_then_rerun_sends_nothing(con, allow_unique):
    fake, u = _setup(allow_unique)
    first = attio_sync.sync(fake, con, unique_ids=u, log=quiet)["results"]
    n_accounts, n_people, n_ab = con.execute("""
        select count(distinct account_id), count(*), count(*) filter (where tier in ('A', 'B'))
        from marts.fct_prospect_scores
    """).fetchone()
    assert first["companies"].created == n_accounts
    assert first["people"].created == n_people
    assert first["prospect_entries"].created == n_ab
    assert len(fake.records["companies"]) == n_accounts
    assert len(fake.records["people"]) == n_people
    assert len(fake.entries) == n_ab

    writes_before = fake.writes
    second = attio_sync.sync(fake, con, unique_ids=u, log=quiet)["results"]
    assert fake.writes == writes_before                 # nothing resent
    assert second["people"].unchanged == n_people
    assert len(fake.records["people"]) == n_people      # no duplicates


@BOTH_MODES
def test_forced_rerun_updates_without_duplicating(con, allow_unique):
    fake, u = _setup(allow_unique)
    attio_sync.sync(fake, con, limit=5, unique_ids=u, log=quiet)
    n = len(fake.records["people"])
    res = attio_sync.sync(fake, con, limit=5, force=True, unique_ids=u, log=quiet)["results"]
    assert res["people"].updated == n and res["people"].created == 0
    assert len(fake.records["people"]) == n


@BOTH_MODES
def test_people_are_linked_to_their_company(con, allow_unique):
    fake, u = _setup(allow_unique)
    attio_sync.sync(fake, con, limit=3, unique_ids=u, log=quiet)
    company_ids = set(fake.records["companies"])
    for rec in fake.records["people"].values():
        assert rec["values"]["company"][0]["target_record_id"] in company_ids


def test_tier_drop_removes_list_entry(con):
    fake, u = _setup()
    attio_sync.sync(fake, con, limit=20, unique_ids=u, log=quiet)
    cid = con.execute("""
        select contact_id from marts.fct_prospect_scores
        where tier = 'A' and account_id in (
            select account_id from marts.dim_account a
            join intermediate.int_account_fit using (account_id)
            order by (a.enrichment_status = 'clay') desc, a.account_id limit 20)
        limit 1
    """).fetchone()[0]
    before = len(fake.entries)
    con.execute("update marts.fct_prospect_scores set tier = 'C' where contact_id = ?", [cid])
    res = attio_sync.sync(fake, con, limit=20, unique_ids=u, log=quiet)["results"]
    assert res["prospect_entries"].removed == 1
    assert len(fake.entries) == before - 1


@BOTH_MODES
def test_rejected_value_is_dropped_and_logged(con, allow_unique):
    fake, u = _setup(allow_unique, reject_domain_suffix=".example")
    res = attio_sync.sync(fake, con, unique_ids=u, log=quiet)["results"]
    assert res["companies"].failed == 0
    assert res["companies"].dropped_values == con.execute(
        "select count(*) from marts.dim_account where domain like '%.example' "
        "and account_id in (select account_id from marts.fct_prospect_scores)").fetchone()[0]


def test_dry_run_writes_payloads_without_network(built_warehouse, monkeypatch, tmp_path):
    db = tmp_path / "dry.duckdb"
    shutil.copy(built_warehouse, db)
    monkeypatch.setenv("GTM_WAREHOUSE", str(db))
    monkeypatch.delenv("ATTIO_API_KEY", raising=False)
    result = attio_sync.main(["--dry-run", "--limit", "5"])
    assert result["results"]["companies"].created == 5


def test_email_rewrite_keeps_addresses_unique_and_undeliverable():
    assert attio_sync.attio_email("jane.doe@acme.test") == "jane.doe+acme@example.com"
    assert attio_sync.attio_email("jane.doe@acme.test", "as_is") == "jane.doe@acme.test"
    assert attio_sync.attio_email("real@company.com") == "real@company.com"
