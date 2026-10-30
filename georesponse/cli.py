"""Command line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import DATA_DIR, ROOT


def _load(scenario_id: str) -> dict:
    path = Path(DATA_DIR) / "scenarios" / f"{scenario_id}.json"
    if not path.exists():
        raise SystemExit(f"scenario not found: {path}. Run: georesponse build-demo")
    return json.loads(path.read_text(encoding="utf-8"))


def cmd_build(args: argparse.Namespace) -> int:
    from .datapack import build_all

    result = build_all(Path(args.data_dir) if args.data_dir else DATA_DIR)
    print(json.dumps(result, indent=2))
    return 0


def cmd_assess(args: argparse.Namespace) -> int:
    from .assessment import write_assessment
    from .ranking import rank_sites

    data = _load(args.scenario)
    excluded = {args.reject} if args.reject else set()
    ranked, warnings = rank_sites(data["sites"], exclude=excluded)
    reviews = {args.reject: "rejected"} if args.reject else {}
    assessment = write_assessment(data, ranked, reviews=reviews)
    assessment["warnings"] = warnings
    print(json.dumps(assessment, indent=2))
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    from .pilot import build_pilot_dashboard

    dashboard = build_pilot_dashboard()
    print(json.dumps(dashboard["summary"], indent=2))
    if args.full:
        print(json.dumps(dashboard, indent=2))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    from .audit import read_events, verify_chain

    events = read_events(args.path)
    ok, message = verify_chain(events)
    print(json.dumps({"events": len(events), "verified": ok, "message": message}, indent=2))
    return 0 if ok else 1


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("georesponse.api:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def cmd_connectors(args: argparse.Namespace) -> int:
    from .connectors import build_connector, ingest_manifest

    names = ["local", "sentinel-2", "sentinel-1", "planet", "maxar", "airbus", "iceye", "capella"]
    rows = []
    for name in names:
        connector = build_connector(name, root=ROOT / "data", dry_run=True)
        rows.append(connector.health())
    print(json.dumps(rows, indent=2))
    if args.manifest:
        print(json.dumps(ingest_manifest(build_connector("sentinel-2", dry_run=True), [6.5, 50.5, 7.5, 51.0], "2021-07-14", "2021-07-16"), indent=2))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from .production.config import doctor

    print(json.dumps(doctor(), indent=2))
    return 0


def cmd_fetch_imagery(args: argparse.Namespace) -> int:
    from .production.imagery import SCENARIOS, fetch_scenario

    ids = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
    results = {}
    for scenario_id in ids:
        try:
            results[scenario_id] = fetch_scenario(scenario_id, ROOT / "runtime" / "imagery")
        except Exception as exc:  # noqa: BLE001
            results[scenario_id] = {"error": str(exc)}
    print(json.dumps(results, indent=2, default=str))
    return 0


def cmd_infer(args: argparse.Namespace) -> int:
    from .production.inference import infer_tile_pair

    print(json.dumps(infer_tile_pair(args.before, args.after), indent=2))
    return 0


def cmd_agent(args: argparse.Namespace) -> int:
    import asyncio

    from .proactive.api import engine
    from .production.agent import LiveAgent, AgentUnavailable
    from .production.config import get_settings
    from .production.openjiuwen_runtime import OpenJiuwenAgent

    settings = get_settings()
    backend = OpenJiuwenAgent(engine, settings) if settings.llm.backend == "openjiuwen" else LiveAgent(engine, settings)
    try:
        result = asyncio.run(backend.chat(args.message, tenant=args.tenant))
    except AgentUnavailable as exc:
        print(json.dumps({"error": str(exc)}))
        return 1
    print(json.dumps(result, indent=2, default=str))
    return 0


def cmd_load_test(args: argparse.Namespace) -> int:
    from .proactive.ops import load_test

    print(json.dumps(load_test(scopes=args.scopes, alerts_per_scope=args.alerts), indent=2))
    return 0


def cmd_drill(args: argparse.Namespace) -> int:
    from .proactive.demo import seed_demo
    from .proactive.ops import backup_restore_drill
    from .proactive.store import ProactiveStore

    store = ProactiveStore(ROOT / "runtime" / "proactive.db")
    if not store.list_scopes("demo"):
        seed_demo(store)
    print(json.dumps(backup_restore_drill(store, args.path), indent=2))
    return 0


def cmd_airgap(args: argparse.Namespace) -> int:
    from .proactive.demo import seed_demo
    from .proactive.ops import run_airgap
    from .proactive.store import ProactiveStore

    store = ProactiveStore(ROOT / "runtime" / "proactive.db")
    if not store.list_scopes("demo"):
        seed_demo(store)
    print(json.dumps(run_airgap(store, {args.scope: args.folder}), indent=2))
    return 0


def cmd_proactive_demo(args: argparse.Namespace) -> int:
    from .proactive.demo import write_demo

    print(json.dumps(write_demo(ROOT / "web" / "public" / "data" / "proactive.json"), indent=2))
    return 0


def cmd_static(args: argparse.Namespace) -> int:
    import http.server
    import socketserver

    directory = str(ROOT / "web" / "dist")
    if not Path(directory).exists():
        raise SystemExit("web/dist missing. Run: cd web && npm run build")
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=directory, **kw)  # noqa: E731
    http.server.SimpleHTTPRequestHandler.extensions_map.update(
        {
            ".mjs": "text/javascript",
            ".js": "text/javascript",
            ".json": "application/json",
            ".geojson": "application/geo+json",
            ".webmanifest": "application/manifest+json",
            ".svg": "image/svg+xml",
            ".png": "image/png",
        }
    )
    with socketserver.TCPServer(("127.0.0.1", args.port), handler) as httpd:
        print(f"serving {directory} at http://127.0.0.1:{args.port}")
        httpd.serve_forever()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="georesponse", description="GeoResponse CLI")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build-demo", help="build the offline demo packs")
    build.add_argument("--data-dir", default=None)
    build.set_defaults(func=cmd_build)

    assess = sub.add_parser("assess", help="print an assessment")
    assess.add_argument("--scenario", default="ahr-2021-flood")
    assess.add_argument("--reject", default=None)
    assess.set_defaults(func=cmd_assess)

    report = sub.add_parser("report", help="pilot metrics")
    report.add_argument("--full", action="store_true")
    report.set_defaults(func=cmd_report)

    verify = sub.add_parser("verify", help="verify the audit chain")
    verify.add_argument("--path", default=str(ROOT / "runtime" / "audit.jsonl"))
    verify.set_defaults(func=cmd_verify)

    serve = sub.add_parser("serve", help="run the optional API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    serve.set_defaults(func=cmd_serve)

    connectors = sub.add_parser("connectors", help="list imagery connectors")
    connectors.add_argument("--manifest", action="store_true")
    connectors.set_defaults(func=cmd_connectors)

    doctor = sub.add_parser("doctor", help="check production wiring without revealing secrets")
    doctor.set_defaults(func=cmd_doctor)

    fetch = sub.add_parser("fetch-imagery", help="fetch real Sentinel-2 before/after pairs")
    fetch.add_argument("--scenario", default="all")
    fetch.set_defaults(func=cmd_fetch_imagery)

    infer = sub.add_parser("infer", help="run real ONNX inference on a before/after pair")
    infer.add_argument("--before", required=True)
    infer.add_argument("--after", required=True)
    infer.set_defaults(func=cmd_infer)

    agent = sub.add_parser("agent", help="ask the configured live agent")
    agent.add_argument("--message", required=True)
    agent.add_argument("--tenant", default="demo")
    agent.set_defaults(func=cmd_agent)

    load = sub.add_parser("load-test", help="run the proactive load test")
    load.add_argument("--scopes", type=int, default=1000)
    load.add_argument("--alerts", type=int, default=10)
    load.set_defaults(func=cmd_load_test)

    drill = sub.add_parser("drill", help="run the proactive backup/restore drill")
    drill.add_argument("--path", default=str(ROOT / "runtime" / "drill"))
    drill.set_defaults(func=cmd_drill)

    airgap = sub.add_parser("airgap", help="import imagery into a scope from a folder")
    airgap.add_argument("--scope", required=True)
    airgap.add_argument("--folder", required=True)
    airgap.set_defaults(func=cmd_airgap)

    action = sub.add_parser("proactive-demo", help="rebuild the proactive Watch demo data")
    action.set_defaults(func=cmd_proactive_demo)

    static = sub.add_parser("static", help="serve the built web app")
    static.add_argument("--port", type=int, default=4173)
    static.set_defaults(func=cmd_static)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
