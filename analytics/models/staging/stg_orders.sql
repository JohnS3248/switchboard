select
    id                          as order_id,
    customer_id,
    amount,
    status                      as order_status,
    cast(ordered_on as date)    as ordered_on
from {{ source('ops', 'orders') }}
