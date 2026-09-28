"""Custom attributes and the Prospects list this project needs in Attio.

`ensure_schema` is idempotent: it only creates what is missing, so it is safe to
run on every sync. Every custom field uses a `gtm_` prefix so it can never clash
with Attio's built-in attributes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.attio.client import AttioError

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


def _create_attr(client, target, identifier, a: Attr, unique: bool) -> None:
    client.request("POST", f"/{target}/{identifier}/attributes", json={"data": {
        "title": a.title,
        "description": a.description or None,
        "api_slug": a.slug,
        "type": a.type,
        "is_required": False,
        "is_unique": unique,
        "is_multiselect": False,
        "config": {},
    }})


def _ensure_attrs(client, target: str, identifier: str, attrs: list[Attr], log) -> dict:
    """Create missing attributes and options. Returns {slug: is_unique} for all attrs."""
    existing = {a["api_slug"]: bool(a.get("is_unique")) for a in client.request(
        "GET", f"/{target}/{identifier}/attributes")["data"]}
    for a in attrs:
        if a.slug not in existing:
            try:
                _create_attr(client, target, identifier, a, a.unique)
                existing[a.slug] = a.unique
            except AttioError as e:
                # Some workspaces don't allow unique custom attributes via the API.
                # Fall back to a normal attribute; the sync then finds records by
                # this id before creating, so there is still one record per id.
                if not (a.unique and e.status == 400 and "unique" in e.message.lower()):
                    raise
                _create_attr(client, target, identifier, a, False)
                existing[a.slug] = False
                log(f"  note: {identifier}.{a.slug} can't be unique here; using find-then-upsert")
            log(f"  created attribute {identifier}.{a.slug}")
        if a.options:
            path = f"/{target}/{identifier}/attributes/{a.slug}/options"
            have = {o["title"] for o in client.request("GET", path)["data"]}
            for opt in a.options:
                if opt not in have:
                    client.request("POST", path, json={"data": {"title": opt}})
            if set(a.options) - have:
                log(f"  added {len(set(a.options) - have)} option(s) to {identifier}.{a.slug}")
    return existing


def ensure_schema(client, log=print, create: bool = True) -> dict:
    """Create whatever is missing. Returns whether each object's GTM id is unique:
    {"companies": bool, "people": bool}. With create=False, only reads."""
    if not create:
        read = lambda obj: {a["api_slug"]: bool(a.get("is_unique")) for a in
                            client.request("GET", f"/objects/{obj}/attributes")["data"]}
        return {"companies": read("companies").get("gtm_account_id", False),
                "people": read("people").get("gtm_contact_id", False)}
    log("Checking Attio schema...")
    companies = _ensure_attrs(client, "objects", "companies", COMPANY_ATTRS, log)
    people = _ensure_attrs(client, "objects", "people", PEOPLE_ATTRS, log)
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
    unique = {"companies": companies["gtm_account_id"], "people": people["gtm_contact_id"]}
    log(f"Schema ready. Match mode: {'unique-id upsert' if all(unique.values()) else 'find-then-upsert'}.")
    return unique
