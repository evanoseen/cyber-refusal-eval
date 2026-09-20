"""ISC-37: publication safety scan.

Reads every real model response from results/full_run/*.eval (the 90 cell
matrix) and flags any sample whose text matches a marker commonly associated
with actionable operational detail: real IP addresses, CVE identifiers,
named offensive tools, Windows registry paths, and fenced code blocks that
contain a real shell or PowerShell command rather than prose.

This is a scan, not a verdict. It narrows 90 samples down to a short list
for a human read, the same two step pattern (automated scan plus manual
re read) already used for the chain dataset's own sanitization pass
(data/sanitization_log.md). Flagged samples still need eyes on them before
the repo goes public (ISC-25) or the post crossposts (ISC-24); this script
does not redact anything itself.

Usage:
    python3 scripts/scan_redaction.py
"""

import re
from pathlib import Path

from inspect_ai.log import read_eval_log

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = REPO_ROOT / "results" / "full_run"
OUT_PATH = REPO_ROOT / "results" / "redaction_scan.md"

MODEL_SHORT_NAMES = {
    "openai-api/deepinfra/meta-llama/Llama-3.3-70B-Instruct": "llama-3.3-70b",
    "openai-api/deepinfra/Qwen/Qwen2.5-72B-Instruct": "qwen-2.5-72b",
    "openai-api/deepinfra/openai/gpt-oss-120b": "gpt-oss-120b",
}

NAMED_TOOLS = [
    "mimikatz", "cobalt strike", "metasploit", "meterpreter", "powersploit",
    "bloodhound", "empire", "impacket", "responder", "psexec", "certutil",
]

PATTERNS = {
    "real_ip": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    "cve_id": re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE),
    "registry_path": re.compile(r"\bHKEY_[A-Z_]+\\|\bHKLM\\|\bHKCU\\"),
    "named_tool": re.compile("|".join(re.escape(t) for t in NAMED_TOOLS), re.IGNORECASE),
    "code_fence": re.compile(r"```"),
    "shell_command": re.compile(
        r"\b(powershell\s+-enc|net\s+user\s+\S+\s+/add|reg\s+add|wmic\s+process|"
        r"schtasks\s+/create|certutil\s+-urlcache|nc\s+-e\s+/bin/sh|bash\s+-i\s+>&)",
        re.IGNORECASE,
    ),
}


def load_samples() -> list[dict]:
    samples = []
    for path in sorted(LOG_DIR.glob("*.eval")):
        log = read_eval_log(str(path))
        variant = "single_turn" if "single-turn" in log.eval.task else "multi_turn"
        model = MODEL_SHORT_NAMES.get(log.eval.model, log.eval.model)
        for sample in log.samples or []:
            score = sample.scores.get("refusal_judge") if sample.scores else None
            if score is None:
                continue
            samples.append(
                {
                    "model": model,
                    "variant": variant,
                    "label": score.value,
                    "category": score.metadata.get("category"),
                    "chain_id": score.metadata.get("chain_id"),
                    "text": score.answer or "",
                }
            )
    return samples


def scan_text(text: str) -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {}
    for name, pattern in PATTERNS.items():
        found = pattern.findall(text)
        if found:
            hits[name] = sorted(set(found))[:5]
    return hits


if __name__ == "__main__":
    samples = load_samples()
    flagged = []
    for sample in samples:
        hits = scan_text(sample["text"])
        if hits:
            flagged.append({**sample, "hits": hits})

    lines = [
        "# Publication safety scan (ISC-37)",
        "",
        f"Scanned {len(samples)} real model responses from results/full_run/. "
        f"{len(flagged)} flagged for human review before the repo goes public "
        "or the post crossposts. A flag is not a confirmed leak, it is a "
        "signal this script cannot judge context for on its own.",
        "",
    ]
    for item in flagged:
        lines.append(
            f"## {item['chain_id']} | {item['model']} | {item['variant']} | "
            f"{item['label']} | {item['category']}"
        )
        for marker, matches in item["hits"].items():
            lines.append(f"- {marker}: {matches}")
        lines.append("")

    if not flagged:
        lines.append("No samples flagged.")

    OUT_PATH.write_text("\n".join(lines))
    print(f"scanned {len(samples)} samples, flagged {len(flagged)}, wrote {OUT_PATH}")
