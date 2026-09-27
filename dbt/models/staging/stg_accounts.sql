-- One row per account, typed and standardized. No rows are dropped here.
select
    account_id,
    trim(company_name)                                         as company_name,
    lower(regexp_replace(trim(domain), '^(https?://)?(www\.)?', '')) as domain,
    seed_industry,
    upper(trim(hq_country))                                    as hq_country,
    is_real_domain = 'True'                                    as is_real_domain,
    source,
    cast(source_updated_at as date)                            as source_updated_at,
    sim_hiring_data_roles = 'True'                             as sim_hiring_data_roles,
    try_cast(sim_months_since_funding as integer)              as sim_months_since_funding,
    sim_tech_stack_match = 'True'                              as sim_tech_stack_match
from {{ source('raw', 'raw_accounts') }}
