#!/usr/bin/env python3
"""Entrada local do instalador; não requer instalação prévia do pacote."""

import sys
from pathlib import Path

if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11 ou superior é necessário.")

PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from hidctl.installation import install_main  # noqa: E402

raise SystemExit(install_main(PROJECT_DIR))
