# CyberSecEval 3 (Wan, Bhatt, Saxe et al, Meta Purple Llama, July 2024)

**Citation:** Shengye Wan, Manish Bhatt, Joshua Saxe et al. CYBERSECEVAL 3: Advancing the Evaluation of Cybersecurity Risks and Capabilities in Large Language Models. arXiv:2408.01605, July 2024.

**Links:**
- arXiv abstract: https://arxiv.org/abs/2408.01605
- HTML: https://arxiv.org/html/2408.01605v1
- PDF: https://arxiv.org/pdf/2408.01605
- Meta AI: https://ai.meta.com/research/publications/purple-llama-cyberseceval-a-benchmark-for-evaluating-the-cybersecurity-risks-of-large-language-models/
- Code: https://github.com/meta-llama/PurpleLlama/blob/main/CybersecurityBenchmarks/README.md

## One paragraph note

Wan, Bhatt, and the Meta Purple Llama team release the third version of CyberSecEval, an eight category benchmark covering risks to third parties (automated spear phishing, scaling manual offensive cyber operations, autonomous offensive cyber operations, autonomous vulnerability discovery and exploitation) and risks to application developers (textual prompt injection, insecure code suggestions, malicious code execution in interpreters, facilitating cyberattacks), with the MITRE ATT&CK framework used to scope the cyberattack helpfulness tests. The most relevant finding for my work is that models refuse less often in lower severity ATT&CK categories like reconnaissance and refuse more often in higher severity categories like privilege escalation, which is direct evidence that refusal behavior varies by category and not just by model. They also show that Llama 3 405B can automate moderately persuasive multi turn spear phishing at 2.62 out of 5, comparable to GPT-4 Turbo, which is the closest published evidence that multi turn cyber attacks elicit non trivial compliance. Methodologically, they validate their LLM judge against human evaluators at r equals 0.89 correlation, which is the target I should aim for in my human spot check (ISC-20). The gap my work fills is that CyberSecEval 3 tests single turn cyberattack helpfulness and separately tests multi turn spear phishing, but never compares single turn versus multi turn versions of the same intent across the ATT&CK taxonomy. That comparison is my contribution. I will steal their category by category reporting, their LLM judge plus human validation pattern, and their framing of severity versus compliance as a relationship worth measuring.
