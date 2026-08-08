# clustering — Claude Code and Codex CLI plugin

Plugin that decides how many clusters **K** of residues share
global parameters in a multi-residue global fit (e.g. relaxation-dispersion
data fitted with shared kex, pB). Output: K, cluster membership, and
per-cluster global parameter values.

## Install

### Codex CLI

```bash
codex plugin marketplace add /path/to/clustering
codex plugin add clustering@clustering
```

Start a new Codex thread after installation so the `clustering` skill is loaded.

### Claude Code

```bash
claude plugin marketplace add /path/to/clustering   # local clone (repo root = plugin root)
claude plugin install clustering@clustering
```

## What it does

The `clustering` skill triggers on cluster/grouping questions about
multi-residue fitting output (model comparison tables with chi2 / AICc /
dAICc / z, jackknife blocks, sk-run logs) and follows a fixed decision
procedure:

1. **Reduced chi² gate** — `chi2_global/(n−k) ≤ 1` → K = 1, stop; any split
   is overfitting.
2. **Whole-dataset verdict** — global preferred + small jackknife rel SE → K = 1.
3. **Outlier diagnosis** — rank residues by `chi2_glob` descending (survives
   contamination), exclude the top, refit, check restoration → 1 main cluster
   + individuals.
4. **K-group structure** — group hypotheses from gaps in individual-fit
   values of the primary global parameter, per-group fits, total-AICc
   structure selection with **n = total data points in every hypothesis**.

Fit runs are dispatched as parallel computation agents (one per config);
only the orchestrator synthesizes K.

## Validation

Tested against synthetic sherekhan scenarios with known truth (seed 4242,
6–8 residues, 2 fields, 1% noise): K = 1, 2, 3, 4 all recovered exactly,
memberships exact (e.g. c2 kex 607/1807 vs truth 600/1800).

## Layout

- `skills/clustering/SKILL.md` — the skill
- `.codex-plugin/plugin.json` — Codex CLI plugin manifest
- `.agents/plugins/marketplace.json` — Codex CLI marketplace
- `.claude-plugin/plugin.json` — plugin manifest
- `.claude-plugin/marketplace.json` — lets this repo serve as its own marketplace
