"""Compatibility namespace to expose src/dlcp_fw without installation."""
from pkgutil import extend_path
from pathlib import Path

__path__ = extend_path(__path__, __name__)  # type: ignore[name-defined]
_src_pkg = Path(__file__).resolve().parent.parent / "src" / "dlcp_fw"
if _src_pkg.exists():
    __path__.append(str(_src_pkg))
