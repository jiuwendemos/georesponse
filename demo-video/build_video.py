"""Build the GeoResponse end-to-end example video.

Recipe follows CoachMe's demo:
  - Edge TTS scene narration (en-US-AndrewNeural)
  - Playwright screen capture with a visible cursor and click ripples
  - ffmpeg assembly, scene-level SRT, silent master

The API must be running with the example scope/alert:
  http://127.0.0.1:8010

Run:
  C:\\Workspace\\openjiuwen\\jiuwenswarm\\.venv\\Scripts\\python.exe build_video.py
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
import wave
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parent
AUDIO = ROOT / "audio"
RAW = ROOT / "raw"
OUT = ROOT / "out"
FFMPEG = Path(r"C:\Workspace\openjiuwendemos\coachme\.venv\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe")
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
BASE = "http://127.0.0.1:8010"
VOICE = "en-US-AndrewNeural"
RATE = "+4%"
LEAD = 1.0
GAP = 1.4
FPS = 25

SCENES = [
    {
        "name": "01_intro",
        "label": "GeoResponse — a decision you can defend",
        "text": (
            "GeoResponse turns satellite imagery into a decision a manager can defend. "
            "Not a map demo: a decision, the evidence behind it, and a human correction. "
            "In this video we use a real example case in the Ahr valley, with real Sentinel-2 images."
        ),
    },
    {
        "name": "02_sources",
        "label": "Demo pack vs my workspace",
        "text": (
            "There are two data sources. The demo pack is the bundled synthetic scenario for a stage or booth. "
            "My workspace is your own sites. You switch in Settings, and the demo pack stays one click away."
        ),
    },
    {
        "name": "03_empty",
        "label": "An empty workspace",
        "text": (
            "The workspace starts empty. Import a CSV or GeoJSON, add one site manually, or load the bundled example. "
            "This is the difference between a demo and a product you can put your own data into."
        ),
    },
    {
        "name": "04_load",
        "label": "Load the example case",
        "text": (
            "We load the example case: six sites in the Ahr supply corridor. "
            "Each row carries coordinates, severity, confidence, value, population, access and notes."
        ),
    },
    {
        "name": "05_map",
        "label": "Map, rows and summary",
        "text": (
            "Every site becomes a pin and a row. Red is high risk, orange is watch. "
            "The summary gives the decision-maker the shape of the problem: six sites, how many red, value at risk, and people."
        ),
    },
    {
        "name": "06_edit",
        "label": "It is your data",
        "text": (
            "This is not a fixed demo. Select a site and edit its name, coordinates, severity, confidence, value, population or access. "
            "Changes are saved in this browser until you connect a backend."
        ),
    },
    {
        "name": "07_export",
        "label": "Export CSV or GeoJSON",
        "trim": True,
        "text": (
            "Export the list as CSV or GeoJSON. The point is not to trap your data in this app; "
            "it is to move the decision into the tools your team already uses."
        ),
    },
    {
        "name": "08_watch",
        "label": "The proactive inbox",
        "pad": 20,
        "text": (
            "The site list is one half. The other half is Watch, the proactive inbox. "
            "For this example we used the API: twelve quiet baseline values, then observations over time. "
            "The last observation crossed the threshold and produced this alert."
        ),
    },
    {
        "name": "09_evidence",
        "label": "Evidence, SLA and why",
        "text": (
            "Watch shows the alert, not just a pin: severity, confidence, the SLA clock, the owner, "
            "the real Sentinel before and after, the value at risk, access, and why it fired against the baseline. "
            "The human sees the evidence before acting."
        ),
    },
    {
        "name": "10_agent",
        "label": "Ask the agent",
        "pad": 20,
        "text": (
            "Now ask the agent. It answers from grounded tools: the portfolio briefing, this alert, and coverage. "
            "It does not guess from a prompt: it calls get_briefing, get_alert and get_coverage, and you can see each step. "
            "The answer is slower than a chat box because the work is real: it reads the alert, the baseline, the SLA and the evidence, "
            "then proposes one safe next action. Notice the answer names the alert, the baseline, the SLA and the evidence; it does not invent a number. Every write is a proposal. Nothing is approved automatically. "
            "The system never approves a claim, dispatches a crew or signs an assessment. "
            "That is the difference between an assistant and an autonomous system."
        ),
    },
    {
        "name": "11_approve",
        "label": "A human approves",
        "text": (
            "The agent proposes assigning a team. A human approves it here. "
            "The alert changes, the action is audited, and the proposal can be undone. "
            "The system never signs, dispatches or approves a claim on its own."
        ),
    },
    {
        "name": "12_demo",
        "label": "The demo pack is still there",
        "text": (
            "Switch back to the demo pack whenever you need the synthetic scenarios for a stage. "
            "Your workspace is untouched. Both paths exist on purpose: one to show, one to use."
        ),
    },
    {
        "name": "13_close",
        "label": "Your sites, your decision",
        "text": (
            "Real imagery. A ranked decision. A human correction. A proactive watch. "
            "That is GeoResponse: your sites, your evidence, your decision."
        ),
    },
]

CURSOR_JS = r"""
() => {
  if (window.__grCursorInstalled) return;
  window.__grCursorInstalled = true;
  const style = document.createElement('style');
  style.textContent = `
    #gr-cursor { position: fixed; left: 0; top: 0; width: 26px; height: 30px; z-index: 2147483647; pointer-events: none; transform: translate(800px, 450px); filter: drop-shadow(0 2px 4px rgba(0,0,0,.55)); transition: transform .06s linear; }
    #gr-cursor svg { display:block; width:100%; height:100%; }
    #gr-cursor.down { transform: translate(var(--x), var(--y)) scale(.82); }
    .gr-ripple { position: fixed; width: 14px; height: 14px; margin: -7px 0 0 -7px; border: 3px solid #22d3ee; border-radius: 50%; z-index: 2147483646; pointer-events: none; animation: grRipple .55s ease-out forwards; }
    @keyframes grRipple { from { transform: scale(.4); opacity: 1; } to { transform: scale(3.6); opacity: 0; } }
  `;
  document.head.appendChild(style);
  const c = document.createElement('div');
  c.id = 'gr-cursor';
  c.innerHTML = '<svg viewBox="0 0 26 30" xmlns="http://www.w3.org/2000/svg"><path d="M2 2 L2 24 L8.5 18 L13 28 L17 26 L12.5 16.5 L21 16.5 Z" fill="#ffffff" stroke="#111111" stroke-width="2.2" stroke-linejoin="round"/></svg>';
  document.body.appendChild(c);
  let x = 800, y = 450;
  const move = (e) => {
    x = e.clientX; y = e.clientY;
    c.style.setProperty('--x', x + 'px');
    c.style.setProperty('--y', y + 'px');
    c.style.transform = `translate(${x}px, ${y}px)`;
  };
  const down = (e) => {
    if (e.button !== 0) return;
    c.classList.add('down');
    const r = document.createElement('div');
    r.className = 'gr-ripple';
    r.style.left = e.clientX + 'px';
    r.style.top = e.clientY + 'px';
    document.body.appendChild(r);
    setTimeout(() => r.remove(), 700);
  };
  const up = () => c.classList.remove('down');
  window.addEventListener('mousemove', move, true);
  window.addEventListener('mousedown', down, true);
  window.addEventListener('mouseup', up, true);
}
"""


def ffmpeg(*args: str) -> None:
    cmd = [str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{' '.join(cmd)}\n{proc.stderr[-2000:]}")


def duration(path: Path) -> float:
    proc = subprocess.run([str(FFMPEG), "-i", str(path)], capture_output=True, text=True)
    match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", proc.stderr)
    if not match:
        raise RuntimeError(f"could not read duration: {path}")
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def make_audio(force: bool = False) -> list[dict]:
    AUDIO.mkdir(parents=True, exist_ok=True)
    info = []
    for scene in SCENES:
        txt = AUDIO / f"{scene['name']}.txt"
        mp3 = AUDIO / f"{scene['name']}.mp3"
        srt = AUDIO / f"{scene['name']}.srt"
        txt.write_text(scene["text"], encoding="utf-8")
        if force or not mp3.exists() or mp3.stat().st_size == 0:
            cmd = [
                "uvx", "edge-tts", "--voice", VOICE, "--rate", RATE,
                "--file", str(txt), "--write-media", str(mp3),
                "--write-subtitles", str(srt), "--no-progress",
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                raise RuntimeError(f"edge-tts failed for {scene['name']}: {proc.stderr[-1000:]}")
        seconds = duration(mp3)
        info.append({**scene, "audio": round(seconds, 3), "duration": round(seconds + GAP + float(scene.get("pad", 0)), 3)})
        print(f"{scene['name']}: {seconds:.1f}s")
    return info


def build_voice(info: list[dict]) -> Path:
    rate = 24000
    silence = lambda seconds: b"\x00\x00" * int(seconds * rate)
    chunks = [silence(LEAD)]
    for scene in info:
        wav = AUDIO / f"{scene['name']}.wav"
        ffmpeg("-i", str(AUDIO / f"{scene['name']}.mp3"), "-ar", str(rate), "-ac", "1", "-c:a", "pcm_s16le", str(wav))
        with wave.open(str(wav), "rb") as handle:
            chunks.append(handle.readframes(handle.getnframes()))
        chunks.append(silence(GAP + float(scene.get("pad", 0))))
    voice = ROOT / "voice.wav"
    with wave.open(str(voice), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"".join(chunks))
    t = LEAD
    for scene in info:
        scene["start"] = round(t, 3)
        scene["end"] = round(t + scene["duration"], 3)
        t += scene["duration"]
    (ROOT / "timing.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    return voice


def make_srt(info: list[dict]) -> Path:
    def ts(value: float) -> str:
        hours = int(value // 3600)
        minutes = int((value % 3600) // 60)
        seconds = value % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}".replace(".", ",")

    lines = []
    for index, scene in enumerate(info, 1):
        lines.append(str(index))
        lines.append(f"{ts(scene['start'])} --> {ts(scene['start'] + scene['audio'] + 0.5)}")
        lines.append(scene["text"])
        lines.append("")
    path = ROOT / "georesponse-example-demo.srt"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def move(page: Page, x: float, y: float, steps: int = 30, pause: int = 180) -> None:
    page.mouse.move(float(x), float(y), steps=steps)
    page.wait_for_timeout(pause)


def center(page: Page, locator, dx: float = 0, dy: float = 0, steps: int = 30, pause: int = 200):
    locator.scroll_into_view_if_needed()
    page.wait_for_timeout(120)
    box = locator.bounding_box()
    if not box:
        raise RuntimeError("element has no bounding box")
    x = box["x"] + box["width"] / 2 + dx
    y = box["y"] + box["height"] / 2 + dy
    move(page, x, y, steps=steps, pause=pause)
    return x, y


def click(page: Page, locator, dx: float = 0, dy: float = 0) -> None:
    x, y = center(page, locator, dx, dy)
    page.mouse.click(x, y)
    page.wait_for_timeout(350)


def remaining(started: float, seconds: float) -> None:
    left = seconds - (time.monotonic() - started)
    if left > 0:
        time.sleep(left)


def record(info: list[dict]) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    for old in RAW.glob("*.webm"):
        old.unlink()
    start_all = time.monotonic()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=str(CHROME),
            headless=True,
            args=["--autoplay-policy=no-user-gesture-required", "--force-device-scale-factor=1"],
        )
        context = browser.new_context(
            viewport={"width": 1600, "height": 900},
            record_video_dir=str(RAW),
            record_video_size={"width": 1600, "height": 900},
            accept_downloads=True,
            service_workers="block",
        )
        context.add_init_script(
            "(() => { try { localStorage.setItem('georesponse.prefs.v2', JSON.stringify({theme:'dark',density:'comfortable',motion:true,language:'en',role:'all',dataMode:'demo'})); localStorage.setItem('georesponse.onboarded.v1','1'); } catch {} })()"
        )
        context.add_init_script(f"({CURSOR_JS})()")
        page = context.new_page()
        page.goto(f"{BASE}/?nosw=1#view=workspace", wait_until="load")
        page.wait_for_selector(".workspace", timeout=30000)
        page.wait_for_timeout(2500)
        actuals = []

        for scene in info:
            started = time.monotonic()
            name = scene["name"]
            if name == "01_intro":
                move(page, 760, 330)
                page.wait_for_timeout(500)
                move(page, 980, 560)
            elif name == "02_sources":
                move(page, 760, 330)
                page.wait_for_timeout(700)
                move(page, 940, 520)
                page.wait_for_timeout(700)
            elif name == "03_empty":
                move(page, 800, 430)
                move(page, 760, 520)
            elif name == "04_load":
                click(page, page.get_by_role("button", name="Load example case").first)
                page.wait_for_timeout(1200)
                move(page, 700, 420)
            elif name == "05_map":
                move(page, 500, 330)
                move(page, 360, 250)
                page.wait_for_timeout(800)
                click(page, page.locator(".ws-row").first)
                move(page, 1240, 260)
            elif name == "06_edit":
                click(page, page.locator(".ws-row").first)
                field = page.get_by_label("Notes")
                field.click()
                field.fill("Care campus. Access road under water. Confirm before dispatch.")
                page.wait_for_timeout(600)
                move(page, 1250, 640)
            elif name == "07_export":
                move(page, 1130, 500)
                move(page, 1250, 500)
                move(page, 760, 500)
            elif name == "08_watch":
                click(page, page.get_by_role("button", name="Watch"))
                page.wait_for_timeout(1200)
                click(page, page.locator(".watch-alert-row").first)
                page.wait_for_timeout(800)
            elif name == "09_evidence":
                move(page, 720, 420)
                page.wait_for_timeout(800)
                move(page, 760, 640)
                page.wait_for_timeout(600)
                move(page, 760, 780)
            elif name == "10_agent":
                click(page, page.get_by_role("button", name="Ask"))
                page.wait_for_timeout(500)
                box = page.locator(".agent-input-row input")
                box.fill("Brief me in three short bullets. Then propose assigning Team 2 to this alert.")
                box.press("Enter")
                page.wait_for_timeout(1500)
                move(page, 900, 520)
                for _ in range(80):
                    if page.locator(".agent-thinking").count() == 0 and page.locator(".agent-result").count() > 0:
                        break
                    page.wait_for_timeout(500)
                page.wait_for_timeout(800)
            elif name == "11_approve":
                if page.locator(".agent-result").count() > 0:
                    click(page, page.locator(".agent-result").first)
                    page.wait_for_timeout(1500)
                page.mouse.click(40, 320)
                page.wait_for_timeout(1000)
                move(page, 900, 560)
            elif name == "12_demo":
                click(page, page.get_by_role("button", name="Stage"))
                page.wait_for_timeout(1200)
                move(page, 700, 380)
            elif name == "13_close":
                move(page, 760, 320)
                move(page, 900, 560)
            remaining(started, scene["duration"])
            measured = round(time.monotonic() - started, 3)
            actuals.append(measured)
            print(f"scene {name}: {measured:.1f}s / {scene['duration']:.1f}s")

        screenshot = OUT / "thumbnail.png"
        OUT.mkdir(parents=True, exist_ok=True)
        if page.locator(".watch-alert-row").count() > 0:
            page.screenshot(path=str(screenshot))
        context.close()
        video_path = page.video.path() if page.video else None
        browser.close()
    if not video_path:
        raise RuntimeError("no video recorded")
    (ROOT / "timing_actual.json").write_text(json.dumps(actuals, indent=2), encoding="utf-8")
    return Path(video_path), actuals


def assemble(info: list[dict], video: Path, voice: Path, srt: Path, actuals: list[float]) -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    segments = OUT / "segments"
    segments.mkdir(exist_ok=True)
    for old in segments.glob("*.mp4"):
        old.unlink()
    finals = []
    for index, scene in enumerate(info):
        if scene.get("trim"):
            finals.append(scene["duration"])
        else:
            finals.append(max(actuals[index], scene["duration"]))

    # Voice: every scene gets silence up to its final visual duration.
    rate = 24000
    silence = lambda seconds: b"\x00\x00" * int(max(0.0, seconds) * rate)
    chunks = [silence(LEAD)]
    for index, scene in enumerate(info):
        wav = AUDIO / f"{scene['name']}.wav"
        with wave.open(str(wav), "rb") as handle:
            chunks.append(handle.readframes(handle.getnframes()))
        chunks.append(silence(finals[index] - scene["audio"]))
    voice_final = ROOT / "voice_final.wav"
    with wave.open(str(voice_final), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"".join(chunks))

    # Video: keep the full action time, pad only when the action was shorter.
    offset = 0.0
    concat_lines = []
    for index, scene in enumerate(info):
        actual = actuals[index]
        final = finals[index]
        segment = segments / f"seg_{index:02d}.mp4"
        vf = f"scale=1600:900,fps={FPS}"
        if final > actual + 0.01:
            vf += f",tpad=stop_mode=clone:stop_duration={final - actual:.3f}"
        ffmpeg(
            "-i", str(video), "-ss", f"{offset:.3f}", "-t", f"{min(actual, final):.3f}",
            "-vf", vf, "-t", f"{final:.3f}", "-an",
            "-c:v", "libx264", "-crf", "22", "-preset", "medium", "-pix_fmt", "yuv420p", str(segment),
        )
        concat_lines.append(f"file '{segment.as_posix()}'")
        offset += actual
    concat_file = OUT / "concat.txt"
    concat_file.write_text("\n".join(concat_lines), encoding="utf-8")
    retimed = OUT / "retimed.mp4"
    ffmpeg("-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(retimed))

    # SRT follows the final scene starts.
    def ts(value: float) -> str:
        hours = int(value // 3600)
        minutes = int((value % 3600) // 60)
        seconds = value % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}".replace(".", ",")

    lines = []
    cursor = 0.0
    for index, scene in enumerate(info, 1):
        lines.append(str(index))
        lines.append(f"{ts(cursor)} --> {ts(cursor + scene['audio'] + 0.5)}")
        lines.append(scene["text"])
        lines.append("")
        cursor += finals[index - 1]
    srt.write_text("\n".join(lines), encoding="utf-8")

    silent = OUT / "georesponse-example-demo-silent.mp4"
    final = OUT / "georesponse-example-demo.mp4"
    soft = OUT / "georesponse-example-demo-softsubs.mp4"
    burned = OUT / "georesponse-example-demo-burned.mp4"
    ffmpeg("-i", str(retimed), "-c", "copy", "-an", str(silent))
    ffmpeg("-i", str(retimed), "-i", str(voice_final), "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(final))
    ffmpeg("-i", str(final), "-i", str(srt), "-map", "0", "-map", "1", "-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text", "-metadata:s:s:0", "language=eng", "-movflags", "+faststart", str(soft))
    ffmpeg("-i", str(final), "-vf", "subtitles=georesponse-example-demo.srt:force_style='FontName=Arial,FontSize=10,Outline=1.2,MarginV=14'", "-c:v", "libx264", "-crf", "22", "-pix_fmt", "yuv420p", "-c:a", "copy", str(burned))
    return {"final": str(final), "silent": str(silent), "soft": str(soft), "burned": str(burned), "duration": duration(final)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-audio", action="store_true")
    parser.add_argument("--assemble-only", action="store_true")
    args = parser.parse_args()
    info = make_audio(force=args.force_audio)
    voice = build_voice(info)
    srt = make_srt(info)
    recording = ROOT / "recording.webm"
    if args.assemble_only:
        if not recording.exists():
            raise SystemExit("no recording.webm")
        actuals = json.loads((ROOT / "timing_actual.json").read_text(encoding="utf-8"))
        video = recording
    else:
        video, actuals = record(info)
        if recording.exists():
            recording.unlink()
        video.replace(recording)
        video = recording
    result = assemble(info, video, voice, srt, actuals)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
