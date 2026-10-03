-- Customers whose requests failed or were rejected in the period: what was hit, when, which orders are still open,
-- and whether a later request from them got through. Sorted so the unrecovered, highest-tier customers come first.
with events as (
    select * from {{ ref('stg_events') }}
),

customers as (
    select * from {{ ref('stg_customers') }}
),

open_orders as (
    select customer_id, count(*) as open_orders, sum(amount) as open_order_value
    from {{ ref('stg_orders') }}
    where order_status in ('processing', 'shipped')
    group by 1
),

problems as (
    select
        customer_email,
        count(*) filter (where outcome = 'failed')      as failed_events,
        count(*) filter (where outcome = 'rejected')    as rejected_events,
        min(received_at)                                as first_failure_at,
        max(received_at)                                as last_failure_at,
        string_agg(distinct coalesce(failure_reason, 'unknown'), ', ') as failure_reasons,
        string_agg(distinct order_id, ', ')             as orders_mentioned
    from events
    where outcome in ('failed', 'rejected')
    group by 1
),

recovered as (
    select p.customer_email, max(e.received_at) as last_success_at
    from problems p
    join events e
      on e.customer_email = p.customer_email
     and e.outcome = 'delivered'
     and e.received_at > p.last_failure_at
    group by 1
)

select
    c.customer_id,
    c.customer_name,
    c.business,
    c.tier,
    p.failed_events,
    p.rejected_events,
    p.failure_reasons,
    p.orders_mentioned,
    p.first_failure_at,
    p.last_failure_at,
    coalesce(o.open_orders, 0)                  as open_orders,
    coalesce(o.open_order_value, 0)             as open_order_value,
    r.last_success_at is not null               as recovered
from problems p
join customers c on c.customer_email = p.customer_email
left join open_orders o on o.customer_id = c.customer_id
left join recovered r on r.customer_email = p.customer_email
order by
    recovered,
    case c.tier when 'vip' then 1 when 'gold' then 2 else 3 end,
    p.failed_events desc
