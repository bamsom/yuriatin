"""Yuriatin backend engine.

The canon store (SQLite) is the single source of truth for the fictional
ballet world. Every mutation flows through the validated Typer CLI in
``engine.cli`` — nothing else should ever open the DB for writing.
"""

__all__ = ["__version__"]
__version__ = "0.1.0"
