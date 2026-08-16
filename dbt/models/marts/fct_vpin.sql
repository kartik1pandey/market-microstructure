-- VPIN (Easley, Lopez de Prado & O'Hara 2012): bucket trades into equal-VOLUME buckets,
-- classify each bucket's volume as buy/sell-initiated via Bulk Volume Classification (the
-- standardized bucket-to-bucket price change run through the normal CDF), then VPIN is a
-- rolling average of |buy_volume - sell_volume| / total_volume across buckets.
--
-- Binance actually tells us the true aggressor per trade (is_buyer_maker), so BVC isn't
-- strictly necessary here - but VPIN as defined in the literature IS the BVC construction,
-- so that's what's implemented (see docs/build-notes.md).

{% set num_buckets = var('vpin_num_buckets', 50) %}
{% set rolling_window_buckets = var('vpin_rolling_window_buckets', 10) %}
{% set sigma_window_buckets = 20 %}

with trades as (
    select ts_ms, price, qty
    from {{ ref('stg_trades') }}
),

with_cumvol as (
    select
        *,
        sum(qty) over (order by ts_ms rows between unbounded preceding and current row) as cum_volume,
        sum(qty) over () as total_volume
    from trades
),

bucketed as (
    select
        *,
        cast(floor(cum_volume / nullif(total_volume / {{ num_buckets }}, 0)) as integer) as bucket_id
    from with_cumvol
),

bucket_agg as (
    select
        bucket_id,
        min(ts_ms) as bucket_start_ts,
        max(ts_ms) as bucket_end_ts,
        sum(qty) as bucket_volume
    from bucketed
    group by bucket_id
),

ranked_by_recency as (
    select
        bucket_id,
        price,
        row_number() over (partition by bucket_id order by ts_ms desc) as rn_desc
    from bucketed
),

bucket_close as (
    select bucket_id, price as bucket_close_price
    from ranked_by_recency
    where rn_desc = 1
),

bucket_combined as (
    select
        a.bucket_id,
        a.bucket_start_ts,
        a.bucket_end_ts,
        a.bucket_volume,
        c.bucket_close_price
    from bucket_agg a
    join bucket_close c on a.bucket_id = c.bucket_id
),

with_price_change as (
    select
        *,
        bucket_close_price - lag(bucket_close_price) over (order by bucket_id) as price_change
    from bucket_combined
),

with_sigma as (
    select
        *,
        stddev_samp(price_change) over (
            order by bucket_id
            rows between {{ sigma_window_buckets - 1 }} preceding and current row
        ) as sigma
    from with_price_change
),

with_zscore as (
    select
        *,
        case when sigma is null or sigma = 0 then null
             else price_change / sigma
        end as z_score
    from with_sigma
),

with_classification as (
    select
        *,
        case when z_score is null then 0.5
             else {{ normal_cdf('z_score') }}
        end as buy_fraction
    from with_zscore
),

with_volumes as (
    select
        *,
        bucket_volume * buy_fraction as buy_volume,
        bucket_volume * (1 - buy_fraction) as sell_volume
    from with_classification
),

with_vpin as (
    select
        bucket_id,
        bucket_start_ts,
        bucket_end_ts,
{% if target.type == 'bigquery' %}
        timestamp_millis(bucket_end_ts) as bucket_end_time,
{% else %}
        to_timestamp(bucket_end_ts / 1000.0) as bucket_end_time,
{% endif %}
        bucket_volume,
        bucket_close_price,
        price_change,
        sigma,
        buy_fraction,
        buy_volume,
        sell_volume,
        sum(abs(buy_volume - sell_volume)) over (
            order by bucket_id
            rows between {{ rolling_window_buckets - 1 }} preceding and current row
        ) / nullif(
            sum(bucket_volume) over (
                order by bucket_id
                rows between {{ rolling_window_buckets - 1 }} preceding and current row
            ), 0
        ) as vpin
    from with_volumes
)

-- vpin_regime: a simple fixed-threshold read of "how toxic does flow look right now".
-- Thresholds (0.2 / 0.4) are a reasonable starting point, not calibrated against this
-- specific instrument's historical VPIN distribution - worth revisiting once enough
-- captured history exists to pick data-driven cutoffs (e.g. percentile-based).
select
    *,
    case
        when vpin < 0.2 then 'normal'
        when vpin < 0.4 then 'elevated'
        else 'toxic'
    end as vpin_regime
from with_vpin
order by bucket_id
