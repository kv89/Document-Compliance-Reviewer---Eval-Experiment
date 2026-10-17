# Dataset & Ground Truth Validation

This directory contains the synthetic contract-compliance review datasets, policy definitions, and cryptographic sign-off records.

---

## 📁 Directory Structure

```
dataset/
├── policies/
│   └── POL-001.json             # Compliance review policy (5 rules)
├── generator/
│   ├── generate.py              # Synthetic document generator (mutations & invariants)
│   ├── validation_report.py     # Generates human spot-check validation.md
│   └── clauses.py               # Template clauses and mutation primitives
└── generated/
    ├── v1/                      # ACTIVE: Full 175-case evaluation dataset (25/category)
    │   ├── DOC-0001.txt ...     # Individual document files
    │   ├── ground_truth.jsonl   # Canonical expected results (agent-independent)
    │   ├── manifest.json        # Generator seed, counts, checksums
    │   └── validation.md        # Cryptographic sign-off & human spot-check audit
    └── v1-m1/                   # HISTORICAL: 14-case pilot dataset (2/category)
        ├── ground_truth.jsonl
        ├── manifest.json
        └── validation.md
```

---

## 🔒 Cryptographic Sign-Off Gate (`validation.md`)

Under spec §9.3 and §28, an experiment result is reportable **only if a human reviewed the exact bytes of the ground truth**.

The gate (`experiments/signoff.py`) reads `dataset/generated/<version>/validation.md` at runtime and verifies:
1. `reviewer` and `result: accepted` are populated.
2. The SHA-256 hash recorded in `validation.md` matches `sha256(ground_truth.jsonl)` exactly.
3. If `ground_truth.jsonl` is regenerated or modified, the sign-off is automatically invalidated.

---

## 🔄 Reproduction

Datasets can be byte-identically reproduced using their pinned seeds:

```bash
# Full dataset (v1 — 175 cases, seed 7):
uv run python -m dataset.generator.generate --version v1 --per-category 25 --seed 7

# Generate spot-check validation template:
uv run python -m dataset.generator.validation_report --version v1
```
