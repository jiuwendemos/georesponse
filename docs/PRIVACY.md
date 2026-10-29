# Privacy review — residential imagery

This is an engineering checklist, not legal advice. Legal review is a pilot gate.

| # | Requirement | Status in demo |
|---|---|---|
| 1 | Lawful basis for processing aerial imagery of residential property | documented in pilot DPA |
| 2 | Minimisation: crop to the insured property footprint | design rule |
| 3 | Redaction: faces, vehicles, private gardens in exports | helper + policy |
| 4 | Retention clock per event; delete raw imagery after decision | deployment policy |
| 5 | Role-based access: analyst, reviewer, auditor, customer | tenant design |
| 6 | DPA and subprocessor list, including NPU vendor | pilot gate |
| 7 | On-site / private-cloud inference; no outbound network | implemented |
| 8 | Customer-facing notice of AI assistance and human decision | report disclosure |
| 9 | Human review; no automated decision about people/property | enforced |
| 10 | Breach playbook and 72-hour notification | deployment policy |

The in-app **Method → Privacy review** panel shows the current state (4/10 done by default; the rest are
pilot gates). `security.privacy_review()` returns the same list as JSON.

## Rules

- No facial recognition. No live video. No persistent surveillance.
- Do not infer occupancy, ethnicity, health or any special-category attribute.
- A wrong map can cost money or lives: the analyst signs every assessment.
- If a finding is uncertain, say so; confidence is not truth.
