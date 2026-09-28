"""Shared fixture: build the full pipeline once into a throwaway warehouse."""

from __future__ import annotations

import os
import subprocess

import pytest

from src.clay import load_clay_export, mock_enricher
from src.config import ROOT
from src.generate import generate
from src.load import load_raw


@pytest.fixture(scope="session")
def built_warehouse(tmp_path_factory):
    """Path to a warehouse built by week 1 + dbt build. Never touches data/warehouse."""
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
    finally:
        if old is None:
            os.environ.pop("GTM_WAREHOUSE", None)
        else:
            os.environ["GTM_WAREHOUSE"] = old
    return db
