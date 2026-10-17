# AI Agent Evaluation — Document Compliance Reviewer
## Implementation Spec v2 (authoritative)

> **Status:** This document supersedes `POC Design and Documentation.md` for all implementation
> work. The v1 document remains the record of original intent; where the two disagree, v2 wins.
>
> **Why v2 exists:** v1 was validated section by section for correctness. It was directionally
> sound but contained (a) three mutually inconsistent finding schemas, (b) metrics that were not
> computable because no matching rule was defined, (c) a category of test case ("ambiguous") with
> no representable ground truth, (d) page-level evidence requirements that text documents cannot
> satisfy, (e) per-category sample sizes too small to support the claims v1 itself planned to make,
> and (f) no non-agent reference baseline. v2 resolves these **before** any data is generated,
> which is required by the pre-registration principle in §2.
>
> Every change carries a marker `[v2 — resolves Bn]` traceable to the review findings, listed in
> Appendix A. Nothing in §1, §2, §4, §13, §27 or §30 — the purpose of the exercise — has been
> weakened. Several corrections exist specifically to protect those sections.

---

## 0. How to use this document (instructions for implementing sessions)

1. **Read §1 and §2 before writing any code, every session.** This is an experiment about
   evaluation methodology. It is not a contract-review product. A change that makes the agent
   better but the measurement weaker is a regression.
2. **Do not change a number, threshold, schema, or metric definition in this document because a
   result looked bad.** That is the one failure mode this project cannot recover from. If a
   definition is genuinely wrong, fix it, record the change in Appendix B with the date and
   reason, and re-run affected configurations from scratch.
3. **Build in milestone order (§29).** Do not implement §18–§22 before §29's Milestone 1 passes.
4. **Anything marked `[OPEN]` is a decision not yet made.** Stop and ask rather than guessing.
5. Keep the system small (§27). The smallest agent that still produces real evaluation problems.

---

## 1. Purpose

Build a small, reproducible AI agent that reviews documents against a defined
compliance policy.

The primary purpose is **not** to build a sophisticated document-review product.

The purpose is to create a controlled experimental system that lets us investigate:

- How should AI agents be evaluated?
- What should constitute success?
- How should tool usage be evaluated?
- How should agent trajectories be evaluated?
- When are deterministic evaluators sufficient?
- When is LLM-as-a-judge useful, and how reliable is an LLM judge?
- How can agent evaluation become part of CI/CD?
- Which metrics are useful for assessing production readiness?

The experiment provides the technical evidence and worked examples for an eight-part LinkedIn
blog series on AI Agent Evaluation (§25).

## 2. Core principle (unchanged, and load-bearing)

**The experiment must be designed before results are collected.**

We must not:

- invent performance numbers;
- modify evaluation criteria after seeing results merely to improve the result;
- assume one specific agent trajectory is always correct;
- treat an LLM judge's score as ground truth;
- present hypothetical results as experimental results.

All quantitative claims in the blog series must be traceable to an actual experiment run, by
`experiment_id` + `dataset_version` + `agent_version`.

**Pre-registration consequence `[v2 — resolves B2, B12, B14]`:** finding-matching rules (§8.4),
metric denominators (§15), release-gate thresholds (§22) and reporting restrictions (§24) are
fixed *in this document* rather than decided when results arrive.

## 3. Use case

A **Document Compliance Reviewer Agent** receives a document, a compliance policy, and a review
request. It must determine whether the document complies and identify violations, with evidence.

### 3.1 Policy model `[v2 — resolves B1, B17]`

A policy is a versioned list of rules. **Severity is an attribute of the rule, not a judgement the
agent makes.** This removes a metric that would otherwise measure nothing (see §15.3).

```json
{
  "policy_id": "POL-001",
  "policy_version": "v1",
  "rules": [
    {
      "rule_id": "CLAUSE-LIAB-001",
      "rule_type": "CLAUSE_REQUIRED",
      "clause": "Liability",
      "severity": "HIGH",
      "statement": "The document must contain a Liability clause."
    },
    {
      "rule_id": "VALUE-PAY-001",
      "rule_type": "VALUE_CONSTRAINT",
      "clause": "Payment Terms",
      "severity": "MEDIUM",
      "statement": "Payment terms must not exceed 45 days.",
      "params": { "field": "payment_days", "operator": "<=", "value": 45 }
    },
    {
      "rule_id": "ENUM-LAW-001",
      "rule_type": "ENUM_CONSTRAINT",
      "clause": "Governing Law",
      "severity": "HIGH",
      "statement": "Governing law must be one of the approved jurisdictions.",
      "params": { "field": "jurisdiction", "allowed": ["India", "Singapore", "England and Wales"] }
    }
  ]
}
```

`rule_type` is one of `CLAUSE_REQUIRED`, `VALUE_CONSTRAINT`, `ENUM_CONSTRAINT`.
`severity` is one of `HIGH`, `MEDIUM`, `LOW`.

**Every policy requirement has a `rule_id`, including clause-presence requirements.** This is what
makes finding matching well-defined (§8.4).

### 3.2 Document format `[v2 — resolves B4]`

**Decision: plain-text documents only. No PDF. No DOCX. No document parser.**

Documents are UTF-8 `.txt` files with explicitly numbered sections:

```
# MASTER SERVICES AGREEMENT

## 1. Definitions
...body text...

## 4.1 Payment Terms
Customer shall pay all invoices within 60 days of receipt.

## 8.2 Liability
...body text...
```

- `section_id` is the numeric label: `"4.1"`, `"8.2"`.
- A deterministic ~30-line section splitter in the tool layer maps `section_id → (title, body,
  char_start, char_end)`. This is a splitter, not a parser, and it is covered by unit tests.
- **There are no page numbers.** Evidence is located by `section_id` plus a verbatim quote plus
  character offsets into the raw file (§11).
- Docling and all document-parsing dependencies are **removed** from the stack (§6).

Rationale: v1 required page-level evidence (§11, §14 Layer 2) while generating documents from text
templates, and placed a parser in Milestone 1 whose input was already structured. That link was
redundant, untested, and would have let parser errors be scored as agent errors.

### 3.3 Case categories

A generated document may be fully compliant, or carry one or more controlled mutations: a missing
clause, an incorrect value, a policy violation, contradictory information, deliberately ambiguous
wording, or irrelevant distractor content. See §7 and §9.

## 4. Why this use case (unchanged)

Selected because it gives us: deterministic ground truth; synthetic generation; a place for
retrieval; multiple tools; evaluable tool arguments; evaluable document evidence; capturable
trajectories; deliberately ambiguous cases; both deterministic and model-based graders; and one
dataset reusable across every experiment.

The system stays deliberately small. We are testing evaluation methodology, not reproducing an
enterprise contract-review platform.

**Scope correction `[v2 — resolves B3]`:** v1's claim that "deterministic ground truth can be
created" is true for six of seven categories. Ambiguous cases do not have single-valued ground
truth by construction, and are handled explicitly by the accept-set mechanism in §8.3 rather than
being quietly folded into accuracy numbers.

## 5. Experimental architecture `[v2 — resolves B22]`

```
                        Review Request + Policy + Document
                                      |
                                      v
                        +-----------------------------+
                        |        Review Agent         |
                        |   (plain Python ReAct loop) |<--------+
                        +--------------+--------------+         |
                                       |                        |
                     tool call         v         tool result    |
                        +--------------+--------------+         |
                        |  list_document_sections()   |         |
                        |  get_document_section()     |---------+
                        |  search_document()          |  loop until decision
                        |  lookup_policy()            |  or max_steps
                        +--------------+--------------+
                                       |
                                       v
                             Structured Findings
                                       |
                        +--------------+--------------+
                        v                             v
                   Trace Store                  Results Store
                        |                             |
          +-------------+-------------+               |
          v             v             v               |
   Deterministic   Safety /       Model-based         |
    Evaluators    Constraint      Evaluators         |
   (outcome,       Evaluators     (LLM judge,        |
    evidence,                      task completion)  |
    tool, traj.)                        |             |
          +-------------+-------------+-+-------------+
                                      |
                                      v
                           Experiment Results (JSONL + SQLite)
                                      |
                                      v
                              Analysis / Report
```

The loop-back edge is deliberate: the agent iterates. v1's diagram showed a single forward pass,
which §28 forbids ("every diagram represents the actual implementation").

The agent is implemented as **plain Python** — the loop must be visible and inspectable, because
the loop is the object of study. LangGraph or similar may be evaluated later as a controlled
experiment (§16), not adopted as a baseline dependency.

## 6. Technology constraints

The experiment must run without paid APIs and without a paid cloud service. It need not run
offline. `[v2.1 — see 6.3]`

| Concern | Choice | Notes |
|---|---|---|
| Runtime | Python 3.11+, `google-genai` client | hosted inference, free tier |
| Model | Gemini free-tier model via Google AI Studio | exact alias **and** reported `model_version` recorded per trial |
| Documents | plain text (`.txt`) | **no parser dependency** `[v2 — B4]` |
| Agent | plain Python | no agent framework in v1 |
| Deterministic evaluation | custom Python | the primary evaluation layer |
| Tool correctness | DeepEval `ToolCorrectnessMetric` | deterministic, no LLM required |
| Model-based metrics | DeepEval task completion / step efficiency | **LLM-based — see §6.1** |
| Testing | pytest | evaluators have their own fixtures and tests |
| Data | JSONL (source of truth) + SQLite (query convenience) | `[v2 — B19]` |
| Analysis | pandas, matplotlib | |
| VCS | Git + GitHub | |

### 6.1 DeepEval configuration `[v2 — resolves B6, B7]`

- `ToolCorrectnessMetric` is deterministic and may be used from Milestone 1.
- DeepEval's **task completion and step efficiency metrics are LLM-based**. They are therefore
  judges, and §18 forbids introducing judges before deterministic evaluation is established. They
  are **excluded from the baseline run** and enter only in the judge phase.
- DeepEval's LLM-based metrics default to a hosted OpenAI model, which is paid. They **must** be
  explicitly configured against the same free-tier Gemini model the agent uses, or §6's no-paid-API
  constraint is silently violated. Verify at setup by running with no OpenAI key present and
  confirming the metric still completes.
- Disable DeepEval telemetry.
- Baseline trajectory evaluation uses **deterministic** trace-derived metrics instead (§14 Layer 4).

### 6.2 Run configuration that must be recorded `[v2 — resolves B16]`

Every result row and trace records: `model_name`, `model_tag`, `temperature`, `top_p`, `top_k`,
`seed`, `max_output_tokens`, `max_steps`, `provider`, `model_version`, `runtime_version`,
`python_version`, `hardware_id`, `prompt_version`, `tool_set_version`, `agent_version`,
`dataset_version`, `policy_version`.

`seed` was missing from v1 and is required for §28's reproducibility claim.

`thinking_level` is recorded, and `thinking_tokens` is recorded per trial, because internal
reasoning **cannot be disabled** on the baseline model `[v2.1 — measured]`. Gemini 2.5 accepted
`thinking_budget = 0`; Gemini 3.x rejects it with a 400 and exposes a `thinking_level` whose lowest
value is `MINIMAL`. Some proportion of each trial's reasoning is therefore charged, never returned,
and invisible to the trace. This is a disclosed limit on Layer 4 (§14): trajectory evaluation sees
the tool calls and the answers, not the whole of the deliberation behind them. The tokens are
counted so that the hidden portion is at least quantified, and are included in `total_tokens`
because excluding them would understate every trial's cost.

`model_version` is the provider-reported identifier for the weights that actually served the
request, and it is mandatory `[v2.1]`. Under local inference the model tag was immutable, so
recording the tag was enough. A hosted alias is not immutable: the provider may re-point it at new
weights at any time, without a version bump on our side. Capturing what the API reports is the only
evidence of what produced a given result. `quantization` and `num_ctx` are dropped, as neither is
observable or controllable through a hosted API.

### 6.3 Inference provider `[v2.1 — supersedes the local-only constraint]`

Inference runs on **Google AI Studio free tier** via the `google-genai` Python client, not on local
Ollama. The binding constraint in §6 was always *no paid APIs*, and a free tier satisfies it. The
change was made before any LLM trial was executed, so no result influenced it (§2).

What this costs the experiment, stated plainly because §30 requires it:

1. **Weight-level reproducibility is lost.** A reader cannot re-run this experiment years later and
   be certain of hitting the same weights. Mitigation: prefer dated model aliases where the provider
   offers them, record `model_version` per trial, and report determinism empirically (§17) rather
   than assuming it.
2. **Quota becomes part of the harness.** Free-tier request-per-minute and request-per-day limits
   apply. A rejected request is an infrastructure failure, not an agent failure, and is recorded in
   `harness_error` and excluded from every metric denominator. Counting a quota rejection as a wrong
   answer would be the same class of measurement bug as silently truncating context.
3. **Prompts leave the machine.** Free-tier usage grants the provider the right to use submitted
   prompts and responses to improve its products. This is acceptable here only because every
   document and policy in the dataset is synthetic and contains no real or confidential content
   (§9). It would **not** be acceptable for real contracts, and any reader adapting this setup to
   real documents must revisit this decision first.
4. **The Experiment C comparator weakens.** Comparing two models from the same provider family is a
   narrower contrast than comparing two independently trained open models. The finding must be
   reported as within-family, not as a general cross-model result.

The API key is read from an environment variable only. It is never written to a config file, a
result row, a trace, or the repository.

### 6.4 Model selection and pinning `[v2.1 — resolves O-1]`

| Role | Model | Why |
|---|---|---|
| Baseline | `gemini-2.5-flash-lite` | Stable, not a preview, and the only tier whose free request cap makes the matrix affordable `[v2.1]` |
| Experiment C comparator | `gemma-4-31b-it` | A **different model family** reachable through the same API, which recovers most of the cross-family contrast §6.3 said we had lost |
| Experiment C fallback | `gemini-2.5-flash` | Used only if Gemma cannot drive the tool protocol. Reported as a within-family comparison |
| Capability-ceiling probe (optional, §16) | `gemini-3.8-flash` | Only to check whether a baseline failure is a capability limit or a harness limit. Never the reported baseline |

Two pinning rules, both mandatory:

1. **No `-latest` aliases.** `gemini-flash-latest` and friends are explicitly moving targets and
   would make a result uninterpretable six months later. Named versions only.
2. **No `-preview` models in the reported baseline.** Previews are withdrawn without notice, so a
   preview result cannot be re-run. A preview may appear only in an exploratory arm that is labelled
   as such.

The comparator choice is conditional on `gemma-4-31b-it` supporting the tool-calling mechanism the
agent uses (§10). If it does not, Experiment C falls back to `gemini-2.5-flash-lite` and is reported
as a within-family comparison, as §6.3 item 4 describes. Verify before Milestone 3, not after.

#### Request budget is the binding constraint `[v2.1 — measured, not assumed]`

The first live run measured the real limit, and it is not wall clock. `gemini-2.5-flash` allows
**20 requests per day** on the free tier (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`), and
the agent used about **ten model requests per trial**. That is two trials per day: Milestone 1's 14
cases would take a week, and 175 cases × 3 trials would need roughly 5,250 requests per
configuration.

Model latency was never the problem — about 1.1 s per request, 13 s of model time per trial. Every
runtime projection must therefore be stated in **requests**, and the §7 gate is
`daily request cap ÷ requests per trial`. The runner reports requests per trial for this reason.

Deliberately avoided: the `pro` tier, image, TTS, transcription, robotics, computer-use, omni and
deep-research models. The task is text in, structured JSON out. A stronger or multimodal model
would raise free-tier cost per trial and risk a ceiling effect, where the baseline scores so highly
that the evaluation layers have no variance to measure — which would defeat the purpose of the
experiment (§1).

## 7. Dataset design `[v2 — resolves B14]`

**Dataset v1 = 175 cases, 25 per category.**

| Category | Cases | Scoring mode |
|---|---|---|
| Fully compliant | 25 | strict |
| Missing required clause | 25 | strict |
| Incorrect policy value | 25 | strict |
| Multiple violations | 25 | strict |
| Contradictory clauses | 25 | strict |
| Ambiguous | 25 | **accept_set** |
| Distractor / irrelevant content | 25 | strict |

Why this changed: v1 proposed 10 contradiction, 10 ambiguous and 5 distractor cases, then planned
to report per-category percentages for exactly those categories (§24's own example quotes
"Contradiction: 74%"). At n=10 a 74% point estimate carries roughly a ±28pp 95% interval; at n=5
the interval spans most of the range. §2 forbids unsupported quantitative claims, so either the
categories grow or the claims cannot be made. Generation is synthetic and nearly free, so they grow.

**Two standing rules that follow from this:**

1. **Reporting floor `[v2 — B14]`:** no per-category percentage may be published for a stratum with
   fewer than 20 case-level observations. Report counts plus an interval instead.
2. **The distribution is diagnostic, not prevalence.** 50 compliant-ish cases vs 125 violation
   cases (100 of them in the strict stratum) is a stratified design for measuring per-failure-mode behaviour. Aggregate numbers over
   this dataset must never be presented as expected production rates. State this in every post
   that quotes an aggregate.

**Runtime gate.** Measure wall-clock per case during Milestone 1. If the full matrix
(175 cases × 3 trials × configurations) is impractical, reduce **trials or configurations**, and
never the category sizes — shrinking strata is what reintroduces rule 1's problem.

## 8. Ground truth structure `[v2 — resolves B1, B3, B5]`

### 8.1 Canonical finding schema (one schema, used everywhere)

v1 contained three incompatible variants (`type` vs `finding_type`; `clause` vs `rule_id`). This is
now the single schema for ground truth, agent output, and evaluator internals.

```json
{
  "rule_id": "CLAUSE-LIAB-001",
  "finding_type": "MISSING_CLAUSE",
  "clause": "Liability",
  "severity": "HIGH",
  "description": "No Liability clause is present in the document.",
  "evidence": null
}
```

| Field | Type | Required | Rule |
|---|---|---|---|
| `rule_id` | string | yes | must exist in the active policy |
| `finding_type` | enum | yes | `MISSING_CLAUSE`, `POLICY_VIOLATION`, `CONTRADICTION`, `AMBIGUOUS` |
| `clause` | string | yes | must equal the policy rule's `clause` |
| `severity` | enum | yes | must equal the policy rule's `severity` (derived, not judged) |
| `description` | string | yes | free text, not scored deterministically |
| `evidence` | object or null | yes (may be null) | `null` **iff** `finding_type == MISSING_CLAUSE` |

Evidence object (§11.1) is `{ "section_id", "quote", "char_start", "char_end" }`.

### 8.2 Per-case ground truth

```json
{
  "case_id": "DOC-0042",
  "dataset_version": "v1",
  "category": "incorrect_value",
  "policy_id": "POL-001",
  "policy_version": "v1",
  "document_path": "dataset/generated/v1/DOC-0042.txt",
  "scoring_mode": "strict",

  "expected_status": "NON_COMPLIANT",
  "accepted_statuses": ["NON_COMPLIANT"],
  "expected_findings": [
    {
      "rule_id": "VALUE-PAY-001",
      "finding_type": "POLICY_VIOLATION",
      "clause": "Payment Terms",
      "severity": "MEDIUM",
      "description": "Payment terms of 60 days exceed the 45-day maximum.",
      "evidence": { "section_id": "4.1", "quote": "within 60 days of receipt",
                    "char_start": 1182, "char_end": 1207 }
    }
  ],

  "required_information": [
    { "rule_id": "VALUE-PAY-001", "must_consult_sections": ["4.1"] }
  ],
  "prohibited_actions": [],
  "mutations": [
    { "mutation_id": "M-VALUE-PAY", "target_section": "4.1",
      "from": "within 30 days", "to": "within 60 days",
      "expected_effect": "VALUE-PAY-001 violated" }
  ],
  "notes": ""
}
```

New fields versus v1, and why: `required_information`, `prohibited_actions` and `accepted_statuses`
give §13's principles somewhere to live. v1 correctly said "define required information, prohibited
actions, constraints, acceptable outcomes" instead of a mandatory tool sequence — but then provided
no per-case field to hold them, leaving Layers 3 and 5 with nothing deterministic to check.

### 8.3 Ambiguous cases: accept-set scoring `[v2 — resolves B3]`

Ambiguous cases use `scoring_mode: "accept_set"`:

```json
{
  "case_id": "DOC-0131",
  "category": "ambiguous",
  "scoring_mode": "accept_set",
  "expected_status": null,
  "accepted_statuses": ["NEEDS_REVIEW", "NON_COMPLIANT"],
  "accepted_finding_sets": [
    [ { "rule_id": "ENUM-LAW-001", "finding_type": "AMBIGUOUS",  "...": "..." } ],
    [ { "rule_id": "ENUM-LAW-001", "finding_type": "POLICY_VIOLATION", "...": "..." } ]
  ],
  "unacceptable_statuses": ["COMPLIANT"],
  "ambiguity_note": "Jurisdiction is stated as 'the laws of the Company's principal place of business', which is never specified."
}
```

Rules:

- A case passes if its status is in `accepted_statuses` **and** its finding set matches any one
  member of `accepted_finding_sets` under §8.4's matching rule.
- **Accept-set cases are excluded from the primary precision/recall/accuracy aggregates** and
  reported as their own stratum, with their own pass rate. Pooling a multi-valued stratum into a
  single-truth metric is the error v1 would have made at §24.
- They are the primary material for §19 (where do evaluators disagree?) and §25 Post 6.
- The third status value `NEEDS_REVIEW` exists for these cases (§11).

### 8.4 Finding-matching rule — pre-registered `[v2 — resolves B2]`

Without this, none of §15's precision/recall/accuracy numbers are computable, and choosing it after
seeing results would violate §2.

1. **Dedupe:** within the agent's findings, group by `rule_id`; keep the first occurrence; count the
   rest as `duplicate_findings` (reported as a quality/efficiency signal, **not** as false positives).
2. **Join:** match expected to actual findings **one-to-one on `rule_id`**.
3. **Classify:** `rule_id` in both → **TP**. Actual only → **FP**. Expected only → **FN**.
4. **Secondary agreement, computed on TPs only, with the denominator always printed:**
   - `finding_type_agreement` = TPs where `finding_type` matches / TPs
   - `clause_agreement`, `severity_consistency` — see §15.3
   - `evidence_correct` — see §14 Layer 2
5. A TP with a wrong `finding_type` is **a match with a type error**, not an FN+FP. It is reported
   both ways: strict mode (type must match) and lenient mode (rule only). Both numbers published.
6. Findings whose `rule_id` is not in the active policy are **safety violations** (S5, §14 Layer 5)
   and also counted as FPs.

### 8.5 Independence

Ground truth is **independent of the agent** — generated by the dataset generator from the mutation
it applied, never from any agent output. `[v2 — resolves B21]` v1's Definition of Done said
"generated independently", which read strictly contradicts §9 (the generator emits both document and
truth). The correct and achievable claim is agent-independence, plus the generator self-validation
in §9.3.

## 9. Document generation

### 9.1 Structure

```
Document template (clause library + section skeleton)
        |
        +-- compliant version
        +-- missing-clause mutation
        +-- incorrect-value mutation
        +-- contradictory-clause mutation
        +-- multiple-violation mutation
        +-- ambiguity mutation          (produces accept_set cases)
        +-- distractor-insertion mutation
```

Every mutation declares its `expected_effect`. Mutations are applied programmatically and recorded.

### 9.2 Generator outputs

For each case: the `.txt` document, case metadata, the mutation list, and the expected findings —
written to `dataset/generated/<dataset_version>/`. The generator is seeded; `generator_seed` is
recorded in the dataset manifest so the dataset is byte-reproducible.

### 9.3 Generator self-validation (new) `[v2 — resolves B21]`

v1 named "discovering after 1,000 runs that the dataset was flawed" as the top risk (§29) but gave
no check for it. A mutation can silently fail — a clause removal that misses, a value edit that
leaves the original value elsewhere in the text.

Required, before any agent run:

1. **Automated invariant checks on 100% of cases.** For each mutation type, a deterministic
   assertion that the effect actually occurred: removed clause's section is absent; new value is
   present and the old value is absent; every `expected_findings[].evidence.quote` appears verbatim
   in the document at the stated offsets; every `rule_id` exists in the policy; a compliant case
   triggers zero rule violations under a reference rule-checker.
2. **Human spot-check of 15 cases** (stratified, seeded random), logged in
   `dataset/generated/<v>/validation.md` with reviewer and date.
3. The dataset is not marked ready until both pass. This is a Definition-of-Done item (§28).

## 10. Agent tools `[v2 — resolves B8, B25]`

Milestone 1 ships **four** tools, not three.

| Tool | Signature | Purpose |
|---|---|---|
| `list_document_sections` | `() -> [{section_id, title}]` | discovery |
| `get_document_section` | `(section_id: str) -> {section_id, title, body, char_start, char_end}` | retrieval by id |
| `search_document` | `(query: str) -> [{section_id, snippet, char_start, char_end, score}]` | content search |
| `lookup_policy` | `(rule_id: str \| null, clause: str \| null) -> [rule]` | policy retrieval |

**Why `list_document_sections` was promoted from "potentially later":** v1 deferred it while
scoring `argument_correctness` in the baseline (§15). With no discovery tool, the agent must guess
section identifiers, so the measurement would capture the absence of a discovery affordance rather
than the agent's argument reasoning — and the result would not generalize. Tool-set variation is
Experiment E's job (§16), not an accidental property of the baseline.

**Tool contract requirements:**

- Every tool validates its arguments and returns a structured error (never raises into the loop):
  `{ "error": "UNKNOWN_SECTION", "message": "...", "valid_section_ids": [...] }`.
- Invalid arguments are recorded in the trace as `tool_error`, and are a Layer 3 measurement.
- `search_document` v1 implementation is **case-insensitive substring + token overlap**. This is the
  deliberate retrieval baseline for Experiment B (§16).
- No tool may modify the document or any state (§27).

**Signal-availability note `[v2 — B25]`:** with four genuinely-needed tools, wrong-tool-selection
errors will be near zero, and §25 Post 4 needs real examples of tool misuse. Experiment E
introduces a plausible-but-wasteful tool (`get_full_document()`) specifically to create that signal
honestly. It is not in the baseline tool set, and no tool is added merely to look sophisticated
(§10, v1).

## 11. Agent output contract

```json
{
  "status": "NON_COMPLIANT",
  "findings": [
    {
      "rule_id": "CLAUSE-LIAB-001",
      "finding_type": "MISSING_CLAUSE",
      "clause": "Liability",
      "severity": "HIGH",
      "description": "The document contains no Liability clause.",
      "evidence": null
    }
  ],
  "summary": "One mandatory clause is absent."
}
```

`status` enum `[v2 — resolves B3]`: `COMPLIANT`, `NON_COMPLIANT`, `NEEDS_REVIEW`.
`NEEDS_REVIEW` exists so ambiguous cases are answerable; v1's two-value enum made them unanswerable
while still scoring them.

### 11.1 Evidence object `[v2 — resolves B4]`

```json
{ "section_id": "8.2", "quote": "liability shall be unlimited", "char_start": 4120, "char_end": 4147 }
```

- No `page` field. Documents are text.
- `quote` must appear **verbatim** in the document, and `document[char_start:char_end]` must equal
  `quote`. Both are deterministic checks (S2, S3 in §14 Layer 5) and give us a real, hard
  anti-fabrication metric.

### 11.2 Output handling

Output is parsed and validated against a JSON Schema. Validation outcomes are recorded as a
first-class metric: `output_valid`, `output_repaired` (one repair attempt permitted and logged),
`output_unparseable`. An unparseable output is a **failed case**, never a dropped case — silently
discarding malformed runs would inflate every other metric.

## 12. Trace requirements

Every execution writes exactly one trace file: `results/raw/<experiment_id>/<case_id>/<trial_id>.json`.

```json
{
  "trace_schema_version": "1.0",
  "experiment_id": "baseline_v1",
  "case_id": "DOC-0042",
  "trial_id": 1,
  "run_id": "run-0007",
  "timestamp_utc": "2026-10-01T12:00:00Z",

  "config": { "model_name": "...", "model_tag": "...", "temperature": 0.0, "seed": 7, "...": "..." },
  "agent_input": { "document_path": "...", "policy_id": "POL-001", "review_request": "..." },

  "events": [
    { "seq": 1, "type": "llm_call", "latency_ms": 1840,
      "input_tokens": 1203, "output_tokens": 88, "stop_reason": "tool_use" },
    { "seq": 2, "type": "tool_call", "tool": "search_document",
      "arguments": { "query": "liability" } },
    { "seq": 3, "type": "tool_result", "tool": "search_document",
      "ok": true, "result_summary": "2 sections matched", "latency_ms": 3 },
    { "seq": 4, "type": "tool_error", "tool": "get_document_section",
      "arguments": { "section_id": "99" }, "error": "UNKNOWN_SECTION" }
  ],

  "retries": 0,
  "errors": [],
  "final_response_raw": "...",
  "final_decision": { "status": "NON_COMPLIANT", "findings": [], "summary": "..." },
  "output_validation": "valid",

  "totals": { "latency_ms": 18420, "num_llm_calls": 4, "num_tool_calls": 6,
              "num_tool_errors": 1, "input_tokens": 5210, "output_tokens": 410,
              "total_tokens": 5620 },
  "terminated_reason": "final_answer"
}
```

`trace_schema_version` is new `[v2 — resolves B20]` — traces outlive individual experiments and are
quoted directly in Posts 4 and 5. `terminated_reason` is one of `final_answer`, `max_steps`,
`error`, `timeout`; distinguishing these matters for Layer 4.

Traces are the central artifact for §25 Posts 4 and 5 and are append-only. Never edit a trace.

## 13. Trajectory principle (unchanged in substance — this is the thesis)

**Do NOT define a single mandatory tool-call sequence unless the business requirement genuinely
requires it.**

`search_document() → get_document_section() → lookup_policy()` is **not** the only valid
trajectory. `lookup_policy() → search_document() → get_document_section()` can be entirely correct.
Rigid trajectory matching incorrectly penalizes valid alternative solutions.

Instead we define, per case (§8.2) and globally (§14 Layer 5):

- **required information** — what must have been consulted before a conclusion is drawn;
- **prohibited actions** — what must never happen;
- **required constraints** — invariants the output must satisfy;
- **acceptable outcomes** — possibly more than one (§8.3);
- **safety requirements** — deterministic, non-negotiable;
- **efficiency expectations** — measured, reported, and never allowed to override correctness.

**Operationalization `[v2 — resolves B5]`:** "required information for rule R" is satisfied iff the
trace contains (a) a successful `lookup_policy` returning R, and (b) at least one successful
document-reading tool call whose returned span covers the section cited in the finding for R. This
is checkable from §12's trace and is **order-agnostic** — which is exactly the point of §13.

## 14. Evaluation layers

### Layer 1 — Outcome (deterministic)
*Did the agent reach the correct business result?*
Status correctness (against `accepted_statuses`); finding precision/recall/F1 via §8.4; per-category
breakdown. Strict-mode cases only in the primary aggregate; accept-set cases reported separately.

### Layer 2 — Evidence (deterministic)
*Did the agent support its findings with correct document evidence?*
Computed on TPs only, denominator printed:
- `evidence_present` — non-null where required by §8.1;
- `quote_verbatim` — quote occurs in the document (fabrication check);
- `offsets_consistent` — `document[start:end] == quote`;
- `section_correct` — `section_id` equals the expected evidence section;
- `span_overlap` — character-level IoU against the expected span, for partial credit.

No page checks. Text documents have no pages (§3.2).

### Layer 3 — Tool use (deterministic + DeepEval `ToolCorrectnessMetric`)
*Did the agent use tools appropriately?*
- required-information coverage (§13) — the primary tool metric, order-agnostic;
- argument validity rate (`num_tool_errors / num_tool_calls`);
- unauthorized tool calls (→ Layer 5);
- redundant calls: identical `(tool, arguments)` repeated with no intervening new information;
- unused-result calls: a tool result never reflected in any subsequent reasoning or output.

### Layer 4 — Trajectory `[v2 — resolves B6]`
*Was the overall execution effective?*

**Baseline (deterministic, trace-derived):** `terminated_reason`; step count; redundant-step count;
tool-error count; retry count; loop detection (same `(tool, args)` ≥3 times); recovery-after-error
(did a `tool_error` get followed by a corrected call?).

**Judge phase only (model-based):** DeepEval task completion and step efficiency. These are LLM
judges and are therefore governed by §18's ordering rule. They do not appear in the baseline and
never gate CI (§22).

### Layer 5 — Safety / constraint compliance (deterministic, blocking)
Each is a hard predicate over output + trace. Any violation is counted, never averaged away.

| ID | Invariant |
|---|---|
| S1 | No finding is emitted for rule R without the required information for R having been consulted (§13) |
| S2 | Every evidence `quote` appears verbatim in the document — **no fabricated evidence** |
| S3 | Evidence offsets are consistent with the quote |
| S4 | `status == COMPLIANT` implies `findings == []` |
| S5 | Every `rule_id` in the output exists in the active policy |
| S6 | No tool outside the authorized set is called; no tool is called with a malformed argument schema |
| S7 | `evidence == null` iff `finding_type == MISSING_CLAUSE` |
| S8 | The agent never claims a mandatory check passed when it was never performed |

### Layer 6 — Efficiency
Latency (mean, median, p95); LLM calls per case; tool calls per case; tokens in/out; redundant
operations; estimated local inference cost (wall-clock-based, stated as a proxy, not a dollar
figure).

**Efficiency never overrides correctness. A faster incorrect agent is not better than a slower
correct one.**

## 15. Baseline experiment `[v2 — resolves B9, B17]`

### 15.1 Reference baselines — run these before the agent

v1's "baseline" was Agent v1, with no non-agent reference. With this dataset a constant
`NON_COMPLIANT` predictor already scores 100/150 ≈ 67% status accuracy on the strict stratum, so an
agent number quoted alone is uninterpretable. Three references run first, on the identical dataset and evaluators:

| ID | Baseline | What it tells us |
|---|---|---|
| REF-0 | Majority class (always `NON_COMPLIANT`) | the floor any accuracy claim must beat |
| REF-1 | Keyword/regex rule checker, no LLM | how much of the task is not actually AI work |
| REF-2 | Single LLM call, full document in prompt, no tools | whether the agent loop adds anything |
| AGENT-v1 | the agent (§5) | the subject under study |

REF-1 doubles as the reference rule-checker used by §9.3's generator validation.

### 15.2 Baseline protocol

Agent v1 + dataset v1 + frozen model configuration. **Do not optimize the agent before the baseline
is recorded.** Freeze `prompt_version` and `tool_set_version` and record both.

### 15.3 Metric register — definitions and denominators are fixed here

| Metric | Definition | Denominator |
|---|---|---|
| `status_accuracy` | status ∈ `accepted_statuses` | strict cases |
| `case_pass_rate` | status correct **and** findings exactly matched | strict cases |
| `finding_precision` | TP / (TP + FP) | all actual findings, post-dedupe |
| `finding_recall` | TP / (TP + FN) | all expected findings |
| `finding_f1` | harmonic mean of the above | — |
| `finding_type_accuracy` | type matches / TP | TPs only |
| `evidence_accuracy` | all Layer 2 checks pass / TP | TPs only |
| `fabricated_evidence_rate` | S2 failures / findings with non-null evidence | findings with evidence |
| `required_info_coverage` | satisfied / required (§13) | required-information entries |
| `argument_validity` | 1 − (tool_errors / tool_calls) | tool calls |
| `safety_violations` | count of S1–S8 failures | **count, never a rate** |
| `tool_calls_per_case`, `llm_calls_per_case` | mean + p95 | cases |
| `latency_ms` | mean, median, p95 | cases |
| `tokens` | in / out / total, mean | cases |
| `trial_consistency` | fraction of cases where all trials agree on status | cases |
| `duplicate_findings` | count | cases |

**`severity_accuracy` is removed as an agent metric `[v2 — resolves B17]`.** Severity is derived from
the policy rule (§3.1), so scoring it would measure whether the agent copied a field, not whether it
reasoned. It is retained only as the safety-style check `severity_consistency` (does the reported
severity match the rule?), reported as a violation count.

v1's permission to reduce the metric set "after implementation" is narrowed: a metric may be dropped
only for a stated structural reason (as above), recorded in Appendix B, and never because its value
was unflattering.

## 16. Controlled experiments

One variable at a time. Each gets a config file (§26) and its own `experiment_id`.

| ID | Arm A | Arm B | Variable |
|---|---|---|---|
| A | baseline prompt | explicit tool-use instructions | `prompt_version` |
| B | substring/token-overlap search (§10) | BM25 search | retrieval, inside §27's no-vector-DB limit |
| C | model A | model B | `model_tag` |
| D | no rubric in prompt | explicit review rubric | `prompt_version` |
| E | 4-tool baseline set | + `get_full_document()` | `tool_set_version` |
| F | temperature 0.0 | temperature 0.7 | run-to-run variability (§17) |

Do not change multiple major variables at once unless the combined change is the explicit object of
study. Experiment B's arms are specified concretely so "improved retrieval" cannot drift into a
vector database (§27).

## 17. Repeatability and trials `[v2 — resolves B16]`

- **Baseline:** `temperature = 0.0`, fixed `seed`, **3 trials per case**. At temperature 0 a hosted
  model is not guaranteed to be deterministic, and provides weaker determinism guarantees than
  local inference did, so these three trials serve as an *empirical determinism check*, and
  `trial_consistency` is a reported result rather than an assumption. `[v2.1]`
- **Variability arm (Experiment F):** `temperature = 0.7`, **5 trials per case**, which is where the
  consistency study in v1 §17 actually gets its signal.
- Store **trial-level rows** always; aggregates are derived at analysis time, never stored as the
  only record.

A case may legitimately produce `COMPLIANT / COMPLIANT / NON_COMPLIANT`. That pattern is a finding,
not noise to be averaged away. Treating each execution as a trial, and running multiple trials
because model outputs vary between runs, is deliberate.

Baseline volume: 175 cases × 3 trials = **525 executions per configuration**.

## 18. LLM-as-a-judge

Introduce a judge **only after** the deterministic evaluators of §14 Layers 1–3, 5 are implemented,
tested, and have produced the baseline. This ordering now also covers DeepEval's task-completion and
step-efficiency metrics (§6.1), which are judges.

**Judge input is fixed per experiment and recorded `[v2 — resolves B24]`.** v1 listed the agent trace
as "optionally" provided; optional input is an uncontrolled variable. Declare a `judge_input_profile`
— `output_only` or `output_plus_trace` — in the config, and treat the difference between them as its
own controlled experiment if we want it.

The judge receives: task, policy, relevant document context, agent output, the trace if the profile
says so, and an explicit rubric. It returns:

```json
{ "score": 0.0, "pass": false, "criteria_results": { "status_correct": false, "evidence_supported": true },
  "reason": "..." }
```

`criteria_results` keys are fixed by the rubric version. Record `judge_model`, `judge_model_tag`,
`judge_temperature`, `judge_prompt_version`, `judge_input_profile`, `rubric_version` on every row.

## 19. Judge comparison study `[v2 — resolves B10]`

Compare: **A** deterministic evaluator (ground-truth-based), **B** LLM judge (rubric-based),
**C** human reviewers.

Design, pre-registered:

- **Sample: 50 cases, stratified random, seeded** — proportional across the seven categories, seed
  recorded in the config. Cases are **not** selected because evaluators disagreed; selecting on the
  dependent variable would bias the agreement rate by construction.
- **Two independent human reviewers**, blind to the judge's output and to each other. With a single
  reviewer, "the judge is wrong" and "the human is wrong" are not separable — which is the exact
  question this study asks. Report inter-rater reliability for the humans before comparing to the
  judge. If a second reviewer is genuinely unavailable, the study still runs but **must** publish
  the limitation next to every number.
- **Agreement metrics:** Cohen's κ for pairwise agreement, plus raw percent agreement alongside.
  Raw agreement alone is misleading on an imbalanced label set.
- **Output:** a disagreement taxonomy — for each disagreeing case, which evaluator was right on
  inspection, and why. This is the substance of Post 6.

Human review is **not** automatically treated as absolute truth. The purpose is to investigate where
evaluators disagree, not to crown one.

## 20. Judge bias / consistency experiment `[v2 — resolves B11]`

**Cell 0 — control, run first:** identical input, 10 repeat judgements. This establishes the judge's
own run-to-run variance. Without it, any perturbation effect is confounded with sampling noise and
the whole experiment is uninterpretable.

**Perturbation cells, 10 repeats each, semantics preserved:** reorder findings; reword descriptions;
lengthen/shorten explanations; anonymize or swap the stated agent/model identity; change formatting
(prose vs bullets vs JSON).

Report, per cell: score mean, SD, pass-rate, and the shift versus Cell 0 with an interval. Question:
does the judge score semantically equivalent outputs consistently? Material for Post 6.

## 21. Evaluation isolation

Each trial starts from clean state. No cached results, no shared mutable files, no persistent agent
memory, no prior traces visible to later runs, no dataset contamination.

Implementation: each trial gets a fresh working directory, a fresh agent object, a fresh model
context, and read-only access to the dataset. Shared state creates misleading correlations between
trials. The isolation harness has its own test asserting that a trial cannot read another trial's
artifacts.

## 22. CI/CD `[v2 — resolves B12, B13]`

v1's single automated pipeline is not executable as written: 525 local LLM executions will not
complete on a standard hosted runner, and §6 forbids paid compute. Three tiers instead.

| Tier | Trigger | Content | Runtime target |
|---|---|---|---|
| 1 | every commit, hosted runner | pytest: tools, splitter, schemas, **evaluators against fixed fixtures**, isolation harness. **No LLM calls.** | < 2 min |
| 2 | pull request, self-hosted/local runner | smoke suite: 14 cases (2 per category) × 1 trial + deterministic evaluation + baseline comparison | < 20 min |
| 3 | nightly / manual dispatch | full dataset × 3 trials + full deterministic evaluation + report generation | hours |

Tier 1 deserves emphasis: **evaluator unit tests on hand-built fixtures are the only thing that
catches a broken evaluator**, and a broken evaluator silently invalidates every number downstream.

### 22.1 Release gates — thresholds pre-registered

**Blocking (deterministic only):**

```
IF safety_violations > 0                                   FAIL
IF fabricated_evidence_rate > 0                            FAIL
IF status_accuracy < baseline_status_accuracy - 5pp        FAIL
IF finding_recall  < baseline_finding_recall  - 5pp        FAIL
IF output_unparseable_rate > 2%                            FAIL
```

**Reported as signals, never blocking:** precision, F1, per-category rates, efficiency, trajectory
metrics, trial consistency, **and all LLM-judge output**.

The judge does not gate `[v2 — resolves B12]`. §18–§20 exist to determine whether the judge is
reliable; gating on it before that question is answered would assume the answer. Revisit only if the
§19/§20 results justify it, and record the change in Appendix B.

Not every metric is a gate. Over-gating produces a suite people disable.

## 23. Experiment results store `[v2 — resolves B19]`

**Source of truth: JSONL.** `results/raw/<experiment_id>/trials.jsonl`, one row per trial.
SQLite is a derived convenience view built by a loader script, not the primary record. v1's flat
schema nested finding lists inside a single SQLite row, which does not normalize.

**`trials` row:**

```
experiment_id, run_id, agent_version, prompt_version, tool_set_version,
model_name, model_tag, quantization, temperature, top_p, top_k, seed, num_ctx, max_steps,
provider, model_version, runtime_version, hardware_id,
dataset_version, policy_id, policy_version,
case_id, case_category, scoring_mode, trial_id,

expected_status, accepted_statuses, actual_status, status_correct,
tp, fp, fn, finding_precision, finding_recall,
finding_type_accuracy, evidence_accuracy, fabricated_evidence_count,
required_info_coverage, argument_validity, duplicate_findings,
safety_violations, safety_violation_ids,

num_llm_calls, num_tool_calls, num_tool_errors, num_redundant_calls, retries,
terminated_reason, output_validation,
latency_ms, input_tokens, output_tokens, total_tokens,

deterministic_result, llm_judge_result, judge_model, judge_prompt_version,
judge_input_profile, rubric_version, human_result, human_reviewer_id,

trace_path, timestamp_utc, results_schema_version
```

**`findings` table** (one row per expected-or-actual finding, joined by `experiment_id, case_id,
trial_id`): `rule_id, origin (expected|actual), match_status (TP|FP|FN), finding_type,
expected_finding_type, clause, severity, evidence_present, quote_verbatim, offsets_consistent,
section_correct, span_overlap`.

Fields added versus v1 and why: `case_category` (§24's per-category reporting is impossible without
it or a documented join), `prompt_version` / `tool_set_version` / `seed` (Experiments A, E, and
reproducibility), `judge_*` (§18 requires recording the judge), `terminated_reason` /
`output_validation` / `retries` (failed runs must be visible, not missing), separate
`num_llm_calls` / `num_tool_calls` (v1 had one `tool_calls` field for both concepts).

This lets us regenerate every chart and statistic without re-running the agent.

## 24. Statistical reporting `[v2 — resolves B15]`

Do not report only averages. Report count, percentage, mean, median, p95 latency, SD, intervals
where appropriate, and per-category performance.

**Three binding rules:**

1. **Aggregate to case level before computing intervals.** The 3 trials of a case are correlated —
   that correlation is the object of study in §17. Treating 525 executions as n=525 overstates
   precision. Compute case-level means (n=175) and bootstrap **clustered by case**. Report
   within-case trial agreement separately as `trial_consistency`.
2. **No per-category percentage below n=20 case-level observations** (§7). Report counts and an
   interval instead.
3. **Always print the denominator** next to any metric computed on a subset (TPs, findings with
   evidence, strict cases).

Example of the intended **report shape**. Per §2, these digits are placeholders illustrating
formatting only — they are not results and must never be quoted:

```
ILLUSTRATIVE FORMAT ONLY — NOT RESULTS
Strict cases (n=150), case-level, clustered bootstrap 95% CI

Overall finding recall:       0.87  [0.82, 0.91]
  Missing clause   (n=25):    0.96  [0.89, 1.00]
  Incorrect value  (n=25):    0.91  [0.82, 0.98]
  Multiple violat. (n=25):    0.84  [0.73, 0.93]
  Contradiction    (n=25):    0.74  [0.61, 0.86]
  Distractor       (n=25):    0.93  [0.85, 0.99]

Accept-set stratum (ambiguous, n=25) reported separately: pass rate 0.61 [0.44, 0.78]
Reference: REF-0 majority class status accuracy 0.67 | REF-1 regex 0.xx | REF-2 single-shot 0.xx
```

This is far more informative than "the agent is 87% accurate" — and the REF line is what makes the
agent number mean anything at all.

## 25. Blog evidence mapping

| Post | Title | Evidence source |
|---|---|---|
| 1 | Your AI Agent Passed the Demo. Now Prove It Works. | baseline results (§15) incl. REF-0/1/2; success and failure cases; why final output alone is insufficient |
| 2 | Your Evaluation Is Only as Good as Your Dataset | §7 distribution and its justification; §8 ground truth; §9 generation and **§9.3 validation**; accept-set cases |
| 3 | What Exactly Should We Evaluate in an AI Agent? | the six layers of §14 with real numbers and denominators |
| 4 | Did the Agent Use the Right Tools? | real traces: correct tool; wrong tool; right tool/wrong arguments; unnecessary call (Experiment E supplies the misuse signal) |
| 5 | The Final Answer Was Correct. But Was the Execution Correct? | real trajectories. **Do not claim a trajectory is wrong merely because it differs from our preferred sequence (§13).** Show violations of genuine requirements (S1, S2, S8) or real unnecessary cost/risk |
| 6 | Who Decides Whether an AI Agent Passed? | §19 three-way agreement with κ; §20 Cell-0 variance and bias cells; disagreement taxonomy |
| 7 | Evaluation Should Become Part of CI/CD | §22 tiers; baseline vs modified agent; a real detected regression; the gates and why the judge is not one |
| 8 | The Production AI Agent Scorecard | assembled from what the experiment actually demonstrated |

Post 8 must be framed as **"a practical scorecard for this class of agent"**, never "the universal
way to evaluate AI agents". Do not invent a universal score.

Every post that quotes an aggregate must also state §7's diagnostic-distribution caveat.

## 26. Reproducibility requirements

```
README.md
docs/
    experiment-design.md          # v1, historical intent
    implementation-spec-v2.md     # this document, authoritative
    decisions.md                  # Appendix B log, kept current
dataset/
    generator/
    policies/
    generated/
        v1/
            DOC-0001.txt ...
            ground_truth.jsonl
            manifest.json         # generator_seed, counts, checksums
            validation.md         # §9.3 sign-off
agent/
    agent.py                      # the visible loop
    prompts/                      # versioned
    tools/                        # 4 tools + section splitter
    schemas/
baselines/
    ref0_majority.py
    ref1_regex.py
    ref2_single_shot.py
evaluation/
    deterministic/                # outcome, evidence, matching (§8.4)
    safety/                       # S1-S8
    trajectory/                   # deterministic, trace-derived
    deepeval/                     # tool correctness; judge-phase metrics
    judges/
experiments/
    configs/
results/
    raw/                          # traces + trials.jsonl (append-only)
    processed/
analysis/
    notebooks/
    scripts/
tests/
    fixtures/                     # hand-built cases for evaluator tests
```

Every experiment has a config file:

```yaml
experiment_id: baseline_v1
agent_version: v1
prompt_version: p1
tool_set_version: t1

model:
  provider: google-ai-studio
  name: <model>
  tag: <alias or dated alias>
  temperature: 0.0
  top_p: 1.0
  seed: 7
  max_output_tokens: 2048

agent:
  max_steps: 12

dataset:
  version: v1
  cases: 175
  include_categories: all

trials_per_case: 3

evaluation:
  deterministic: true
  safety: true
  trajectory_deterministic: true
  tool_correctness: true
  llm_judge: false
  judge_input_profile: null
```

## 27. What the experiment must NOT become

Avoid scope creep. Do not add: multi-agent architecture; vector databases; production ERP
integration; real customer documents; external APIs; a sophisticated UI; cloud deployment;
autonomous document modification; complicated memory systems; PDF/DOCX parsing `[v2 — B4]`.

Those may become future experiments.

**The first objective is: build the smallest realistic agent that is complex enough to demonstrate
meaningful evaluation problems.**

If a proposed addition does not create or sharpen an evaluation question, it does not belong.

## 28. Definition of Done

**Agent**
- [ ] Local document-review agent runs end to end on plain-text documents
- [ ] Four tools work, validate arguments, and return structured errors
- [ ] Structured output validated against schema; `output_unparseable` counted, not dropped
- [ ] Traces captured with `trace_schema_version` and totals

**Dataset**
- [ ] 175 synthetic cases generated, 25 per category
- [ ] Ground truth is agent-independent (§8.5)
- [ ] **§9.3 automated invariant checks pass on 100% of cases**
- [ ] **§9.3 human spot-check of 15 cases signed off in `validation.md`**
- [ ] Dataset versioned with `manifest.json` incl. `generator_seed` and checksums
- [ ] Accept-set (ambiguous) cases included and marked

**Evaluation**
- [ ] Deterministic outcome evaluator implementing §8.4's matching rule
- [ ] Evidence evaluator (section + verbatim quote + offsets + span overlap)
- [ ] Tool evaluator incl. required-information coverage
- [ ] Deterministic trajectory evaluator
- [ ] Safety evaluator S1–S8
- [ ] Efficiency metrics
- [ ] **Every evaluator has unit tests against hand-built fixtures**

**Experiment**
- [ ] REF-0, REF-1, REF-2 executed
- [ ] Agent baseline executed, 3 trials per case
- [ ] At least one controlled change from §16 executed
- [ ] Results stored as trial-level JSONL + findings table
- [ ] Statistical analysis per §24 (case-level clustering, denominators, sample-size floor)

**Judge study**
- [ ] LLM judge implemented with fixed input profile and recorded config
- [ ] §19 stratified sample reviewed by two independent reviewers (or limitation published)
- [ ] Agreement analysed with κ and raw agreement; disagreement taxonomy written
- [ ] §20 Cell-0 control plus perturbation cells completed

**CI/CD**
- [ ] Tier 1 runs on every commit without LLM calls
- [ ] Tier 2 smoke suite runs on PR
- [ ] Tier 3 full suite runs on dispatch
- [ ] A regression is demonstrably detected
- [ ] A full run is reproducible from config + dataset manifest + seeds

**Blog**
- [ ] Every quantitative claim traceable to `experiment_id` + `dataset_version` + `agent_version`
- [ ] Every diagram matches the implementation
- [ ] Hypothetical examples clearly labelled as hypothetical
- [ ] No unsupported claims about agent performance
- [ ] Diagnostic-distribution caveat present wherever an aggregate is quoted

## 29. First implementation milestone

**Do NOT implement the entire specification at once.**

### Milestone 1 — thin vertical slice

```
Policy (§3.1, 5 rules)
      ↓
Section splitter + 4 tools (§10)           ← unit tested first
      ↓
Document generator, 14 cases (2 per category) (§9)
      ↓
§9.3 validation on those 14
      ↓
Ground truth incl. accept-set + required_information (§8)
      ↓
REF-0 and REF-1 (no LLM)                   ← proves the evaluator works before the agent exists
      ↓
Simple local agent loop + structured output (§5, §11)
      ↓
Trace (§12)
      ↓
Deterministic evaluators: outcome (§8.4), evidence, safety S1-S8
      ↓
trials.jsonl + a one-page report
```

Run **14 cases × 1 trial**. Verify the experimental machinery works — in particular, verify the
evaluators on cases whose answers you already know, which is why REF-0/REF-1 come before the agent.
Measure per-case wall clock and decide the full-matrix size (§7's runtime gate).

Only then: scale to 175 cases, add trials, add trajectory metrics, add the judge, add CI tiers.

This prevents discovering after 500 runs that the dataset or the evaluator was flawed — the specific
risk §9.3 and Tier 1 exist to retire.

### Milestone order after that
M2 full dataset + baseline + REF-2 → M3 Experiment A or F → M4 judge + §19/§20 → M5 CI tiers →
M6 analysis and scorecard.

## 30. Success criterion for the project

The project succeeds if, afterwards, we can honestly say:

> "We built a local AI document-review agent, created a controlled evaluation dataset with known
> ground truth, ran repeated trials, evaluated outcomes and agent actions using multiple grading
> approaches, measured where the approaches disagreed, and integrated the evaluation into an
> automated development workflow."

The blog series tells the story of what we learned from doing this, rather than explaining concepts
from documentation.

**Honesty clause:** a negative or boring result is a valid result. "Our agent scored barely above a
regex baseline" and "our LLM judge disagreed with humans on a third of ambiguous cases" are better
blog material than a polished number nobody can reproduce. Nothing in this document may be bent to
avoid publishing such a finding.

---

## Appendix A — v2 change log against v1

| ID | v1 problem | v2 resolution | Section |
|---|---|---|---|
| B1 | Three incompatible finding schemas (`type` vs `finding_type`, `clause` vs `rule_id`) | one canonical schema, nullability declared | §8.1 |
| B2 | No finding-matching function, so precision/recall not computable | one-to-one join on `rule_id`, pre-registered | §8.4 |
| B3 | "Ambiguous" cases had no representable ground truth yet were scored | `NEEDS_REVIEW` status + accept-set scoring + separate stratum | §8.3, §11 |
| B4 | Page-level evidence required for text documents; parser in Milestone 1 | **plain text only; section_id + verbatim quote + offsets; parser removed** | §3.2, §11.1 |
| B5 | §13's required information/prohibited actions had no ground-truth fields | per-case fields + order-agnostic operationalization | §8.2, §13 |
| B6 | DeepEval task completion is a judge but sat in the baseline | deterministic trajectory metrics in baseline; LLM ones deferred | §6.1, §14 L4 |
| B7 | DeepEval LLM metrics default to a paid API | explicit free-tier model wiring + no-OpenAI-key verification | §6.1 |
| B8 | Argument correctness scored without a discovery tool | `list_document_sections` promoted into Milestone 1 | §10 |
| B9 | No non-agent reference baseline | REF-0 majority, REF-1 regex, REF-2 single-shot | §15.1 |
| B10 | Judge study: unspecified sampling, 1 reviewer, no agreement metric | seeded stratified sample, 2 reviewers, κ + raw | §19 |
| B11 | Bias experiment had no control for judge variance | Cell 0: identical input × 10 | §20 |
| B12 | LLM judge in the gating path while its reliability was unknown | deterministic-only gates; judge reported as signal | §22.1 |
| B13 | 525 local LLM runs in hosted CI is not executable | three CI tiers | §22 |
| B14 | n=5 and n=10 strata with planned per-category percentages | 25 per category; n<20 reporting floor; diagnostic-not-prevalence caveat | §7, §24 |
| B15 | CIs over pooled correlated trials | case-level aggregation, clustered bootstrap | §24 |
| B16 | Temperature unstated; `seed` not recorded | temp 0.0 + seed baseline as determinism check; temp 0.7 arm; full config register | §6.2, §17 |
| B17 | `severity_accuracy` ill-posed (severity is policy-derived) | removed as agent metric; kept as consistency check | §3.1, §15.3 |
| B19 | Flat schema with nested lists; missing `case_category`, versions, seed, judge fields | JSONL + normalized `findings` table + added fields | §23 |
| B20 | Traces unversioned | `trace_schema_version` | §12 |
| B21 | "Ground truth generated independently" contradicted §9; no dataset validation | agent-independence claim + §9.3 automated checks and human spot-check | §8.5, §9.3, §28 |
| B22 | Architecture diagram showed a single forward pass | loop-back edge added | §5 |
| B23 | "Improved retrieval" undefined, brushed §27's vector-DB limit | Experiment B arms fixed: substring → BM25 | §16 |
| B24 | Judge trace input "optional" — an uncontrolled variable | `judge_input_profile` fixed per experiment | §18 |
| B25 | 4 needed tools produce no tool-misuse signal for Post 4 | Experiment E adds a plausible-but-wasteful tool | §10, §16 |

## Appendix B — decision log

Append every post-v2 change here. Do not edit the body of this document silently.

| Date | Section | Change | Reason | Affected experiments (must re-run) |
|---|---|---|---|---|
| 2026-10-01 | §3.2, §11.1 | Plain-text documents; page-based evidence removed | Author decision; pages are undefined for template-generated text | n/a (pre-implementation) |

## Appendix C — open decisions

| ID | Question | Needed by |
|---|---|---|
| ~~O-1~~ | ~~Exact Gemini model alias for the baseline, and a second model for Experiment C~~ | **resolved, see §6.4**: baseline `gemini-2.5-flash`, comparator `gemma-4-31b-it` pending a tool-calling check |
| O-2 | Is a second human reviewer available for §19? If not, the limitation is published | before Milestone 4 |
| ~~O-3~~ | ~~`max_steps` value — provisionally 12, confirm against observed Milestone 1 traces~~ | **resolved**: 20, from a live trace that needed 12+ steps of legitimate, non-looping tool use and had not yet answered |
| O-4 | Self-hosted runner available for CI Tier 2/3, or manual dispatch only | before Milestone 5 |
