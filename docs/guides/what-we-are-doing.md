# What we are doing, in plain terms

A step-by-step explanation of this project for someone new to it. Exact numbers live in the
reports, not here: the [README](../../README.md) has the results table, and
[blog-evidence.md](../reports/blog-evidence.md) has every count with its source.

## The goal

This is not a product build. It is a controlled experiment about **how to judge an AI agent**.

We give an AI agent a realistic job — check whether a contract follows a company policy — and then
study how well we can *measure* its work. The agent is almost a prop. The real subject is the
measurement method, and the findings feed an eight-part blog series on AI agent evaluation.

## Step 1: The task the agent does

The agent gets one document and one policy, and must answer one question: does this document
follow the policy?

- **The policy** is `POL-001`, five rules: the contract must have a Payment Terms clause, a
  Termination clause and a Liability clause; payment terms must not exceed a limit; and the
  governing law must be an allowed one.
- **The answer** is one of `COMPLIANT`, `NON_COMPLIANT` or `NEEDS_REVIEW` (when the document
  genuinely cannot be decided), plus a list of problems found. Each problem must quote the exact
  text from the document as evidence, with its position (character offsets).

## Step 2: How the agent works

The agent does not see the whole document at once. It works like a person with a search box:

1. It reads the task.
2. It calls tools: `lookup_policy` to read a rule, `search_document` to find text,
   `get_document_section` to read a section.
3. It repeats until it is confident, up to 20 steps.
4. It gives its final answer as structured JSON.

The model behind it is Google's `gemini-3.5-flash-lite` on the free tier, using a fixed prompt
called `p1`.

## Step 3: The test documents

We cannot measure correctness on real contracts, because nobody knows the right answer for sure.
So the documents are **synthetic**: generated from templates, so that the correct answer for each
one is known in advance (the "ground truth").

There are 175 documents in dataset `v1`, 25 in each of seven categories. Each category tests one
kind of difficulty:

| category | what it tests |
|---|---|
| compliant | follows every rule; the right answer is `COMPLIANT` |
| missing_clause | a required clause is absent |
| incorrect_value | a clause exists but breaks a limit, such as payment terms that are too long |
| multiple_violations | several rules are broken at once |
| contradictory | the document contradicts itself, for example two different payment terms |
| ambiguous | the document cannot be decided; an honest `NEEDS_REVIEW` beats a confident guess |
| distractor | text that looks like a violation but is not, to catch false alarms |

A person spot-checked the dataset and signed it off. The sign-off is tied to a fingerprint (hash)
of the answer file, so if the dataset is ever changed, the sign-off stops counting automatically.

Because each category has the same number of cases, results describe *how the agent handles each
kind of difficulty*, not how often it would be right on real contracts. Every published number
carries that caveat.

## Step 4: A run

A run points the agent at the documents one by one. We use a fixed sample of **140 documents
(20 per category)**, chosen by a seeded shuffle so anyone can reproduce the same selection.

For every document the run saves two things:

- **a trace**: every model reply, every tool call, every token spent, step by step;
- **a result row**: the answer and all its scores.

The agent is never graded on what it *says* it did, only on what the trace proves it did.

The free tier allows only a few hundred model requests a day, and the agent uses about eleven per
document, so a run can stop partway. Runs are built for that: documents are mixed across
categories so any stopping point is still balanced, each row is saved immediately, and `--resume`
continues where the run stopped.

## Step 5: How an answer is scored

Each answer is checked by code, not by opinion, on several layers:

1. **Outcome**: is the status right, and are the reported problems exactly the true ones?
2. **Evidence**: is the quote really in the document, in the right section, at the stated
   position?
3. **Tool use and path**: were the right tools used, with no loops or wasted calls?
4. **Safety**: eight hard rules (S1–S8) that must never break. For example, S2 says a quote must
   never be invented, and S3 says the stated position must match the quote. These are reported as
   counts, never hidden inside an average.
5. **Cost**: tokens, time and number of model calls.

Two rules keep the scores honest:

- **No answer still counts.** If the agent runs out of steps, that is recorded as a failure, not
  dropped.
- **Broken infrastructure does not count against the agent.** If the API rejects a request (quota,
  outage), the row is marked *void* and left out of the scores, then retried later.

## Step 6: Comparing against simple baselines

A score means little on its own. "84% correct" sounds good until a trivial method also gets 84%.
So the agent is compared with three reference baselines on the same 140 documents:

| baseline | what it is | the question it answers |
|---|---|---|
| REF-0 | always answers `NON_COMPLIANT`, reads nothing | what does pure guessing score? |
| REF-1 | hand-written text rules, no AI at all | can a simple program do this job? |
| REF-2 | one AI call with the whole document in the prompt, no tools | do the agent's steps and tools add anything? |

## Step 7: Checking consistency

The same question can get different answers from an AI model on different tries. To measure
that, 28 of the documents (4 per category) were run three times each, and we count how often all
three answers agreed. The main results use only the first try, so those 28 documents do not count
three times.

## Step 8: Playing fair (pre-registration)

Settings, scoring rules and sample are written down **before** a run. If anything changes
afterwards, the change and its reason go into the [decision log](../decisions/decisions.md). A
setting is never changed because a result looked bad. Improvements go into a new, separately
named version (for example a prompt `p2`) and are measured as their own experiment. This is what
lets a reader trust that no number was tuned after the fact.

## What we have learned so far

On this synthetic, deliberately balanced set (figures in the [README](../../README.md)):

- The agent gets the status right on most clear-cut documents, but on **contradictory** documents
  it almost always says `COMPLIANT`.
- It usually **finds and quotes the right text, then reports the wrong position** for it, even
  though its tool returned the correct one. This is the most common safety violation (S3).
- **The simple rule-based checker (REF-1) beats the agent** on full correctness, though it fails
  completely on contradictory documents, as expected.
- **Every run starts with the same wasted tool call**: a policy lookup with an invalid rule name.
- **One AI call with the whole document (REF-2) gets the status right more often than the agent**
  and catches the contradictions the agent misses, at a small fraction of the cost. But it raises
  false alarms and cannot give correct text positions without tools. So the agent's tools buy
  precision and evidence, not better verdicts.
- Answers were stable across repeated tries on almost every repeated document.
- **Experiment A (a more explicit prompt, `p2`) fixed the causes but broke the format.** The
  wasted first call disappeared and invented positions fell by about half. But the model
  more often answered in a form the program could not read (34 of 133 documents) or returned
  nothing (7 documents never produced an answer), so overall status accuracy fell from 95 to 74 of
  114 clear-cut documents. Where `p2` did answer, it was slightly more often right than `p1`.
  Contradictions are still mostly missed. Details in
  [expA-p1-vs-p2.md](../reports/expA-p1-vs-p2.md).

## What comes next

The ordered list is the "Project Roadmap & Next Steps" section of the [README](../../README.md). In
short: a follow-up experiment on making the output format reliable (to be pre-registered), then
a second model family, then testing whether an AI judge can grade answers reliably against human
reviewers, then automated test tiers and the final statistics.

## Where to look

| to see | open |
|---|---|
| the full technical rules | [specs/implementation-spec-v2.md](../specs/implementation-spec-v2.md) |
| every change and why | [decisions/decisions.md](../decisions/decisions.md) |
| how the code runs, file by file | [code-review-walkthrough.md](code-review-walkthrough.md) |
| headline results | [README](../../README.md) and [milestone-1-report.md](../reports/milestone-1-report.md) |
| every number used in the blog | [blog-evidence.md](../reports/blog-evidence.md) and [blog-evidence-expA-p2.md](../reports/blog-evidence-expA-p2.md) |
| the prompt experiment, `p1` vs `p2` | [expA-p1-vs-p2.md](../reports/expA-p1-vs-p2.md) |
| raw data | `results/raw/` (one row per answer) and `results/traces/` (step-by-step traces) |
