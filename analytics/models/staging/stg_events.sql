-- One row per inbound event, with the JSON body unpacked and the outcome reduced to a few categories.
-- Times are kept in UTC so a day means the same thing wherever the report is run.
with source as (
    select * from {{ source('ops', 'events') }}
)

select
    idem_key                                                    as event_id,
    source                                                      as event_source,
    to_timestamp(received_at) at time zone 'UTC'                as received_at,
    cast(to_timestamp(received_at) at time zone 'UTC' as date)  as received_date,
    status                                                      as raw_status,
    case
        when status = 'forwarded'         then 'delivered'
        when status like 'failed:%'       then 'failed'
        when status like 'rejected:%'     then 'rejected'
        else 'unknown'
    end                                                         as outcome,
    nullif(split_part(status, ':', 2), '')                      as failure_reason,
    retries,
    retries > 0                                                 as was_retried,
    latency_ms,
    json_extract_string(body, '$.event_type')                   as event_type,
    lower(json_extract_string(body, '$.customer'))              as customer_email,
    nullif(regexp_extract(json_extract_string(body, '$.text'), 'O-[0-9]{4}'), '') as order_id
from source
