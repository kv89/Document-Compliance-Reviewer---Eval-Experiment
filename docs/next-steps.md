# Next steps to Milestone 1 completion and blog handoff

1. Re-run `--limit 2` to confirm the `max_steps=20` fix (DOC-0001 passes again, DOC-0002 reaches
   `final_answer` instead of `MAX_STEPS`).
2. Check quota remaining today on `gemini-3.5-flash-lite` before the next step — the report's
   "Request budget" section shows mean requests per trial, compare against the daily cap.
3. Run the full 14-case Milestone 1 set (`experiments.run_baseline`, no `--limit`), 1 trial per
   case, confirm no `stopped_early`.
4. Inspect `results/processed/<run_id>.md`: all 6 evaluation layers scored, safety invariants
   S1-S8 checked, no voided trials.
5. Confirm REF-0 and REF-1 baseline numbers already exist for the same dataset and schema 1.2 —
   re-run them if the schema changed since they were last generated.
6. Decide the full-matrix scale (175 cases x 3 trials) is feasible under the free-tier daily
   quota, using the step 4 report's section 7 runtime/request gate numbers. If not feasible,
   resolve it (upgrade tier, reduce trials, or document the constraint).
7. Get fresh human sign-off for dataset v1 at full scale (175 cases), per
   `experiments/signoff.py`'s hash-binding rule — a new sign-off is needed if the sweep scope
   changes from Milestone 1's 14 cases.
8. Run the full 175x3 matrix for the baseline (`gemini-3.5-flash-lite`).
9. Run the Experiment C comparator (`gemma-4-31b-it`) — first check it accepts the JSON
   tool-calling protocol (flagged condition in spec section 6.4, not yet tested).
10. Run the remaining experiments per spec section 29 (A-F) and REF-2, as time and quota allow —
    at minimum whichever ones the blog series needs.
11. Write the one-page Milestone 1 report (spec deliverable) summarizing the clean run.
12. Pull together the evidence set for blog handoff: `docs/decisions.md` (narrative and timeline),
    `docs/implementation-spec-v2.md` (method and rigor), `results/processed/*.md` and
    `results/raw/*/trials.jsonl` (concrete numbers and examples).
13. Push the repository to git (user's call, deferred until now per "skip git, push at the end").

Blog writing can start once steps 1-10 (or whichever experiments are in scope) and step 12 are
done.
