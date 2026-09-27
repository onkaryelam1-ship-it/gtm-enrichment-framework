"""Week 2 tests: the full pipeline builds, the rule-based checks catch every planted
error, and the clean marts contain nothing that should have been quarantined.

Runs against a throwaway warehouse (GTM_WAREHOUSE) so it never touches your real one.
"""

from __future__ import annotations

import os
import subprocess

import duckdb
import pytest

from src.clay import load_clay_export, mock_enricher
from src.config import ROOT
from src.generate import generate
from src.load import load_raw


@pytest.fixture(scope="module")
def warehouse(tmp_path_factory):
    db = tmp_path_factory.mktemp("wh") / "test.duckdb"
    old = os.environ.get("GTM_WAREHOUSE")
    os.environ["GTM_WAREHOUSE"] = str(db)
    try:
        generate.main()
        load_raw.main()
        mock_enricher.main()
        load_clay_export.main()
        result = subprocess.run(
            ["dbt", "build", "--full-refresh", "--project-dir", "dbt", "--profiles-dir", "dbt"],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        assert result.returncode == 0, result.stdout[-3000:]
        con = duckdb.connect(str(db), read_only=True)
        yield con
        con.close()
    finally:
        if old is None:
            os.environ.pop("GTM_WAREHOUSE", None)
        else:
            os.environ["GTM_WAREHOUSE"] = old


def one(con, sql):
    return con.execute(sql).fetchone()


def test_rule_based_checks_catch_every_planted_error(warehouse):
    rows = warehouse.execute("""
        select expected_check, planted, caught
        from quality.dq_planted_vs_caught
        where expected_check <> 'industry_conflict'
    """).fetchall()
    assert len(rows) == 5
    for check, planted, caught in rows:
        assert caught == planted, f"{check}: caught {caught} of {planted}"


def test_detectable_industry_conflicts_are_caught(warehouse):
    detectable, caught = one(warehouse, """
        select detectable, caught from quality.dq_planted_vs_caught
        where expected_check = 'industry_conflict'
    """)
    assert caught == detectable


def test_no_false_alarms_on_clean_contacts(warehouse):
    # every contact failure must trace back to a planted error
    unexplained = one(warehouse, """
        select count(*) from quality.dq_failures f
        where f.entity = 'contact'
          and f.check_name in ('invalid_email', 'missing_title', 'stale_contact',
                               'orphan_contact', 'duplicate_contact')
          and f.record_id not in (select record_id from raw.planted_errors)
    """)[0]
    assert unexplained == 0


def test_dim_contact_is_clean(warehouse):
    total, distinct_emails, bad = one(warehouse, """
        select count(*), count(distinct email),
               count(*) filter (where not regexp_full_match(email,
                 '^[a-z0-9_%+-]+(\\.[a-z0-9_%+-]+)*@[a-z0-9-]+(\\.[a-z0-9-]+)*\\.[a-z]{2,}$'))
        from marts.dim_contact
    """)
    assert total == distinct_emails
    assert bad == 0


def test_dim_contact_row_count_is_explained(warehouse):
    raw, clean = one(warehouse, "select (select count(*) from raw.raw_contacts), "
                                "(select count(*) from marts.dim_contact)")
    removed = one(warehouse, """
        select count(distinct record_id) from quality.dq_failures
        where action in ('quarantine', 'merge')
    """)[0]
    assert clean == raw - removed


def test_every_account_has_an_industry(warehouse):
    assert one(warehouse, "select count(*) from marts.dim_account where industry is null")[0] == 0


def test_real_accounts_without_clay_are_queued(warehouse):
    queued = one(warehouse, """
        select count(*) from quality.dq_failures where check_name = 'missing_enrichment'
    """)[0]
    unenriched_real = one(warehouse, """
        select count(*) from marts.dim_account
        where is_real_domain and enrichment_status = 'missing'
    """)[0]
    assert queued == unenriched_real


def test_titles_are_fully_parsed(warehouse):
    unparsed = one(warehouse, """
        select count(*) from staging.stg_contacts
        where title is not null and (seniority is null or department is null)
    """)[0]
    assert unparsed == 0
