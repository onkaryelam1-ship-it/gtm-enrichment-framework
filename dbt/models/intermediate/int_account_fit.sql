-- Account fit (0-100): how closely a company matches the ideal customer profile.
--   industry 50% : ICP bucket 100, adjacent 60, other 20
--   size     35% : 200-2,000 employees 100, 50-199 or 2,001-10,000 60, else/unknown 30
--   country  15% : US/CA/GB 100, elsewhere 50
with a as (
    select * from {{ ref('dim_account') }}
),

parts as (
    select
        account_id,
        case
            when industry in {{ sql_list(var('icp_industries')) }} then 100
            when industry in {{ sql_list(var('adjacent_industries')) }} then 60
            else 20
        end as industry_pts,
        case
            when employee_count between 200 and 2000 then 100
            when employee_count between 50 and 199 or employee_count between 2001 and 10000 then 60
            else 30
        end as size_pts,
        case when country in ('US', 'CA', 'GB') then 100 else 50 end as country_pts,
        (sim_hiring_data_roles::int
         + coalesce(sim_months_since_funding <= 12, false)::int
         + sim_tech_stack_match::int) as intent_signals
    from a
)

select
    account_id,
    industry_pts,
    size_pts,
    country_pts,
    round(0.50 * industry_pts + 0.35 * size_pts + 0.15 * country_pts, 1) as fit_score,
    intent_signals,
    round(100.0 * intent_signals / 3, 1)                                  as intent_score
from parts
