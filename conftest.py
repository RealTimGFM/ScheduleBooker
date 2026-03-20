from __future__ import annotations

import itertools
import shutil
from pathlib import Path

import pytest

_TMP_COUNTER = itertools.count()
_TMP_ROOT = Path(__file__).resolve().parent / ".test_tmp"


@pytest.fixture()
def tmp_path() -> Path:
    """
    Use a workspace-local temp directory instead of the default Windows temp area.
    This keeps tests isolated while avoiding host temp-directory permission issues.
    """
    _TMP_ROOT.mkdir(parents=True, exist_ok=True)
    case_dir = _TMP_ROOT / f"case_{next(_TMP_COUNTER)}"
    if case_dir.exists():
        shutil.rmtree(case_dir, ignore_errors=True)
    case_dir.mkdir(parents=True, exist_ok=True)
    return case_dir
