#!/usr/bin/env python3
"""Annotate disassembly files with semantic names from SEMANTIC_FUNCTION_MAP.md."""

from __future__ import annotations

import _bootstrap  # noqa: F401

from dlcp_fw.analysis.annotate_disasm import main

if __name__ == "__main__":
    raise SystemExit(main())
