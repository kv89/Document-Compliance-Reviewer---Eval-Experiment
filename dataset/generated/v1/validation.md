# Dataset validation — v1

Spec section 9.3. Two gates: automated invariant checks on 100% of cases, and a human
spot-check of 15 stratified cases. The dataset is not ready for agent runs until both pass.

## Provenance

- dataset_version: `v1`
- generator_version: `g1`
- generator_seed: `7`
- policy: `POL-001` `v1`
- created_utc: `2026-10-02T08:47:15+00:00`
- cases: 175 — {"compliant": 25, "missing_clause": 25, "incorrect_value": 25, "multiple_violations": 25, "contradictory": 25, "ambiguous": 25, "distractor": 25}

Regenerate byte-identically with:

```
python -m dataset.generator.generate --version v1 --per-category 25 --seed 7
```

## Automated gate (passed — the generator refuses to write otherwise)

Checked for every one of the 175 cases at generation time:

- no duplicate section identifiers;
- every expected evidence quote appears exactly once in the document (S2), and its
  character offsets resolve to that quote (S3);
- every cited section exists, and the quote lies inside it;
- severity and clause equal the policy rule's values;
- `MISSING_CLAUSE` findings carry no evidence, all other types carry evidence (S7);
- status and findings agree (S4), and accept-set cases never accept `COMPLIANT`;
- every expected finding has a `required_information` entry;
- the mutation actually took effect, judged by the independent reference checker.

All 175 cases passed; the generator would have refused to write the dataset otherwise.

## Human spot-check: 15 stratified cases

Per spec section 9.3 item 2, 15 cases drawn stratified and seeded (`random.Random(7)`,
2 per category plus 1 extra from `compliant`), not a full re-review of all 175. Sample
selection is reproducible from the seed above.

| case | category | scoring mode | expected status | rule(s) |
|---|---|---|---|---|
| DOC-0003 | compliant | strict | COMPLIANT | - |
| DOC-0013 | compliant | strict | COMPLIANT | - |
| DOC-0021 | compliant | strict | COMPLIANT | - |
| DOC-0027 | missing_clause | strict | NON_COMPLIANT | CLAUSE-TERM-001 |
| DOC-0042 | missing_clause | strict | NON_COMPLIANT | CLAUSE-LIAB-001 |
| DOC-0062 | incorrect_value | strict | NON_COMPLIANT | VALUE-PAY-001 |
| DOC-0069 | incorrect_value | strict | NON_COMPLIANT | VALUE-PAY-001 |
| DOC-0077 | multiple_violations | strict | NON_COMPLIANT | CLAUSE-LIAB-001, ENUM-LAW-001 |
| DOC-0082 | multiple_violations | strict | NON_COMPLIANT | VALUE-PAY-001, ENUM-LAW-001 |
| DOC-0102 | contradictory | strict | NON_COMPLIANT | ENUM-LAW-001 |
| DOC-0103 | contradictory | strict | NON_COMPLIANT | VALUE-PAY-001 |
| DOC-0130 | ambiguous | accept_set | NEEDS_REVIEW or NON_COMPLIANT | ENUM-LAW-001 |
| DOC-0136 | ambiguous | accept_set | NEEDS_REVIEW or NON_COMPLIANT | ENUM-LAW-001 |
| DOC-0154 | distractor | strict | COMPLIANT | - |
| DOC-0168 | distractor | strict | COMPLIANT | - |

### DOC-0003 — compliant

- document: `dataset/generated/v1/DOC-0003.txt`
- note: All five rules satisfied. Payment terms 15 days, at or under the 45-day cap.
- expected findings: none.

- [ ] DOC-0003 verdict is correct

### DOC-0013 — compliant

- document: `dataset/generated/v1/DOC-0013.txt`
- note: All five rules satisfied. Payment terms 15 days, at or under the 45-day cap.
- expected findings: none.

- [ ] DOC-0013 verdict is correct

### DOC-0021 — compliant

- document: `dataset/generated/v1/DOC-0021.txt`
- note: All five rules satisfied. Payment terms 30 days, at or under the 45-day cap.
- expected findings: none.

- [ ] DOC-0021 verdict is correct

### DOC-0027 — missing_clause

- document: `dataset/generated/v1/DOC-0027.txt`
- note: Section 6 (Termination) removed entirely.
- `CLAUSE-TERM-001` **MISSING_CLAUSE** (Termination, severity HIGH): The document contains no
  Termination clause. Evidence: none, correct for a missing clause.
- mutation `M-REMOVE-CLAUSE` on section 6: removed "Either party may terminate this Agreement
  for convenience by giving 90 days written notice. Either party may terminate immediately for
  material breach that remains uncured after 14 days."

- [ ] DOC-0027 verdict is correct

### DOC-0042 — missing_clause

- document: `dataset/generated/v1/DOC-0042.txt`
- note: Section 7 (Liability) removed entirely.
- `CLAUSE-LIAB-001` **MISSING_CLAUSE** (Liability, severity HIGH): The document contains no
  Liability clause. Evidence: none, correct for a missing clause.
- mutation `M-REMOVE-CLAUSE` on section 7: removed "The total aggregate liability of each
  party under this Agreement is limited to the total fees paid in the twelve months preceding
  the claim."

- [ ] DOC-0042 verdict is correct

### DOC-0062 — incorrect_value

- document: `dataset/generated/v1/DOC-0062.txt`
- note: Payment Terms clause is present, so only the value rule is breached.
- `VALUE-PAY-001` **POLICY_VIOLATION** (Payment Terms, severity MEDIUM): Payment terms of 120
  days exceed the 45-day maximum.
  - cites section 4.1, chars 567-593, quote: "within 120 days of receipt"
- mutation `M-VALUE-PAY` on section 4.1: "within 45 days of receipt" -> "within 120 days of
  receipt"

- [ ] DOC-0062 verdict is correct

### DOC-0069 — incorrect_value

- document: `dataset/generated/v1/DOC-0069.txt`
- note: Payment Terms clause is present, so only the value rule is breached.
- `VALUE-PAY-001` **POLICY_VIOLATION** (Payment Terms, severity MEDIUM): Payment terms of 75
  days exceed the 45-day maximum.
  - cites section 4.1, chars 570-595, quote: "within 75 days of receipt"
- mutation `M-VALUE-PAY` on section 4.1: "within 45 days of receipt" -> "within 75 days of
  receipt"

- [ ] DOC-0069 verdict is correct

### DOC-0077 — multiple_violations

- document: `dataset/generated/v1/DOC-0077.txt`
- note: A missing clause and a value breach in one document, with different evidence shapes.
- `CLAUSE-LIAB-001` **MISSING_CLAUSE** (Liability, severity HIGH): The document contains no
  Liability clause. Evidence: none.
- `ENUM-LAW-001` **POLICY_VIOLATION** (Governing Law, severity HIGH): California is not an
  approved jurisdiction.
  - cites section 8, chars 1052-1074, quote: "the laws of California"
- mutations: section 7 Liability clause removed; section 8 "India" -> "California"

- [ ] DOC-0077 verdict is correct

### DOC-0082 — multiple_violations

- document: `dataset/generated/v1/DOC-0082.txt`
- note: Two independent rule breaches: payment value and jurisdiction.
- `VALUE-PAY-001` **POLICY_VIOLATION** (Payment Terms, severity MEDIUM): Payment terms of 75
  days exceed the 45-day maximum.
  - cites section 4.1, chars 570-595, quote: "within 75 days of receipt"
- `ENUM-LAW-001` **POLICY_VIOLATION** (Governing Law, severity HIGH): Delaware is not an
  approved jurisdiction.
  - cites section 8, chars 1214-1234, quote: "the laws of Delaware"
- mutations: section 4.1 "within 45 days of receipt" -> "within 75 days of receipt"; section 8
  "India" -> "Delaware"

- [ ] DOC-0082 verdict is correct

### DOC-0102 — contradictory

- document: `dataset/generated/v1/DOC-0102.txt`
- note: Both jurisdictions are individually approved, so this is a pure contradiction with no
  underlying value breach.
- `ENUM-LAW-001` **CONTRADICTION** (Governing Law, severity HIGH): Section 8 names Singapore as
  the governing law while section 9 names India.
  - cites section 9, chars 1493-1540, quote: "this Agreement is governed by the laws of India"
  - citing either section 8 or 9 is accepted
- mutation `M-CONTRADICT-LAW` on section 9: appended "For the avoidance of doubt, this
  Agreement is governed by the laws of India."

- [ ] DOC-0102 verdict is correct

### DOC-0103 — contradictory

- document: `dataset/generated/v1/DOC-0103.txt`
- note: The 60-day branch also breaches the 45-day cap, so an agent may reasonably report
  POLICY_VIOLATION instead of CONTRADICTION. Spec section 8.4 step 5 counts that as a match
  with a type error, and both strict and lenient numbers are published.
- `VALUE-PAY-001` **CONTRADICTION** (Payment Terms, severity MEDIUM): Section 4.1 requires
  payment within 30 days while section 12.3 requires 60 days. The two cannot both hold.
  - cites section 12.3, chars 1557-1591, quote: "within 60 days of the invoice date"
  - citing either section 4.1 or 12.3 is accepted
- mutation `M-CONTRADICT-PAY` on section 12.3: added "Notwithstanding clause 4.1, Customer
  shall settle all invoices within 60 days of the invoice date."

- [ ] DOC-0103 verdict is correct

### DOC-0130 — ambiguous

- document: `dataset/generated/v1/DOC-0130.txt`
- scoring mode: `accept_set`
- expected status: any of `NEEDS_REVIEW, NON_COMPLIANT`; unacceptable: `COMPLIANT`
- ambiguity: The governing law is defined by reference to a place the document never states,
  so the jurisdiction cannot be checked against the approved list.
- accepted answer 1: `ENUM-LAW-001` **AMBIGUOUS** — the governing law is unresolvable from the
  document.
- accepted answer 2: `ENUM-LAW-001` **POLICY_VIOLATION** — the governing law is not stated as
  an approved jurisdiction.
- both cite section 8, chars 1213-1265, quote: "the laws of the Vendor's principal place of
  business"
- excluded from the primary (strict) aggregates by design.

- [ ] DOC-0130 verdict is correct

### DOC-0136 — ambiguous

- document: `dataset/generated/v1/DOC-0136.txt`
- scoring mode: `accept_set`
- expected status: any of `NEEDS_REVIEW, NON_COMPLIANT`; unacceptable: `COMPLIANT`
- ambiguity: same pattern as DOC-0130 — governing law defined by an undefined reference.
- both accepted answers cite section 8, chars 1220-1272, quote: "the laws of the Vendor's
  principal place of business"
- excluded from the primary (strict) aggregates by design.

- [ ] DOC-0136 verdict is correct

### DOC-0154 — distractor

- document: `dataset/generated/v1/DOC-0154.txt`
- note: Compliant document plus 3 irrelevant sections, including a 30-day expense deadline
  that must not be mistaken for payment terms.
- expected findings: none.
- mutations add sections 20-22 (travel expense, site access, equipment return) — no rule
  affected, irrelevant content only.

- [ ] DOC-0154 verdict is correct

### DOC-0168 — distractor

- document: `dataset/generated/v1/DOC-0168.txt`
- note: Compliant document plus 3 irrelevant sections, including a 30-day expense deadline
  that must not be mistaken for payment terms.
- expected findings: none.
- mutations add sections 20-22 (travel expense, site access, equipment return) — no rule
  affected, irrelevant content only.

- [ ] DOC-0168 verdict is correct

## Sign-off

This dataset is signed off. The sha256 below ties the sign-off to the exact
`ground_truth.jsonl` bytes that were reviewed; regenerating the dataset invalidates it and
`experiments/run_baseline.py` / `experiments/run_references.py` will refuse to treat a run as
reportable otherwise.

| field | value |
|---|---|
| reviewer | Vishal Kalaskar (vishal.kalaskar@searce.com) |
| date | 2026-10-02 |
| cases reviewed | 15 / 175 (stratified spot-check, all 7 categories, spec section 9.3) |
| result | accepted |
| reviewed ground_truth.jsonl sha256 | `7f9f3ed9b015b3729cbfd9d7a30338419e5475aaf6f4f9df8a9760d95f7300c3` |
| notes | Scaled from Milestone 1 (`v1-m1`, 14 cases) to full dataset `v1` (175 cases, 25 per category), per decision to run the full matrix at 1 trial/case. |
