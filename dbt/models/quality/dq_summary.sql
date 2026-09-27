-- Pass rate per check, against the number of records that check looks at.
with failures as (
    select check_name, entity, any_value(severity) as severity, any_value(action) as action,
           count(distinct record_id) as rows_failed
    from {{ ref('dq_failures') }}
    group by 1, 2
),

checks as (
    -- every check appears even when nothing failed
    select * from (values
        ('invalid_email', 'contact'), ('orphan_contact', 'contact'),
        ('duplicate_contact', 'contact'), ('possible_duplicate', 'contact'),
        ('missing_title', 'contact'), ('unmapped_title', 'contact'),
        ('stale_contact', 'contact'), ('missing_enrichment', 'account'),
        ('stale_enrichment', 'account'), ('missing_industry', 'account'),
        ('missing_employee_count', 'account'), ('unmapped_industry_label', 'account'),
        ('industry_conflict', 'account'), ('country_conflict', 'account'),
        ('suspected_wrong_entity', 'account'),
        ('headcount_band_mismatch', 'account')
    ) as t(check_name, entity)
),

totals as (
    select 'contact' as entity, count(*) as rows_tested from {{ ref('stg_contacts') }}
    union all
    select 'account', count(*) from {{ ref('stg_accounts') }}
)

select
    c.check_name,
    c.entity,
    coalesce(f.severity, '-')                               as severity,
    coalesce(f.action, '-')                                 as action,
    t.rows_tested,
    coalesce(f.rows_failed, 0)                              as rows_failed,
    round(100.0 * (t.rows_tested - coalesce(f.rows_failed, 0)) / t.rows_tested, 1) as pass_rate_pct
from checks c
join totals t using (entity)
left join failures f using (check_name, entity)
order by c.entity desc, rows_failed desc
