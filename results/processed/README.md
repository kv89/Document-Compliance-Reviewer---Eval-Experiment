# Experiment Processed Results

This directory contains human-readable summary reports generated from raw trial rows (`results/raw/*/trials.jsonl`) via `analysis/scripts/aggregate.py`.

---

## 📊 Active Authoritative Reports

| Report | Description | Dataset & Sample |
|---|---|---|
| [baseline_v1-20261002T092914Z.md](baseline_v1-20261002T092914Z.md) | **Agent v1 Baseline Sweep.** Evaluates `gemini-3.5-flash-lite` with prompt `p1` and tools `t1` across 140 cases, including multi-trial consistency measurements. | Dataset `v1` (20 cases/category, seed 7) |
| [references-v1-s7-n20.md](references-v1-s7-n20.md) | **Reference Baselines.** Evaluates REF-0 (majority class floor) and REF-1 (deterministic regex rule check) on the exact same 140 cases for like-for-like comparison. | Dataset `v1` (20 cases/category, seed 7) |

---

## 📈 Metric Standards & Statistical Reporting

As specified in spec §24:
1. **Case-Level Aggregation:** Multi-trial cases are averaged at the case level before calculating statistics. Clustered bootstrap intervals (2,000 resamples) prevent overstating precision on correlated trials.
2. **Strata Separation:** Ambiguous cases (`accept_set` scoring) are reported separately and never pooled into strict single-truth metrics.
3. **Reporting Floor:** Per-category percentages are only published for strata with $n \ge 20$ cases.

---

## 🗄️ Historical Archive (`archive/`)

Reports from early machinery shakedowns and the 14-case pilot are stored in [`archive/`](archive/):
- `references-v1-m1.md`: Reference baselines on the initial 14-case pilot dataset.
- `baseline_v1-20261001T*.md`: Shakedown runs used to calibrate quota backoff, output parsing, and step caps (`max_steps` 12 → 20).
- `baseline_v1-20261002T061059Z.md`: First live run against `gemini-3.5-flash-lite` prior to dataset v1 scaling.
