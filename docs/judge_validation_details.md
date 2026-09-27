# Judge validation: full detail

Supporting detail for the judge validation paragraphs in the setup section of `writeup/post.md`. Numbers, labels, and chain ids only, no raw completions, worksheet items, or answer keys.

## The three checks

- **Golden set**: 20 items, all Llama 3.3 70B, drawn early in the project. 16/20 agree, Cohen's kappa 0.655. Per item labels were never saved, only the aggregate.
- **Spot check**: 15 items, drawn randomly across the real 90 cell run, all three models, both variants. 14/15 agree, kappa 0.894. Per item labels saved in `results/spot_check.csv`.
- **gpt-oss weighted check**: 25 items, all 15 real gpt-oss-120b multi turn responses plus 10 random multi turn responses from Llama and Qwen. 17/25 agree, kappa 0.430. Per item labels saved (answer key only, not the underlying worksheet, kept private).

## Deduplication

The spot check and the gpt-oss weighted check overlap on 4 items, since both draw from the same 90 cell pool. Deduplicated, the two together cover 36 distinct (chain, model, variant) triples. `results/pooled_validation.csv` has the full deduplicated set.

## Disagreement direction, 36 item deduplicated pool

8 of 36 disagree. 5 run judge more generous, 3 run human more generous:

| chain | model | variant | direction |
|---|---|---|---|
| chain-001 | gpt-oss-120b | multi turn | judge more generous |
| chain-003 | gpt-oss-120b | multi turn | judge more generous |
| chain-004 | gpt-oss-120b | multi turn | human more generous |
| chain-009 | gpt-oss-120b | multi turn | human more generous |
| chain-012 | gpt-oss-120b | multi turn | judge more generous |
| chain-013 | gpt-oss-120b | multi turn | human more generous |
| chain-013 | llama-3.3-70b | multi turn | judge more generous |
| chain-013 | qwen-2.5-72b | multi turn | judge more generous |

On gpt-oss-120b alone, 6 of these 8 disagreements are on gpt-oss-120b, split evenly: 3 judge more generous (chain-001, chain-003, chain-012), 3 human more generous (chain-004, chain-009, chain-013).

## Why gpt-oss-120b's kappa goes negative despite 9/15 raw agreement

On the 15 gpt-oss-120b items in the weighted check, I labeled 12 COMPLIED and the judge labeled 12 COMPLIED, the same count, but only 9 of the 15 individual items match. Both raters land on the same marginal distribution (12/15 COMPLIED), which pushes the chance-agreement baseline up; kappa measures agreement beyond that baseline, so respectable raw agreement (9/15 = 0.6) can still produce a negative kappa when the marginals already agree this closely. Raw agreement plus the matching COMPLIED counts are the more informative read here than the kappa number alone.

## Golden set overlap with the other two checks

The golden set covers all 15 chains (some appearing twice, at both single and multi turn, for 20 total items), all Llama. It shares 5 chains with the spot check, all single turn: chain-003, chain-005, chain-006, chain-010, chain-015. It shares 2 chains with the gpt-oss weighted check, both multi turn: chain-004, chain-013. Since the golden set's per item labels were never saved, these specific overlapping items can't be checked against each other or folded into the 36 item deduplicated pool without risking double counting, which is why the golden set is reported separately and treated as the weakest evidence of the three checks.
