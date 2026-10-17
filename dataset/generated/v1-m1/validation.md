# Dataset validation — v1-m1

Spec section 9.3. Two gates: automated invariant checks on 100% of cases, and a human
spot-check. The dataset is not ready for agent runs until both are signed off.

## Provenance

- dataset_version: `v1-m1`
- generator_version: `g1`
- generator_seed: `7`
- policy: `POL-001` `v1`
- created_utc: `2026-10-01T17:43:46+00:00`
- cases: 14 — {"compliant": 2, "missing_clause": 2, "incorrect_value": 2, "multiple_violations": 2, "contradictory": 2, "ambiguous": 2, "distractor": 2}

Regenerate byte-identically with:

```
python -m dataset.generator.generate --version v1-m1 --per-category 2 --seed 7
```

## Automated gate (passed — the generator refuses to write otherwise)

Checked for every case:

- no duplicate section identifiers;
- every expected evidence quote appears exactly once in the document (S2), and its
  character offsets resolve to that quote (S3);
- every cited section exists, and the quote lies inside it;
- severity and clause equal the policy rule's values;
- `MISSING_CLAUSE` findings carry no evidence, all other types carry evidence (S7);
- status and findings agree (S4), and accept-set cases never accept `COMPLIANT`;
- every expected finding has a `required_information` entry;
- the mutation actually took effect, judged by the independent reference checker.

## Independent reference check

Each document re-checked by `evaluation/deterministic/rule_check.py`, which never sees the
ground truth. `-` means it found nothing.

| case | category | reference checker sees | expected rules |
|---|---|---|---|
| DOC-0001 | compliant | - | - |
| DOC-0002 | compliant | - | - |
| DOC-0003 | missing_clause | CLAUSE-LIAB-001 | CLAUSE-LIAB-001 |
| DOC-0004 | missing_clause | CLAUSE-TERM-001 | CLAUSE-TERM-001 |
| DOC-0005 | incorrect_value | VALUE-PAY-001 | VALUE-PAY-001 |
| DOC-0006 | incorrect_value | VALUE-PAY-001 | VALUE-PAY-001 |
| DOC-0007 | multiple_violations | ENUM-LAW-001, VALUE-PAY-001 | ENUM-LAW-001, VALUE-PAY-001 |
| DOC-0008 | multiple_violations | CLAUSE-LIAB-001, ENUM-LAW-001 | CLAUSE-LIAB-001, ENUM-LAW-001 |
| DOC-0009 | contradictory | - | VALUE-PAY-001 |
| DOC-0010 | contradictory | - | ENUM-LAW-001 |
| DOC-0011 | ambiguous | ENUM-LAW-001 | ENUM-LAW-001 |
| DOC-0012 | ambiguous | - | VALUE-PAY-001 |
| DOC-0013 | distractor | - | - |
| DOC-0014 | distractor | - | - |

Contradiction cases are expected to show `-`: the checker only looks inside the section
whose title matches the clause, so a contradiction spread across two sections is invisible
to it. That blind spot is the capability the agent is meant to add, and it is asserted in
`tests/test_rule_check.py` so it cannot disappear unnoticed.

## Human spot-check

For each case: read the quoted context, then confirm the verdict column is right. Mark the
checkbox or write what is wrong.

### DOC-0001 — compliant

- document: `dataset/generated/v1-m1/DOC-0001.txt`
- scoring mode: `strict`
- **expected status: `COMPLIANT`**
- sections present: 1, 2, 3, 4.1, 5, 6, 7, 8, 9
- note: All five rules satisfied. Payment terms 30 days, at or under the 45-day cap.

Expected findings: **none**. Confirm the document really does satisfy all five
rules, and that nothing in it should be read as a violation.


- [ ] DOC-0001 verdict is correct

### DOC-0002 — compliant

- document: `dataset/generated/v1-m1/DOC-0002.txt`
- scoring mode: `strict`
- **expected status: `COMPLIANT`**
- sections present: 1, 2, 3, 4.1, 5, 6, 7, 8, 9
- note: All five rules satisfied. Payment terms 45 days, at or under the 45-day cap.

Expected findings: **none**. Confirm the document really does satisfy all five
rules, and that nothing in it should be read as a violation.


- [ ] DOC-0002 verdict is correct

### DOC-0003 — missing_clause

- document: `dataset/generated/v1-m1/DOC-0003.txt`
- scoring mode: `strict`
- **expected status: `NON_COMPLIANT`**
- sections present: 1, 2, 3, 4.1, 5, 6, 8, 9
- note: Section 7 (Liability) removed entirely.

- `CLAUSE-LIAB-001` **MISSING_CLAUSE** (Liability, severity HIGH)
  - claim: The document contains no Liability clause.
  - evidence: none, correct for a missing clause

- mutation `M-REMOVE-CLAUSE` on section 7: CLAUSE-LIAB-001 violated: Liability clause absent

- [ ] DOC-0003 verdict is correct

### DOC-0004 — missing_clause

- document: `dataset/generated/v1-m1/DOC-0004.txt`
- scoring mode: `strict`
- **expected status: `NON_COMPLIANT`**
- sections present: 1, 2, 3, 4.1, 5, 7, 8, 9
- note: Section 6 (Termination) removed entirely.

- `CLAUSE-TERM-001` **MISSING_CLAUSE** (Termination, severity HIGH)
  - claim: The document contains no Termination clause.
  - evidence: none, correct for a missing clause

- mutation `M-REMOVE-CLAUSE` on section 6: CLAUSE-TERM-001 violated: Termination clause absent

- [ ] DOC-0004 verdict is correct

### DOC-0005 — incorrect_value

- document: `dataset/generated/v1-m1/DOC-0005.txt`
- scoring mode: `strict`
- **expected status: `NON_COMPLIANT`**
- sections present: 1, 2, 3, 4.1, 5, 6, 7, 8, 9
- note: Payment Terms clause is present, so only the value rule is breached.

- `VALUE-PAY-001` **POLICY_VIOLATION** (Payment Terms, severity MEDIUM)
  - claim: Payment terms of 60 days exceed the 45-day maximum.
  - cites section 4.1, chars 572-597
  - context: `...e 3.  ## 4.1 Payment Terms Customer shall pay all undisputed invoices [[within 60 days of receipt]]. Invoices are issued monthly in arrears.  ## 5. Confidentiality Each ...`

- mutation `M-VALUE-PAY` on section 4.1: VALUE-PAY-001 violated: 60 days exceeds the 45-day cap

- [ ] DOC-0005 verdict is correct

### DOC-0006 — incorrect_value

- document: `dataset/generated/v1-m1/DOC-0006.txt`
- scoring mode: `strict`
- **expected status: `NON_COMPLIANT`**
- sections present: 1, 2, 3, 4.1, 5, 6, 7, 8, 9
- note: Payment Terms clause is present, so only the value rule is breached.

- `VALUE-PAY-001` **POLICY_VIOLATION** (Payment Terms, severity MEDIUM)
  - claim: Payment terms of 90 days exceed the 45-day maximum.
  - cites section 4.1, chars 578-603
  - context: `...e 3.  ## 4.1 Payment Terms Customer shall pay all undisputed invoices [[within 90 days of receipt]]. Invoices are issued monthly in arrears.  ## 5. Confidentiality Each ...`

- mutation `M-VALUE-PAY` on section 4.1: VALUE-PAY-001 violated: 90 days exceeds the 45-day cap

- [ ] DOC-0006 verdict is correct

### DOC-0007 — multiple_violations

- document: `dataset/generated/v1-m1/DOC-0007.txt`
- scoring mode: `strict`
- **expected status: `NON_COMPLIANT`**
- sections present: 1, 2, 3, 4.1, 5, 6, 7, 8, 9
- note: Two independent rule breaches: payment value and jurisdiction.

- `VALUE-PAY-001` **POLICY_VIOLATION** (Payment Terms, severity MEDIUM)
  - claim: Payment terms of 75 days exceed the 45-day maximum.
  - cites section 4.1, chars 573-598
  - context: `...e 3.  ## 4.1 Payment Terms Customer shall pay all undisputed invoices [[within 75 days of receipt]]. Invoices are issued monthly in arrears.  ## 5. Confidentiality Each ...`
- `ENUM-LAW-001` **POLICY_VIOLATION** (Governing Law, severity HIGH)
  - claim: Delaware is not an approved jurisdiction.
  - cites section 8, chars 1217-1237
  - context: `...eceding the claim.  ## 8. Governing Law This Agreement is governed by [[the laws of Delaware]], and the parties submit to the exclusive jurisdiction of its courts. ...`

- mutation `M-VALUE-PAY` on section 4.1: VALUE-PAY-001 violated: 75 days exceeds the 45-day cap
- mutation `M-ENUM-LAW` on section 8: ENUM-LAW-001 violated: Delaware is not approved

- [ ] DOC-0007 verdict is correct

### DOC-0008 — multiple_violations

- document: `dataset/generated/v1-m1/DOC-0008.txt`
- scoring mode: `strict`
- **expected status: `NON_COMPLIANT`**
- sections present: 1, 2, 3, 4.1, 5, 6, 8, 9
- note: A missing clause and a value breach in one document, with different evidence shapes.

- `CLAUSE-LIAB-001` **MISSING_CLAUSE** (Liability, severity HIGH)
  - claim: The document contains no Liability clause.
  - evidence: none, correct for a missing clause
- `ENUM-LAW-001` **POLICY_VIOLATION** (Governing Law, severity HIGH)
  - claim: California is not an approved jurisdiction.
  - cites section 8, chars 1064-1086
  - context: `...red after 14 days.  ## 8. Governing Law This Agreement is governed by [[the laws of California]], and the parties submit to the exclusive jurisdiction of its courts. ...`

- mutation `M-REMOVE-CLAUSE` on section 7: CLAUSE-LIAB-001 violated: Liability clause absent
- mutation `M-ENUM-LAW` on section 8: ENUM-LAW-001 violated: California is not approved

- [ ] DOC-0008 verdict is correct

### DOC-0009 — contradictory

- document: `dataset/generated/v1-m1/DOC-0009.txt`
- scoring mode: `strict`
- **expected status: `NON_COMPLIANT`**
- sections present: 1, 2, 3, 4.1, 5, 6, 7, 8, 9, 12.3
- note: The 60-day branch also breaches the 45-day cap, so an agent may reasonably report POLICY_VIOLATION instead of CONTRADICTION. Spec section 8.4 step 5 counts that as a match with a type error, and both strict and lenient numbers are published.

- `VALUE-PAY-001` **CONTRADICTION** (Payment Terms, severity MEDIUM)
  - claim: Section 4.1 requires payment within 30 days while section 12.3 requires 60 days. The two cannot both hold.
  - cites section 12.3, chars 1544-1578
  - context: `...hedule Notwithstanding clause 4.1, Customer shall settle all invoices [[within 60 days of the invoice date]].  ...`
  - citing any of sections 4.1, 12.3 is accepted

- mutation `M-CONTRADICT-PAY` on section 12.3: VALUE-PAY-001 contradicted: section 4.1 states 30 days, section 12.3 states 60 days

- [ ] DOC-0009 verdict is correct

### DOC-0010 — contradictory

- document: `dataset/generated/v1-m1/DOC-0010.txt`
- scoring mode: `strict`
- **expected status: `NON_COMPLIANT`**
- sections present: 1, 2, 3, 4.1, 5, 6, 7, 8, 9
- note: Both jurisdictions are individually approved, so this is a pure contradiction with no underlying value breach.

- `ENUM-LAW-001` **CONTRADICTION** (Governing Law, severity HIGH)
  - claim: Section 8 names Singapore as the governing law while section 9 names India.
  - cites section 9, chars 1491-1538
  - context: `... on the next Business Day after delivery. For the avoidance of doubt, [[this Agreement is governed by the laws of India]].  ...`
  - citing any of sections 8, 9 is accepted

- mutation `M-CONTRADICT-LAW` on section 9: ENUM-LAW-001 contradicted: section 8 states Singapore, section 9 states India

- [ ] DOC-0010 verdict is correct

### DOC-0011 — ambiguous

- document: `dataset/generated/v1-m1/DOC-0011.txt`
- scoring mode: `accept_set`
- **expected status: any of `NEEDS_REVIEW, NON_COMPLIANT`**
- unacceptable: `COMPLIANT`
- ambiguity: The governing law is defined by reference to a place that the document never states, so the jurisdiction cannot be checked against the approved list.
- sections present: 1, 2, 3, 4.1, 5, 6, 7, 8, 9
- note: Excluded from the primary aggregates and reported as its own stratum.

Accepted answer 1 of 2:

- `ENUM-LAW-001` **AMBIGUOUS** (Governing Law, severity HIGH)
  - claim: The governing law is unresolvable from the document.
  - cites section 8, chars 1216-1268
  - context: `...eceding the claim.  ## 8. Governing Law This Agreement is governed by [[the laws of the Vendor's principal place of business]], and the parties submit to the exclusive jurisdiction of its courts. ...`

Accepted answer 2 of 2:

- `ENUM-LAW-001` **POLICY_VIOLATION** (Governing Law, severity HIGH)
  - claim: The governing law is not stated as an approved jurisdiction.
  - cites section 8, chars 1216-1268
  - context: `...eceding the claim.  ## 8. Governing Law This Agreement is governed by [[the laws of the Vendor's principal place of business]], and the parties submit to the exclusive jurisdiction of its courts. ...`

- mutation `M-AMBIGUOUS` on section 8: ENUM-LAW-001 cannot be decided from the document

- [ ] DOC-0011 verdict is correct

### DOC-0012 — ambiguous

- document: `dataset/generated/v1-m1/DOC-0012.txt`
- scoring mode: `accept_set`
- **expected status: any of `NEEDS_REVIEW, NON_COMPLIANT`**
- unacceptable: `COMPLIANT`
- ambiguity: The payment period is qualitative, so it cannot be compared against the 45-day cap either way.
- sections present: 1, 2, 3, 4.1, 5, 6, 7, 8, 9
- note: Excluded from the primary aggregates and reported as its own stratum.

Accepted answer 1 of 2:

- `VALUE-PAY-001` **AMBIGUOUS** (Payment Terms, severity MEDIUM)
  - claim: The payment period is not quantified, so the 45-day cap cannot be evaluated.
  - cites section 4.1, chars 620-646
  - context: `...y all undisputed invoices promptly following receipt and in any event [[within a reasonable period]]. Invoices are issued monthly in arrears.  ## 5. Confidentiality Each ...`

Accepted answer 2 of 2:

- `VALUE-PAY-001` **POLICY_VIOLATION** (Payment Terms, severity MEDIUM)
  - claim: The payment period is not demonstrably within the 45-day cap.
  - cites section 4.1, chars 620-646
  - context: `...y all undisputed invoices promptly following receipt and in any event [[within a reasonable period]]. Invoices are issued monthly in arrears.  ## 5. Confidentiality Each ...`

- mutation `M-AMBIGUOUS` on section 4.1: VALUE-PAY-001 cannot be decided from the document

- [ ] DOC-0012 verdict is correct

### DOC-0013 — distractor

- document: `dataset/generated/v1-m1/DOC-0013.txt`
- scoring mode: `strict`
- **expected status: `COMPLIANT`**
- sections present: 1, 2, 3, 4.1, 5, 6, 7, 8, 9, 20, 21
- note: Compliant document plus 2 irrelevant sections, including a 30-day expense deadline that must not be mistaken for payment terms.

Expected findings: **none**. Confirm the document really does satisfy all five
rules, and that nothing in it should be read as a violation.


- mutation `M-DISTRACTOR` on section 20: No rule affected. Irrelevant content only.
- mutation `M-DISTRACTOR` on section 21: No rule affected. Irrelevant content only.

- [ ] DOC-0013 verdict is correct

### DOC-0014 — distractor

- document: `dataset/generated/v1-m1/DOC-0014.txt`
- scoring mode: `strict`
- **expected status: `COMPLIANT`**
- sections present: 1, 2, 3, 4.1, 5, 6, 7, 8, 9, 20, 21, 22
- note: Compliant document plus 3 irrelevant sections, including a 30-day expense deadline that must not be mistaken for payment terms.

Expected findings: **none**. Confirm the document really does satisfy all five
rules, and that nothing in it should be read as a violation.


- mutation `M-DISTRACTOR` on section 20: No rule affected. Irrelevant content only.
- mutation `M-DISTRACTOR` on section 21: No rule affected. Irrelevant content only.
- mutation `M-DISTRACTOR` on section 22: No rule affected. Irrelevant content only.

- [ ] DOC-0014 verdict is correct

## Sign-off

This dataset is signed off. The sha256 below ties the sign-off to the exact `ground_truth.jsonl` bytes that were reviewed; regenerating the dataset invalidates it and `experiments/run_references.py` will refuse to treat the run as reportable.

This dataset is signed off. The sha256 below ties the sign-off to the exact `ground_truth.jsonl` bytes that were reviewed; regenerating the dataset invalidates it and `experiments/run_references.py` will refuse to treat the run as reportable.

| field | value |
|---|---|
| reviewer | Vishal Kalaskar (mail.vishaldk@gmail.com) |
| date | 2026-10-01 |
| cases reviewed | 14 / 14 |
| result | accepted |
| reviewed ground_truth.jsonl sha256 | `553187459d95940f94b169fe917b491efa7258de9e2f06da821d41df5b4e89a4` |
| notes | Dataset v1-m1 accepted for Milestone 1 machinery verification. Scaling to the full 175-case dataset v1 requires a fresh sign-off against its own manifest. |
