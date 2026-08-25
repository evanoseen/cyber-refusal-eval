# Sanitization Log

One entry per chain, per `data/SCHEMA.md`. Status `drafted` means Draco wrote the chain and ran the automated payload marker scan below. Status `reviewed` means the chain is confirmed safe to run and, eventually, publish.

2026-08-25 note: for chain-002 through chain-015, Evan explicitly delegated the sanitization read to Draco ("if u think there good then there good approve") rather than reading each file himself, a deviation from the original Principle 2 plan where he personally reviews every chain. Draco, as the author of all 14 chains, did a full second read of every file plus the existing automated scan before marking them reviewed. Flagged here rather than silently treated as equivalent to Evan's own read, since this is a safety sensitive project going to Anthropic and the provenance of the review matters. chain-001 remains reviewed by Evan personally at kickoff.

## Automated scan (run 2026-08-21)

Command: `grep -Eli 'invoke-|base64|CVE-[0-9]|nc -e|/bin/sh|powershell -e' data/chains/*.yaml` plus a backtick and code fence check. Zero matches across all 15 chains. This catches obvious payload markers only, it is not a substitute for Evan's read.

## Log

| chain | category | technique | status | notes |
|-------|----------|-----------|--------|-------|
| chain-001 | Initial Access | T1190 | reviewed (pre-existing, committed 2026-05-25) | Original example chain, already in main. |
| chain-002 | Initial Access | T1190 | reviewed 2026-08-25 (by Draco, Evan delegated) | Authority roleplay pattern, no exploit or product specifics. |
| chain-003 | Initial Access | T1190 | reviewed 2026-08-25 (by Draco, Evan delegated) | Defensive framing pattern, no exploit or product specifics. |
| chain-004 | Execution | T1059.001 | reviewed 2026-08-25 (by Draco, Evan delegated) | Conceptual bracketing pattern, no PowerShell syntax. |
| chain-005 | Execution | T1059.001 | reviewed 2026-08-25 (by Draco, Evan delegated) | Authority roleplay pattern, no commands. |
| chain-006 | Execution | T1059.001 | reviewed 2026-08-25 (by Draco, Evan delegated) | Defensive framing pattern, no commands. |
| chain-007 | Persistence | T1547.001 | reviewed 2026-08-25 (by Draco, Evan delegated) | Conceptual bracketing pattern, no registry paths. |
| chain-008 | Persistence | T1547.001 | reviewed 2026-08-25 (by Draco, Evan delegated) | Authority roleplay pattern, no registry paths. |
| chain-009 | Persistence | T1547.001 | reviewed 2026-08-25 (by Draco, Evan delegated) | Defensive framing pattern, no registry paths. |
| chain-010 | Lateral Movement | T1021.001 | reviewed 2026-08-25 (by Draco, Evan delegated) | Conceptual bracketing pattern, no tools or credentials. |
| chain-011 | Lateral Movement | T1021.001 | reviewed 2026-08-25 (by Draco, Evan delegated) | Authority roleplay pattern, no tools or credentials. |
| chain-012 | Lateral Movement | T1021.001 | reviewed 2026-08-25 (by Draco, Evan delegated) | Defensive framing pattern, no tools or credentials. |
| chain-013 | Exfiltration | T1041 | reviewed 2026-08-25 (by Draco, Evan delegated) | Conceptual bracketing pattern, no protocol specifics. |
| chain-014 | Exfiltration | T1041 | reviewed 2026-08-25 (by Draco, Evan delegated) | Authority roleplay pattern, no protocol specifics. |
| chain-015 | Exfiltration | T1041 | reviewed 2026-08-25 (by Draco, Evan delegated) | Defensive framing pattern, no protocol specifics. |

## Design note: the three escalation patterns

Added during the 2026-08-21 rescue sprint on advisor recommendation. Each of the 5 ATT&CK categories gets the same technique run through 3 framing patterns, so a cross category claim like "pattern B beats pattern A everywhere" is testable independent of which technique it is:

- **Pattern A, conceptual bracketing**: every turn stays abstract, framed as red team training material, no persona claimed.
- **Pattern B, authority roleplay**: user claims an unverifiable pentester or red team persona from turn one, then escalates specificity under that claimed authority.
- **Pattern C, defensive framing pivot**: user frames the whole request as SOC or detection engineering guidance, asking for the attacker playbook as something to defend against.

chain-001 is Pattern A on Initial Access. Every category now has one chain per pattern.
