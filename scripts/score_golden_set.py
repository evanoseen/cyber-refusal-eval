"""Score Evan's blind golden set labels against the hidden judge answer key (ISC-35).

Usage:
    python3 scripts/score_golden_set.py "1 REFUSED, 2 PARTIAL, 3 COMPLIED, ..."

Reads MEMORY/golden_set_answer_key.md for the judge labels, parses Evan's
reply string, and reports raw agreement, a per class confusion matrix, and
Cohen's kappa. This script never writes or suggests labels, it only scores
a set that has already been produced independently.
"""

import re
import sys
from pathlib import Path

LABELS = ("REFUSED", "PARTIAL", "COMPLIED")
ANSWER_KEY_PATH = Path(__file__).resolve().parent.parent / "MEMORY" / "golden_set_answer_key.md"


def load_answer_key(path: Path) -> dict[int, str]:
    text = path.read_text()
    key = {}
    for line in text.splitlines():
        match = re.match(r"\|\s*(\d+)\s*\|[^|]*\|[^|]*\|\s*(REFUSED|PARTIAL|COMPLIED)\s*\|", line)
        if match:
            key[int(match.group(1))] = match.group(2)
    return key


def parse_evan_labels(reply: str) -> dict[int, str]:
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


def confusion_matrix(pairs: list[tuple[str, str]]) -> dict[str, dict[str, int]]:
    matrix = {row: {col: 0 for col in LABELS} for row in LABELS}
    for evan_label, judge_label in pairs:
        matrix[evan_label][judge_label] += 1
    return matrix


def score(reply: str) -> str:
    answer_key = load_answer_key(ANSWER_KEY_PATH)
    evan_labels = parse_evan_labels(reply)

    missing = sorted(set(answer_key) - set(evan_labels))
    if missing:
        raise ValueError(f"missing labels for items: {missing}")

    pairs = [(evan_labels[i], answer_key[i]) for i in sorted(answer_key)]
    n = len(pairs)
    agreement_count = sum(1 for evan_label, judge_label in pairs if evan_label == judge_label)
    raw_agreement = agreement_count / n
    kappa = cohens_kappa(pairs)
    matrix = confusion_matrix(pairs)

    lines = [
        f"n = {n}",
        f"raw agreement = {agreement_count}/{n} = {raw_agreement:.3f}",
        f"cohen's kappa = {kappa:.3f}",
        "",
        "confusion matrix (rows = Evan's label, cols = judge's label):",
        "            " + "  ".join(f"{label:>9}" for label in LABELS),
    ]
    for row_label in LABELS:
        row = "  ".join(f"{matrix[row_label][col_label]:>9}" for col_label in LABELS)
        lines.append(f"{row_label:>10}  {row}")

    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python3 scripts/score_golden_set.py \"1 REFUSED, 2 PARTIAL, ...\"")
        sys.exit(1)
    print(score(sys.argv[1]))
