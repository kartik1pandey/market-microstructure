# Causal case study: did ending the TUSD zero-maker-fee promotion widen BTC/TUSD liquidity?

## Estimand

Did Binance's removal of the zero-maker-fee promotion on TUSD trading pairs cause a change
in BTC/TUSD liquidity, relative to what BTC/TUSD's liquidity would have been absent the
change?

## The event

Binance ended its zero-maker-fee promotion on TUSD spot/margin pairs, **effective
2024-07-16 00:00 UTC** — standard VIP-tier maker fees applied from that point for BTC/TUSD
and several other TUSD pairs. Source: [Binance's own announcement](https://www.binance.com/en/support/announcement/updates-on-zero-fee-trading-for-tusd-spot-and-margin-trading-pairs-e47b316081a44aeca6e133b3e6c5a897),
fetched and quoted directly rather than recalled from memory.

**Hypothesis (stated before looking at any data):** removing a maker-fee subsidy reduces
market-makers' incentive to post tight quotes, so BTC/TUSD liquidity should measurably
*worsen* (proxy value increase) right after the cutover, relative to unaffected BTC pairs.

## Pre-registered design (written down before pulling data)

| | |
|---|---|
| Treated unit | BTC/TUSD |
| Event date | 2024-07-16 00:00 UTC |
| Pre-period | 2024-06-01 → 2024-07-15 |
| Post-period | 2024-07-16 → 2024-07-30 |
| Donor pool | BTC/USDT, BTC/USDC, BTC/FDUSD |
| Outcome metric | hourly `(high − low) / close` |
| Placebo | re-run the identical method with each donor as the "treated" unit |

BTC/BUSD was considered and dropped from the donor pool: Binance's public klines API returns
no data for it by June 2024 (BUSD had been wound down by then) — checked empirically before
finalizing the donor list, not assumed.

## Honest limitation

Historical klines don't include bid-ask spread, only OHLC/volume — true spread history for
July 2024 doesn't exist in data we have access to (our own live L2 capture only starts this
week). The outcome metric is therefore a **liquidity proxy**: `(high-low)/close`, a standard
stand-in for spread/liquidity used when true order-book history isn't available. This is a
real methodological compromise, not a hidden one.

## Data & donor pool validation

1,417 hourly candles per symbol, 2024-06-01 to 2024-07-30, fetched from Binance's public
`/api/v3/klines` endpoint (no auth required).

Pre-period correlation with BTC/TUSD (must be high before trusting these as controls):

| Donor | Correlation |
|---|---|
| BTC/USDT | 0.983 |
| BTC/USDC | 0.975 |
| BTC/FDUSD | 0.984 |

All comfortably above the >0.8 threshold — expected, since these are all BTC priced in
different USD-pegged stablecoins tracking the same underlying asset.

## Primary result (pre-registered: hourly granularity)

Synthetic control weights: BTC/USDT 0.333, BTC/USDC 0.333, BTC/FDUSD 0.333 (equal weights —
plausible given how highly correlated all three donors are with each other, not a fitting
failure). Pre-period fit RMSE: 0.00094.

| | Actual (post) | Synthetic (post) | Gap | % effect |
|---|---|---|---|---|
| BTC/TUSD | 0.00711 | 0.00719 | **-0.0000791** | **-1.10%** |

**Placebo test** (same method, each donor as fake-"treated"):

| Placebo unit | Gap |
|---|---|
| BTC/USDT | -0.0000306 |
| BTC/USDC | -0.0000456 |
| BTC/FDUSD | +0.0001553 |

The real effect's magnitude (0.0000791) ranks **2nd of 4** against the placebo distribution
— right in the middle, not in either tail. **Conclusion at this granularity: no effect
distinguishable from noise.** The hourly proxy is simply too noisy, at this sample size, to
separate a real effect (if one exists) from ordinary hour-to-hour variation in any of these
pairs.

## Secondary result — exploratory, NOT pre-registered (daily granularity)

After finding a null result at hourly granularity, we re-ran the identical method on daily
bars as a robustness check. **This was not specified in the pre-registration above** — it's
reported as an exploratory follow-up, not a confirmatory finding, and should be weighted
accordingly.

Pre-period correlation with BTC/TUSD (daily): BTC/USDT 0.993, BTC/USDC 0.986, BTC/FDUSD
0.993. Synthetic control weights: equal (0.333 each again). Pre-period RMSE: 0.00235.

| | Actual (post) | Synthetic (post) | Gap | % effect |
|---|---|---|---|---|
| BTC/TUSD | 0.03968 | 0.03613 | **+0.00355** | **+9.83%** |

**Placebo test** (daily):

| Placebo unit | Gap |
|---|---|
| BTC/USDT | -0.00028 |
| BTC/USDC | -0.00107 |
| BTC/FDUSD | -0.00029 |

At daily granularity, the real effect (+0.00355) is **larger in magnitude than all three
placebo effects** and, notably, in the *hypothesized direction* (liquidity proxy widened) —
unlike the hourly result. This is suggestive of a real effect that gets washed out by noise
at hourly resolution but survives when aggregated to daily bars.

## Conclusion

The pre-registered (hourly) analysis found **no effect distinguishable from placebo noise**.
An exploratory daily-granularity check found a **larger-than-placebo, direction-consistent**
effect (+9.8%), but because this check wasn't pre-registered, it should be read as a
hypothesis worth a proper confirmatory test — not as confirmed evidence. Reporting both,
rather than only the one that "worked," is the point of pre-registration: it stops a
convenient post-hoc result from being presented as if it were the planned finding.

The honest summary: **there's a directionally-consistent, placebo-dominant signal at daily
resolution, but it isn't confirmed at the granularity we originally committed to.** A
follow-up study with a longer post-period and/or true spread data (once our own live capture
has enough history) would be the right next step to actually confirm or reject this.

## Reproducibility

```
python -m ds_analytics.run_analysis --interval 1h   # primary, pre-registered result
python -m ds_analytics.run_analysis --interval 1d   # secondary, exploratory result
```
Both commands were run to produce the exact numbers in the tables above. Binance's klines
are immutable historical data, so re-running these should reproduce these numbers exactly.
