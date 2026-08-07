---
name: clustering
description: Use when multi-residue (or multi-dataset) fitting output must be judged for how many clusters share global parameters — e.g. global-vs-individual model comparison tables (chi2, AICc, dAICc, z), jackknife validation, relaxation-dispersion sk-run logs — to decide between 1-global, K-global, and individual models.
---

# Counting Residue Clusters in Global Fits

## Overview

Given a program that fits N residues with shared **global parameters** (example:
kex, pB — but always ask/confirm which parameters are global for this model) plus
per-residue locals, decide how many clusters K of residues each share one set of
global parameters. Output: K, cluster membership, per-cluster global values.

**Core principle:** least-squares global fitting is NOT robust — one divergent
residue drags the shared parameters, so ALL residues flip to `better=individual`.
Binary flags hide the cause; magnitudes (reduced chi², chi2_glob ranking) survive.

## Setup — establish before running anything

1. Fit command (e.g. `sk-run run.conf`) and how to toggle residues on/off in config.
2. Names of the global parameter(s); the **primary** one (first listed, e.g. kex)
   is used for z-scores and clustering.
3. Where to read: global chi², parameter count k, total data points n, per-residue
   `chi2_glob`/`chi2_indiv`/`dAICc`/`z`, jackknife block, per-residue individual
   fit values of the global parameters.

## Decision procedure — stop at the first step that resolves

**Step 1 — reduced chi² gate (do this FIRST, before reading any verdict).**
Compute `red_chi2 = chi2_global / (n − k)` for the full global fit.
If `red_chi2 ≤ 1`: **K = 1, done.** The global model already fits within noise;
any split is overfitting. Do NOT run more fits, do NOT weigh per-residue
`better=individual` flags, dAICc, or z against this — they are noise-chasing here.

**Step 2 — whole-dataset verdict.** If `Preferred model: global` AND jackknife
relative SE is small (≲ a few %) with no `*` influential flags: **K = 1, done.**

**Step 3 — outlier diagnosis (single or few individuals).**
If verdict is individual or jackknife rel SE is large (≳ 15–20%):
- Rank residues by `chi2_glob` **descending**. True individuals cluster at the
  top with a visible gap; this ranking survives even heavy contamination, while
  the `better` column and the jackknife `*` flag do not (one strong outlier
  inflates jackknife SE and masks its own flag). `z` is a secondary signal.
- Turn the top residue(s) `off`, refit. Restored = verdict returns to global,
  all remaining `better=global`, jackknife rel SE drops to ≲ 3%.
- If restored: **answer = 1 main cluster + the excluded residues as
  individuals.** Report both.

**Step 4 — K-group structure (exclusion does not restore).**
If the individual-fit values of the primary global parameter form value groups
(sort them; split at gaps ≫ within-group spread):
- Build one config per hypothesized group (only that group `on`), fit each.
- Each group must internally pass: all `better=global`, small jackknife rel SE.
- **Structure selection:** compare total AICc of 1-global vs K-global vs
  individual, `AICc = chi2 + 2k + 2k(k+1)/(n−k−1)`, where for K-global
  chi2 = Σ group chi², k = Σ group k, and **n = TOTAL data points in every
  hypothesis** (same data, same n — never per-group n). Lowest AICc wins → that
  is K. Try K = 2, 3… only while AICc keeps dropping.

## Execution — orchestrator + parallel computation agents

The procedure needs several fit runs (Step 3 exclusion refits, Step 4 group
fits). Never run them serially yourself — act as the **orchestrator**:

1. Run the initial full global fit (this one is sequential — everything depends
   on it) and form your hypotheses from its output.
2. List every config the current step needs (all exclusion variants, all group
   configs, extra K hypotheses). Dispatch **one computation agent per config,
   all in a single message** so they run in parallel.
3. Each computation agent's contract: copy the base config, toggle the assigned
   residue flags, run the fit command, parse the output (prefer labelled JSON
   blocks like `##### model_comparison` / `##### jackknife` over the human
   table), and return ONLY compact JSON:
   `{config, residues_on, global: {chi2, k, n}, individual: {chi2, k},
   verdict, per_residue: [{resId, chi2_glob, chi2_indiv, dAICc, z, better}],
   jackknife: {value, rel_se_pct, influential}, global_params: {...}}`
4. Synthesis (orchestrator only): collect the JSON results, verify each group
   passes internally, compute total AICc per hypothesis with **total n**,
   decide K, and report. Computation agents never draw conclusions about K.
5. Results that spawn new hypotheses (a group fails internally, a new gap
   appears) start another parallel wave. Waves are sequential; runs within a
   wave are parallel.

## Quick reference

| Signal | Reading |
|---|---|
| `red_chi2(global) ≤ 1` | K=1, stop — everything else is overfitting noise |
| `delta AICc (indiv − glob) > 0` | global preferred |
| per-residue `dAICc < 0` | that residue prefers individual (unreliable when fit is contaminated) |
| `\|z(primary)\| > 2` | outlier candidate vs leave-one-out consensus |
| jackknife rel SE large | unstable global — heterogeneity, go to Step 3 |
| `chi2_glob` ranking gap | contamination-proof pinpoint of individuals |

## Common mistakes

- Skipping Step 1 and arguing AICc/Bonferroni instead — wasted runs; red_chi2 ≤ 1 already decides.
- Counting `better=individual` residues as the cluster count.
- Using per-group n in the K-global AICc — n is the total, identical across hypotheses.
- Trusting the jackknife `*` flag with a single strong outlier present (it masks itself; breakdown point = 1).
- Reporting K without per-cluster refit evidence (Step 4 group fits must each pass internally).
