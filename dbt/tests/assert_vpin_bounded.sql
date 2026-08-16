-- Singular test: passes when this returns zero rows.
select *
from {{ ref('fct_vpin') }}
where vpin < 0 or vpin > 1
