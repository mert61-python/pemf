"""pytest ortak ayarı — guii kökünü import yoluna ekler ve izole temp app_data sağlar."""
import os
import sys
import tempfile
from pathlib import Path

import pytest

_GUII_ROOT = Path(__file__).resolve().parent.parent
if str(_GUII_ROOT) not in sys.path:
    sys.path.insert(0, str(_GUII_ROOT))


@pytest.fixture()
def temp_app_data(tmp_path, monkeypatch):
    """Her test için izole app_data dizini (gerçek %APPDATA%/PEMF_GUI'ye dokunma)."""
    d = tmp_path / "PEMF_GUI"
    d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return d
