AI Agent Evaluation
Document Compliance Reviewer — Experiment Design v1
1. Purpose
Build a small, reproducible, fully local AI agent that reviews documents against a defined compliance policy.

The primary purpose is not to build a sophisticated document-review product.

The purpose is to create a controlled experimental system that allows us to investigate:

How should AI agents be evaluated?
What should constitute success?
How should tool usage be evaluated?
How should agent trajectories be evaluated?
When are deterministic evaluators sufficient?
When is LLM-as-a-judge useful?
How reliable is an LLM judge?
How can agent evaluation become part of CI/CD?
Which metrics are useful for assessing production readiness?
The resulting experiment will provide the technical evidence and examples for an eight-part LinkedIn blog series on AI Agent Evaluation.

2. Core principle
The experiment must be designed before results are collected.

We must not:

invent performance numbers;
modify evaluation criteria after seeing results merely to improve the result;
assume one specific agent trajectory is always correct;
treat an LLM judge’s score as ground truth;
present hypothetical results as experimental results.
All quantitative claims in the blog series must be traceable to an actual experiment run.

3. Use case
Document Compliance Reviewer Agent
The agent receives:

A document.
A compliance/review policy.
A review request.
The agent must determine whether the document complies with the policy and identify any violations.

Example:

Review policy
A document must contain:

Payment Terms
Termination Clause
Confidentiality Clause
Liability Clause
Governing Law
Additional policy rules may specify constraints such as:

payment terms must not exceed a defined threshold;
liability must have a defined cap;
governing law must belong to an approved set.
Document
A synthetic document may contain:

all required clauses;
one missing clause;
multiple missing clauses;
an incorrect value;
a policy violation;
contradictory information;
ambiguous wording;
irrelevant information.
Expected result
The agent produces structured findings.

Example:

{
  "status": "NON_COMPLIANT",
  "findings": [
    {
      "type": "MISSING_CLAUSE",
      "clause": "Liability",
      "severity": "HIGH",
      "evidence": null
    }
  ]
}
The exact schema should be finalized before dataset generation.

4. Why this use case
This use case was selected because it provides several properties required by the experiment:

deterministic ground truth can be created;
documents can be generated synthetically;
retrieval can be introduced;
multiple tools can be introduced;
tool arguments can be evaluated;
document evidence can be evaluated;
agent trajectories can be captured;
ambiguous cases can be deliberately introduced;
deterministic and model-based graders can both be used;
the same dataset can be reused across all experiments.
The system should remain deliberately small.

We are testing evaluation methodology, not attempting to reproduce an enterprise contract-review platform.

5. Experimental architecture
Initial architecture:

                    Review Request
                          |
                          v
                  +---------------+
                  | Review Agent  |
                  +-------+-------+
                          |
                +---------+---------+
                |         |         |
                v         v         v
          search_document() 
          get_document_section()
          lookup_policy()
                |         |         |
                +---------+---------+
                          |
                          v
                   Review Decision
                          |
                          v
                 Structured Findings
                          |
                          v
                     Trace Store
                          |
              +-----------+-----------+
              |                       |
              v                       v
       Deterministic             Model-based
         Evaluators                Evaluators
              |                       |
              +-----------+-----------+
                          |
                          v
                    Experiment Results
The initial agent should be implemented using plain Python rather than hiding the agent loop behind a framework.

A framework such as LangGraph may be evaluated later, but it should not be a dependency of the first experiment unless it provides a clear experimental benefit.

6. Open-source technology constraints
The experiment must run without paid APIs.

Preferred stack:

Runtime
Python
Ollama
Local model
Use an appropriately licensed open model supported by Ollama.

The exact model must be recorded in every experiment result:

model
model version/tag
quantization, if applicable
temperature
context configuration
hardware
Document processing
Use an open-source local document parser such as Docling if PDF/document parsing is required.

Agent
Plain Python initially.

Evaluation
Use two layers:

Custom deterministic evaluation implemented in Python.
DeepEval for selected agent-evaluation capabilities.
DeepEval currently supports trajectory-level evaluation such as task completion and step efficiency, as well as component-level evaluation such as tool correctness and argument correctness. (DeepEval)

Testing
pytest
Data
JSON
SQLite initially if useful
Analysis
pandas
matplotlib
Version control
Git
GitHub
The core experiment must remain runnable without a paid cloud service.

7. Dataset design
Start with approximately 100–200 synthetic documents.

The exact number should be decided after measuring execution time.

The dataset must contain known ground truth.

Suggested initial distribution:

Category

Approx. cases

Fully compliant

20

Missing required clause

20

Incorrect policy value

20

Multiple violations

15

Contradictory clauses

10

Ambiguous cases

10

Distractor/irrelevant content

5

These are initial design targets, not final numbers.

The final distribution should be documented.

8. Ground-truth structure
Each test case should have a machine-readable expected result.

Example:

{
  "case_id": "DOC-0042",
  "expected_status": "NON_COMPLIANT",
  "expected_findings": [
    {
      "type": "POLICY_VIOLATION",
      "rule_id": "PAYMENT-001",
      "severity": "MEDIUM"
    }
  ]
}
Where possible, expected findings should contain:

finding type;
rule ID;
severity;
relevant clause;
expected evidence location;
expected status.
The ground truth must be independent of the agent.

9. Document generation
Documents should be generated from structured templates rather than manually written one by one.

Example:

Document template
        |
        +-- compliant version
        |
        +-- missing clause mutation
        |
        +-- incorrect value mutation
        |
        +-- contradictory clause mutation
        |
        +-- multiple violation mutation
Every mutation should have a known expected effect.

This provides controlled test cases.

The dataset generator must save:

source document;
case metadata;
mutation(s);
expected findings.
10. Agent tools
Start with a small tool set.

Tool 1 — search_document
Search document content for a phrase or concept.

Tool 2 — get_document_section
Retrieve a specific section/page or relevant document segment.

Tool 3 — lookup_policy
Retrieve the applicable policy rule.

Potentially later:

Tool 4 — list_document_sections
Return available document sections.

Do not add tools merely to make the agent appear more sophisticated.

Every tool should have an evaluation purpose.

11. Agent output contract
The agent should return structured output.

Example:

{
  "status": "NON_COMPLIANT",
  "findings": [
    {
      "rule_id": "LIABILITY-001",
      "finding_type": "POLICY_VIOLATION",
      "severity": "HIGH",
      "description": "...",
      "evidence": {
        "page": 4,
        "section": "8.2"
      }
    }
  ],
  "summary": "..."
}
The structured output is important because it allows deterministic evaluation.

12. Trace requirements
Every agent execution must generate a trace.

At minimum capture:

case_id
run_id
timestamp
model
model configuration

agent input

LLM calls
tool calls
tool arguments
tool results

errors
retries
final response
final structured decision

latency
token usage, where available
number of model calls
number of tool calls
Example:

{
  "case_id": "DOC-0042",
  "run_id": "run-0007",

  "events": [
    {
      "type": "llm_call"
    },
    {
      "type": "tool_call",
      "tool": "search_document",
      "arguments": {
        "query": "liability"
      }
    },
    {
      "type": "tool_result"
    }
  ],

  "final_decision": "NON_COMPLIANT"
}
The trace is central to Posts 4 and 5.

13. Important trajectory principle
Do NOT define a single mandatory tool-call sequence unless the business requirement genuinely requires it.

For example, do not automatically define:

search_document()
→ get_section()
→ lookup_policy()
as the only valid trajectory.

An agent may legitimately:

lookup_policy()
→ search_document()
→ get_section()
and still perform correctly.

Instead, define:

required information;
prohibited actions;
required constraints;
acceptable outcomes;
safety requirements;
efficiency expectations where appropriate.
This is consistent with current guidance that overly rigid trajectory matching can incorrectly penalize valid alternative solutions. (Anthropic)

14. Evaluation layers
The experiment should deliberately separate evaluation into layers.

Layer 1 — Outcome evaluation
Question:

Did the agent reach the correct business result?

Examples:

correct compliance status;
correct findings;
correct classification;
correct severity.
Use deterministic evaluation wherever possible.

Layer 2 — Evidence evaluation
Question:

Did the agent support its findings with the correct document evidence?

Check:

correct page;
correct section;
correct text;
evidence actually supports finding.
Layer 3 — Tool evaluation
Question:

Did the agent use tools appropriately?

Measure:

correct tool selection;
correct arguments;
invalid tool calls;
unnecessary calls;
missing required information.
DeepEval provides current metrics specifically for tool correctness and argument correctness. (DeepEval)

Layer 4 — Trajectory evaluation
Question:

Was the overall execution effective?

Potential measurements:

task completion;
unnecessary/redundant steps;
failed tool calls;
retries;
excessive loops;
recovery from errors.
DeepEval currently treats task completion and step efficiency as trajectory-level metrics, rather than individual tool-call metrics. (DeepEval)

Layer 5 — Safety / policy compliance
Question:

Did the agent violate any explicit operational constraint?

Examples:

cite evidence before reporting a finding;
never invent evidence;
never approve a document when a mandatory check has failed;
never use unauthorized tools.
Where possible these checks should be deterministic.

Layer 6 — Efficiency
Measure:

latency;
model calls;
tool calls;
tokens;
estimated inference cost;
redundant operations.
Efficiency should not override correctness.

A faster incorrect agent is not better than a slower correct one.

15. Baseline experiment
First run:

Agent v1 + fixed dataset + fixed model configuration

Do not optimize the agent before establishing the baseline.

Record:

Task success
Finding precision
Finding recall
Classification accuracy
Severity accuracy
Evidence accuracy
Tool correctness
Argument correctness
Tool calls / task
LLM calls / task
Latency
Token usage
The exact metric set may be reduced after implementation if a metric is not meaningful.

16. Controlled experiment
After baseline, make one controlled change at a time.

Possible experiments:

Experiment A
Baseline prompt

vs.

Improved tool-use instructions.

Experiment B
Baseline retrieval

vs.

Improved retrieval.

Experiment C
Model A

vs.

Model B.

Experiment D
No explicit evaluation guidance

vs.

Explicit review rubric.

Experiment E
Basic tool set

vs.

Expanded tool set.

Do not change multiple major variables simultaneously unless the experiment specifically intends to study the combined change.

17. Repeatability
Because local LLM agent behavior may vary between executions, each evaluation case should support multiple trials.

Initial target:

100 cases × 3 trials
This gives:

300 agent executions per configuration.

The exact number can be adjusted according to execution time.

Record trial-level results rather than only aggregate averages.

A case may produce:

Trial 1 → COMPLIANT
Trial 2 → COMPLIANT
Trial 3 → NON_COMPLIANT
This allows us to study consistency.

Anthropic’s current evaluation guidance explicitly treats each execution as a trial and recommends multiple trials because model outputs can vary between runs. (Anthropic)

18. LLM-as-a-judge experiment
Introduce an LLM judge only after deterministic evaluation is established.

The judge receives:

task;
policy;
document context or relevant evidence;
agent output;
optionally the agent trace;
explicit evaluation rubric.
The judge should produce:

{
  "score": 0.0,
  "pass": false,
  "criteria_results": {},
  "reason": "..."
}
The judge model must be recorded.

19. Judge comparison
Compare three evaluation approaches:

A. Deterministic evaluator
Ground-truth-based.

B. LLM judge
Rubric-based.

C. Human reviewer
A small independently reviewed sample.

For example:

50 selected cases
       |
       +---- deterministic
       |
       +---- LLM judge
       |
       +---- human review
Then measure agreement.

Important:

Human review is not automatically treated as absolute truth.

The purpose is to investigate where evaluators disagree.

20. Judge bias experiment
Deliberately test whether changing irrelevant presentation details changes the judge’s result.

Potential tests:

reorder findings;
change wording while preserving meaning;
change explanation length;
anonymize agent/model identity;
vary formatting.
Question:

Does the judge score semantically equivalent outputs consistently?

This becomes material for Post 6.

21. Evaluation isolation
Each trial should start from a clean state.

Avoid:

cached previous results;
shared mutable files;
persistent agent memory;
previous traces being visible to later runs;
dataset contamination.
Each trial should have an isolated working directory or equivalent state.

This is particularly important because shared state can create misleading correlations between trials. (Anthropic)

22. CI/CD experiment
Once the evaluation suite is stable, run it automatically.

Example:

Git commit
    ↓
Unit tests
    ↓
Agent evaluation suite
    ↓
Deterministic checks
    ↓
LLM evaluation
    ↓
Compare against baseline
    ↓
Generate report
Potential release gates:

IF critical correctness < threshold
    FAIL

IF false-positive rate > threshold
    FAIL

IF safety violation > 0
    FAIL
Do not make every metric a blocking gate.

Some metrics should be reported as signals.

DeepEval currently supports running evaluation suites through CI/CD workflows. (DeepEval)

23. Experiment results database
Store every trial in machine-readable form.

Suggested schema:

experiment_id
agent_version
model
model_config
dataset_version
case_id
trial_id

expected_status
actual_status

expected_findings
actual_findings

evidence_score

tool_calls
tool_correctness
argument_correctness

task_completion
step_efficiency

latency_ms
input_tokens
output_tokens
total_tokens

deterministic_result
llm_judge_result
human_result

timestamp
This allows us to regenerate charts and statistics without rerunning the agent.

24. Statistical reporting
Do not report only averages.

Where useful, report:

count;
percentage;
mean;
median;
p95 latency;
standard deviation;
confidence intervals where appropriate;
per-category performance.
Example:

Overall finding recall: 87%

But:

Missing clause:       96%
Incorrect value:      91%
Contradiction:        74%
Ambiguous cases:      61%
This is much more informative than:

“The agent is 87% accurate.”

25. Blog evidence mapping
The experiment must explicitly map to the eight planned posts.

Post 1
Your AI Agent Passed the Demo. Now Prove It Works.
Use:

baseline results;
examples of successful and failed cases;
explanation of why final output alone isn’t sufficient.
Post 2
Your Evaluation Is Only as Good as Your Dataset
Use:

dataset construction;
ground truth;
case categories;
examples of edge cases;
dataset distribution.
Post 3
What Exactly Should We Evaluate in an AI Agent?
Use:

outcome metrics;
evidence metrics;
tool metrics;
trajectory metrics;
safety;
efficiency.
Post 4
Did the Agent Use the Right Tools?
Use actual traces showing:

correct tool;
wrong tool;
correct tool/wrong arguments;
unnecessary tool call.
Post 5
The Final Answer Was Correct. But Was the Execution Correct?
Use real trajectory examples.

Important: do not claim a trajectory is wrong merely because it differs from our preferred sequence.

Demonstrate cases where execution violated a genuine requirement or introduced unnecessary cost/risk.

Post 6
Who Decides Whether an AI Agent Passed?
Use:

deterministic grader;
LLM judge;
human review;
disagreement analysis;
judge consistency experiment.
Post 7
Evaluation Should Become Part of CI/CD
Use:

baseline vs modified agent;
regression detection;
automated evaluation;
release gates.
Post 8
The Production AI Agent Scorecard
Assemble the final metrics based on what the experiment demonstrated.

Do not invent a universal score.

The scorecard should be presented as:

“A practical scorecard for this class of agent”

rather than:

“The universal way to evaluate AI agents.”

26. Reproducibility requirements
The GitHub repository should contain:

README.md

docs/
    experiment-design.md

dataset/
    generator/
    generated/

agent/
    agent.py
    prompts/
    tools/

evaluation/
    deterministic/
    deepeval/
    judges/

experiments/
    configs/

results/
    raw/
    processed/

analysis/
    notebooks/
    scripts/

tests/
Every experiment should have a configuration file.

Example:

experiment_id: baseline_v1

model:
  provider: ollama
  name: <model>
  temperature: <value>

dataset:
  version: v1
  cases: 100

trials_per_case: 3

evaluation:
  deterministic: true
  llm_judge: false
27. What the experiment must NOT become
Avoid scope creep.

Do not initially add:

multi-agent architecture;
complex vector databases;
production ERP integration;
real customer documents;
external APIs;
sophisticated UI;
cloud deployment;
autonomous document modification;
complicated memory systems.
Those may become future experiments.

The first objective is:

Build the smallest realistic agent that is complex enough to demonstrate meaningful evaluation problems.

28. Definition of Done
The experiment is ready for the blog series when we have:

Agent
☐ Local document-review agent works.
☐ Tools work.
☐ Structured output works.
☐ Traces are captured.
Dataset
☐ Synthetic dataset generated.
☐ Ground truth generated independently.
☐ Dataset versioned.
☐ Edge cases included.
Evaluation
☐ Deterministic outcome evaluator.
☐ Evidence evaluator.
☐ Tool evaluator.
☐ Trajectory evaluator.
☐ Safety/constraint evaluator.
☐ Efficiency metrics.
Experiment
☐ Baseline executed.
☐ Multiple trials executed.
☐ At least one controlled change tested.
☐ Results stored.
☐ Statistical analysis generated.
Judge study
☐ LLM judge implemented.
☐ Human sample reviewed.
☐ Agreement/disagreement analyzed.
☐ Judge consistency tested.
CI/CD
☐ Evaluation can run automatically.
☐ Regression can be detected.
☐ Results are reproducible.
Blog
☐ Every quantitative claim traceable to experiment results.
☐ Every diagram represents the actual implementation.
☐ Hypothetical examples clearly labelled.
☐ No unsupported claims about agent performance.
29. First implementation milestone
Do NOT implement the entire specification at once.

Milestone 1
Build only:

Synthetic documents
        ↓
Ground truth
        ↓
Document parser
        ↓
Simple local agent
        ↓
Three tools
        ↓
Structured output
        ↓
Trace
        ↓
Deterministic evaluator
Run 10–20 cases first.

Verify that the experimental machinery works.

Only then scale to the full dataset and introduce LLM judges, trajectory metrics and CI/CD.

This prevents us from discovering after 1,000 runs that the dataset or evaluator itself was flawed.

30. Success criterion for the project
The project succeeds if, after completing it, we can honestly say:

“We built a local AI document-review agent, created a controlled evaluation dataset with known ground truth, ran repeated trials, evaluated outcomes and agent actions using multiple grading approaches, measured where the approaches disagreed, and integrated the evaluation into an automated development workflow.”

The blog series should then tell the story of what we learned from doing this, rather than simply explaining concepts from documentation.