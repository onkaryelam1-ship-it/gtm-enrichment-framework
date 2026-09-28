-- One row per clean contact with the four score parts, the weighted priority score,
-- a tier, a segment, and a pipeline stage derived from engagement.
with c as (select * from {{ ref('dim_contact') }}),
     a as (select * from {{ ref('dim_account') }}),
     fit as (select * from {{ ref('int_account_fit') }}),
     eng as (select * from {{ ref('int_contact_engagement') }}),

role as (
    select
        contact_id,
        case
            when seniority is null then 10
            when department in ('Data', 'RevOps') then
                case seniority when 'VP' then 100 when 'Director' then 100
                               when 'C-level' then 90 when 'Manager' then 70 else 40 end
            else
                case seniority when 'C-level' then 60 when 'VP' then 60
                               when 'Director' then 50 when 'Manager' then 35 else 15 end
        end as role_score
    from c
),

scored as (
    select
        c.contact_id,
        c.account_id,
        c.full_name,
        c.first_name,
        c.last_name,
        c.email,
        c.title,
        c.seniority,
        c.department,
        c.persona,
        c.is_missing_title,
        c.is_stale,
        a.company_name,
        a.domain,
        a.industry,
        a.employee_count,
        a.country,
        a.enrichment_status,
        a.description                                   as company_description,
        fit.fit_score,
        role.role_score,
        eng.engagement_score,
        fit.intent_score,
        eng.events_90d,
        eng.replies,
        eng.meetings,
        round(
            {{ var('w_fit') }} * fit.fit_score
            + {{ var('w_role') }} * role.role_score
            + {{ var('w_engagement') }} * eng.engagement_score
            + {{ var('w_intent') }} * fit.intent_score
        , 1)                                            as priority_score
    from c
    join a using (account_id)
    join fit using (account_id)
    join role using (contact_id)
    join eng using (contact_id)
)

select
    *,
    case
        when priority_score >= {{ var('tier_a_min') }} then 'A'
        when priority_score >= {{ var('tier_b_min') }} then 'B'
        else 'C'
    end                                                 as tier,
    case
        when meetings > 0 then 'Meeting booked'
        when replies > 0 then 'Replied'
        when events_90d > 0 then 'Engaged'
        else 'New'
    end                                                 as stage,
    rank() over (order by priority_score desc)          as priority_rank
from scored
