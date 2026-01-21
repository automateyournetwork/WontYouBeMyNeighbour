"""
REST API Interface

HTTP REST API for natural language network management with RubberBand.
"""

from .server import create_api_server, RubberBandAPI

__all__ = [
    "create_api_server",
    "RubberBandAPI",
]
