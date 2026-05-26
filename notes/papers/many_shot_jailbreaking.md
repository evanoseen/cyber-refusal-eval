# Many Shot Jailbreaking (Anil et al, Anthropic, April 2024)

**Citation:** Cem Anil, Esin Durmus, Nina Panickssery, Mrinank Sharma et al. Many-shot Jailbreaking. NeurIPS 2024.

**Links:**
- Anthropic blog: https://www.anthropic.com/research/many-shot-jailbreaking
- PDF: https://www-cdn.anthropic.com/af5633c94ed2beb282f6a53c595eb437e8e7b630/Many_Shot_Jailbreaking__2024_04_02_0936.pdf
- NeurIPS: https://proceedings.neurips.cc/paper_files/paper/2024/file/ea456e232efb72d261715e33ce25f208-Paper-Conference.pdf

## One paragraph note

Anil et al show that prepending many fake dialogues of an assistant complying with harmful requests jailbreaks the model on a final real request, and this scales as a power law in the number of shots across Claude, OpenAI, Mistral, and Meta models. Larger models are more vulnerable because they are better at in context learning, which is the same capability that makes them useful. The mitigations they tested were either crippling (shorter context windows), only delaying (fine tuning to refuse jailbreak shaped prompts), or genuinely useful (a pre processing classifier that cut attack success from 61 percent to 2 percent in one configuration). For my work, this paper is the closest published cousin: where they stack many fake shots in a single turn, I am decomposing one real request across multiple real turns. The mechanism hypothesis is shared, the attack surface differs, and a positive result in my eval would be evidence that the vulnerability is not just a context length problem but a more general pattern of context dependent refusal degradation. I will steal their reporting frame (compliance rate as a function of variant) and their categorical breakdown (their harm categories become my ATT&CK tactics).
