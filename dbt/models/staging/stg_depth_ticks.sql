-- Typed pass-through of the raw depth-tick table. No business logic here -
-- that lives in the marts models. Just casting and a human-readable event_time.

select
    ts_ms,
{% if target.type == 'bigquery' %}
    timestamp_millis(ts_ms) as event_time,
{% else %}
    to_timestamp(ts_ms / 1000.0) as event_time,
{% endif %}
    first_update_id,
    final_update_id,
    best_bid,
    best_ask,
    spread,
    bid_prices,
    bid_qtys,
    ask_prices,
    ask_qtys
from {{ source('raw', 'depth_ticks') }}
