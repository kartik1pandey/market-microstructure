-- Per-depth-event features: mid-price, spread, top-5 depth, book imbalance, realized vol.
--
-- order_flow_imbalance here is the simplified *static queue-imbalance ratio* at the best
-- level - (bid_qty - ask_qty) / (bid_qty + ask_qty) - naturally bounded in [-1, 1]. This is
-- NOT the literal Cont-Kukanov-Stoikov (2014) event-flow OFI (which is unbounded, in share
-- units, comparing consecutive book states) - see docs/build-notes.md for why.

{% if target.type == 'bigquery' %}
    {% set best_bid_qty_expr = "bid_qtys[OFFSET(0)]" %}
    {% set best_ask_qty_expr = "ask_qtys[OFFSET(0)]" %}
    {% set depth_bid_expr = "(select sum(x) from unnest(bid_qtys) as x)" %}
    {% set depth_ask_expr = "(select sum(x) from unnest(ask_qtys) as x)" %}
{% else %}
    {% set best_bid_qty_expr = "bid_qtys[1]" %}
    {% set best_ask_qty_expr = "ask_qtys[1]" %}
    {% set depth_bid_expr = "list_sum(bid_qtys)" %}
    {% set depth_ask_expr = "list_sum(ask_qtys)" %}
{% endif %}

with base as (
    select
        ts_ms,
        event_time,
        final_update_id,
        best_bid,
        best_ask,
        spread,
        (best_bid + best_ask) / 2.0 as mid_price,
        {{ best_bid_qty_expr }} as best_bid_qty,
        {{ best_ask_qty_expr }} as best_ask_qty,
        {{ depth_bid_expr }} as depth_bid_top5,
        {{ depth_ask_expr }} as depth_ask_top5
    from {{ ref('stg_depth_ticks') }}
),

with_imbalance as (
    select
        *,
        spread / nullif(mid_price, 0) * 10000 as spread_bps,
        (best_bid_qty - best_ask_qty) / nullif(best_bid_qty + best_ask_qty, 0) as order_flow_imbalance,
        ln(mid_price / nullif(lag(mid_price) over (order by final_update_id), 0)) as log_return
    from base
)

-- realized_vol_100events: sqrt of sum of squared log-returns over the trailing 100 events.
-- Caveat: sampled in *event time* (per book update), not fixed clock time, so it isn't
-- directly comparable to a calendar-time realized-vol estimate - worth stating explicitly
-- rather than implying a false apples-to-apples comparison.
select
    *,
    sqrt(
        sum(power(log_return, 2)) over (
            order by final_update_id
            rows between 99 preceding and current row
        )
    ) as realized_vol_100events
from with_imbalance
