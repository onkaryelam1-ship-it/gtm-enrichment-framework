-- One row per (account, field) where the seed and the enrichment disagree,
-- with the value we kept and the rule that decided it.
select
    account_id,
    company_name,
    'industry'                  as field,
    seed_industry               as seed_value,
    industry_label              as enrichment_value,
    industry                    as resolved_value,
    industry_rule               as resolution_rule,
    enrichment_provider
from {{ ref('int_accounts_resolved') }}
where has_industry_conflict

union all

select
    account_id,
    company_name,
    'hq_country',
    hq_country,
    enriched_country,
    country,
    'seed_wins_curated_source',
    enrichment_provider
from {{ ref('int_accounts_resolved') }}
where has_country_conflict
