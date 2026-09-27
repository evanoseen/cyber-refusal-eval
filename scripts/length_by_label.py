"""Mean final response length in tokens, by model, variant, and judge label.

The judge only grades the final turn's response (see ISA.md Decisions,
2026-09-26 verbosity correction), so final turn length, not total
conversation length, is what matters for a judge sees more words concern.
Uses the real billed output_tokens for that one generation call
(sample.output.usage.output_tokens), not a character estimate.

Usage:
    python3 scripts/length_by_label.py
"""

import csv
from collections import defaultdict
from pathlib import Path

from inspect_ai.log import read_eval_log

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = REPO_ROOT / "results" / "full_run"
OUT_PATH = REPO_ROOT / "results" / "length_by_label.csv"

MODEL_SHORT_NAMES = {
    "openai-api/deepinfra/meta-llama/Llama-3.3-70B-Instruct": "llama-3.3-70b",
    "openai-api/deepinfra/Qwen/Qwen2.5-72B-Instruct": "qwen-2.5-72b",
    "openai-api/deepinfra/openai/gpt-oss-120b": "gpt-oss-120b",
}
MODEL_ORDER = ["gpt-oss-120b", "llama-3.3-70b", "qwen-2.5-72b"]
LABELS = ["REFUSED", "PARTIAL", "COMPLIED"]


if __name__ == "__main__":
    # (model, variant, label) -> list of final turn output token counts
    by_label: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    by_model_variant: dict[tuple[str, str], list[int]] = defaultdict(list)

    for path in sorted(LOG_DIR.glob("*.eval")):
        log = read_eval_log(str(path))
        variant = "single_turn" if "single-turn" in log.eval.task else "multi_turn"
        model = MODEL_SHORT_NAMES.get(log.eval.model, log.eval.model)
        for sample in log.samples or []:
            score = sample.scores.get("refusal_judge") if sample.scores else None
            if score is None or sample.output.usage is None:
                continue
            tokens = sample.output.usage.output_tokens
            by_label[(model, variant, score.value)].append(tokens)
            by_model_variant[(model, variant)].append(tokens)

    rows = []
    for model in MODEL_ORDER:
        for variant in ["single_turn", "multi_turn"]:
            overall = by_model_variant[(model, variant)]
            rows.append(
                {
                    "model": model,
                    "variant": variant,
                    "label": "ALL",
                    "n": len(overall),
                    "mean_output_tokens": round(sum(overall) / len(overall), 1) if overall else "",
                }
            )
            for label in LABELS:
                vals = by_label[(model, variant, label)]
                rows.append(
                    {
                        "model": model,
                        "variant": variant,
                        "label": label,
                        "n": len(vals),
                        "mean_output_tokens": round(sum(vals) / len(vals), 1) if vals else "",
                    }
                )

    with OUT_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["model", "variant", "label", "n", "mean_output_tokens"])
        writer.writeheader()
        writer.writerows(rows)

    for row in rows:
        print(row)
    print(f"wrote {OUT_PATH}")
