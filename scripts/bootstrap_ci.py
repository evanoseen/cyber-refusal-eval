"""ISC-21: confidence intervals per model per category.

Reads the real per-sample judge labels straight out of results/full_run/*.eval
(same approach as scripts/summarize_full_run.py, since inspect_ai's own
built-in rate metrics are broken for this scorer, see ISA.md Decisions
2026-09-19). For each (model, category) pair, computes single turn and multi
turn REFUSED rate and COMPLIED rate, and the multi minus single delta for
both.

Each rate gets a Wilson score interval, not a percentile bootstrap. A
percentile bootstrap on a rate that sits at or near 0% or 100% collapses to a
zero width interval (every resample is identical), which understates
uncertainty at exactly the small n, extreme rate regime this project runs in.
Wilson intervals do not have that failure mode.

Each delta (multi rate minus single rate) gets a paired bootstrap: every
chain has a single turn and a multi turn outcome from the same underlying
request, so resampling must draw whole chains, not single turn and multi
turn observations independently, or the resampling ignores that the two
observations come from the same chain and overstates how independent they
are. See scripts/mcnemar_test.py for the paired significance test this
project actually reports on COMPLIED; these deltas and their intervals are
the descriptive companion to that test, not a substitute for it.

Per category n is 3 chains (15 chains / 5 categories), so per (model,
category) confidence intervals are necessarily very wide - this is expected
and consistent with ISC-38's exploratory, not significance tested, framing,
not a bug in the analysis. A secondary, tighter per-model (n=15, all
categories pooled) table is also written, since that is the level at which
the headline finding (ISA.md Changelog, 2026-09-19) is actually defensible.

Usage:
    python3 scripts/bootstrap_ci.py
"""

from collections import defaultdict
from math import sqrt
from pathlib import Path

import numpy as np
import pandas as pd

from inspect_ai.log import read_eval_log

LOG_DIR = Path(__file__).resolve().parent.parent / "results" / "full_run"
OUT_PER_CATEGORY = Path(__file__).resolve().parent.parent / "results" / "bootstrap.csv"
OUT_PER_MODEL = Path(__file__).resolve().parent.parent / "results" / "bootstrap_by_model.csv"

N_BOOTSTRAP = 10_000
CI_LOW, CI_HIGH = 2.5, 97.5
SEED = 20260919
Z_95 = 1.959964

MODEL_SHORT_NAMES = {
    "openai-api/deepinfra/meta-llama/Llama-3.3-70B-Instruct": "llama-3.3-70b",
    "openai-api/deepinfra/Qwen/Qwen2.5-72B-Instruct": "qwen-2.5-72b",
    "openai-api/deepinfra/openai/gpt-oss-120b": "gpt-oss-120b",
}


def load_paired_rows() -> dict[tuple[str, str], dict[str, dict[str, str]]]:
    """(model, category) -> chain_id -> {"single": label, "multi": label}."""
    data: dict[tuple[str, str], dict[str, dict[str, str]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    for path in sorted(LOG_DIR.glob("*.eval")):
        log = read_eval_log(str(path))
        variant = "single" if "single-turn" in log.eval.task else "multi"
        model = MODEL_SHORT_NAMES.get(log.eval.model, log.eval.model)
        for sample in log.samples or []:
            score = sample.scores.get("refusal_judge") if sample.scores else None
            if score is None:
                continue
            category = score.metadata.get("category")
            chain_id = score.metadata.get("chain_id")
            data[(model, category)][chain_id][variant] = score.value
    return data


def wilson_interval(k: int, n: int, z: float = Z_95) -> tuple[float, float]:
    """Wilson score interval for a single proportion k/n."""
    if n == 0:
        return float("nan"), float("nan")
    p_hat = k / n
    denom = 1 + z**2 / n
    center = (p_hat + z**2 / (2 * n)) / denom
    half_width = z * sqrt(p_hat * (1 - p_hat) / n + z**2 / (4 * n**2)) / denom
    return max(0.0, center - half_width), min(1.0, center + half_width)


def paired_bootstrap_delta_ci(
    single_labels: list[str], multi_labels: list[str], target: str, rng: np.random.Generator
) -> tuple[float, float]:
    """Percentile bootstrap CI on (multi rate - single rate), resampling chains.

    single_labels[i] and multi_labels[i] must already be the same chain's two
    outcomes, in matching order. Each bootstrap draw resamples chain indices
    with replacement, then applies that same draw of indices to both lists,
    preserving the pairing instead of resampling each variant independently.
    """
    n = len(single_labels)
    single_arr = np.array([1 if x == target else 0 for x in single_labels])
    multi_arr = np.array([1 if x == target else 0 for x in multi_labels])
    deltas = np.empty(N_BOOTSTRAP)
    for i in range(N_BOOTSTRAP):
        idx = rng.integers(0, n, size=n)
        deltas[i] = multi_arr[idx].mean() - single_arr[idx].mean()
    lo, hi = np.percentile(deltas, [CI_LOW, CI_HIGH])
    return float(lo), float(hi)


def build_table(
    paired: dict[tuple[str, str], dict[str, dict[str, str]]],
    group_by_category: bool,
    rng: np.random.Generator,
) -> pd.DataFrame:
    # Re-group by model alone when group_by_category is False, merging every
    # category's chains for that model into one paired chain list.
    merged: dict[tuple, dict[str, dict[str, str]]] = defaultdict(dict)
    for (model, category), chains in paired.items():
        key = (model, category) if group_by_category else (model,)
        merged[key].update(chains)

    rows = []
    for key, chains in merged.items():
        chain_ids = sorted(chains)
        single_labels = [chains[c]["single"] for c in chain_ids]
        multi_labels = [chains[c]["multi"] for c in chain_ids]
        n = len(chain_ids)

        refused_single_k = sum(1 for label in single_labels if label == "REFUSED")
        refused_multi_k = sum(1 for label in multi_labels if label == "REFUSED")
        complied_single_k = sum(1 for label in single_labels if label == "COMPLIED")
        complied_multi_k = sum(1 for label in multi_labels if label == "COMPLIED")

        refused_single_rate = refused_single_k / n
        refused_multi_rate = refused_multi_k / n
        complied_single_rate = complied_single_k / n
        complied_multi_rate = complied_multi_k / n

        refused_single_wilson = wilson_interval(refused_single_k, n)
        refused_multi_wilson = wilson_interval(refused_multi_k, n)
        complied_single_wilson = wilson_interval(complied_single_k, n)
        complied_multi_wilson = wilson_interval(complied_multi_k, n)

        refused_delta_ci = paired_bootstrap_delta_ci(single_labels, multi_labels, "REFUSED", rng)
        complied_delta_ci = paired_bootstrap_delta_ci(single_labels, multi_labels, "COMPLIED", rng)

        row = dict(zip(["model", "category"] if group_by_category else ["model"], key))
        row.update(
            {
                "n_chains": n,
                "refused_rate_single": round(refused_single_rate, 3),
                "refused_rate_single_wilson_low": round(refused_single_wilson[0], 3),
                "refused_rate_single_wilson_high": round(refused_single_wilson[1], 3),
                "refused_rate_multi": round(refused_multi_rate, 3),
                "refused_rate_multi_wilson_low": round(refused_multi_wilson[0], 3),
                "refused_rate_multi_wilson_high": round(refused_multi_wilson[1], 3),
                "refused_rate_delta": round(refused_multi_rate - refused_single_rate, 3),
                "refused_rate_delta_ci_low": round(refused_delta_ci[0], 3),
                "refused_rate_delta_ci_high": round(refused_delta_ci[1], 3),
                "complied_rate_single": round(complied_single_rate, 3),
                "complied_rate_single_wilson_low": round(complied_single_wilson[0], 3),
                "complied_rate_single_wilson_high": round(complied_single_wilson[1], 3),
                "complied_rate_multi": round(complied_multi_rate, 3),
                "complied_rate_multi_wilson_low": round(complied_multi_wilson[0], 3),
                "complied_rate_multi_wilson_high": round(complied_multi_wilson[1], 3),
                "complied_rate_delta": round(complied_multi_rate - complied_single_rate, 3),
                "complied_rate_delta_ci_low": round(complied_delta_ci[0], 3),
                "complied_rate_delta_ci_high": round(complied_delta_ci[1], 3),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    rng = np.random.default_rng(SEED)
    paired = load_paired_rows()
    total_chains = sum(len(chains) for chains in paired.values())
    assert total_chains == 45, f"expected 3 models x 15 chains = 45 total, got {total_chains}"

    per_category = build_table(paired, group_by_category=True, rng=rng)
    per_category = per_category.sort_values(["model", "category"]).reset_index(drop=True)
    per_category.to_csv(OUT_PER_CATEGORY, index=False)
    print(f"wrote {OUT_PER_CATEGORY} ({len(per_category)} rows, expected 15)")

    per_model = build_table(paired, group_by_category=False, rng=rng)
    per_model = per_model.sort_values("model").reset_index(drop=True)
    per_model.to_csv(OUT_PER_MODEL, index=False)
    print(f"wrote {OUT_PER_MODEL} ({len(per_model)} rows, expected 3)")

    print()
    print(per_model.to_string(index=False))
