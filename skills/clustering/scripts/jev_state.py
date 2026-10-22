#!/usr/bin/env python3
"""Turn sk-run fit logs into a compact state for a jev cross-check.

    python3 jev_state.py fit-full.log [--groups fit-gA.log fit-gB.log ...] > state.json

Each log contributes one entry keyed by its file name. Per-residue rows are
sorted by chi2_glob descending (the contamination-proof ranking). Feed the
output as `state` to jev_ask together with references/jev-questions.json.
Undefined numbers are null; --groups must partition the full fit; errors exit 2.
"""

import json
import math
import os
import sys

# Mirrors the sk_run jackknife '*' flag: |delta_kex| > DELTA_KEX_SIGMA * se.
DELTA_KEX_SIGMA = 2.0
OUTPUT_INDENT = 1


class InputError(ValueError):
    """Bad user input; the CLI reports it as one line and exits 2."""


def read_block(text, name):
    tag = f"##### {name}\n"
    i = text.find(tag)
    if i < 0:
        return None
    line = text[i + len(tag) :].split("\n", 1)[0]
    return json.loads(line)


def finite_or_none(x, nd=None):
    """Round a finite number; undefined (None, nan, inf) becomes None."""
    if x is None or not math.isfinite(x):
        return None
    return round(x) if nd is None else round(x, nd)


def load_fit(path):
    try:
        with open(path) as fh:
            text = fh.read()
    except OSError as e:
        raise InputError(f"{path}: cannot read ({e.strerror})") from e

    def json_block(name):
        try:
            return read_block(text, name)
        except json.JSONDecodeError as e:
            raise InputError(f"{path}: malformed {name} block") from e

    mc = json_block("model_comparison")
    if mc is None:
        raise InputError(f"{path}: no model_comparison block")
    jk = json_block("jackknife") or {}
    g = mc["global"]
    n, k = g["n"], g["k"]
    kex = jk.get("kex_full")
    se = jk.get("se")
    rel_se = finite_or_none(100 * se / kex, 2) if kex and se is not None else None
    kex_global = kex or (mc["per_residue"][0].get("kex_global") if mc["per_residue"] else None)
    rows = [
        {
            "label": r["label"],
            "chi2_glob": finite_or_none(r["chi2_global"], 1),
            "chi2_indiv": finite_or_none(r["chi2"], 1),
            "dAICc": finite_or_none(r.get("delta_aicc"), 1),
            "z": finite_or_none(r.get("z_kex"), 1),
            "better": r["preferred"],
            "kex_indiv": finite_or_none(r.get("kex")),
        }
        for r in mc["per_residue"]
    ]
    rows.sort(key=lambda r: math.inf if r["chi2_glob"] is None else -r["chi2_glob"])
    return {
        "residues_on": [r["label"] for r in mc["per_residue"]],
        "global": {
            "chi2": finite_or_none(g["chi2"], 2),
            "k": k,
            "n": n,
            "red_chi2": None if n - k <= 0 else finite_or_none(g["chi2"] / (n - k), 3),
            "aicc": finite_or_none(g["aicc"], 1),
            "kex": finite_or_none(kex_global),
        },
        "individual": {
            "chi2": finite_or_none(mc["individual"]["chi2"], 2),
            "k": mc["individual"]["k"],
            "aicc": finite_or_none(mc["individual"]["aicc"], 1),
        },
        "preferred": mc["preferred"],
        "jackknife": {
            "rel_se_pct": rel_se,
            "influential": [
                r["label"]
                for r in jk.get("per_residue", [])
                if se and se > 0 and r.get("delta_kex") is not None
                and abs(r["delta_kex"]) > DELTA_KEX_SIGMA * se
            ],
        },
        "per_residue": rows,
    }


def aicc(chi2, k, n):
    if chi2 is None or n - k - 1 <= 0:
        return None
    return chi2 + 2 * k + 2 * k * (k + 1) / (n - k - 1)


def resolve_keys(paths):
    """Map each normalized input path to its state key (basename unless ambiguous)."""
    files = [os.path.normpath(p) for p in paths]
    for f in files:
        if files.count(f) > 1:
            raise InputError(f"duplicate input {f}")
    names = [f.rsplit(os.sep, 1)[-1] for f in files]
    return {f: nm if names.count(nm) == 1 else f for f, nm in zip(files, names)}


def check_partition(full, groups):
    """Group logs must partition the residues of the full fit and sum to its n."""
    seen = set()
    for g in groups:
        for r in g["residues_on"]:
            if r in seen:
                raise InputError(f"residue {r} appears in more than one group log")
            seen.add(r)
    full_set = set(full["residues_on"])
    if seen != full_set:
        raise InputError(
            f"groups must cover the full fit: missing {sorted(full_set - seen)}, "
            f"extra {sorted(seen - full_set)}"
        )
    n = full["global"]["n"]
    total = sum(g["global"]["n"] for g in groups)
    if total != n:
        raise InputError(f"group n sum {total} != full n {n}")


def hypothesis_entry(groups, n):
    """K-global hypothesis: chi2 summed over groups, k summed, aicc with the full n."""
    chi2 = None
    if all(g["global"]["chi2"] is not None for g in groups):
        chi2 = sum(g["global"]["chi2"] for g in groups)
    k = sum(g["global"]["k"] for g in groups)
    return {
        "chi2": finite_or_none(chi2, 2),
        "k": k,
        "n": n,
        "aicc": finite_or_none(aicc(chi2, k, n), 1),
        "shared_groups": sum(1 for g in groups if len(g["residues_on"]) >= 2),
        "individuals": sorted(
            g["residues_on"][0] for g in groups if len(g["residues_on"]) == 1
        ),
    }


def hypothesis_name(h, n_groups):
    """K{n}_global for shared clusters only; K{shared}_plus_individuals_global when
    single-residue groups are present, so the key matches the jev structure options."""
    if h["individuals"]:
        return f"K{h['shared_groups']}_plus_individuals_global"
    return f"K{n_groups}_global"


def build_state(paths, groups=()):
    """paths[0] is the full fit; `groups` are group-fit logs of ONE K-global hypothesis."""
    key = resolve_keys(list(paths) + list(groups))
    files = list(key)
    state = {key[f]: load_fit(f) for f in files}
    full = state[key[files[0]]]
    n = full["global"]["n"]  # total n, identical in every hypothesis
    hyp = {
        "K1_global": {"aicc": full["global"]["aicc"]},
        "individual": {"aicc": full["individual"]["aicc"]},
    }
    if groups:
        gs = [state[key[f]] for f in files[len(paths) :]]
        check_partition(full, gs)
        h = hypothesis_entry(gs, n)
        hyp[hypothesis_name(h, len(gs))] = h
    state[f"hypotheses_total_n_{n}"] = hyp
    return state


def _selfcheck():
    import tempfile

    def put(path, text):
        with open(path, "w") as fh:
            fh.write(text)

    def log_text(mc, jk=None):
        text = f"##### model_comparison\n{json.dumps(mc)}\n"
        if jk is not None:
            text += f"##### jackknife\n{json.dumps(jk)}\n"
        return text + "#####\n"

    def write_log(path, mc, jk=None):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        put(path, log_text(mc, jk))
        return path

    def group(path, labels, n):
        rows = [
            {"label": L, "chi2_global": 30.0, "chi2": 10.0, "delta_aicc": 0.0,
             "z_kex": 0.0, "preferred": "individual", "kex": 1.0}
            for L in labels
        ]
        m = {
            "global": {"chi2": 100.0, "k": 10, "n": n, "aicc": 130.0},
            "individual": {"chi2": 50.0, "k": 20, "aicc": 100.0},
            "preferred": "individual",
            "per_residue": rows,
        }
        return write_log(path, m)

    mc = {
        "global": {"chi2": 100.0, "k": 10, "n": 60, "aicc": 130.0},
        "individual": {"chi2": 50.0, "k": 20, "aicc": 100.0},
        "preferred": "individual",
        "per_residue": [
            {
                "label": "R1",
                "chi2_global": 30.0,
                "chi2": 10.0,
                "delta_aicc": -5.0,
                "z_kex": 2.5,
                "preferred": "individual",
                "kex": 500.0,
            },
            {
                "label": "R2",
                "chi2_global": 70.0,
                "chi2": 40.0,
                "delta_aicc": 1.0,
                "z_kex": -0.1,
                "preferred": "global",
                "kex": 1000.0,
            },
        ],
    }
    jk = {"kex_full": 800.0, "se": 40.0, "per_residue": []}
    null_mc = {
        "global": {"chi2": None, "k": 60, "n": 60, "aicc": None},
        "individual": {"chi2": 50.0, "k": 20, "aicc": 100.0},
        "preferred": "individual",
        "per_residue": [
            {
                "label": "R1",
                "chi2_global": None,
                "chi2": None,
                "delta_aicc": None,
                "preferred": "individual",
                "kex": None,
            }
        ],
    }
    null_jk = {"kex_full": None, "se": None, "per_residue": []}
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "fit-x.log")
        put(p, "junk\n" + log_text(mc, jk))
        s = build_state([p], [group(os.path.join(d, "fit-g1.log"), ["R1"], 30),
                              group(os.path.join(d, "fit-g2.log"), ["R2"], 30)])
        q = write_log(os.path.join(d, "fit-null.log"), null_mc, null_jk)
        t = build_state([q])
    e = s["fit-x.log"]
    assert e["global"]["red_chi2"] == 2.0 and e["jackknife"]["rel_se_pct"] == 5.0
    assert [r["label"] for r in e["per_residue"]] == ["R2", "R1"]
    h = s["hypotheses_total_n_60"]["K0_plus_individuals_global"]
    assert "K2_global" not in s["hypotheses_total_n_60"]
    assert h == {"chi2": 200.0, "k": 20, "n": 60, "aicc": round(aicc(200, 20, 60), 1),
                 "shared_groups": 0, "individuals": ["R1", "R2"]}
    with tempfile.TemporaryDirectory() as d:
        mc3 = dict(mc, per_residue=mc["per_residue"] + [dict(mc["per_residue"][0], label="R3")])
        full3 = write_log(os.path.join(d, "f3", "fit.log"), mc3)
        ga = group(os.path.join(d, "ga", "fit.log"), ["R1", "R2"], 40)
        gb = group(os.path.join(d, "gb", "fit.log"), ["R3"], 20)
        hyp3 = build_state([full3], [ga, gb])["hypotheses_total_n_60"]
        gc = group(os.path.join(d, "gc", "fit.log"), ["R3"], 20)
        ga2 = group(os.path.join(d, "ga2", "fit.log"), ["R1"], 20)
        gb2 = group(os.path.join(d, "gb2", "fit.log"), ["R2"], 20)
        assert "K3_plus_individuals_global" not in build_state([full3], [ga2, gb2, gc])["hypotheses_total_n_60"]
    h3 = hyp3["K1_plus_individuals_global"]
    assert "K2_global" not in hyp3
    assert h3["shared_groups"] == 1 and h3["individuals"] == ["R3"]
    assert hypothesis_name({"shared_groups": 2, "individuals": []}, 2) == "K2_global"
    assert hypothesis_name({"shared_groups": 2, "individuals": ["R5"]}, 3) == "K2_plus_individuals_global"
    with tempfile.TemporaryDirectory() as d:
        with_nl = write_log(os.path.join(d, "fit-eof.log"), mc)
        no_nl = os.path.join(d, "fit-eof-nonl.log")
        put(no_nl, "##### model_comparison\n" + json.dumps(mc))
        for p in (no_nl, with_nl):
            with open(p) as fh:
                assert read_block(fh.read(), "model_comparison") == mc
    assert aicc(10, 5, 6) is None
    infl = {"kex_full": 800.0, "se": 40.0, "per_residue": [
        {"label": "R1", "delta_kex": 100.0}, {"label": "R2", "delta_kex": -81.0},
        {"label": "R3", "delta_kex": 80.0}]}
    flat = dict(infl, se=0.0)
    with tempfile.TemporaryDirectory() as d:
        i_path = write_log(os.path.join(d, "fit-infl.log"), mc, infl)
        f_path = write_log(os.path.join(d, "fit-flat.log"), mc, flat)
        i = build_state([i_path])["fit-infl.log"]["jackknife"]["influential"]
        f = build_state([f_path])["fit-flat.log"]["jackknife"]["influential"]
    assert i == ["R1", "R2"] and f == []
    def kex_of(m, jk_):
        with tempfile.TemporaryDirectory() as d:
            p_ = write_log(os.path.join(d, "fit-kx.log"), m, jk_)
            return build_state([p_])["fit-kx.log"]["global"]["kex"]

    rp = mc["per_residue"][0]
    assert kex_of(dict(mc, per_residue=[dict(rp, kex_global=2488.6)]), None) == 2489
    assert kex_of(dict(mc, per_residue=[dict(rp, kex_global=801.0)]), jk) == 800
    z = t["fit-null.log"]
    row = z["per_residue"][0]
    assert row["z"] is None and row["dAICc"] is None and row["chi2_glob"] is None
    assert z["global"]["aicc"] is None and z["global"]["red_chi2"] is None
    assert z["jackknife"]["rel_se_pct"] is None
    json.dumps(t, allow_nan=False)

    def raises(f):
        try:
            f()
        except InputError as e:
            return str(e)
        raise AssertionError("expected InputError")

    with tempfile.TemporaryDirectory() as d:
        full = write_log(os.path.join(d, "full", "fit.log"), mc)
        g1 = group(os.path.join(d, "g1", "fit.log"), ["R1"], 30)
        g2 = group(os.path.join(d, "g2", "fit.log"), ["R2"], 30)
        s = build_state([full], [g1, g2])
        assert set(s) == {full, g1, g2, "hypotheses_total_n_60"}
        assert s["hypotheses_total_n_60"]["K0_plus_individuals_global"]["chi2"] == 200.0
        assert "duplicate input" in raises(lambda: build_state([full], [full]))
        ov = group(os.path.join(d, "ov", "fit.log"), ["R1", "R2"], 30)
        assert "more than one group" in raises(lambda: build_state([full], [ov, g1]))
        assert "missing ['R2']" in raises(lambda: build_state([full], [g1]))
        n40 = group(os.path.join(d, "n40", "fit.log"), ["R2"], 40)
        assert "group n sum 70 != full n 60" in raises(lambda: build_state([full], [g1, n40]))
        bad = os.path.join(d, "bad", "fit.log")
        os.makedirs(os.path.dirname(bad))
        put(bad, "##### model_comparison\n{not json\n#####\n")  # deliberately malformed
        assert "malformed model_comparison block" in raises(lambda: build_state([bad]))
        none = os.path.join(d, "none", "fit.log")
        os.makedirs(os.path.dirname(none))
        put(none, "junk\n")  # deliberately has no model_comparison block
        assert "no model_comparison block" in raises(lambda: build_state([none]))
    print("selfcheck ok")


USAGE = __doc__ + "\n  --groups fit-gA.log fit-gB.log   add K-global total AICc with total n\n"


def parse_argv(args):
    """Split argv into (paths, groups); raises InputError on a bad --groups position."""
    i = args.index("--groups") if "--groups" in args else len(args)
    if i == 0:
        raise InputError("full-fit log required before --groups")
    if i == len(args) - 1 and args[i] == "--groups":
        raise InputError("--groups needs at least one log")
    return args[:i], args[i + 1 :]


def main(argv):
    if argv == ["--selfcheck"]:
        _selfcheck()
        return 0
    if "-h" in argv or "--help" in argv:
        print(USAGE, end="")
        return 0
    if not argv:
        print(USAGE, end="", file=sys.stderr)
        return 2
    try:
        paths, groups = parse_argv(argv)
        print(json.dumps(build_state(paths, groups), indent=OUTPUT_INDENT))
    except InputError as e:
        print(f"jev_state: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
