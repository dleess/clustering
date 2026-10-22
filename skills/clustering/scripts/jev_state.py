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


class InputError(ValueError):
    """Bad user input; the CLI reports it as one line and exits 2."""


def block(text, name):
    tag = f"##### {name}\n"
    i = text.find(tag)
    if i < 0:
        return None
    j = text.find("\n", i + len(tag))
    return json.loads(text[i + len(tag) : j])


def _r(x, nd=None):
    """Round a finite number; undefined (None, nan, inf) becomes None."""
    if x is None or not math.isfinite(x):
        return None
    return round(x) if nd is None else round(x, nd)


def entry(path):
    try:
        with open(path) as fh:
            text = fh.read()
    except OSError as e:
        raise InputError(f"{path}: cannot read ({e.strerror})") from e

    def json_block(name):
        try:
            return block(text, name)
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
    rel_se = _r(100 * se / kex, 2) if kex and se is not None else None
    rows = [
        {
            "label": r["label"],
            "chi2_glob": _r(r["chi2_global"], 1),
            "chi2_indiv": _r(r["chi2"], 1),
            "dAICc": _r(r.get("delta_aicc"), 1),
            "z": _r(r.get("z_kex"), 1),
            "better": r["preferred"],
            "kex_indiv": _r(r.get("kex")),
        }
        for r in mc["per_residue"]
    ]
    rows.sort(key=lambda r: math.inf if r["chi2_glob"] is None else -r["chi2_glob"])
    return {
        "residues_on": [r["label"] for r in mc["per_residue"]],
        "global": {
            "chi2": _r(g["chi2"], 2),
            "k": k,
            "n": n,
            "red_chi2": None if n - k <= 0 else _r(g["chi2"] / (n - k), 3),
            "aicc": _r(g["aicc"], 1),
            "kex": _r(kex) if kex else None,
        },
        "individual": {
            "chi2": _r(mc["individual"]["chi2"], 2),
            "k": mc["individual"]["k"],
            "aicc": _r(mc["individual"]["aicc"], 1),
        },
        "preferred": mc["preferred"],
        "jackknife": {
            "rel_se_pct": rel_se,
            "influential": [
                r["label"]
                for r in jk.get("per_residue", [])
                if se and se > 0 and r.get("delta_kex") is not None
                and abs(r["delta_kex"]) > 2.0 * se
            ],
        },
        "per_residue": rows,
    }


def aicc(chi2, k, n):
    if chi2 is None or n - k - 1 <= 0:
        return None
    return chi2 + 2 * k + 2 * k * (k + 1) / (n - k - 1)


def main(paths, groups=()):
    """paths[0] is the full fit; `groups` are group-fit logs of ONE K-global hypothesis."""
    files = [os.path.normpath(p) for p in list(paths) + list(groups)]
    for f in files:
        if files.count(f) > 1:
            raise InputError(f"duplicate input {f}")
    names = [f.rsplit(os.sep, 1)[-1] for f in files]
    key = {f: nm if names.count(nm) == 1 else f for f, nm in zip(files, names)}
    state = {key[f]: entry(f) for f in files}
    full = state[key[files[0]]]
    n = full["global"]["n"]  # total n, identical in every hypothesis
    hyp = {
        "K1_global": {"aicc": full["global"]["aicc"]},
        "individual": {"aicc": full["individual"]["aicc"]},
    }
    if groups:
        gs = [state[key[f]] for f in files[len(paths) :]]
        seen = set()
        for g in gs:
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
        if sum(g["global"]["n"] for g in gs) != n:
            raise InputError(
                f"group n sum {sum(g['global']['n'] for g in gs)} != full n {n}"
            )
        chi2 = None
        if all(g["global"]["chi2"] is not None for g in gs):
            chi2 = sum(g["global"]["chi2"] for g in gs)
        k = sum(g["global"]["k"] for g in gs)
        hyp[f"K{len(gs)}_global"] = {
            "chi2": _r(chi2, 2),
            "k": k,
            "n": n,
            "aicc": _r(aicc(chi2, k, n), 1),
        }
    state[f"hypotheses_total_n_{n}"] = hyp
    return state


def _selfcheck():
    import tempfile

    def put(path, text):
        with open(path, "w") as fh:
            fh.write(text)

    def write_log(path, m):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        put(path, f"##### model_comparison\n{json.dumps(m)}\n#####\n")
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
        put(p, 
            f"junk\n##### model_comparison\n{json.dumps(mc)}\n##### jackknife\n{json.dumps(jk)}\n#####\n"
        )
        s = main([p], [group(os.path.join(d, "fit-g1.log"), ["R1"], 30),
                       group(os.path.join(d, "fit-g2.log"), ["R2"], 30)])
        q = os.path.join(d, "fit-null.log")
        put(q, 
            f"##### model_comparison\n{json.dumps(null_mc)}\n##### jackknife\n{json.dumps(null_jk)}\n#####\n"
        )
        t = main([q])
    e = s["fit-x.log"]
    assert e["global"]["red_chi2"] == 2.0 and e["jackknife"]["rel_se_pct"] == 5.0
    assert [r["label"] for r in e["per_residue"]] == ["R2", "R1"]
    h = s["hypotheses_total_n_60"]["K2_global"]
    assert h == {"chi2": 200.0, "k": 20, "n": 60, "aicc": round(aicc(200, 20, 60), 1)}
    assert aicc(10, 5, 6) is None
    infl = {"kex_full": 800.0, "se": 40.0, "per_residue": [
        {"label": "R1", "delta_kex": 100.0}, {"label": "R2", "delta_kex": -81.0},
        {"label": "R3", "delta_kex": 80.0}]}
    flat = dict(infl, se=0.0)
    with tempfile.TemporaryDirectory() as d:
        for name, jkb in (("fit-infl.log", infl), ("fit-flat.log", flat)):
            p = os.path.join(d, name)
            put(p, 
                f"##### model_comparison\n{json.dumps(mc)}\n##### jackknife\n{json.dumps(jkb)}\n#####\n"
            )
        i = main([os.path.join(d, "fit-infl.log")])["fit-infl.log"]["jackknife"]["influential"]
        f = main([os.path.join(d, "fit-flat.log")])["fit-flat.log"]["jackknife"]["influential"]
    assert i == ["R1", "R2"] and f == []
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
        s = main([full], [g1, g2])
        assert set(s) == {full, g1, g2, "hypotheses_total_n_60"}
        assert s["hypotheses_total_n_60"]["K2_global"]["chi2"] == 200.0
        assert "duplicate input" in raises(lambda: main([full], [full]))
        ov = group(os.path.join(d, "ov", "fit.log"), ["R1", "R2"], 30)
        assert "more than one group" in raises(lambda: main([full], [ov, g1]))
        assert "missing ['R2']" in raises(lambda: main([full], [g1]))
        n40 = group(os.path.join(d, "n40", "fit.log"), ["R2"], 40)
        assert "group n sum 70 != full n 60" in raises(lambda: main([full], [g1, n40]))
        bad = os.path.join(d, "bad", "fit.log")
        os.makedirs(os.path.dirname(bad))
        put(bad, "##### model_comparison\n{not json\n#####\n")
        assert "malformed model_comparison block" in raises(lambda: main([bad]))
        none = os.path.join(d, "none", "fit.log")
        os.makedirs(os.path.dirname(none))
        put(none, "junk\n")
        assert "no model_comparison block" in raises(lambda: main([none]))
    print("selfcheck ok")


USAGE = __doc__ + "\n  --groups fit-gA.log fit-gB.log   add K-global total AICc with total n\n"

if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["--selfcheck"]:
        _selfcheck()
    elif "-h" in args or "--help" in args:
        print(USAGE, end="")
    elif not args:
        print(USAGE, end="", file=sys.stderr)
        sys.exit(2)
    else:
        try:
            i = args.index("--groups") if "--groups" in args else len(args)
            if i == 0:
                raise InputError("full-fit log required before --groups")
            if i == len(args) - 1 and args[i] == "--groups":
                raise InputError("--groups needs at least one log")
            print(json.dumps(main(args[:i], args[i + 1 :]), indent=1))
        except InputError as e:
            print(f"jev_state: {e}", file=sys.stderr)
            sys.exit(2)
