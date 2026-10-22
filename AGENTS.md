# PROJECT KNOWLEDGE BASE: clustering

**Generated:** 2026-10-22 · **Commit:** e0a4a7d · **Branch:** refactor/jev-state-debug

## OVERVIEW

Claude/Codex plugin (`clustering`, v0.2.1) that answers "how many clusters of residues share one exchange model?" for NMR global fits produced by sherekhan (`github.com/deepnmr/sherekhan`). The skill runs fits, applies AICc/chi2 decision rules, and cross-checks the result with a jev judgment model via a state JSON built by `jev_state.py`.

## STRUCTURE

```
clustering/
├── AGENTS.md                              # this file
├── README.md                              # install, layout, validation, development commands
├── HANDOFF.md                             # project history, validation results, addenda
├── .gitignore
├── .agents/plugins/marketplace.json       # Codex marketplace entry
├── .claude-plugin/
│   ├── marketplace.json                   # Claude marketplace entry
│   └── plugin.json                        # Claude plugin manifest
├── .codex-plugin/plugin.json              # Codex plugin manifest
└── skills/clustering/
    ├── SKILL.md                           # the skill: procedure, decision rules, jev step
    ├── references/jev-questions.json      # jev questions + _rules + _usage
    └── scripts/jev_state.py               # state builder (stdlib only)
```

`.kbsi/` (plans, evidence) is local working state and is not tracked.

## WHERE TO LOOK

| Task | Location | Notes |
| --- | --- | --- |
| Decision procedure (K, groups, thresholds) | `skills/clustering/SKILL.md` | Steps 1-4 are the statistical contract |
| Build the jev state from fit logs | `skills/clustering/scripts/jev_state.py` | Output keys are a contract |
| jev questions and rules | `skills/clustering/references/jev-questions.json` | `_rules` and `questions` are frozen |
| Plugin metadata and versions | `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json` | Bump both together |
| Install/marketplace | `.claude-plugin/marketplace.json`, `.agents/plugins/marketplace.json` | `source` paths are fixed |
| History and validation results | `HANDOFF.md` | Historical paths are marked as such |

## CODE MAP

`skills/clustering/scripts/jev_state.py`:
- `DELTA_KEX_SIGMA = 2.0`: influential-residue threshold (mirrors the sk_run jackknife `*` flag).
- `OUTPUT_INDENT = 1`: indent passed to `json.dumps` for stdout.
- `InputError`: bad input; the CLI prints `jev_state: <msg>` and exits 2.
- `read_block(text, name)`: extracts a named JSON block from a sherekhan fit log (also accepts a block on the last line without newline).
- `finite_or_none(x, nd=None)`: rounds finite numbers; returns `None` for None/nan/inf.
- `load_fit(path)`: parses one fit log into per-residue and global fields; `global.kex` falls back to `model_comparison` when the jackknife is absent.
- `aicc(chi2, k, n)`: AICc; `None` when n-k-1 <= 0.
- `resolve_keys(paths)`: maps each input to a unique key (basename, or normalized path when basenames collide).
- `check_partition(full, groups)`: validates that the group fits partition the full fit's residues.
- `hypothesis_entry(groups, n)`: builds the K-global hypothesis object (with `shared_groups` and `individuals`).
- `hypothesis_name(h, n_groups)`: `K{n}_global` for shared clusters only, `K{shared}_plus_individuals_global` when single-residue groups are present (matches the jev structure options).
- `build_state(paths, groups=())`: `paths[0]` is the full fit; `groups` are group fits of one K-global hypothesis.
- `parse_argv(args)`: splits argv into `(paths, groups)`.
- `main(argv) -> int`: CLI dispatch; returns the exit code.
- `_selfcheck()`: built-in tests, run with `--selfcheck`; every log is written through `log_text(mc, jk=None)`.

## CONVENTIONS

- Script is stdlib-only (`json`, `math`, `os`, `sys`; `tempfile` inside `_selfcheck`). No third-party imports.
- Tests live in `_selfcheck()`; no separate test framework or test files.
- Output keys and rounding are a contract with the jev `_rules` and with the copy kbsi bundles byte-for-byte. Keep them stable for valid inputs.
- Hypothesis objects may only gain fields; never rename `K{n}_global` for pure K-group hypotheses. Hypotheses with single-residue groups are keyed `K{shared}_plus_individuals_global` because jev misread `K{len}_global` as len shared clusters.
- Output is `json.dumps(..., indent=1)` to stdout.
- Version bumps touch both plugin manifests in the same commit.
- Docs must name only paths that exist or are URLs.

## ANTI-PATTERNS

- Never change state keys, rounding, or values for inputs that already worked.
- Never use per-group n in the AICc of a K-global hypothesis; use the full fit n.
- Never edit `_rules` or question text without re-validating with jev.
- Never hand-build the state JSON; always run `jev_state.py` on the real logs.
- Never let an undefined number reach the output as NaN or inf; emit `null`.
- Never commit or push from an executor agent; the orchestrator commits.

## COMMANDS

```bash
# built-in tests (stdlib only)
python3 skills/clustering/scripts/jev_state.py --selfcheck

# build the state from a full fit log
python3 skills/clustering/scripts/jev_state.py fit-full.log > state.json

# validate the plugin
claude plugin validate .

# regenerate sherekhan demo fixtures
git clone https://github.com/deepnmr/sherekhan
python -m venv venv && venv/bin/pip install numpy scipy matplotlib
venv/bin/python sherekhan/demo/multi/make_multi.py
cd sherekhan/demo/multi/g2 && ../../../../venv/bin/python ../../../sk_run.py g2.conf > fit-full.log
```

## NOTES

- sherekhan writes `null` for nan/inf values (`_finite_json` in `sk_run.py`), so z_kex, aicc, delta_aicc, and kex can be null.
- The jackknife block is absent when there are fewer than 2 residues or jackknife is off.
- sherekhan never writes an `influential` key; influential residues are derived from `delta_kex` and `se` (flag if abs(delta_kex) > 2*se, se > 0).
- The jev step is required whenever `jev_ask` is available.
- `codex exec` needs `< /dev/null` or it hangs waiting on stdin.
- Installed skill copies can be stale; reinstall the plugin after a version bump.
- Historical paths in HANDOFF.md (under `/Users/donghanlee/work/projects`, `~/.claude/skills/clustering`) do not exist as current state.
- Subdirectory AGENTS.md: none. The repo has 11 tracked files, so one root file is enough.
