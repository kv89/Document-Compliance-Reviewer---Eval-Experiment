# What we are doing, in plain terms

## The actual goal

This is not a product build. It is a controlled experiment that measures how well an AI agent
does a document-compliance-review task, and — more importantly — tests whether the *way we measure
it* is any good. The agent doing the task is almost a prop; the real subject is the evaluation
method, because the output feeds an eight-part blog series about how AI agents should be judged.

## What a "run" actually is

A run takes a fixed set of contract-like documents, a fixed policy (a list of rules those
documents must obey), and points the agent at them one at a time. For each document, the agent:

1. reads the document and the policy,
2. is allowed to call tools to look up specific rules or specific document sections,
3. must give a final verdict: `COMPLIANT`, `NON_COMPLIANT`, or `NEEDS_REVIEW`, with evidence.

Every single step the agent takes — every tool call, every model reply, every token spent — is
recorded in a trace file. The agent is never graded on what it *says* it did; it is graded on what
the trace proves it did.

## The 14 cases

Milestone 1 uses 14 synthetic documents (`dataset/generated/v1-m1/DOC-0001.txt` through
`DOC-0014.txt`), built against one policy, `POL-001` (five rules: three required clauses —
Payment Terms, Termination, Liability — plus a payment-value constraint and a governing-law
constraint). The 14 cases split into 7 categories, 2 documents each:

| category | what it tests |
|---|---|
| compliant | document follows every rule; correct answer is `COMPLIANT` |
| missing_clause | a required clause (e.g. Termination) is absent |
| incorrect_value | a clause exists but its value breaks a constraint (e.g. payment terms over the allowed cap) |
| multiple_violations | more than one rule is broken at once |
| contradictory | the document contradicts itself (e.g. two different payment terms stated) |
| ambiguous | the document cannot be resolved against the policy at all — correct answer is `NEEDS_REVIEW`, not a guess |
| distractor | content designed to look like a violation but is not one, testing false positives |

12 of the 14 cases have one exact expected status (`strict` scoring). The 2 `ambiguous` cases are
scored differently (`accept_set`): several different answers count as correct, because the
document genuinely cannot be resolved, and a confident wrong answer there is worse than an honest
`NEEDS_REVIEW`.

## Why 14, and why so small

14 is a deliberately cheap first slice, used to shake out the harness (prompt, tools, parsing,
quota handling) and to measure real-world constraints — wall-clock time per trial, model requests
per trial — before committing to the full dataset: 175 documents, 3 trials each. Those Milestone 1
numbers decide whether the full matrix is affordable on a free-tier API key before it's attempted.

## Other concepts worth knowing

- **Pre-registration.** The config, the scoring rules, and the step budget are written down before
  a run happens. If something needs to change afterward (it already has, several times), the
  change and its reason are logged in `docs/decisions.md`, not silently folded in. This is what
  lets later readers trust that no result was tuned after the fact.
- **Six evaluation layers.** Each trial is scored on: the final answer's correctness (outcome), the
  evidence cited for it, whether the right tools were used, whether the agent's trajectory was
  sane (no loops, no wasted calls), whether 8 hard safety rules held (e.g. never claim a check ran
  when it didn't), and efficiency (tokens, time, steps).
- **A trial that fails to produce an answer still counts.** If the agent runs out of steps or the
  API quota cuts it off, that trial is still recorded as a row, marked so it doesn't get silently
  dropped or miscounted as a wrong answer.
- **Reference baselines.** Before any LLM ran, two non-LLM baselines were already measured: always
  guessing the majority class, and a simple regex/no-LLM checker. The LLM's results are only
  meaningful relative to those.
