"""
BFD Constants - RFC 5880, 5881, 5882, 5883

Protocol constants for Bidirectional Forwarding Detection.
"""

# BFD Version
BFD_VERSION = 1

# UDP Ports (RFC 5881)
BFD_UDP_PORT = 3784          # Single-hop BFD control
BFD_ECHO_PORT = 3785         # BFD echo
BFD_MULTIHOP_PORT = 4784     # Multi-hop BFD (RFC 5883)

# Packet sizes
BFD_PACKET_MIN_LEN = 24      # Minimum BFD packet length
BFD_PACKET_MAX_LEN = 100     # Maximum with authentication
BFD_HEADER_LEN = 24          # Standard header without auth

# Default timers (in microseconds)
DEFAULT_MIN_TX_INTERVAL = 1000000      # 1 second (conservative default)
DEFAULT_MIN_RX_INTERVAL = 1000000      # 1 second
DEFAULT_ECHO_TX_INTERVAL = 0           # Echo disabled by default
DEFAULT_DETECT_MULT = 3                # 3x miss = down

# Aggressive timers for fast detection
FAST_MIN_TX_INTERVAL = 100000          # 100ms
FAST_MIN_RX_INTERVAL = 100000          # 100ms
AGGRESSIVE_MIN_TX_INTERVAL = 50000     # 50ms
AGGRESSIVE_MIN_RX_INTERVAL = 50000     # 50ms

# Minimum supported intervals
MIN_TX_INTERVAL_FLOOR = 10000          # 10ms absolute minimum
MIN_RX_INTERVAL_FLOOR = 10000          # 10ms absolute minimum

# State machine constants
ADMIN_DOWN_POLL_INTERVAL = 1.0         # Poll interval when admin down (seconds)
UP_POLL_INTERVAL = 0.1                 # Poll interval when up (100ms)

# Authentication
AUTH_TYPE_NONE = 0
AUTH_TYPE_SIMPLE = 1
AUTH_TYPE_KEYED_MD5 = 2
AUTH_TYPE_METICULOUS_KEYED_MD5 = 3
AUTH_TYPE_KEYED_SHA1 = 4
AUTH_TYPE_METICULOUS_KEYED_SHA1 = 5

# IP Protocol
IPPROTO_UDP = 17

# TTL for single-hop BFD (RFC 5881 Section 5)
BFD_SINGLE_HOP_TTL = 255

# DSCP for BFD (Network Control - CS6)
BFD_DSCP = 48  # CS6 = 110000 binary = 48 decimal

# Session limits
MAX_SESSIONS_DEFAULT = 256
SESSION_ID_MIN = 1
SESSION_ID_MAX = 0xFFFFFFFF
