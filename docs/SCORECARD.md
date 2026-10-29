# Rehearsal scorecard

Run after every rehearsal. Do not book the next conference if the five-stranger test fails.

## Five strangers

Ask five people who did not build the demo, immediately after the 90-second run:

1. “In one sentence, what decision did the map support?”
2. “Where would you send the first team, and why?”
3. “What did the analyst reject, and why?”
4. “What would you do differently if the flood kept moving?”
5. “Who signs the assessment?”

| Participant | Q1 correct | Q2 correct | Q3 correct | Q4 correct | Q5 correct |
|---|---|---|---|---|---|
| 1 |  |  |  |  |  |
| 2 |  |  |  |  |  |
| 3 |  |  |  |  |  |
| 4 |  |  |  |  |  |
| 5 |  |  |  |  |  |

**Pass:** at least four can explain the decision in one sentence.

## Timing

| Measure | Target | Actual |
|---|---|---|
| First touch | ≤ 15 s |  |
| Flood-edge reveal | ≤ 30 s |  |
| Full arc | ≤ 90 s |  |
| Reset | < 5 s |  |
| Two volunteers assign a team without help | yes |  |
| Network cable unplugged | runs |  |
| Seven of ten repeat the closing line | ≥ 7 |  |

## Closing-line recall

Ask ten viewers, 10 minutes later: *“What was the line?”*

> “We knew where to send the teams before the second coffee.”

Record how many repeat it verbatim or near-verbatim.

## Contrast / legibility at 10 metres

- HUD body text ≥ 9 px at 1600×1000, headings ≥ 16 px.
- Red/amber/cyan/green are distinguishable without relying on hue alone (pins carry rank numbers,
  legends carry labels).
- The trust beat is readable in silence; the card has a text reason, not just colour.
- The printed A1 map and tokens match the screen.

## Result

```
Date:
Presenter:
Venue / screen:
Five-stranger pass:        yes / no
Volunteer completion:      ___%
Recall:                    ___/10
Reset time:                ___ s
Notes / changes:
```


## Proactive monitoring gates

Use the Watch → Settings → Pilot gates panel and the API `GET /api/watch/pilot`:

| Gate | Pass condition |
|---|---|
| Shadow validations | At least 3 analyst-validated alerts per scope |
| Precision | ≥ 0.80 on closed alerts |
| Alert load | ≤ 8 per analyst per 8h |
| SLA | 0 breaches in the measurement window |
| Coverage | freshness within contract; blind spots disclosed |
| Safety | zero auto-approvals / auto-dispatch |
| Privacy | DPA, retention and scope review signed |

The bundled demo pack has three SLA breaches, so the launch gate is red by design. Do not launch a
real customer on a red gate.
