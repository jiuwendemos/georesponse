# Pilot in 90 days

**Buyer:** Head of Claims (insurer) · Asset Management Director (utility) · Emergency Management (government, later).

**Scope:** one insurer, one storm or flood event, one region. The AI assessment runs in parallel with the
analyst’s manual process. Compare results.

## Deliverables

1. Imagery pipeline for the customer’s event (Sentinel-2 before-image, commercial/drone after-image).
2. Ranked site list with confidence, value at risk, access and population.
3. Claims first-notice assessment, human-signed.
4. Accuracy, false-positive and time-saved report.
5. On-site or private-cloud deployment option.

## Success measures

| Measure | Target | How measured |
|---|---|---|
| Time to assessment | days → hours | event timestamp to signed assessment |
| Detection precision | ≥ 0.85 | adjuster-confirmed damage |
| Recall | ≥ 0.80 | confirmed / claims |
| Analyst hours saved | ≥ 40% | baseline vs pilot |
| False positives | logged by reason | review log |
| Automated approvals | **zero** | audit trail |
| Cost per assessed area | agreed | pilot invoice |

## 90-day plan

- **Days 1–10** — data access, security review, imagery delivery, baseline time measurement.
- **Days 11–30** — pipeline run on one historical event; parallel manual review; calibrate the ranking.
- **Days 31–60** — live event or second historical event; analyst workflow; adjuster confirmation.
- **Days 61–80** — accuracy report, false-positive log, time saved, integration dry-run.
- **Days 81–90** — readout, go/no-go, commercial proposal.

## Commercial

Fixed pilot fee, credited against the annual subscription if the customer proceeds. Per-area / per-asset /
per-claim pricing is available for production. Optional on-site NPU server.

## Proactive follow-on

Once the reactive pilot clears its gates, the monitoring subscription is the expansion motion:
one corridor, one asset class, shadow mode first. See [MONITORING_PILOT.md](MONITORING_PILOT.md).

## Gate

Do not start the pilot until the stage piece has passed the acceptance tests in
[STAGE_RUNBOOK.md](STAGE_RUNBOOK.md) and [SCORECARD.md](SCORECARD.md).

## Post-stage follow-up (48 hours)

- Send the recording, the one-pager and the live demo link.
- Log: name, role, organisation, event type, imagery provider, current process, next step.
- Capture 20 named claims and asset leaders across the event.
- Book five pilot intros.

## CRM fields

`name · role · organisation · segment (insurer/utility/government/agri/mining) · event type ·
imagery provider · current time-to-assessment · pilot fit (A/B/C) · next step · owner · date`.

## Honesty

The bundled pilot numbers are synthetic and labelled. Never quote them as production accuracy. Replace
them with adjuster-confirmed outcomes before a commercial claim.
