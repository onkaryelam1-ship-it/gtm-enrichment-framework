-- Clean account dimension: one row per account with resolved firmographics.
select
    account_id,
    company_name,
    domain,
    is_real_domain,
    industry,
    industry_label                          as provider_industry_label,
    industry_rule,
    country,
    employee_count,
    size_band,
    founded_year,
    description,
    case
        when not has_enrichment then 'missing'
        else enrichment_provider
    end                                     as enrichment_status,
    enriched_at,
    coalesce(is_stale_enrichment, false)    as is_stale_enrichment,
    has_industry_conflict,
    has_country_conflict,
    is_suspected_wrong_entity,
    has_headcount_band_mismatch,
    sim_hiring_data_roles,
    sim_months_since_funding,
    sim_tech_stack_match
from {{ ref('int_accounts_resolved') }}
