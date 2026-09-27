PY ?= python3

.PHONY: help setup seed load clay-export mock-enrich clay-load week1 transform dq-report week2 all docs test lint clean

help:
	@echo "make setup        install Python dependencies"
	@echo "make seed         generate synthetic accounts, contacts, engagement (+ planted errors)"
	@echo "make load         load seed CSVs into DuckDB raw schema"
	@echo "make clay-export  write Clay-ready CSV batches of real-domain accounts"
	@echo "make mock-enrich  enrich synthetic accounts with the schema-matched mock enricher"
	@echo "make clay-load    load Clay export CSVs (data/clay_exports) into raw_clay_enrichment"
	@echo "make week1        seed + load + clay-export + mock-enrich + clay-load"
	@echo "make transform    dbt build: seeds, staging, dedup, marts, quality checks, tests"
	@echo "make dq-report    write docs/dq_report.md (planted vs caught, all checks)"
	@echo "make week2        transform + dq-report"
	@echo "make all          week1 + week2"
	@echo "make docs         open dbt docs (lineage graph) at http://localhost:8080"
	@echo "make test         run pytest"
	@echo "make lint         run ruff"

setup:
	$(PY) -m pip install -r requirements.txt

seed:
	$(PY) -m src.generate.generate

load:
	$(PY) -m src.load.load_raw

clay-export:
	$(PY) -m src.clay.export_for_clay

mock-enrich:
	$(PY) -m src.clay.mock_enricher

clay-load:
	$(PY) -m src.clay.load_clay_export

week1: seed load clay-export mock-enrich clay-load

DBT = dbt --no-use-colors
DBT_ARGS = --project-dir dbt --profiles-dir dbt

transform:
	$(DBT) build --full-refresh $(DBT_ARGS)

dq-report:
	$(PY) -m src.validation.report

week2: transform dq-report

all: week1 week2

docs:
	$(DBT) docs generate $(DBT_ARGS) && $(DBT) docs serve $(DBT_ARGS)

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check src tests

clean:
	rm -f data/seed/*.csv data/clay_imports/*.csv data/warehouse/*.duckdb
