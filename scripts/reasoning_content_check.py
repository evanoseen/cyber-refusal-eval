"""Check whether gpt-oss-120b's reasoning content is separate from what the judge sees.

Round 1 of this check (2026-09-26) summed str(message.content) across all
four turns and compared it to the billed output token total, and concluded
there was no hidden reasoning component. That was wrong: str() on a content
list of parts produces Python's repr of the list of ContentReasoning and
ContentText objects, not the actual text, so the sum silently included
reasoning object reprs rather than excluding reasoning content. This script
redoes it correctly: separates true ContentReasoning parts (type=="reasoning")
from ContentText parts (type=="text") per message, using the same .text
property inspect_ai itself uses to build ModelOutput.completion, which is
what the judge is actually shown as the target model's response. See
_judge_prompt_and_response and ModelOutput.set_completion in the installed
inspect_ai package.

Usage:
    python3 scripts/reasoning_content_check.py
"""

from pathlib import Path

from inspect_ai.log import read_eval_log

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = REPO_ROOT / "results" / "full_run"
OUT_PATH = REPO_ROOT / "results" / "reasoning_content_check.csv"


if __name__ == "__main__":
    rows = []
    for path in sorted(LOG_DIR.glob("*.eval")):
        log = read_eval_log(str(path))
        if "gpt-oss" not in log.eval.model or "multi-turn" not in log.eval.task:
            continue
        text_chars = 0
        reasoning_chars = 0
        for sample in log.samples or []:
            for message in sample.messages:
                if message.role != "assistant":
                    continue
                text_chars += len(message.text)
                if not isinstance(message.content, str):
                    for part in message.content:
                        if part.type == "reasoning":
                            reasoning_chars += len(part.reasoning)

        billed_output_tokens = log.stats.model_usage[log.eval.model].output_tokens
        est_text_tokens = text_chars / 4
        est_reasoning_tokens = reasoning_chars / 4
        rows.append(
            {
                "model": log.eval.model,
                "judge_visible_text_chars": text_chars,
                "reasoning_chars_never_shown_to_judge": reasoning_chars,
                "reasoning_share_of_total_chars": round(
                    reasoning_chars / (text_chars + reasoning_chars), 4
                ),
                "est_judge_visible_text_tokens": round(est_text_tokens, 1),
                "est_reasoning_tokens": round(est_reasoning_tokens, 1),
                "billed_output_tokens_all_15_samples": billed_output_tokens,
            }
        )
        print(rows[-1])

    import csv

    with OUT_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {OUT_PATH}")
