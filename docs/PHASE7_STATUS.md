# Phase 7 status — ready vs blocked

Last updated: 2026-10-30. Source of truth: [ROADMAP.md](ROADMAP.md) Phase 7
(306 checkboxes). A box is checked only with a reproducible command, a test, or a
live artefact.

Current: **27 done / 279 open.**

## Done (verified)

- Pause/resume with an audited reason
- Alert-quality feedback (`useful / not useful / wrong`)
- “What changed since I last looked”
- Mobile location indicator
- Section transitions without reloads
- Swipe before/after compare
- Mini-map, scale bar and compass
- Layer opacity, ordering and saved layer sets
- Confidence in words and intervals
- Accessible chart tables
- Context awareness of the current view/alert/scope
- Agent evaluation set with golden questions and tool traces
- Guardrail tests for injection and unsafe actions
- Tool-argument schema validation, retry/backoff and circuit breaker
- Multi-tenant isolation test
- Audit export with tamper verification
- Per-principal rate limiting
- Imagery retention/pruning
- Skeletons that match the layout
- 11 px minimum type, enforced in Playwright
- openjiuwen sessions, planning, four subagents, policy rail, SSE streaming and backend auto-selection (live proof)

## Ready to build next (no external input)

These can be implemented and verified in this repository:

- Virtualised alert/scope lists and a 10k-row load test
- Scope edit, measure, snap and undo
- Agent streaming responses and stop/retry
- API-enforced proposal approval and undo
- OIDC verification harness with a local key set
- Key rotation and previous-key fallback
- More openjiuwen parity tests and a pinned version check
- Notification templates in German for chat channels
- Offline alert queue with retry and conflict handling
- Chart system frame with shared axes and tooltips
- PWA notification click deep link
- Synthetic checks and budget trend history in CI
- Migration notes and screenshots

## Blocked on operator input

Each item below needs something that is not in this workspace. Providing it is
the unblock action.

| Area | What is missing | Unblock |
|---|---|---|
| Commercial imagery | Planet, Maxar, Airbus, ICEYE, Capella credentials and licences | Issue sandbox keys and confirm licence terms |
| Customer imagery | Drone/SFTP orthophotos, LAS/GeoTIFF, delivery contract | Provide an SFTP endpoint and sample delivery |
| Notifications | SMTP host, Slack/Teams webhooks, Twilio, PagerDuty | Provide one sandbox credential per channel and a test recipient |
| Enterprise systems | Jira, ServiceNow, Guidewire, Duck Creek, Maximo, SAP, ArcGIS, SIEM | Provide sandbox tenants and API tokens |
| NPU | Ascend/OpenVINO/QNN hardware or remote runner | Provide access to the target box and vendor runtime |
| Production vision model | Customer-trained roof-damage model | Provide the model and its evaluation set |
| Platform drill | Running PostgreSQL, Redis and MinIO | Start Docker Desktop or provide connection strings |
| Customer data | Sites, assets, policies, claims, adjuster labels | Provide a data pack or warehouse extract |
| Identity | Customer IdP issuer, audience, client credentials | Register GeoResponse as a client |
| Legal | DPA, privacy review, pen test | Provide sign-off and test window |
| Research | Five users per role, screen-reader user, diary study | Recruit participants and schedule sessions |
| Launch | Pilot tenant and acceptance owner | Name the pilot owner and dates |

## What “done” would mean

Phase 7 reaches 306/306 only when the blocked rows above are supplied and the
live drills pass. Code for those paths exists or can be written, but marking
them done without the drill would be a false claim.

## Recommended order

1. Ready-to-build list above (keeps raising verified coverage).
2. Platform drill once Docker or connection strings are available.
3. One real notification recipient and one enterprise sandbox.
4. NPU acceptance on the target box.
5. Customer data pack and adjuster labels.
6. Research sessions and launch gate.
