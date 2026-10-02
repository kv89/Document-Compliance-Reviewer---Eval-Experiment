# Code review walkthrough: one baseline run

This document traces what happens, file by file and function by function, when a baseline run is
executed, with real sample output captured from run `baseline_v1-20261001T184634Z`, case `DOC-0001`.
Use it as a map for reviewing the code: start at the entry point and follow the call order below.

## Starting file

`experiments/run_baseline.py` — this is the entry point. Everything else is called from its `main()`.

## File / function call sequence

```
experiments/run_baseline.py : main()
 1. experiments/run_baseline.py : load_config()
 2. agent/schemas/loaders.py  : load_ground_truth(), load_policy(), load_document()
 3. experiments/signoff.py    : signoff_status()
 4. experiments/run_baseline.py : build_run_config()
 5. agent/llm/client.py       : GeminiClient.__init__(), .generate()  (preflight)
 6. agent/agent.py            : Agent.__init__(), Agent.run()         (per trial, loop)
      6a. agent/prompts/p1.py       : initial_prompt(), SYSTEM_PROMPT
      6b. agent/llm/client.py       : GeminiClient.generate()          (per step)
      6c. agent/agent.py            : extract_json()
      6d. agent/tools/toolset.py    : ToolSet.call()                  (if tool call)
      6e. agent/schemas/models.py   : AgentOutput.model_validate()    (if final_answer)
 7. evaluation/deterministic/evaluate.py : evaluate_case(), to_row() / no_answer_row()
 8. agent/schemas/loaders.py  : write_jsonl()
 9. analysis/scripts/aggregate.py : summarize()
10. experiments/run_baseline.py : report write (results/processed/<run_id>.md)
```

## Sample output at each step

Captured from the real run `baseline_v1-20261001T184634Z`, case `DOC-0001`.

### 1. `load_config()`

Loads `experiments/configs/baseline_v1.yaml` into a dict. Checks `model.name` for `-latest` or
`-preview`; raises `SystemExit` if found. Sample field: `name: gemini-3.5-flash-lite`.

### 2. `load_ground_truth()`, `load_policy()`, `load_document()`

```
Case(case_id='DOC-0001', expected_status='COMPLIANT', ...)
document: raw text, 1454 characters
```

### 3. `signoff_status()`

Printed to console:

```
dataset sign-off: verified — signed off by Vishal Kalaskar (vishal.kalaskar@searce.com)
```

### 4. `build_run_config()`

```python
RunConfig(
    provider='google-ai-studio',
    model_name='gemini-3.5-flash-lite',
    max_steps=20,
    thinking_level='MINIMAL',
    ...
)
```

### 5. Preflight `GeminiClient.generate()`

One request before the sweep starts, confirming the model is callable by this key. Printed:

```
preflight ok: model reports version gemini-3.5-flash-lite
```

### 6. `Agent.run()` loop

Each step appends an event to the trace. First two events of this trial:

```json
// event seq 1, type "llm_call"
{
  "result_summary": "{\"tool\": \"lookup_policy\", \"arguments\": {\"rule_id\": \"POL-001\"}}",
  "latency_ms": 763,
  "input_tokens": 635,
  "output_tokens": 23
}
```

```json
// event seq 2, type "tool_call"
{
  "tool": "lookup_policy",
  "arguments": {"rule_id": "POL-001"}
}
```

This trial ran 9 tool calls (1 tool error) and 10 LLM calls in total before producing a final
answer. Loop end state:

```
terminated_reason: final_answer
output_validation: valid
final_decision: {
  "status": "COMPLIANT",
  "findings": [],
  "summary": "The document contains all required clauses (Liability, Payment Terms, Termination) and complies with the governing law and payment term value constraints."
}
totals: {
  "num_llm_calls": 10,
  "num_tool_calls": 9,
  "num_tool_errors": 1,
  "num_redundant_calls": 0,
  "total_tokens": 13194
}
```

### 7. `evaluate_case()` / `to_row()`

Produces one `TrialRow`:

```
case_id=DOC-0001, expected_status=COMPLIANT, actual_status=COMPLIANT,
status_correct=true, tp=0, fp=0, fn=0, ...
```

### 8. `write_jsonl()`

Writes one JSON line per trial to `results/raw/baseline_v1-20261001T184634Z/trials.jsonl`
(the row from step 7, serialized).

### 9. `summarize()`

Produces the aggregate markdown table, e.g.:

```
| metric | value | denominator |
|---|---|---|
| status accuracy | 1/2 | strict executions |
```

Safety violations reported as a count: `0`.

### 10. Final report

Written to `results/processed/baseline_v1-20261001T184634Z.md`:

```
# baseline_v1 — dataset `v1-m1`
> Dataset sign-off verified: signed off by Vishal Kalaskar (vishal.kalaskar@searce.com).
Model `gemini-3.5-flash-lite`, reported version `gemini-3.5-flash-lite`, temperature 0.0,
seed 7, thinking level `MINIMAL`, prompt `p1`, tools `t1`.
```
