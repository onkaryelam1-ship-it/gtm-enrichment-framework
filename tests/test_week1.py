"""Week 1 tests: generator is deterministic, errors are planted at the configured
rates, the manifest is accurate, and the raw + enrichment loads line up."""

from __future__ import annotations

import re

import duckdb
import pandas as pd
import pytest

from src.clay import load_clay_export, mock_enricher
from src.clay.load_clay_export import normalize_domain
from src.config import load_settings, path
from src.generate import generate
from src.load import load_raw

EMAIL_RE = re.compile(r"^[a-z0-9_%+-]+(\.[a-z0-9_%+-]+)*@[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}$")


@pytest.fixture(scope="module")
def seed():
    generate.main()
    d = path("seed_dir")
    return {
        "accounts": pd.read_csv(d / "accounts.csv", dtype=str, keep_default_na=False),
        "contacts": pd.read_csv(d / "contacts.csv", dtype=str, keep_default_na=False),
        "events": pd.read_csv(d / "engagement_events.csv", dtype=str),
        "manifest": pd.read_csv(d / "planted_errors.csv", dtype=str, keep_default_na=False),
    }


def test_generator_is_deterministic(seed):
    first = seed["contacts"].copy()
    generate.main()
    second = pd.read_csv(path("seed_dir") / "contacts.csv", dtype=str, keep_default_na=False)
    pd.testing.assert_frame_equal(first, second)


def test_account_count_and_ids_unique(seed):
    cfg = load_settings()
    acc = seed["accounts"]
    assert len(acc) == cfg["generation"]["total_accounts"]
    assert acc["account_id"].is_unique
    assert acc["domain"].is_unique


def test_all_contact_emails_use_reserved_test_domain(seed):
    emails = seed["contacts"]["email"].str.strip().str.lower()
    # Fake people never get a deliverable domain, even at real companies.
    assert not emails.str.contains(r"\.(?:com|io|co|net|org|ai|so|us|tech)$").any()
    assert emails.str.endswith(".test").mean() > 0.95


def test_planted_counts_match_rates(seed):
    cfg = load_settings()
    rates = cfg["error_injection"]
    m = seed["manifest"]["error_type"].value_counts()
    n_original = len(seed["contacts"]) - m["duplicate_contact"]
    assert m["missing_title"] == round(n_original * rates["missing_titles"])
    assert m["invalid_email"] == round(n_original * rates["invalid_emails"])
    assert m["stale_record"] == round(n_original * rates["stale_records"])
    assert m["orphan_contact"] == round(n_original * rates["orphan_contacts"])
    assert m["duplicate_contact"] == round(n_original * rates["duplicate_contacts"])
    assert m["conflicting_industry"] == round(len(seed["accounts"]) * rates["conflicting_industry"])


def test_manifest_matches_data(seed):
    c = seed["contacts"].set_index("contact_id")
    m = seed["manifest"]
    for r in m[m.error_type == "missing_title"].itertuples():
        assert c.at[r.record_id, "title"] == ""
    for r in m[m.error_type == "invalid_email"].itertuples():
        assert not EMAIL_RE.match(c.at[r.record_id, "email"])
    account_ids = set(seed["accounts"]["account_id"])
    for r in m[m.error_type == "orphan_contact"].itertuples():
        assert c.at[r.record_id, "account_id"] not in account_ids
    for r in m[m.error_type == "duplicate_contact"].itertuples():
        assert r.related_record_id in c.index


def test_clean_emails_are_valid(seed):
    m = seed["manifest"]
    broken = set(m.loc[m.error_type == "invalid_email", "record_id"])
    dups = set(m.loc[m.error_type == "duplicate_contact", "record_id"])
    clean = seed["contacts"][~seed["contacts"]["contact_id"].isin(broken | dups)]
    assert clean["email"].map(lambda e: bool(EMAIL_RE.match(e))).all()


def test_event_types_are_known(seed):
    ev = seed["events"]
    assert set(ev["event_type"]) <= {"email_open", "web_visit", "reply", "meeting"}


@pytest.mark.parametrize(
    "raw,expected",
    [("https://www.Stripe.com/", "stripe.com"), ("  snowflake.com ", "snowflake.com"), ("", None)],
)
def test_normalize_domain(raw, expected):
    assert normalize_domain(raw) == expected


def test_raw_load_and_enrichment_join(seed):
    load_raw.main()
    mock_enricher.main()
    load_clay_export.main()
    con = duckdb.connect(str(path("warehouse")), read_only=True)
    n_contacts = con.execute("select count(*) from raw.raw_contacts").fetchone()[0]
    unmatched = con.execute(
        "select count(*) from raw.raw_clay_enrichment where record_id is null"
    ).fetchone()[0]
    mock_accounts = con.execute(
        "select count(distinct record_id) from raw.raw_clay_enrichment where provider = 'mock'"
    ).fetchone()[0]
    con.close()
    assert n_contacts == len(seed["contacts"])
    assert unmatched == 0
    assert mock_accounts == (seed["accounts"]["is_real_domain"] == "False").sum()
