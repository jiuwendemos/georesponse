# GeoResponse example demo video

End-to-end usage of GeoResponse with the **Ahr supply corridor example case**.

- Runtime: **4:09**
- Resolution: **1600×900**, 25 fps, H.264/AAC
- Language: English (Edge TTS, `en-US-AndrewNeural`)
- Captions: scene-level English SRT

## Files

| File | What it is |
|---|---|
| `out/georesponse-example-demo.mp4` | Final video with voiceover |
| `out/georesponse-example-demo-silent.mp4` | Same visuals, no audio — record your own voice |
| `out/georesponse-example-demo-burned.mp4` | Final video with captions burned in |
| `out/georesponse-example-demo-softsubs.mp4` | Final video with a toggleable subtitle track |
| `georesponse-example-demo.srt` | Scene-level captions |
| `out/thumbnail.png` | Suggested thumbnail (Watch alert with evidence) |
| `build_video.py` | Reproducible build: Edge TTS + Playwright + ffmpeg |
| `timing.json` | Scene starts and durations used by the edit |

## What the video shows

| Time | Scene |
|---|---|
| 0:00 | What GeoResponse does and the example case |
| 0:18 | Demo pack vs My workspace |
| 0:31 | An empty workspace |
| 0:44 | Load the six-site example |
| 0:57 | Map, rows, value at risk, people |
| 1:10 | Edit a site; it is your data |
| 1:24 | Export CSV/GeoJSON |
| 1:35 | Watch, the proactive inbox, live store |
| 1:51 | Evidence before/after, SLA, why it fired |
| 2:07 | Ask the live agent; inspect tool steps and proposal |
| 3:11 | The proposal and human approval |
| 3:25 | Switch back to the demo pack; workspace stays |
| 3:37 | Close |

## What is real in this video

- The **workspace import**: the actual `examples/workspace-example/sites.geojson`.
- The **proactive path**: a scope, a 12-value historical baseline, and three
  observations sent to the API; the third produced the alert.
- The **Sentinel-2 before/after** images in Watch: real Copernicus data committed
  under `web/public/data/real/ahr-2021-flood/`.
- The **agent**: a live OpenAI-compatible model (`deepseek-v4-pro`) with grounded
  tools and a real proposal; approval is recorded by the API.
- The **audit and proposal lifecycle**: server-side, not a UI mock.

Sample values: site names are realistic, but value, population, severity and
confidence are illustrative. Replace them with customer data before an
operational decision.

## Rebuild it

1. Start the API with a clean production store and seed the example:

```powershell
cd C:\Workspace\openjiuwendemos\georesponse
$env:GEORESPONSE_MODE = "production"
$env:GEORESPONSE_AGENT_BACKEND = "openai"
& "C:\Workspace\openjiuwen\jiuwenswarm\.venv\Scripts\python.exe" -m uvicorn georesponse.api:app --port 8010
```

2. In another terminal:

```powershell
py examples/workspace-example/run_api_example.py --base http://127.0.0.1:8010
```

3. Build the video:

```powershell
cd demo-video
& "C:\Workspace\openjiuwen\jiuwenswarm\.venv\Scripts\python.exe" build_video.py --force-audio
```

If only the visuals changed:

```powershell
& "C:\Workspace\openjiuwen\jiuwenswarm\.venv\Scripts\python.exe" build_video.py
```

The build records each scene with Playwright, re-times every segment to its
narration duration, muxes the voice track, and writes the SRT, silent, soft-sub
and burned-sub versions.

## Requirements

- Python with Playwright (`jiuwenswarm` venv already has it)
- Google Chrome
- `uvx edge-tts` for narration
- ffmpeg from `coachme/.venv/Lib/site-packages/imageio_ffmpeg/binaries/`
- The API on `http://127.0.0.1:8010` with the example alert
