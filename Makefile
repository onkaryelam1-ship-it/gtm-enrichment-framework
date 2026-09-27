PY ?= python3

.PHONY: help setup seed load clay-export mock-enrich clay-load week1 test lint clean

help:
	@echo "make setup        install Python dependencies"
	@echo "make seed         generate synthetic accounts, contacts, engagement (+ planted errors)"
	@echo "make load         load seed CSVs into DuckDB raw schema"
	@echo "make clay-export  write Clay-ready CSV batches of real-domain accounts"
	@echo "make mock-enrich  enrich synthetic accounts with the schema-matched mock enricher"
	@echo "make clay-load    load Clay export CSVs (data/clay_exports) into raw_clay_enrichment"
	@echo "make week1        seed + load + clay-export + mock-enrich + clay-load"
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

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check src tests

clean:
	rm -f data/seed/*.csv data/clay_imports/*.csv data/warehouse/*.duckdb
