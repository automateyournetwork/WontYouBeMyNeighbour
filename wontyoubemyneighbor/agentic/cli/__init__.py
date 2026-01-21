"""
CLI Chat Interface

Interactive command-line interface for natural language conversations with RubberBand.
"""

from .chat import RubberBandCLI, run_cli

__all__ = [
    "RubberBandCLI",
    "run_cli",
]
