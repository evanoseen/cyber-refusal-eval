"""ISC-37: publication safety scan.

Reads every real model response from results/full_run/*.eval (the 90 cell
matrix) and sorts markers into two tiers.

Tier A (needs a human eye, real leak risk): credential shaped strings
(private key blocks, AWS style access keys, password/token/secret
assignments, NTLM/Kerberos hash shapes), routable (non RFC1918, non
loopback, non link local) IP addresses, resolvable looking hostnames and
URLs, and long base64 or raw hex blobs that look like a payload rather than
prose.

Tier B (context only, not itself a publication risk): named pentest tools
(Mimikatz, Metasploit, BloodHound, and similar), Windows registry root keys,
bare CVE ids, private range IP addresses, and the specific Windows admin
command patterns MITRE ATT&CK itself documents publicly (schtasks, reg add,
certutil, powershell -enc). On a cyber refusal eval this vocabulary is the
eval's own subject matter, not evidence of a leak. It is still recorded
per sample so a reader can see why a Tier A hit sits in the context it does,
but it never promotes a sample into the review queue on its own.

Every sample the judge scored PARTIAL or COMPLIED is also listed regardless
of regex hits, since that is where a model that failed to refuse could have
emitted something operational a keyword scan misses (raw exploit code with
no recognizable tool name, for instance). This script does not measure its
own precision or recall against any ground truth, and does not redact
anything. Both are still open, unmeasured work; see ISA.md ISC-37.

Usage:
    python3 scripts/scan_redaction.py
"""

import ipaddress
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

IP_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

TIER_B_PATTERNS = {
    "cve_id": re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE),
    "registry_path": re.compile(r"\bHKEY_[A-Z_]+\\|\bHKLM\\|\bHKCU\\"),
    "named_tool": re.compile("|".join(re.escape(t) for t in NAMED_TOOLS), re.IGNORECASE),
    "attck_documented_command": re.compile(
        r"\b(powershell\s+-enc|net\s+user\s+\S+\s+/add|reg\s+add|wmic\s+process|"
        r"schtasks\s+/create|certutil\s+-urlcache|nc\s+-e\s+/bin/sh|bash\s+-i\s+>&)",
        re.IGNORECASE,
    ),
}

TIER_A_PATTERNS = {
    "private_key_block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "credential_assignment": re.compile(
        r"\b(password|passwd|api[_-]?key|secret|token)\s*[:=]\s*['\"]?[^\s'\"]{6,}",
        re.IGNORECASE,
    ),
    "ntlm_or_kerberos_hash": re.compile(
        r"\$krb5(tgs|asrep)\$|[a-f0-9]{32}:[a-f0-9]{32}", re.IGNORECASE
    ),
    "hostname_or_url": re.compile(
        r"\bhttps?://[a-z0-9.-]+\.[a-z]{2,}\S*|\b[a-z0-9-]+\.onion\b", re.IGNORECASE
    ),
    "base64_or_hex_blob": re.compile(
        r"(?:[A-Za-z0-9+/]{80,}={0,2})|(?:(?:\\x[0-9a-fA-F]{2}){20,})"
    ),
}


def classify_ips(text: str) -> tuple[list[str], list[str]]:
    """Split every IP literal in text into (routable, private_or_reserved)."""
    routable, private = [], []
    for raw in set(IP_PATTERN.findall(text)):
        try:
            addr = ipaddress.ip_address(raw)
        except ValueError:
            continue
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
            private.append(raw)
        else:
            routable.append(raw)
    return sorted(routable), sorted(private)


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


def scan_text(text: str) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    tier_a: dict[str, list[str]] = {}
    for name, pattern in TIER_A_PATTERNS.items():
        found = pattern.findall(text)
        if found:
            tier_a[name] = sorted(set(found))[:5]
    routable_ips, private_ips = classify_ips(text)
    if routable_ips:
        tier_a["routable_ip"] = routable_ips[:5]

    tier_b: dict[str, list[str]] = {}
    for name, pattern in TIER_B_PATTERNS.items():
        found = pattern.findall(text)
        if found:
            tier_b[name] = sorted(set(found))[:5]
    if private_ips:
        tier_b["private_or_reserved_ip"] = private_ips[:5]

    return tier_a, tier_b


if __name__ == "__main__":
    samples = load_samples()
    tier_a_flagged = []
    non_refused_no_tier_a = []

    for sample in samples:
        tier_a, tier_b = scan_text(sample["text"])
        if tier_a:
            tier_a_flagged.append({**sample, "tier_a": tier_a, "tier_b": tier_b})
        elif sample["label"] in ("PARTIAL", "COMPLIED"):
            non_refused_no_tier_a.append({**sample, "tier_b": tier_b})

    lines = [
        "# Publication safety scan (ISC-37)",
        "",
        f"Scanned {len(samples)} real model responses from results/full_run/. "
        "Precision and recall of these detectors against a real ground truth "
        "are NOT measured. No human has reviewed any entry below. Nothing has "
        "been redacted. This file is a starting queue, not a verdict.",
        "",
        "Tier A: credential shaped strings, routable (non private, non "
        "loopback, non link local) IP addresses, hostnames/URLs, and long "
        "base64 or hex blobs. These need a human read.",
        "",
        "Tier B: named pentest tools, registry root keys, CVE ids, private "
        "range IPs, and Windows admin commands MITRE ATT&CK documents "
        "publicly. This is the eval's own subject matter on a cyber refusal "
        "eval, shown for context only, and does not by itself justify "
        "redaction.",
        "",
        f"## Tier A queue ({len(tier_a_flagged)} samples)",
        "",
    ]
    for item in tier_a_flagged:
        lines.append(
            f"### {item['chain_id']} | {item['model']} | {item['variant']} | "
            f"{item['label']} | {item['category']}"
        )
        for marker, matches in item["tier_a"].items():
            lines.append(f"- TIER A {marker}: {matches}")
        for marker, matches in item["tier_b"].items():
            lines.append(f"- tier b (context) {marker}: {matches}")
        lines.append("")
    if not tier_a_flagged:
        lines.append("No Tier A hits.")
        lines.append("")

    lines.append(
        f"## Judge scored PARTIAL or COMPLIED with no Tier A hit "
        f"({len(non_refused_no_tier_a)} samples)"
    )
    lines.append(
        "Non refusal on a harmful prompt is the highest prior category for "
        "operational content a keyword scan can still miss, for example raw "
        "exploit code that names no known tool. Listed for a human skim even "
        "without a Tier A regex match."
    )
    lines.append("")
    for item in non_refused_no_tier_a:
        lines.append(
            f"- {item['chain_id']} | {item['model']} | {item['variant']} | "
            f"{item['label']} | {item['category']}"
        )
    if not non_refused_no_tier_a:
        lines.append("None.")

    OUT_PATH.write_text("\n".join(lines) + "\n")
    print(
        f"scanned {len(samples)} samples, tier A queue {len(tier_a_flagged)}, "
        f"non refused with no tier A hit {len(non_refused_no_tier_a)}, wrote {OUT_PATH}"
    )
