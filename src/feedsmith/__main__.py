"""Enable ``python -m feedsmith`` to invoke the CLI.

This mirrors the ``feedsmith`` console script (declared in ``pyproject.toml``)
and works in an editable install without a reinstall.
"""
from __future__ import annotations

import sys

from feedsmith.cli import main

if __name__ == "__main__":
    sys.exit(main())
