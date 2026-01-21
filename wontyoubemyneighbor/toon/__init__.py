"""
TOON - Token Oriented Object Notation

A compact, token-efficient serialization format optimized for AI/LLM consumption.
Designed for network configuration and state persistence.

Features:
- Short key names for token efficiency
- Human-readable with compression
- Schema validation
- Support for nested structures (agents, networks, state)
"""

from .format import (
    TOONEncoder,
    TOONDecoder,
    serialize,
    deserialize,
    validate,
    compress,
    decompress
)

from .schemas import (
    AgentSchema,
    NetworkSchema,
    InterfaceSchema,
    ProtocolConfigSchema,
    MCPConfigSchema,
    RuntimeStateSchema
)

from .models import (
    TOONAgent,
    TOONNetwork,
    TOONInterface,
    TOONProtocolConfig,
    TOONMCPConfig,
    TOONRuntimeState,
    TOONTopology
)

__version__ = "1.0.0"
__all__ = [
    "TOONEncoder",
    "TOONDecoder",
    "serialize",
    "deserialize",
    "validate",
    "compress",
    "decompress",
    "AgentSchema",
    "NetworkSchema",
    "InterfaceSchema",
    "ProtocolConfigSchema",
    "MCPConfigSchema",
    "RuntimeStateSchema",
    "TOONAgent",
    "TOONNetwork",
    "TOONInterface",
    "TOONProtocolConfig",
    "TOONMCPConfig",
    "TOONRuntimeState",
    "TOONTopology"
]
