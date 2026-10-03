-- Fails if any day reports a delivery rate outside 0..1 or more outcomes than events.
select *
from {{ ref('fct_daily_operations') }}
where delivery_rate < 0 or delivery_rate > 1
   or delivered + failed + rejected <> events
