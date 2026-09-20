#!/usr/bin/env python3
"""Turn sk-run fit logs into a compact state for a jev cross-check.

    python3 jev_state.py fit-full.log [fit-gA.log ...] > state.json

Each log contributes one entry keyed by its file name. Per-residue rows are
sorted by chi2_glob descending (the contamination-proof ranking). Feed the
output as `state` to jev_ask together with references/jev-questions.json.
"""

import json
import math
import sys


def block(text, name):
    tag = f"##### {name}\n"
    i = text.find(tag)
    if i < 0:
        return None
    j = text.find("\n", i + len(tag))
    return json.loads(text[i + len(tag) : j])


def entry(path):
    text = open(path).read()
    mc = block(text, "model_comparison")
    if mc is None:
        raise SystemExit(f"{path}: no model_comparison block")
    jk = block(text, "jackknife") or {}
    g = mc["global"]
    n, k = g["n"], g["k"]
    kex = jk.get("kex_full")
    rel_se = round(100 * jk["se"] / kex, 2) if kex else None
    rows = [
        {
            "label": r["label"],
            "chi2_glob": round(r["chi2_global"], 1),
            "chi2_indiv": round(r["chi2"], 1),
            "dAICc": round(r["delta_aicc"], 1),
            "z": round(r.get("z_kex", math.nan), 1),
            "better": r["preferred"],
            "kex_indiv": round(r["kex"]),
        }
        for r in mc["per_residue"]
    ]
    rows.sort(key=lambda r: -r["chi2_glob"])
    return {
        "residues_on": [r["label"] for r in mc["per_residue"]],
        "global": {
            "chi2": round(g["chi2"], 2),
            "k": k,
            "n": n,
            "red_chi2": round(g["chi2"] / (n - k), 3),
            "aicc": round(g["aicc"], 1),
            "kex": round(kex) if kex else None,
        },
        "individual": {
            "chi2": round(mc["individual"]["chi2"], 2),
            "k": mc["individual"]["k"],
            "aicc": round(mc["individual"]["aicc"], 1),
        },
        "preferred": mc["preferred"],
        "jackknife": {
            "rel_se_pct": rel_se,
            "influential": [
                r["label"] for r in jk.get("per_residue", []) if r.get("influential")
            ],
        },
        "per_residue": rows,
    }


def aicc(chi2, k, n):
    return chi2 + 2 * k + 2 * k * (k + 1) / (n - k - 1)


def main(paths, groups=()):
    """paths[0] is the full fit; `groups` are group-fit logs of ONE K-global hypothesis."""
    state = {p.rsplit("/", 1)[-1]: entry(p) for p in list(paths) + list(groups)}
    full = state[paths[0].rsplit("/", 1)[-1]]
    n = full["global"]["n"]  # total n, identical in every hypothesis
    hyp = {
        "K1_global": {"aicc": full["global"]["aicc"]},
        "individual": {"aicc": full["individual"]["aicc"]},
    }
    if groups:
        gs = [state[g.rsplit("/", 1)[-1]] for g in groups]
        chi2 = sum(g["global"]["chi2"] for g in gs)
        k = sum(g["global"]["k"] for g in gs)
        hyp[f"K{len(gs)}_global"] = {
            "chi2": round(chi2, 2),
            "k": k,
            "n": n,
            "aicc": round(aicc(chi2, k, n), 1),
        }
    state[f"hypotheses_total_n_{n}"] = hyp
    return state


def _selfcheck():
    import os, tempfile

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
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "fit-x.log")
        open(p, "w").write(
            f"junk\n##### model_comparison\n{json.dumps(mc)}\n##### jackknife\n{json.dumps(jk)}\n#####\n"
        )
        s = main([p], [p, p])
    e = s["fit-x.log"]
    assert e["global"]["red_chi2"] == 2.0 and e["jackknife"]["rel_se_pct"] == 5.0
    assert [r["label"] for r in e["per_residue"]] == ["R2", "R1"]
    h = s["hypotheses_total_n_60"]["K2_global"]
    assert h == {"chi2": 200.0, "k": 20, "n": 60, "aicc": round(aicc(200, 20, 60), 1)}
    print("selfcheck ok")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["--selfcheck"]:
        _selfcheck()
    elif not args:
        raise SystemExit(
            __doc__
            + "\n  --groups fit-gA.log fit-gB.log   add K-global total AICc with total n\n"
        )
    else:
        i = args.index("--groups") if "--groups" in args else len(args)
        print(json.dumps(main(args[:i], args[i + 1 :]), indent=1))
