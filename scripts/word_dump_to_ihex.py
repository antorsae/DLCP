#!/usr/bin/env python3
"""CLI wrapper for tabular word dump -> Intel HEX conversion."""

from __future__ import annotations

import _bootstrap

from dlcp_fw.analysis.word_dump_to_ihex import main


if __name__ == "__main__":
    raise SystemExit(main())
