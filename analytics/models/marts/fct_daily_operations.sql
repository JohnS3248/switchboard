-- One row per day: how many events came in, how many reached the downstream workflow, how many needed retries,
-- the slow tail, and how many changes the agent wrote. A day under 85% delivery is flagged as an incident.
with events as (
    select * from {{ ref('stg_events') }}
),

writebacks as (
    select written_date, count(*) as writebacks
    from {{ ref('stg_writebacks') }}
    group by 1
),

daily as (
    select
        received_date                                           as ops_date,
        count(*)                                                as events,
        count(*) filter (where outcome = 'delivered')           as delivered,
        count(*) filter (where outcome = 'failed')              as failed,
        count(*) filter (where outcome = 'rejected')            as rejected,
        count(*) filter (where was_retried)                     as retried,
        round(quantile_cont(latency_ms, 0.5), 1)                as p50_latency_ms,
        round(quantile_cont(latency_ms, 0.95), 1)               as p95_latency_ms
    from events
    group by 1
)

select
    daily.*,
    round(delivered / events, 4)                                as delivery_rate,
    coalesce(writebacks.writebacks, 0)                          as agent_writebacks,
    delivered / events < 0.85                                   as is_incident_day
from daily
left join writebacks on writebacks.written_date = daily.ops_date
order by ops_date
