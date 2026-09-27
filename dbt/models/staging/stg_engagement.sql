select
    event_id,
    contact_id,
    event_type,
    cast(event_ts as timestamp) as event_ts
from {{ source('raw', 'raw_engagement') }}
