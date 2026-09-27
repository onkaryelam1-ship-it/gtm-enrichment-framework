-- Every error the generator planted, and whether the matching check caught it.
with planted as (
    select
        error_id,
        error_type,
        record_id,
        field,
        original_value,
        planted_value,
        case error_type
            when 'invalid_email'        then 'invalid_email'
            when 'missing_title'        then 'missing_title'
            when 'stale_record'         then 'stale_contact'
            when 'orphan_contact'       then 'orphan_contact'
            when 'duplicate_contact'    then 'duplicate_contact'
            when 'conflicting_industry' then 'industry_conflict'
        end as expected_check
    from {{ source('raw', 'planted_errors') }}
)

select
    p.*,
    a.industry_label                                           as enrichment_industry_label,
    -- a planted industry conflict is only detectable when the provider returned a
    -- specific label; blank or generic labels can't contradict anything
    case when p.error_type = 'conflicting_industry'
         then a.industry_label is not null and not a.label_is_generic
    end                                                        as is_detectable,
    exists (
        select 1 from {{ ref('dq_failures') }} f
        where f.check_name = p.expected_check and f.record_id = p.record_id
    )                                                          as was_caught
from planted p
left join {{ ref('int_accounts_resolved') }} a
  on p.error_type = 'conflicting_industry' and a.account_id = p.record_id
