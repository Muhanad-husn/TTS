#!/usr/bin/env python3
"""Backwards-compatible shim — delegates to the read_aloud package."""

from read_aloud.cli import main

if __name__ == "__main__":
    main()
