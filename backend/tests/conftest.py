from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_backend_dir = str(Path(__file__).resolve().parents[1])
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

for _name in tuple(os.environ):
    if _name.startswith("ANVEXA_"):
        os.environ.pop(_name)

os.environ["ANVEXA_ENVIRONMENT"] = "development"
os.environ["ANVEXA_DEV_DATABASE_MODE"] = "false"
os.environ["ANVEXA_JWT_SECRET_KEY"] = "test-only-anvexa-jwt-secret-key-32-bytes-minimum"


def pytest_configure() -> None:
    from app.core.config import Settings

    Settings.model_config = {**Settings.model_config, "env_file": None}


@pytest.fixture(autouse=True)
def clear_settings_and_engine_caches():
    from app.core.config import get_settings
    from app.database.connection import get_engine

    get_settings.cache_clear()
    get_engine.cache_clear()
    yield
    get_engine.cache_clear()
    get_settings.cache_clear()
