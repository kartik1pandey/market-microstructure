-- Singular test: passes when this returns zero rows.
select *
from {{ ref('fct_depth_features') }}
where order_flow_imbalance < -1 or order_flow_imbalance > 1
