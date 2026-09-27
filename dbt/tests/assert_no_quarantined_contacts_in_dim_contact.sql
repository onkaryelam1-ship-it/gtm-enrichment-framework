-- Nothing routed to quarantine may appear in the clean contact dimension.
select c.contact_id, f.check_name
from {{ ref('dim_contact') }} c
join {{ ref('dq_failures') }} f
  on f.record_id = c.contact_id and f.action in ('quarantine', 'merge')
