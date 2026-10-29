# Stage runbook — “Where do we send the teams?”

## Before the room

- Open the live demo or the local build. Click **Booth → Offline pack**.
- Unplug the network. Reload once. The app must still work.
- Reset the clock to **12:00**. Three teams unassigned. No review decisions.
- Print the A1 map and the three team tokens: **Booth → Print map & tokens**.
- Put the tokens next to the printed map. The screen mirrors the print.
- Sound: one low flood/rain bed, one ping when a site flips to high risk. Silence under the trust beat.
- Fallback laptop with the same offline pack and the 90-second script open.

## The 90 seconds

| Time | Beat | Action | What the room sees |
|---|---|---|---|
| 0:00–0:10 | Cold open | Say: “14:32. Forty square kilometres under water. Eighteen places that matter. Three teams.” | Map at 12:00, 18 pins, watch colours |
| 0:10–0:25 | First touch | Click **Scrub the flood edge to 18:00** or drag the slider | Flood edge advances east; pins flip to high risk |
| 0:25–0:40 | Agent ranks | Click **Inspect the #1 ranked site** | Site card: access, power, people, confidence, rank contributions |
| 0:40–0:55 | Trust beat | Click **Reject this finding** | Trust panel: dark roof + water reflection; rank re-orders; a team is freed |
| 0:55–1:10 | Audience choice | Click **Let the room choose Team 3**; ask for a show of hands | A/B cards, coverage preview, response time, trade-off |
| 1:10–1:20 | Reveal | Click **Assign the three teams**, then **Reveal** | Zoom-out; 40 km², 18 sites, 42 minutes; one-page field order |
| 1:20–1:30 | The line | Say: “We knew where to send the teams before the second coffee.” | QR / reset |

The stage HUD also exposes the six beats as buttons, so a rehearsal can jump to any beat.

## Trust beat, exactly

1. The agent’s top site is S01, Ahrweiler Altstadt, 94% confident.
2. The card says: *“Agent’s top finding — check before dispatch.”*
3. Read the reason: **the roof edge is intact; the dark shape is water reflection.**
4. Click **Reject this finding**. The card says it is removed; the ranking re-orders; S02 rises.
5. Say: *“The model was confident. The analyst was right. This is why a human signs the assessment.”*

## Audience choice, exactly

- **A — Heppingen Substation.** €8.4m value, open road, power. Choose it and the dense housing block stays uncovered.
- **B — Bachem Valley Road.** 1,250 people, blocked access, housing. Choose it and the substation stays on the watch list.
- Both are defensible. Commit to the room’s choice and name the trade-off. Do not re-vote.

## Props

- A1 printed map from **Print map & tokens**.
- Three magnetic tokens labelled Team 1/2/3.
- One printed field order (the app prints it).
- A phone/QR to the live demo, not a signup form.

## Reset

Press `R`, or click **Reset**. Under five seconds. The data pack is deterministic; a reload returns to the
same cold open. The audit trail keeps prior sessions; reset clears the current scenario’s work.

## Fallback

If the laptop fails, use the second laptop with the offline pack. If both fail, read the 90-second script
and show the printed A1 map. Do not improvise a live imagery download on stage.

## Acceptance tests

Use [SCORECARD.md](SCORECARD.md) after every rehearsal. Do not book the next conference if the
five-stranger test fails.
