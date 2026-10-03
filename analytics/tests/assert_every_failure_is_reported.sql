-- Fails if a customer with a failed or rejected event is missing from the affected-customers report.
select distinct e.customer_email
from {{ ref('stg_events') }} e
left join {{ ref('stg_customers') }} c on c.customer_email = e.customer_email
left join {{ ref('rpt_affected_customers') }} r on r.customer_id = c.customer_id
where e.outcome in ('failed', 'rejected')
  and r.customer_id is null
