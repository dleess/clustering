# HANDOFF: `clustering` skill — residue-cluster counting for global fits (built & validated)

**Written:** 2026-08-07 · **Working dir:** `/Users/donghanlee/work/projects/clustering` (renamed from `.../globalfit` on 2026-08-07; directory itself is empty) · **Branch:** `codex/codex-beginner-manual` (git repo is rooted at `$HOME`, not in this folder)

## Goal
A Claude Code skill that, given a program fitting multi-residue data with shared
global parameters (user-specifiable; example kex, pB), decides how many clusters
K of residues share global parameters. Acceptance test (set via `/goal`): generate
1/2/3/4-cluster synthetic data with the sherekhan program and the skill must find
the right K each time. **This was met 4/4 — goal complete, no work is pending.**

## Status
100% done. Skill deployed and validated. This handoff exists only so a fresh
agent can pick up follow-on work (new scenarios, skill refinements).

## What worked
- Skill file: `/Users/donghanlee/.claude/skills/clustering/SKILL.md` (frontmatter `name: clustering`; dir was `counting-residue-clusters` before rename on 2026-08-07). **[still applied]**
- Decision procedure encoded (from user's manual §6–8, sherekhan `MANUAL.en.md` covers the same ground):
  1. reduced chi² gate: `chi2_global/(n−k) ≤ 1` → K=1, stop, no more runs;
  2. whole-dataset AICc verdict + jackknife rel SE small → K=1;
  3. `chi2_glob` descending ranking to pinpoint individual outliers (survives contamination; jackknife `*` flag self-masks), exclude → refit → check restoration;
  4. K-group hypotheses from gaps in individual-fit primary-param values → per-group fits → total-AICc structure selection with **n = total data points in every hypothesis**.
- Orchestration section (added at user request): orchestrator runs initial full fit sequentially, dispatches one computation agent per config **in a single message** (parallel waves), agents return compact JSON only, orchestrator alone synthesizes. **[still applied]**
- Validation vs sherekhan: generator `scratchpad/make_goal_scenarios.py` (see paths below) built scenarios c1–c4 (seed 4242, 6–8 residues, 2 fields, Matrix model, pB=0.1, 1% noise). Four independent test agents each got only the skill + scenario dir; results: c1 K=1 ✓ (Step-1 gate, red χ²=0.883), c2 K=2 ✓ (kex 607/1807, truth 600/1800), c3 K=3 ✓ (387/972/2513, truth 400/1000/2500), c4 K=4 ✓ (382/888/1587/2837, truth 400/900/1600/2800). Memberships all exact.
- c3 subtlety: K=4 came within ΔAICc=1.28 of K=3; the test agent correctly broke the tie by applying the red-χ² gate at group level ({R5,R6} group red χ²=0.99 ≤ 1 → don't split). This tiebreak is NOT written in the skill — it emerged from the gate principle. Worked untested-as-text; consider codifying only if a future run fails here.

## What didn't work
- `python`/`python3` at `/opt/homebrew/bin/python3` (3.14.6) has no numpy → sherekhan scripts fail with `ModuleNotFoundError: No module named 'numpy'`. Fixed by venv (below), don't retry bare python3. **[venv still exists]**
- During an earlier mock test, the orchestrating test agent ended its turn while its background computation agents were still running; had to be resumed via SendMessage. Mitigation used in all later tests: instruct test agents to dispatch computation agents with `run_in_background: false`, all calls in one message. This instruction lives in the test prompts, not in the skill.

## Key files & commands
- `/Users/donghanlee/.claude/skills/clustering/SKILL.md` — the skill. Registered as `/clustering`.
- `/Users/donghanlee/work/projects/sherekhan/` — fit program repo. `sk_run.py` is the fitter; `demo/multi/make_multi.py` is the generator template mine was adapted from; `MANUAL.en.md` documents the statistics.
- Scratchpad (session-scoped, `/private/tmp/claude-501/-Users-donghanlee-work-projects-globalfit/f0318c54-b928-4219-a2f1-3eac23e83f01/scratchpad/`, may be gone in a new session):
  - `venv/` — python venv with numpy/scipy/matplotlib.
  - `make_goal_scenarios.py` — regenerates c1–c4 into `goalcheck/<name>/` and truth into `answers/<name>.json` (kept separate so test agents can't peek).
  - `goalcheck/c{1..4}/` — data (`f60.dat`, `f90.dat`), `run.conf`, group configs, logs.
  - `mockfit/` — bash mock `sk-run` used for the earlier orchestration GREEN test.
- Run a fit: `cd <scenario dir> && <venv>/bin/python3 /Users/donghanlee/work/projects/sherekhan/sk_run.py run.conf` — prints human tables plus strict-JSON blocks `##### model_comparison` and `##### jackknife`; residue toggling via `"residues": [{"name":"R1","flag":"on"|"off"}]` in the JSON conf. c1 run takes <1 s.

## Next steps
1. Nothing required — goal met. If the user wants more hardening, the untested spots are: Step 3 positive case (single-outlier contamination, cf. sherekhan `demo/multi` m1–m4 scenarios) and unequal group sizes / K-group + outlier combined.
2. If scratchpad is gone, recreate: `python3 -m venv venv && venv/bin/pip install numpy scipy matplotlib`, then rerun `make_goal_scenarios.py` (it hardcodes REPO=`/Users/donghanlee/work/projects/sherekhan` and writes relative to its own location).

## Open questions / risks
- The skill's Execution section assumes the runner supports parallel subagents (Claude Code Agent tool); on runtimes without it the skill still works but runs serially — unverified.
- Whether `~/.claude/skills/counting-residue-clusters` → `clustering` rename left any stale references elsewhere: none known, but only the skills dir itself was checked.
- Test-agent success used prompts that named the fit command and config format explicitly; skill relies on its "Setup" section to elicit these in real use — real-data ergonomics unverified.
