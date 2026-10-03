select
    id              as customer_id,
    name            as customer_name,
    lower(email)    as customer_email,
    business,
    tier
from {{ source('ops', 'customers') }}
