"""Schema-matched mock enricher for the synthetic accounts.

Clay can only enrich real domains (and the free plan caps credits), so the
synthetic `.example` accounts are enriched here instead. The output uses the
SAME column names as a Clay export (the keys of `clay.column_map`), so both
flow through one loader and one set of dbt models.

To keep the downstream checks honest, the mock provider behaves like a real one:
    * industries come back as LinkedIn-style labels, not our 12 buckets
    * ~3% of rows have no industry, ~4% have no employee count
    * ~5% of rows were "enriched" more than 90 days ago (stale enrichment)
    * headcounts carry +/-15% noise

Run:  python -m src.clay.mock_enricher
"""

from __future__ import annotations

import random
from datetime import date, timedelta

import pandas as pd

from src.config import load_settings, path

# One or more provider-style labels per internal bucket. dbt maps them back.
PROVIDER_LABELS = {
    "Software": ["Software Development", "Computer Software"],
    "Data & Analytics": ["Data Infrastructure and Analytics", "Information Technology & Services"],
    "Cybersecurity": ["Computer and Network Security"],
    "Fintech": ["Financial Services", "Banking"],
    "Healthcare": ["Hospitals and Health Care", "Health, Wellness & Fitness"],
    "Marketing Tech": ["Marketing Services", "Advertising Services"],
    "Sales Tech": ["Software Development"],
    "HR Tech": ["Human Resources Services", "Staffing and Recruiting"],
    "E-commerce & Retail": ["Retail", "Internet Marketplace Platforms"],
    "Logistics": ["Transportation, Logistics, Supply Chain and Storage"],
    "Developer Tools": ["Software Development", "IT Services and IT Consulting"],
    "Media": ["Online Audio and Video Media", "Entertainment Providers"],
}

MOCK_FILE = "mock_synthetic_accounts.csv"


def main() -> int:
    cfg = load_settings()
    rng = random.Random(cfg["random_seed"] + 1)
    today = date.fromisoformat(cfg["generation"]["reference_date"])
    truth = pd.read_csv(path("seed_dir") / "_synthetic_truth.csv")
    cols = list(cfg["clay"]["column_map"])  # Clay-style export headers

    rows = []
    for t in truth.itertuples():
        industry = rng.choice(PROVIDER_LABELS[t.industry])
        headcount = int(t.employee_count * rng.uniform(0.85, 1.15))
        if rng.random() < 0.03:
            industry = None
        if rng.random() < 0.04:
            headcount = None
        age_days = rng.randint(100, 240) if rng.random() < 0.05 else rng.randint(0, 30)
        values = [t.domain, industry, headcount, t.hq_country, t.founded_year]
        row = dict(zip(cols, values))
        row["Enriched At"] = (today - timedelta(days=age_days)).isoformat()
        rows.append(row)

    df = pd.DataFrame(rows)
    df[cols[2]] = df[cols[2]].astype("Int64")
    out = path("clay_export_dir") / MOCK_FILE
    df.to_csv(out, index=False)
    print(f"Mock-enriched {len(df)} synthetic accounts -> {out}")
    return len(df)


if __name__ == "__main__":
    main()
