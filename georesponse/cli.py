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

    static = sub.add_parser("static", help="serve the built web app")
    static.add_argument("--port", type=int, default=4173)
    static.set_defaults(func=cmd_static)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
