# clustering — Claude Code and Codex CLI plugin

Plugin that decides how many clusters **K** of residues share
global parameters in a multi-residue global fit (e.g. relaxation-dispersion
data fitted with shared kex, pB). Output: K, cluster membership, and
per-cluster global parameter values.

## Install

### Codex CLI

```bash
codex plugin marketplace add dleess/clustering
codex plugin add clustering@clustering
```

Start a new Codex thread after installation so the `clustering` skill is loaded.

### Claude Code

```bash
claude plugin marketplace add dleess/clustering
claude plugin install clustering@clustering
```

### jev MCP server (recommended; enables the required cross-check step)

The skill's final cross-check uses [jev](https://www.npmjs.com/package/jev-mcp),
TypeSafe's judgment model, through the `jev-mcp` server. It needs a TypeSafe
API key (`TYPESAFE_API_KEY`). Without the server the skill still runs and skips step 5; with it, step 5 always runs before K is reported.

Claude Code:

```bash
claude mcp add jev -s user -e TYPESAFE_API_KEY=<your key> -- npx -y jev-mcp
```

Codex CLI — add to `~/.codex/config.toml`:

```toml
[mcp_servers.jev]
command = "npx"
args = ["-y", "jev-mcp"]
startup_timeout_sec = 60

[mcp_servers.jev.env]
TYPESAFE_API_KEY = "<your key>"
```

Verify with the `jev_models` tool in a new session; it lists `jev-latest`
when the key works.

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

5. **jev cross-check** (required whenever the `jev` MCP server is configured) —
   `scripts/jev_state.py` turns the fit logs into a compact state and
   `references/jev-questions.json` holds a fixed question set (evidence
   strength, selected structure, split-further, more-fits-needed). Undefined
   numbers are `null`; `--groups` logs must partition the full fit, otherwise
   it exits 2 with a `jev_state:` message. jev is a gate on the orchestrator's
   conclusion, never an override of the red χ² gate or a failed group refit. Single-residue group logs are reported as `individuals`, and such a hypothesis is keyed `K<shared>_plus_individuals_global`.

Fit runs are dispatched as parallel computation agents (one per config);
only the orchestrator synthesizes K.

## Validation

Tested against synthetic sherekhan scenarios with known truth (seed 4242,
6–8 residues, 2 fields, 1% noise): K = 1, 2, 3, 4 all recovered exactly,
memberships exact (e.g. c2 kex 607/1807 vs truth 600/1800).

## Development

- Self-test the state builder (stdlib only, any python3 >= 3.8):
  `python3 skills/clustering/scripts/jev_state.py --selfcheck`
- Regenerate the fixtures from the sherekhan simulator:
  `git clone https://github.com/deepnmr/sherekhan`, create a venv with
  numpy, scipy and matplotlib, then run `python demo/multi/make_multi.py`
  and `cd demo/multi/g2 && python ../../../sk_run.py g2.conf > fit-full.log`.
- Validate the plugin: `claude plugin validate .`

## Layout

- `AGENTS.md` - knowledge base for coding agents
- `skills/clustering/SKILL.md` — the skill
- `skills/clustering/scripts/jev_state.py` — fit logs → jev state (`--selfcheck` runs its test)
- `skills/clustering/references/jev-questions.json` — jev question set + decision rules
- `.codex-plugin/plugin.json` — Codex CLI plugin manifest
- `.agents/plugins/marketplace.json` — Codex CLI marketplace
- `.claude-plugin/plugin.json` — plugin manifest
- `.claude-plugin/marketplace.json` — lets this repo serve as its own marketplace
