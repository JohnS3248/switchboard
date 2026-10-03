-- The agent's audited write-backs, tagged with the kind of record they touched.
select
    id                                                  as writeback_id,
    record_id,
    case when record_id like 'O-%' then 'order' else 'customer' end as record_type,
    field,
    old_value,
    new_value,
    reason,
    cast("at" as timestamp)                             as written_at,
    cast(cast("at" as timestamp) as date)               as written_date
from {{ source('ops', 'writeback_log') }}
