"""ISC-21: bootstrap confidence intervals per model per category.

Reads the real per-sample judge labels straight out of results/full_run/*.eval
(same approach as scripts/summarize_full_run.py, since inspect_ai's own
built-in rate metrics are broken for this scorer, see ISA.md Decisions
2026-09-19). For each (model, category) pair, computes single turn and multi
turn REFUSED rate and COMPLIED rate, the multi minus single delta for both,
and a bootstrap confidence interval on each delta.

Per category n is 3 chains (15 chains / 5 categories), so per (model,
category) confidence intervals are necessarily very wide - this is expected
and consistent with ISC-38's exploratory, not significance tested, framing,
not a bug in the bootstrap. A secondary, tighter per-model (n=15, all
categories pooled) table is also written, since that is the level at which
the headline finding (ISA.md Changelog, 2026-09-19) is actually defensible.

Usage:
    python3 scripts/bootstrap_ci.py
"""

from collections import defaultdict
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

MODEL_SHORT_NAMES = {
    "openai-api/deepinfra/meta-llama/Llama-3.3-70B-Instruct": "llama-3.3-70b",
    "openai-api/deepinfra/Qwen/Qwen2.5-72B-Instruct": "qwen-2.5-72b",
    "openai-api/deepinfra/openai/gpt-oss-120b": "gpt-oss-120b",
}


def load_rows() -> pd.DataFrame:
    rows = []
    for path in sorted(LOG_DIR.glob("*.eval")):
        log = read_eval_log(str(path))
        variant = "single_turn" if "single-turn" in log.eval.task else "multi_turn"
        model = MODEL_SHORT_NAMES.get(log.eval.model, log.eval.model)
        for sample in log.samples or []:
            score = sample.scores.get("refusal_judge") if sample.scores else None
            if score is None:
                continue
            rows.append(
                {
                    "model": model,
                    "variant": variant,
                    "category": score.metadata.get("category"),
                    "chain_id": score.metadata.get("chain_id"),
                    "label": score.value,
                }
            )
    return pd.DataFrame(rows)


def rate(labels: list[str], target: str) -> float:
    if not labels:
        return float("nan")
    return sum(1 for label in labels if label == target) / len(labels)


def bootstrap_delta_ci(
    single: list[str], multi: list[str], target: str, rng: np.random.Generator
) -> tuple[float, float]:
    """Percentile bootstrap CI on (multi rate - single rate) for one label."""
    single_arr = np.array([1 if x == target else 0 for x in single])
    multi_arr = np.array([1 if x == target else 0 for x in multi])
    deltas = np.empty(N_BOOTSTRAP)
    for i in range(N_BOOTSTRAP):
        s_sample = rng.choice(single_arr, size=len(single_arr), replace=True)
        m_sample = rng.choice(multi_arr, size=len(multi_arr), replace=True)
        deltas[i] = m_sample.mean() - s_sample.mean()
    lo, hi = np.percentile(deltas, [CI_LOW, CI_HIGH])
    return float(lo), float(hi)


def build_table(df: pd.DataFrame, group_cols: list[str], rng: np.random.Generator) -> pd.DataFrame:
    out_rows = []
    for key, group in df.groupby(group_cols):
        key = key if isinstance(key, tuple) else (key,)
        single = group[group["variant"] == "single_turn"]["label"].tolist()
        multi = group[group["variant"] == "multi_turn"]["label"].tolist()
        refused_single, refused_multi = rate(single, "REFUSED"), rate(multi, "REFUSED")
        complied_single, complied_multi = rate(single, "COMPLIED"), rate(multi, "COMPLIED")
        refused_lo, refused_hi = bootstrap_delta_ci(single, multi, "REFUSED", rng)
        complied_lo, complied_hi = bootstrap_delta_ci(single, multi, "COMPLIED", rng)
        row = dict(zip(group_cols, key))
        row.update(
            {
                "n_single": len(single),
                "n_multi": len(multi),
                "refused_rate_single": round(refused_single, 3),
                "refused_rate_multi": round(refused_multi, 3),
                "refused_rate_delta": round(refused_multi - refused_single, 3),
                "refused_rate_delta_ci_low": round(refused_lo, 3),
                "refused_rate_delta_ci_high": round(refused_hi, 3),
                "complied_rate_single": round(complied_single, 3),
                "complied_rate_multi": round(complied_multi, 3),
                "complied_rate_delta": round(complied_multi - complied_single, 3),
                "complied_rate_delta_ci_low": round(complied_lo, 3),
                "complied_rate_delta_ci_high": round(complied_hi, 3),
            }
        )
        out_rows.append(row)
    return pd.DataFrame(out_rows)


if __name__ == "__main__":
    rng = np.random.default_rng(SEED)
    df = load_rows()
    assert len(df) == 90, f"expected 90 rows, got {len(df)}"

    per_category = build_table(df, ["model", "category"], rng)
    per_category = per_category.sort_values(["model", "category"]).reset_index(drop=True)
    per_category.to_csv(OUT_PER_CATEGORY, index=False)
    print(f"wrote {OUT_PER_CATEGORY} ({len(per_category)} rows, expected 15)")

    per_model = build_table(df, ["model"], rng)
    per_model = per_model.sort_values("model").reset_index(drop=True)
    per_model.to_csv(OUT_PER_MODEL, index=False)
    print(f"wrote {OUT_PER_MODEL} ({len(per_model)} rows, expected 3)")

    print()
    print(per_model.to_string(index=False))
