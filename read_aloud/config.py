"""Configuration file handling (~/.read_aloud.toml)."""

import argparse
import sys

from read_aloud import CONFIG_PATH, DEFAULT_URI, console


def load_config() -> dict:
    """Load defaults from ~/.read_aloud.toml if it exists."""
    if not CONFIG_PATH.is_file():
        return {}
    try:
        if sys.version_info >= (3, 11):
            import tomllib
        else:
            try:
                import tomli as tomllib
            except ImportError:
                return {}
        with open(CONFIG_PATH, "rb") as f:
            data = tomllib.load(f)
        return data.get("defaults", {})
    except Exception:
        return {}


def save_config(args: argparse.Namespace) -> None:
    """Write current args to ~/.read_aloud.toml."""
    lines = ["[defaults]"]
    if args.voice != "alba":
        lines.append(f'voice = "{args.voice}"')
    if args.uri != DEFAULT_URI:
        lines.append(f'uri = "{args.uri}"')
    if args.device is not None:
        lines.append(f'device = "{args.device}"')
    CONFIG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    console.print(f"[green]Config saved to {CONFIG_PATH}[/green]")
