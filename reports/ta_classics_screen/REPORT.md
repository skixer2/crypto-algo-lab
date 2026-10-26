# Classic-TA Expedition — Verbatim Screen of Canonical Technical-Analysis Systems

**Date:** 2026-10-26 · **Runner:** subagent (Classic-TA brief) · **Contract:** AGENT_CONTRACT.md (binding)
**Scope:** 7 canonical TA systems × 2 pre-registered arms (`_native`, `_hm`). No tuning, no extra variants, no re-runs. Every number below is verbatim `tools/screen_candidate.py` output (log: `screen_runs.txt` in this folder).

## Pre-registration (stated in every formula header BEFORE any run)

- **Arms:** `_native` = canonical published periods applied as-is to 15m bars. `_hm` = every period parameter ×96 (daily-equivalent on 15m: RSI 1344, Stoch 1344/288/288, BB 1920, MACD 1152/2496/864, Aroon 2400, ADX 1344, OBV lookback 1344). Band/level constants (RSI 30/50, Stoch 20/80, BB 2σ, ADX 25) **stay as published**.
- **Engine:** canonical convention — decide@close, fill next bar, fee 0.0008 on |Δpos|, long-only clip, buy-hold bench, 2024+ door. Ruler: `tools/stats_canonical.grade()`. Floors: mean>0, worst≥−40, both halves≥0, 2024+>0.
- **Declared encodings (only where the classic is ambiguous):**
  - RSI: Wilder ewm(α=1/N) RMA; level-latch (entry event every bar RSI<30, exit every bar RSI>50, hold between).
  - Stoch: slow (14,3,3); strict sign-change cross; "below 20 / above 80" = crossing line %K at the cross bar.
  - BB: population std (ddof=0, TA-lib convention); level-latch (close<lower → in, close≥middle → out).
  - MACD: ewm(span) EMAs, strict sign-change crosses, latch.
  - Aroon: window P+1 bars incl. current; Aroon = 100·(P − bars-since-extreme)/P; strict crosses, latch.
  - ADX: Wilder DI machinery; entry = level-state (DI+>DI− AND ADX>25), exit = DI+<DI− event; latch between.
  - OBV: **one declared deviation** — divergence encoded as disjoint 14-bar windows (NOW vs PREV): entry = price lower low AND OBV higher low; exit = OBV lower low AND price not making a new low; level-triggered latch (pivot-swing divergence replaced by windowed divergence, per pre-registered allowance).
- **Validation:** `tuner/validate_formula.py` — **14/14 PASS**, 0 warnings (causality proof incl.).
- **Warmup:** CLOSED everywhere (min_periods = declared warmup; engine flat during NaN).

## Results — 7×2 verbatim table (stats_canonical, engine convention)

| System (canonical) | Arm | mean_excess %/mo | t | worst month % | Halves H1/H2 % | 2024+ %/mo | Floor verdict |
|---|---|---:|---:|---:|---:|---:|---|
| RSI(14) Wilder reversion | native | **−6.37** | −2.86 | −30.3 | −55.5 / −153.2 | −7.15 | **FAIL** |
| RSI(14) | hm | **−1.85** | −0.67 | +0.0 † | +0.0 / +0.0 † | −2.58 | **FAIL** † |
| Stochastic (14,3,3) | native | **−7.42** | −3.81 | −36.5 | −125.1 / −130.8 | −6.46 | **FAIL** |
| Stochastic (14,3,3) | hm | **−2.16** | −0.97 | −44.7 | +83.2 / −59.2 | −4.64 | **FAIL** |
| Bollinger (20,2) reversion | native | **−10.23** | −5.09 | −39.5 | −189.2 / −323.0 | −11.72 | **FAIL** |
| Bollinger (20,2) | hm | **−2.11** | −0.86 | −35.9 | +66.2 / −15.1 | −3.23 | **FAIL** |
| MACD (12,26,9) | native | **−19.67** | −8.87 | −39.5 | −600.8 / −639.3 | −20.07 | **FAIL** |
| MACD (12,26,9) | hm | **−1.03** | −0.63 | −29.6 | +43.1 / +11.4 | −1.59 | **FAIL** |
| Aroon(25) | native | **−11.48** | −6.34 | −46.4 | −171.8 / −382.7 | −13.24 | **FAIL** |
| Aroon(25) | hm | **−1.51** | −0.76 | −44.7 | +63.9 / +28.2 | −2.14 | **FAIL** |
| ADX(14) with DI | native | **−6.22** | −2.87 | −26.6 | −143.7 / −144.7 | −6.84 | **FAIL** |
| ADX(14) with DI | hm | **−1.85** | −0.67 | +0.0 † | +0.0 / +0.0 † | −2.58 | **FAIL** † |
| OBV(14) divergence | native | **−4.79** | −2.20 | −27.2 | −28.9 / −42.6 | −4.00 | **FAIL** |
| OBV(14) divergence | hm | **−2.95** | −1.17 | −40.4 | −79.8 / +43.9 | −1.38 | **FAIL** |

† Diagnostic (episode counts, not a performance number): `ta_rsi_hm` and `ta_adx_hm` produced **0 position episodes in 5.8 years** — the canonical thresholds (RSI(1344)<30; DI+>DI− with ADX>25 at 1344-Wilder smoothing) **never occur** on ETH 15m. Their flat-equity numbers = pure benchmark drift. All other hm arms' first entry lands Feb–Mar 2021, after warmup — warmups respected.

## Floor-passers

**None. 0/14.** No arm passes all four floors; no plateau-jitter question arises for the operator.

## Activity diagnostics (episodes / % bars long, implementation sanity only)

| System | native | hm |
|---|---|---|
| RSI | 1363 / 15.6% | **0 / 0%** |
| Stoch | 1981 / 42.1% | 26 / 41.2% |
| Bollinger | 3921 / 26.6% | 57 / 33.0% |
| MACD | 8023 / 50.0% | 79 / 50.0% |
| Aroon | 4520 / 49.4% | 51 / 49.7% |
| ADX | 2734 / 25.8% | **0 / 0%** |
| OBV div | 1919 / 48.6% | 15 / 18.4% |

## 5-line verdict

1. **The classics do not survive crypto 15m in either arm — 0/14 floor-passers, every mean_excess negative, no exceptions.**
2. **Native settings are not just weak but reliably extractable-against:** all 7 t-stats negative (−2.20…−8.87) with 93–100% continuous DD — churn + fee bleed (native MACD: 8023 episodes, −19.67%/mo) dominates any edge the rules ever had.
3. **Horizon-matching (×96) is uniformly less bad — never a worse mean, t-stats collapse toward 0 (−0.63…−1.17)** — but the failure mode only shifts from churn-death to silence: 26–79 lifetime episodes, and two arms (RSI-hm, ADX-hm) never trade at all because the canonical thresholds (RSI<30, ADX>25) never trigger at daily-equivalent smoothing.
4. **No arm is positive 2024+** (range −1.38…−20.07%/mo); the mildly positive hm H1 halves are a 2021–2023 artifact, not a live edge.
5. **Conclusion: at published settings, canonical TA on ETH 15m is dead on arrival — native arms are short-signals at best, horizon-matched arms are inert. Any future use of these systems here requires a re-mechanization, not a re-parameterization (which this pre-registered screen rules out).**

## Artifacts

- Formulas: `models/alpha_formulas/ta_{rsi,stoch,bb,macd,aroon,adx,obv}_{native,hm}.py` (14 files, rule + arm + encodings in headers, all validator-PASS)
- Verbatim screen log: `reports/ta_classics_screen/screen_runs.txt`
- Engine/ruler untouched: `tools/screen_candidate.py`, `tools/stats_canonical.py`, data cache unmodified by this run.
