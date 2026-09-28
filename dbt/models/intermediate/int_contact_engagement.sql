-- Engagement (0-100) per contact: recent activity counts more.
-- Points per event (meeting 80, reply 50, web visit 15, email open 8), halved every
-- `engagement_half_life_days` days of age, summed and capped at 100.
with events as (
    select
        contact_id,
        event_type,
        date_diff('day', cast(event_ts as date), date '{{ var("reference_date") }}') as age_days
    from {{ ref('fct_engagement') }}
),

scored as (
    select
        contact_id,
        event_type,
        case event_type
            when 'meeting' then 80 when 'reply' then 50
            when 'web_visit' then 15 when 'email_open' then 8 else 0
        end * pow(0.5, age_days / {{ var('engagement_half_life_days') }}) as pts
    from events
)

select
    c.contact_id,
    least(100, round(coalesce(sum(s.pts), 0), 1))                  as engagement_score,
    count(s.contact_id)                                            as events_90d,
    count(*) filter (where s.event_type = 'reply')                 as replies,
    count(*) filter (where s.event_type = 'meeting')               as meetings,
    count(*) filter (where s.event_type in ('email_open', 'web_visit')) as touches
from {{ ref('dim_contact') }} c
left join scored s using (contact_id)
group by 1
