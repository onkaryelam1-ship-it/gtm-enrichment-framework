-- Two-stage dedup.
--   1. Exact: same normalized email (lowercased, trimmed) = same person. The best
--      record in each group survives: has a title, most recently updated, lowest id.
--   2. Fuzzy (review only, never auto-merged): different emails at the same
--      account with the same last name and a near-identical first name.
with contacts as (
    select * from {{ ref('stg_contacts') }}
),

ranked as (
    select
        *,
        row_number() over (
            partition by email
            order by (title is null), source_updated_at desc, contact_id
        ) as rn,
        count(*) over (partition by email) as group_size
    from contacts
),

exact as (
    select
        r.*,
        first_value(contact_id) over (
            partition by email
            order by (title is null), source_updated_at desc, contact_id
        ) as survivor_contact_id
    from ranked r
),

survivors as (
    select * from exact where rn = 1
),

fuzzy_pairs as (
    select
        a.contact_id,
        min(b.contact_id) as possible_duplicate_of
    from survivors a
    join survivors b
      on a.account_id = b.account_id
     and a.contact_id > b.contact_id
     and a.email <> b.email
     and lower(a.last_name) = lower(b.last_name)
     and jaro_winkler_similarity(lower(a.first_name), lower(b.first_name)) >= 0.9
    group by 1
)

select
    e.* exclude (rn),
    e.rn = 1                                                   as is_survivor,
    case when e.group_size > 1 then 'exact_email' end          as match_rule,
    f.possible_duplicate_of
from exact e
left join fuzzy_pairs f using (contact_id)
