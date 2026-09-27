-- Clean contact dimension: deduplicated survivors only, with quarantined records
-- (invalid email, unknown account) removed. Softer problems stay as flags.
with deduped as (
    select * from {{ ref('int_contacts_deduped') }}
),

merged as (
    select
        survivor_contact_id,
        list(contact_id order by contact_id) filter (where not is_survivor) as merged_contact_ids
    from deduped
    group by 1
)

select
    d.contact_id,
    d.account_id,
    d.first_name,
    d.last_name,
    d.full_name,
    d.email,
    d.title,
    d.seniority,
    d.department,
    case
        when d.department in ('Data', 'RevOps') and d.seniority in ('Director', 'VP', 'C-level')
            then 'Data/RevOps leader'
        when d.department in ('Data', 'RevOps') then 'Data/RevOps practitioner'
        when d.seniority in ('VP', 'C-level') then 'Executive'
        when d.seniority is null then 'Unknown'
        else 'Other'
    end                                     as persona,
    d.title is null                         as is_missing_title,
    d.is_stale,
    d.possible_duplicate_of,
    coalesce(m.merged_contact_ids, [])      as merged_contact_ids,
    d.source_updated_at
from deduped d
join {{ ref('dim_account') }} a using (account_id)
left join merged m on m.survivor_contact_id = d.contact_id
where d.is_survivor
  and d.is_valid_email
