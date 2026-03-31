"""Compatibility shim for imports launched from the repository root."""

from __future__ import annotations

from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent

# Allow ``webagentbench.<module>`` lookups to resolve modules that live directly
# in the repository root when Python is started from inside that directory.
__path__ = [str(_HERE), str(_REPO_ROOT)]
__version__ = "1.3.0"
