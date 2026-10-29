import json
from pathlib import Path

import pytest

from georesponse.config import DATA_DIR


@pytest.fixture(scope="session")
def scenario() -> dict:
    path = Path(DATA_DIR) / "scenarios" / "ahr-2021-flood.json"
    if not path.exists():
        from georesponse.datapack import build_all

        build_all(DATA_DIR)
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def index() -> dict:
    return json.loads((Path(DATA_DIR) / "index.json").read_text(encoding="utf-8"))
