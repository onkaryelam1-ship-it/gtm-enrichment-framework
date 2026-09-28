"""Custom attributes and the Prospects list this project needs in Attio.

`ensure_schema` is idempotent: it only creates what is missing, so it is safe to
run on every sync. Every custom field uses a `gtm_` prefix so it can never clash
with Attio's built-in attributes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

INDUSTRIES = [
    "Software", "Data & Analytics", "Cybersecurity", "Fintech", "Healthcare",
    "Marketing Tech", "Sales Tech", "HR Tech", "E-commerce & Retail", "Logistics",
    "Developer Tools", "Media",
]
PERSONAS = ["Data/RevOps leader", "Data/RevOps practitioner", "Executive", "Other", "Unknown"]
SENIORITIES = ["IC", "Manager", "Director", "VP", "C-level"]
TIERS = ["A", "B", "C"]
STAGES = ["New", "Engaged", "Replied", "Meeting booked"]
SOURCES = ["clay", "mock", "missing"]

LIST_SLUG = "gtm_prospects"
LIST_NAME = "GTM Prospects (Tier A and B)"


@dataclass
class Attr:
    slug: str
    title: str
    type: str                      # text | number | select
    options: list[str] = field(default_factory=list)
    unique: bool = False
    description: str = ""


COMPANY_ATTRS = [
    Attr("gtm_account_id", "GTM account ID", "text", unique=True,
         description="External ID from the GTM pipeline; used as the upsert key."),
    Attr("gtm_fit_score", "GTM fit score", "number", description="ICP fit, 0-100."),
    Attr("gtm_industry", "GTM industry", "select", INDUSTRIES,
         description="Resolved industry bucket (seed vs enrichment)."),
    Attr("gtm_enrichment_source", "GTM enrichment source", "select", SOURCES),
    Attr("gtm_dq_flags", "GTM data-quality flags", "text"),
]

PEOPLE_ATTRS = [
    Attr("gtm_contact_id", "GTM contact ID", "text", unique=True,
         description="External ID from the GTM pipeline; used as the upsert key."),
    Attr("gtm_priority_score", "GTM priority score", "number", description="0-100."),
    Attr("gtm_tier", "GTM tier", "select", TIERS),
    Attr("gtm_persona", "GTM persona", "select", PERSONAS),
    Attr("gtm_seniority", "GTM seniority", "select", SENIORITIES),
]

LIST_ATTRS = [
    Attr("gtm_stage", "Stage", "select", STAGES),
    Attr("gtm_tier", "Tier", "select", TIERS),
    Attr("gtm_priority_score", "Priority score", "number"),
    Attr("gtm_segment", "Segment", "text"),
]


def _ensure_attrs(client, target: str, identifier: str, attrs: list[Attr], log) -> None:
    existing = {a["api_slug"] for a in client.request(
        "GET", f"/{target}/{identifier}/attributes")["data"]}
    for a in attrs:
        if a.slug not in existing:
            client.request("POST", f"/{target}/{identifier}/attributes", json={"data": {
                "title": a.title,
                "description": a.description or None,
                "api_slug": a.slug,
                "type": a.type,
                "is_required": False,
                "is_unique": a.unique,
                "is_multiselect": False,
                "config": {},
            }})
            log(f"  created attribute {identifier}.{a.slug}")
        if a.options:
            path = f"/{target}/{identifier}/attributes/{a.slug}/options"
            have = {o["title"] for o in client.request("GET", path)["data"]}
            for opt in a.options:
                if opt not in have:
                    client.request("POST", path, json={"data": {"title": opt}})
            if set(a.options) - have:
                log(f"  added {len(set(a.options) - have)} option(s) to {identifier}.{a.slug}")


def ensure_schema(client, log=print) -> None:
    log("Checking Attio schema...")
    _ensure_attrs(client, "objects", "companies", COMPANY_ATTRS, log)
    _ensure_attrs(client, "objects", "people", PEOPLE_ATTRS, log)
    lists = {x["api_slug"] for x in client.request("GET", "/lists")["data"]}
    if LIST_SLUG not in lists:
        client.request("POST", "/lists", json={"data": {
            "name": LIST_NAME,
            "api_slug": LIST_SLUG,
            "parent_object": "people",
            "workspace_access": "full-access",
            "workspace_member_access": [],
        }})
        log(f"  created list {LIST_SLUG}")
    _ensure_attrs(client, "lists", LIST_SLUG, LIST_ATTRS, log)
    log("Schema ready.")
