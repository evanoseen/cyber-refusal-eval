"""Recompute the verbosity check worksheet agreement against the rescored labels.

scripts/score_verbosity_check.py scores Evan's blind labels against the
original judge run. This script scores the same 25 human labels against
results/framing_rescore.csv instead, to see whether the framing sensitivity
rescore changes how well a blind human reader agrees with the judge.

Usage:
    python3 scripts/score_verbosity_check_rescored.py "1 REFUSED, 2 PARTIAL, ..."
"""

import csv
import re
import sys
from pathlib import Path

LABELS = ("REFUSED", "PARTIAL", "COMPLIED")
REPO_ROOT = Path(__file__).resolve().parent.parent
ANSWER_KEY_PATH = REPO_ROOT / "MEMORY" / "verbosity_check_answer_key.md"
RESCORE_PATH = REPO_ROOT / "results" / "framing_rescore.csv"


def load_rescored_labels() -> dict[tuple[str, str, str], str]:
    labels = {}
    with RESCORE_PATH.open() as f:
        for row in csv.DictReader(f):
            labels[(row["chain"], row["model"], row["variant"])] = row["rescored_label"]
    return labels


def load_answer_key(path: Path) -> dict[int, dict[str, str]]:
    text = path.read_text()
    key = {}
    for line in text.splitlines():
        match = re.match(
            r"\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*(REFUSED|PARTIAL|COMPLIED)\s*\|",
            line,
        )
        if match:
            key[int(match.group(1))] = {"chain": match.group(2), "model": match.group(3)}
    return key


def parse_human_labels(reply: str) -> dict[int, str]:
    labels = {}
    for match in re.finditer(r"(\d+)\s*[:.]?\s*(REFUSED|PARTIAL|COMPLIED)", reply, re.IGNORECASE):
        labels[int(match.group(1))] = match.group(2).upper()
    return labels


def cohens_kappa(pairs: list[tuple[str, str]]) -> float:
    n = len(pairs)
    observed_agreement = sum(1 for a, b in pairs if a == b) / n
    row_totals = {label: 0 for label in LABELS}
    col_totals = {label: 0 for label in LABELS}
    for a, b in pairs:
        row_totals[a] += 1
        col_totals[b] += 1
    expected_agreement = sum(row_totals[label] * col_totals[label] for label in LABELS) / (n * n)
    if expected_agreement == 1.0:
        return 1.0
    return (observed_agreement - expected_agreement) / (1 - expected_agreement)


def report(title: str, pairs: list[tuple[str, str]]) -> str:
    n = len(pairs)
    agree = sum(1 for h, j in pairs if h == j)
    kappa = cohens_kappa(pairs)
    return f"{title}: {agree}/{n} = {agree / n:.3f}, kappa = {kappa:.3f}"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('usage: python3 scripts/score_verbosity_check_rescored.py "1 REFUSED, 2 PARTIAL, ..."')
        sys.exit(1)

    answer_key = load_answer_key(ANSWER_KEY_PATH)
    rescored = load_rescored_labels()
    human = parse_human_labels(sys.argv[1])

    all_pairs = []
    gpt_oss_pairs = []
    for item, entry in sorted(answer_key.items()):
        rescored_label = rescored[(entry["chain"], entry["model"], "multi_turn")]
        pair = (human[item], rescored_label)
        all_pairs.append(pair)
        if entry["model"] == "gpt-oss-120b":
            gpt_oss_pairs.append(pair)

    print(report("All 25 items vs rescored labels", all_pairs))
    print(report("gpt-oss-120b only (15 items) vs rescored labels", gpt_oss_pairs))
