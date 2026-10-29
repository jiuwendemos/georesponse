# Government / emergency management framework

**Scope:** event triage for civil protection. Not automated decisions about people.

## Procurement

- Framework agreement with a pilot work order.
- Data-processing annex and security questionnaire.
- Sovereign deployment: on-premise, sovereign cloud, or air-gapped after imagery delivery.
- Acceptance tests from the stage runbook, plus a public-sector accessibility review.

## Deployment

- On-premise Linux / Docker.
- No outbound network after imagery delivery.
- Optional NPU appliance for on-site inference.
- Audit export in JSON/CSV; retention schedule per event.

## Obligations

1. Human review before any field dispatch.
2. Publish provenance for every map.
3. Retention and deletion schedule per event.
4. Accessibility and language requirements.
5. No facial recognition, no live surveillance.
6. Coordinate with the customer's public-information function; the map is decision support, not a public warning.

## First use case

Flood event triage: rank sites by access, power, population and value; give the response lead a one-page
field order; keep the analyst in the loop. Do not start with predictive damage or automated alerts to the
public.

## Metrics

- Time to first field order.
- Sites covered vs missed.
- False alarms by reason.
- Analyst hours saved.
- Equity of coverage across neighbourhoods.
