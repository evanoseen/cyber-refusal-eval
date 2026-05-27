# Best of N Jailbreaking (Hughes, Price, Lynch et al, Anthropic, December 2024)

**Citation:** John Hughes, Sara Price, Aengus Lynch et al. Best-of-N Jailbreaking. arXiv:2412.03556, December 2024. Accepted to NeurIPS 2025.

**Links:**
- arXiv abstract: https://arxiv.org/abs/2412.03556
- PDF: https://arxiv.org/pdf/2412.03556
- HTML: https://arxiv.org/html/2412.03556v1
- Anthropic announcement: https://x.com/AnthropicAI/status/1867608917595107443
- Code: https://github.com/jplhughes/bon-jailbreaking

## One paragraph note

Hughes, Price, and Lynch show that cheap random perturbations of a harmful prompt (capitalization changes, character shuffling, audio noise, image augmentations) jailbreak frontier models with high success when you sample enough variations, reaching 89 percent attack success on GPT-4o and 78 percent on Claude 3.5 Sonnet at 10,000 samples. The attack success rate as a function of N (the number of sampled variations) follows a power law for many orders of magnitude, and the method works across text, vision, and audio modalities. They also defeat state of the art defenses including circuit breakers, and composability is real: stacking BoN with optimized prefix attacks adds up to 35 percent attack success on top. For my work, BoN is the second example of a published refusal fragility result that scales as a power law, the first being Many Shot Jailbreaking. The shared signal is that safety training generalizes only over a narrow input distribution, and small movements outside that distribution (whether by stacking shots, by perturbing characters, or in my case by decomposing across turns) recover compliance. BoN attacks the surface form of a single turn. Many Shot attacks the in context example count. My eval attacks conversation structure. Three different distribution shifts, plausibly the same underlying brittleness. The methodological note for the writeup is that BoN is fully automated while my chains are hand authored, which is a clear future work direction: automate the multi turn decomposition the way BoN automates surface perturbation, and measure scaling in number of decomposition variants.
