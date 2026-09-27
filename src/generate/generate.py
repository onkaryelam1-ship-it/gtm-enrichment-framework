"""Generate the simulated B2B dataset: accounts, contacts, engagement events.

Everything here is fake except the public company names/domains in companies.py.
Contacts use reserved `.test` email domains so they can never reach a real inbox.

Outputs (data/seed/):
    accounts.csv            one row per account, with simulated buying signals
    contacts.csv            contacts with planted data-quality problems
    engagement_events.csv   opens, web visits, replies, meetings (last 90 days)
    planted_errors.csv      manifest of every error injected on purpose
    _synthetic_truth.csv    oracle the mock enricher uses for synthetic accounts

Run:  python -m src.generate.generate
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import pandas as pd
from faker import Faker

from src.config import load_settings, path
from src.generate.companies import INDUSTRY_BUCKETS, REAL_COMPANIES

SENIORITY_WEIGHTS = {"IC": 0.35, "Manager": 0.30, "Director": 0.18, "VP": 0.12, "C-level": 0.05}
DEPARTMENTS = ["Data", "RevOps", "Sales", "Marketing", "Engineering", "Finance", "Operations"]

# Clean titles by (seniority, department). Noise is added separately so the
# dbt staging layer has real standardization work to do.
TITLES = {
    "IC": {
        "Data": ["Data Engineer", "Data Analyst", "Analytics Engineer"],
        "RevOps": ["Revenue Operations Analyst", "Sales Operations Specialist"],
        "Sales": ["Account Executive", "Sales Development Representative"],
        "Marketing": ["Marketing Specialist", "Growth Marketer"],
        "Engineering": ["Software Engineer", "Senior Software Engineer"],
        "Finance": ["Financial Analyst"],
        "Operations": ["Operations Analyst"],
    },
    "Manager": {
        "Data": ["Data Engineering Manager", "Analytics Manager"],
        "RevOps": ["Revenue Operations Manager"],
        "Sales": ["Sales Manager"],
        "Marketing": ["Marketing Manager"],
        "Engineering": ["Engineering Manager"],
        "Finance": ["Finance Manager"],
        "Operations": ["Operations Manager"],
    },
    "Director": {
        "Data": ["Director of Data", "Head of Data"],
        "RevOps": ["Director of Revenue Operations", "Head of RevOps"],
        "Sales": ["Director of Sales"],
        "Marketing": ["Director of Marketing"],
        "Engineering": ["Director of Engineering"],
        "Finance": ["Director of Finance"],
        "Operations": ["Director of Operations"],
    },
    "VP": {
        "Data": ["VP of Data"],
        "RevOps": ["VP of Revenue Operations"],
        "Sales": ["VP of Sales"],
        "Marketing": ["VP of Marketing"],
        "Engineering": ["VP of Engineering"],
        "Finance": ["VP of Finance"],
        "Operations": ["VP of Operations"],
    },
    "C-level": {
        "Data": ["Chief Data Officer"],
        "RevOps": ["Chief Revenue Officer"],
        "Sales": ["Chief Revenue Officer"],
        "Marketing": ["Chief Marketing Officer"],
        "Engineering": ["Chief Technology Officer"],
        "Finance": ["Chief Financial Officer"],
        "Operations": ["Chief Operating Officer"],
    },
}

EVENT_WEIGHTS = {"email_open": 0.55, "web_visit": 0.30, "reply": 0.10, "meeting": 0.05}


@dataclass
class Manifest:
    rows: list[dict] = field(default_factory=list)

    def add(self, error_type, table, record_id, fld, original, planted, related=None):
        self.rows.append(
            {
                "error_id": f"ERR-{len(self.rows) + 1:05d}",
                "error_type": error_type,
                "table_name": table,
                "record_id": record_id,
                "field": fld,
                "original_value": original,
                "planted_value": planted,
                "related_record_id": related,
            }
        )


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def noisy_title(title: str, rng: random.Random) -> str:
    """Return the title with realistic formatting noise ~20% of the time."""
    r = rng.random()
    if r < 0.05:
        return title.lower()
    if r < 0.10:
        return title.replace("Vice President", "VP").replace("VP of ", "VP, ")
    if r < 0.14:
        return title.replace("Senior", "Sr.").replace("Director of", "Dir.")
    if r < 0.20:
        return f"  {title} "
    return title


def ts(d: date | datetime) -> str:
    return d.isoformat(timespec="seconds") if isinstance(d, datetime) else d.isoformat()


def build_accounts(cfg: dict, rng: random.Random, fake: Faker, today: date):
    gen = cfg["generation"]
    n_total = gen["total_accounts"]
    real = REAL_COMPANIES[: gen["real_accounts_max"]]

    accounts, truth = [], []
    for name, domain, industry, country in real:
        accounts.append(
            {"company_name": name, "domain": domain, "seed_industry": industry,
             "hq_country": country, "is_real_domain": True, "source": "public_list"}
        )

    used = {slugify(a["company_name"]) for a in accounts}
    while len(accounts) < n_total:
        name = fake.company().replace(",", "")
        slug = slugify(name)
        if slug in used:
            continue
        used.add(slug)
        industry = rng.choice(INDUSTRY_BUCKETS)
        country = rng.choices(["US", "CA", "GB", "DE", "IN", "AU"], [70, 6, 8, 6, 6, 4])[0]
        domain = f"{slug[:24]}.example"
        accounts.append(
            {"company_name": name, "domain": domain, "seed_industry": industry,
             "hq_country": country, "is_real_domain": False, "source": "synthetic"}
        )
        truth.append(
            {"domain": domain, "industry": industry, "hq_country": country,
             "employee_count": int(rng.lognormvariate(5.5, 1.2)) + 5,
             "founded_year": rng.randint(1995, 2023)}
        )

    for i, a in enumerate(accounts, start=1):
        a["account_id"] = f"ACC-{i:05d}"
        a["source_updated_at"] = ts(today - timedelta(days=rng.randint(1, 150)))
        # Simulated buying signals (clearly labelled as simulated in the README)
        a["sim_hiring_data_roles"] = rng.random() < 0.30
        a["sim_months_since_funding"] = rng.choice([None, None, None, rng.randint(1, 36)])
        a["sim_tech_stack_match"] = rng.random() < 0.40

    cols = ["account_id", "company_name", "domain", "seed_industry", "hq_country",
            "is_real_domain", "source", "source_updated_at", "sim_hiring_data_roles",
            "sim_months_since_funding", "sim_tech_stack_match"]
    df = pd.DataFrame(accounts)[cols]
    df["sim_months_since_funding"] = df["sim_months_since_funding"].astype("Int64")
    return df, pd.DataFrame(truth)


def build_contacts(cfg: dict, accounts: pd.DataFrame, rng: random.Random, fake: Faker, today: date):
    rng_range = cfg["generation"]["contacts_per_account"]
    rows = []
    for acc in accounts.itertuples():
        stem = acc.domain.split(".")[0]
        for _ in range(rng.randint(rng_range["min"], rng_range["max"])):
            seniority = rng.choices(list(SENIORITY_WEIGHTS), list(SENIORITY_WEIGHTS.values()))[0]
            dept = rng.choice(DEPARTMENTS)
            first, last = fake.first_name(), fake.last_name()
            rows.append(
                {
                    "account_id": acc.account_id,
                    "first_name": first,
                    "last_name": last,
                    "email": f"{slugify(first)}.{slugify(last)}@{stem}.test",
                    "title": noisy_title(rng.choice(TITLES[seniority][dept]), rng),
                    "source_updated_at": ts(today - timedelta(days=rng.randint(1, 150))),
                }
            )
    df = pd.DataFrame(rows)
    df.insert(0, "contact_id", [f"CON-{i:06d}" for i in range(1, len(df) + 1)])
    return df


def inject_account_errors(accounts: pd.DataFrame, rates: dict, rng: random.Random, m: Manifest):
    n = round(len(accounts) * rates["conflicting_industry"])
    for idx in rng.sample(list(accounts.index), n):
        original = accounts.at[idx, "seed_industry"]
        planted = rng.choice([b for b in INDUSTRY_BUCKETS if b != original])
        accounts.at[idx, "seed_industry"] = planted
        m.add("conflicting_industry", "accounts", accounts.at[idx, "account_id"],
              "seed_industry", original, planted)
    return accounts


def inject_contact_errors(contacts: pd.DataFrame, rates: dict, rng: random.Random,
                          m: Manifest, today: date) -> pd.DataFrame:
    n = len(contacts)
    counts = {k: round(n * rates[k]) for k in
              ["missing_titles", "invalid_emails", "stale_records", "orphan_contacts", "duplicate_contacts"]}

    # Disjoint target sets so each planted error is attributable to one check.
    pool = list(contacts.index)
    rng.shuffle(pool)
    cursor = 0

    def take(k):
        nonlocal cursor
        chunk = pool[cursor: cursor + counts[k]]
        cursor += counts[k]
        return chunk

    for idx in take("missing_titles"):
        m.add("missing_title", "contacts", contacts.at[idx, "contact_id"], "title",
              contacts.at[idx, "title"], "")
        contacts.at[idx, "title"] = ""

    breakers = [
        lambda e: e.replace("@", ""),            # no @
        lambda e: e.replace("@", "@@"),          # double @
        lambda e: e.replace(".test", ""),        # no TLD
        lambda e: e.replace(".", " ", 1),        # space in local part
        lambda e: e.replace("@", ".@"),          # dot before @
    ]
    for idx in take("invalid_emails"):
        original = contacts.at[idx, "email"]
        planted = rng.choice(breakers)(original)
        contacts.at[idx, "email"] = planted
        m.add("invalid_email", "contacts", contacts.at[idx, "contact_id"], "email", original, planted)

    for idx in take("stale_records"):
        original = contacts.at[idx, "source_updated_at"]
        planted = ts(today - timedelta(days=rng.randint(400, 900)))
        contacts.at[idx, "source_updated_at"] = planted
        m.add("stale_record", "contacts", contacts.at[idx, "contact_id"], "source_updated_at",
              original, planted)

    for i, idx in enumerate(take("orphan_contacts"), start=1):
        original = contacts.at[idx, "account_id"]
        planted = f"ACC-9{i:04d}"
        contacts.at[idx, "account_id"] = planted
        m.add("orphan_contact", "contacts", contacts.at[idx, "contact_id"], "account_id",
              original, planted)

    # Duplicates: new rows copying a clean contact, with a realistic variation.
    dup_rows = []
    next_id = n + 1
    variations = ["email_case", "name_typo", "whitespace", "exact"]
    for idx in take("duplicate_contacts"):
        src = contacts.loc[idx].to_dict()
        kind = rng.choice(variations)
        dup = dict(src)
        if kind == "email_case":
            dup["email"] = src["email"].upper()
        elif kind == "name_typo" and len(src["first_name"]) > 3:
            f = src["first_name"]
            dup["first_name"] = f[:-2] + f[-1] + f[-2]  # swap last two letters
        elif kind == "whitespace":
            dup["email"] = f" {src['email']} "
            dup["last_name"] = f"{src['last_name']} "
        dup["contact_id"] = f"CON-{next_id:06d}"
        next_id += 1
        dup_rows.append(dup)
        m.add("duplicate_contact", "contacts", dup["contact_id"], kind, None, None,
              related=src["contact_id"])

    out = pd.concat([contacts, pd.DataFrame(dup_rows)], ignore_index=True)
    return out.sample(frac=1, random_state=rng.randint(0, 10_000)).reset_index(drop=True)


def build_engagement(contacts: pd.DataFrame, accounts: pd.DataFrame, cfg: dict,
                     rng: random.Random, today: date) -> pd.DataFrame:
    lookback = cfg["generation"]["engagement_lookback_days"]
    signal = accounts.set_index("account_id")[["sim_hiring_data_roles", "sim_tech_stack_match"]]
    events = []
    end = datetime.combine(today, datetime.min.time())
    for c in contacts.itertuples():
        boost = 1.0
        if c.account_id in signal.index:
            s = signal.loc[c.account_id]
            boost += 0.8 * bool(s.sim_hiring_data_roles) + 0.6 * bool(s.sim_tech_stack_match)
        n_events = min(int(rng.expovariate(1 / (1.2 * boost))), 15)
        replied = False
        for _ in range(n_events):
            etype = rng.choices(list(EVENT_WEIGHTS), list(EVENT_WEIGHTS.values()))[0]
            if etype == "meeting" and not replied:
                etype = "reply"
            replied = replied or etype == "reply"
            when = end - timedelta(minutes=rng.randint(0, lookback * 24 * 60))
            events.append({"contact_id": c.contact_id, "event_type": etype, "event_ts": ts(when)})
    df = pd.DataFrame(events).sort_values("event_ts").reset_index(drop=True)
    df.insert(0, "event_id", [f"EVT-{i:07d}" for i in range(1, len(df) + 1)])
    return df


def main() -> dict:
    cfg = load_settings()
    seed = cfg["random_seed"]
    rng = random.Random(seed)
    fake = Faker("en_US")
    Faker.seed(seed)
    today = date.fromisoformat(cfg["generation"]["reference_date"])
    rates = cfg["error_injection"]
    manifest = Manifest()

    accounts, truth = build_accounts(cfg, rng, fake, today)
    contacts = build_contacts(cfg, accounts, rng, fake, today)
    accounts = inject_account_errors(accounts, rates, rng, manifest)
    contacts = inject_contact_errors(contacts, rates, rng, manifest, today)
    events = build_engagement(contacts, accounts, cfg, rng, today)

    out = path("seed_dir")
    accounts.to_csv(out / "accounts.csv", index=False)
    contacts.to_csv(out / "contacts.csv", index=False)
    events.to_csv(out / "engagement_events.csv", index=False)
    pd.DataFrame(manifest.rows).to_csv(out / "planted_errors.csv", index=False)
    truth.to_csv(out / "_synthetic_truth.csv", index=False)

    summary = {
        "accounts": len(accounts),
        "real_domain_accounts": int(accounts["is_real_domain"].sum()),
        "contacts": len(contacts),
        "engagement_events": len(events),
        "planted_errors": len(manifest.rows),
    }
    print("Seed data written to", out)
    for k, v in summary.items():
        print(f"  {k:<22} {v:>6}")
    print(pd.DataFrame(manifest.rows)["error_type"].value_counts().to_string())
    return summary


if __name__ == "__main__":
    main()
