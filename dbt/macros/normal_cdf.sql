{% macro normal_cdf(z) %}
    {#- Abramowitz & Stegun 7.1.26 approximation of the standard normal CDF.
        Works identically on DuckDB and BigQuery: only EXP/POWER/ABS/SIGN needed. -#}
    (
        0.5 * (
            1 + sign({{ z }}) * (
                1 - (
                    0.254829592 * (1 / (1 + 0.3275911 * abs({{ z }})))
                    - 0.284496736 * power(1 / (1 + 0.3275911 * abs({{ z }})), 2)
                    + 1.421413741 * power(1 / (1 + 0.3275911 * abs({{ z }})), 3)
                    - 1.453152027 * power(1 / (1 + 0.3275911 * abs({{ z }})), 4)
                    + 1.061405429 * power(1 / (1 + 0.3275911 * abs({{ z }})), 5)
                ) * exp(-power({{ z }}, 2))
            )
        )
    )
{% endmacro %}
