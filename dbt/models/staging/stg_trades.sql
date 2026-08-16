-- Typed pass-through of the raw trades table.

select
    ts_ms,
{% if target.type == 'bigquery' %}
    timestamp_millis(ts_ms) as trade_time,
{% else %}
    to_timestamp(ts_ms / 1000.0) as trade_time,
{% endif %}
    trade_id,
    price,
    qty,
    is_buyer_maker
from {{ source('raw', 'trades') }}
