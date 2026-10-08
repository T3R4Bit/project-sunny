"""Shared pytest fixtures for Sunny tests."""

import shutil
from pathlib import Path

import pytest


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """Provide a temporary vault directory with fixtures copied in."""
    vault = tmp_path / "vault"
    fixtures_src = Path(__file__).parent.parent / "fixtures" / "vault"

    if fixtures_src.exists():
        shutil.copytree(fixtures_src, vault)
    else:
        vault.mkdir()

    return vault
