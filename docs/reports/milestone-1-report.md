# Milestone 1 Report: Experimental Machinery & Baseline Verification

**Document Compliance Reviewer — Evaluation Experiment**  
**Date:** 2026-10-15  
**Author / Reviewer:** Vishal Kalaskar (mail.vishaldk@gmail.com)  
**Spec Reference:** Spec §7, §9.3, §15.1, §17, §29  

---

## 1. Objective of Milestone 1

Milestone 1 is a thin vertical slice designed to prove the entire experimental apparatus before scaling to multi-arm experiments. Under spec §29, the goal is not to maximize model score, but to:
1. Prove schemas, section splitters, tools, and deterministic evaluators on cases with pre-determined ground truth.
2. Measure per-trial wall clock and provider request budgets to validate the §7 runtime gate.
3. Validate dataset sign-off cryptographic binding (`ground_truth.jsonl` SHA-256).
4. Run deterministic reference baselines (REF-0 majority class, REF-1 regex) to establish ground floors before agent evaluation.
5. Complete the baseline agent sweep (`gemini-3.5-flash-lite`, prompt `p1`, tools `t1`) and measure empirical trial consistency.

---

## 2. Experimental Machinery Verification

| Component | Implementation | Verification State |
|---|---|---|
| **Policy** | `POL-001` (5 rules: Payment, Termination, Liability, Payment Cap, Governing Law) | Verified |
| **Tools** | `search_document`, `get_document_section`, `lookup_policy` (JSON protocol) | 100% verified via unit tests |
| **Evaluators** | Layer 1 Outcome, Layer 2 Evidence, Layer 5 Safety (S1–S8) | 100% verified, 200 unit tests passing |
| **Dataset v1** | 175 synthetic cases (25 / category across 7 categories) | Invariants pass 100%; human spot-check signed off |
| **Sign-off Gate** | SHA-256 hash verified by runner (`signoff.py`) | Verified: `7f9f3ed9b015b372...` |
| **Reference Baselines** | REF-0 (Majority Class), REF-1 (Deterministic Regex) | Executed on aligned 140-case sample |

---

## 3. Measured Results Summary (140-Case Sample)

The diagnostic sample comprises 20 cases per category (140 total: 120 strict stratum, 20 accept-set stratum).

| Metric | REF-0 (Majority) | REF-1 (Regex) | Agent v1 (`p1`, Flash-Lite) |
|---|---|---|---|
| **Strict Status Accuracy** | 80/120 (66.7%) | 100/120 (83.3%) | **101/120 (84.2%)** |
| **Full Case Pass** | 0/120 (0.0%) | **100/120 (83.3%)** | 69/120 (57.5%) |
| **Evidence Accuracy** | undefined | **1.00** | 0.28 |
| **Safety Violations** | **0** | **0** | 63 total (majority S3) |
| **Contradictory Docs Solved** | 20/20 (guessed) | 0/20 (missed) | 1/20 (answers `COMPLIANT`) |
| **Trial Consistency** | N/A | N/A | **27/28 cases (96.4%)** |

---

## 4. Operational Budget & Runtime Gate (Spec §7)

Observed performance during baseline execution on Google AI Studio (`gemini-3.5-flash-lite`):

- **Mean Wall Clock per Trial:** 11.2 seconds.
- **Mean Model Requests per Trial:** 11.5 requests (10.4 tool calls + final verdict + repair if needed).
- **Mean Tokens per Trial:** 16,626 tokens (including charged internal `thinking_tokens`).
- **Free-Tier Constraint:** Daily cap is 500 requests/day per project. Divided by 11.5 requests/trial, practical throughput is **~43 trials/day**.
- **Runtime Gate Decision:** Full 175 × 3 = 525 executions would require ~12–14 days of quota on a single free key. The stratified repeat subset (28 cases × 3 trials + 112 cases × 1 trial = 196 planned executions) successfully captures trial consistency while remaining within practical quota limits.

---

## 5. Key Empirical Discoveries for Subsequent Milestones

1. **Deterministic Baseline Superiority:** REF-1 (no LLM) achieves 100/120 full case pass, soundly beating the agent's 69/120 due to zero evidence hallucinations.
2. **Systematic Offset Hallucination (S3):** The agent cites verbatim text from correct sections but fabricates `char_start` / `char_end` integers in 38+ cases. Target for Experiment A (`p2`).
3. **Wasted First Tool Call:** In 100% of traces, the agent opens with `lookup_policy(rule_id="POL-001")`, returning `UNKNOWN_RULE`. This consumes ~1 in 11 requests pointlessly. Target for Experiment A (`p2`).
4. **Contradiction Blindness:** The agent defaulted to `COMPLIANT` on 19 of 20 contradiction cases. Target for prompt and reasoning improvement.
5. **High Empirical Consistency:** At `temperature: 0.0`, trial consistency reached 96.4% (27/28 cases), proving the baseline is reliable for comparative experimentation.

---

## 6. Milestone 1 Exit Sign-Off

The experimental machinery, evaluation pipelines, sign-off gates, reference baselines, and baseline sweeps are verified and reproducible. Milestone 1 is **CLOSED**.
