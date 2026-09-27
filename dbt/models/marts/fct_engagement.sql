-- Engagement events re-pointed at the surviving contact after dedup, limited to
-- contacts that made it into dim_contact.
select
    e.event_id,
    d.survivor_contact_id   as contact_id,
    e.event_type,
    e.event_ts
from {{ ref('stg_engagement') }} e
join {{ ref('int_contacts_deduped') }} d on d.contact_id = e.contact_id
join {{ ref('dim_contact') }} c on c.contact_id = d.survivor_contact_id
