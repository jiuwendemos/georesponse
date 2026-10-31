"""JSON schema generation and structural validation for the contracts.

The schema is derived from the dataclasses, so it cannot drift from the code.
``laix/schemas/laix-v1.schema.json`` is the committed, versioned artefact; the
test suite regenerates it and fails if the committed file is stale.
"""

from __future__ import annotations

import json
import types
from dataclasses import MISSING, fields
from pathlib import Path
from typing import Any, Union, get_args, get_origin, get_type_hints

from .contracts import CONTRACTS, SCHEMA_VERSION

SCHEMA_ID = "https://laix.local/schemas/laix-v1.schema.json"
SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
SCHEMA_PATH = SCHEMA_DIR / "laix-v1.schema.json"

_ENUMS: dict[str, list[str]] = {
    "verb": ["wait", "ask", "guide", "act", "verify", "escalate"],
    "phase": ["observe", "understand", "decide", "act", "verify", "adapt"],
    "horizon": ["seconds", "minutes", "hours", "days", "weeks"],
    "status": ["pending", "approved", "executed", "refused", "cancelled", "failed", "undone"],
    "label": ["helped", "neutral", "hurt", "unknown"],
    "direction": ["higher-better", "lower-better"],
}


def _schema_for(value: Any) -> dict[str, Any]:
    if value is Any or value is None:
        return {}
    origin = get_origin(value)
    if origin in (Union, types.UnionType):
        args = [item for item in get_args(value) if item is not type(None)]
        optional = any(item is type(None) for item in get_args(value))
        if len(args) == 1:
            inner = _schema_for(args[0])
            return {"anyOf": [inner, {"type": "null"}]} if optional else inner
        return {"anyOf": [_schema_for(item) for item in args]}
    if origin in (list, tuple, set, frozenset):
        args = get_args(value)
        item = _schema_for(args[0]) if args else {}
        return {"type": "array", "items": item}
    if origin is dict:
        return {"type": "object"}
    if value is str:
        return {"type": "string"}
    if value is bool:
        return {"type": "boolean"}
    if value is int:
        return {"type": "integer"}
    if value is float:
        return {"type": "number"}
    if value is dict:
        return {"type": "object"}
    return {}


def _field_schema(contract: type, name: str, annotation: Any, required: bool) -> dict[str, Any]:
    schema = _schema_for(annotation)
    if name in _ENUMS and _ENUMS[name]:
        schema = {**schema, "enum": _ENUMS[name]}
    if name in {"confidence", "expected_benefit", "risk", "interrupt_cost", "priority"}:
        schema = {**schema, "minimum": 0, "maximum": 1}
    if not required:
        # A default of None is representable without making the field optional
        # in the dataclass, so mirror the runtime behaviour in the schema.
        schema = {"anyOf": [schema, {"type": "null"}]} if "anyOf" not in schema else schema
    return schema


def build_schema() -> dict[str, Any]:
    definitions: dict[str, Any] = {}
    for contract in CONTRACTS:
        hints = get_type_hints(contract)
        properties: dict[str, Any] = {}
        required: list[str] = []
        for item in fields(contract):
            has_default = item.default is not MISSING or item.default_factory is not MISSING  # type: ignore[misc]
            if not has_default:
                required.append(item.name)
            properties[item.name] = _field_schema(contract, item.name, hints.get(item.name, Any), not has_default)
        definitions[contract.__name__] = {
            "type": "object",
            "title": contract.__name__,
            "additionalProperties": False,
            "properties": properties,
            "required": required,
        }
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        "title": "LAIX contracts",
        "description": "Domain-neutral decision-layer contracts. Generated from laix.contracts.",
        "version": SCHEMA_VERSION,
        "$defs": definitions,
    }


def dumps_schema() -> str:
    return json.dumps(build_schema(), indent=2, ensure_ascii=False) + "\n"


def write_schema(path: Path | None = None) -> Path:
    target = path or SCHEMA_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(dumps_schema(), encoding="utf-8")
    return target


def check(contract_name: str, payload: dict[str, Any]) -> list[str]:
    """Minimal structural validation.

    This is intentionally not a general JSON Schema implementation.  It checks
    required keys, primitive types and enums for the committed contracts so the
    package stays standard-library only.
    """
    document = build_schema()
    definition = document["$defs"].get(contract_name)
    if definition is None:
        return [f"unknown contract: {contract_name}"]
    errors: list[str] = []
    for key in definition["required"]:
        if key not in payload:
            errors.append(f"missing required field: {key}")
    for key, value in payload.items():
        spec = definition["properties"].get(key)
        if spec is None:
            errors.append(f"unknown field: {key}")
            continue
        expected = _expected_type(spec)
        if expected and not _matches(value, expected):
            errors.append(f"{key}: expected {expected}, got {type(value).__name__}")
        enum = spec.get("enum")
        if enum and value not in enum:
            errors.append(f"{key}: {value!r} is not one of {enum}")
    return errors


def _expected_type(spec: dict[str, Any]) -> str | None:
    if "anyOf" in spec:
        for item in spec["anyOf"]:
            if item.get("type") != "null":
                return item.get("type")
        return None
    return spec.get("type")


def _matches(value: Any, expected: str) -> bool:
    if value is None:
        return True
    return {
        "string": isinstance(value, str),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "object": isinstance(value, dict),
        "array": isinstance(value, (list, tuple)),
    }.get(expected, True)
