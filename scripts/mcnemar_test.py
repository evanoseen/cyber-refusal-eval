"""Exact McNemar test per model on COMPLIED, single turn vs multi turn, paired by chain.

Percentile bootstrap on independently resampled single and multi turn samples
(scripts/bootstrap_ci.py's original method) throws away the pairing: each
chain has a single turn and a multi turn outcome from the SAME underlying
request, so the natural test is a paired one on the discordant pairs, exactly
what McNemar's test is for. Reports the exact binomial McNemar p value per
model (appropriate at this sample size, not the chi square approximation),
plus which direction the discordant pairs run.

Usage:
    python3 scripts/mcnemar_test.py
"""

from collections import defaultdict
from math import comb
from pathlib import Path

from inspect_ai.log import read_eval_log

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = REPO_ROOT / "results" / "full_run"
OUT_PATH = REPO_ROOT / "results" / "mcnemar.csv"

MODEL_SHORT_NAMES = {
    "openai-api/deepinfra/meta-llama/Llama-3.3-70B-Instruct": "llama-3.3-70b",
    "openai-api/deepinfra/Qwen/Qwen2.5-72B-Instruct": "qwen-2.5-72b",
    "openai-api/deepinfra/openai/gpt-oss-120b": "gpt-oss-120b",
}

MODEL_ORDER = ["gpt-oss-120b", "llama-3.3-70b", "qwen-2.5-72b"]


def mcnemar_exact(b: int, c: int) -> float:
    """Two sided exact binomial McNemar p value on the discordant pairs.

    b: chains COMPLIED at single turn but not at multi turn.
    c: chains not COMPLIED at single turn but COMPLIED at multi turn.
    """
    n = b + c
    if n == 0:
        return float("nan")
    k = min(b, c)
    p_one_side = sum(comb(n, i) for i in range(0, k + 1)) * (0.5**n)
    return min(1.0, 2 * p_one_side)


def load_paired_complied() -> dict[str, dict[str, dict[str, str]]]:
    """model -> chain_id -> {"single": label, "multi": label}."""
    data: dict[str, dict[str, dict[str, str]]] = defaultdict(lambda: defaultdict(dict))
    for path in sorted(LOG_DIR.glob("*.eval")):
        log = read_eval_log(str(path))
        variant = "single" if "single-turn" in log.eval.task else "multi"
        model = MODEL_SHORT_NAMES.get(log.eval.model, log.eval.model)
        for sample in log.samples or []:
            score = sample.scores.get("refusal_judge") if sample.scores else None
            if score is None:
                continue
            chain_id = score.metadata.get("chain_id")
            data[model][chain_id][variant] = score.value
    return data


if __name__ == "__main__":
    data = load_paired_complied()
    rows = []
    for model in MODEL_ORDER:
        b = c = concordant_complied = concordant_not = n = 0
        for chain_id, variants in data[model].items():
            if "single" not in variants or "multi" not in variants:
                continue
            n += 1
            s_complied = variants["single"] == "COMPLIED"
            m_complied = variants["multi"] == "COMPLIED"
            if s_complied and not m_complied:
                b += 1
            elif not s_complied and m_complied:
                c += 1
            elif s_complied and m_complied:
                concordant_complied += 1
            else:
                concordant_not += 1

        p = mcnemar_exact(b, c)
        direction = (
            "no discordant pairs"
            if b == c == 0
            else "multi > single" if c > b else "single > multi"
        )
        rows.append(
            {
                "model": model,
                "n_chains": n,
                "b_single_complied_multi_not": b,
                "c_single_not_multi_complied": c,
                "p_value_exact": round(p, 6),
                "direction": direction,
            }
        )
        print(
            f"{model}: n={n}, b={b}, c={c}, exact McNemar p={p:.6f} ({direction})"
        )

    import csv

    with OUT_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {OUT_PATH}")
