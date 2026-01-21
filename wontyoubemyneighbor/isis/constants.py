"""
IS-IS Protocol Constants

Defines constants used throughout the IS-IS implementation based on RFC 1195.
"""

# IS-IS Levels
LEVEL_1 = 1
LEVEL_2 = 2
LEVEL_1_2 = 3  # Level 1 and Level 2

# IS-IS PDU Types
PDU_L1_LAN_IIH = 15      # Level 1 LAN IS-IS Hello
PDU_L2_LAN_IIH = 16      # Level 2 LAN IS-IS Hello
PDU_P2P_IIH = 17         # Point-to-Point IS-IS Hello
PDU_L1_LSP = 18          # Level 1 Link State PDU
PDU_L2_LSP = 20          # Level 2 Link State PDU
PDU_L1_CSNP = 24         # Level 1 Complete Sequence Numbers PDU
PDU_L2_CSNP = 25         # Level 2 Complete Sequence Numbers PDU
PDU_L1_PSNP = 26         # Level 1 Partial Sequence Numbers PDU
PDU_L2_PSNP = 27         # Level 2 Partial Sequence Numbers PDU

# PDU Type Names for logging
PDU_TYPE_NAMES = {
    PDU_L1_LAN_IIH: "L1 LAN IIH",
    PDU_L2_LAN_IIH: "L2 LAN IIH",
    PDU_P2P_IIH: "P2P IIH",
    PDU_L1_LSP: "L1 LSP",
    PDU_L2_LSP: "L2 LSP",
    PDU_L1_CSNP: "L1 CSNP",
    PDU_L2_CSNP: "L2 CSNP",
    PDU_L1_PSNP: "L1 PSNP",
    PDU_L2_PSNP: "L2 PSNP",
}

# TLV Types (Type-Length-Value)
TLV_AREA_ADDRESSES = 1           # Area Addresses
TLV_IS_NEIGHBORS = 2             # IS Neighbors (old style)
TLV_ES_NEIGHBORS = 3             # ES Neighbors
TLV_PARTITION_DR = 4             # Partition Designated Router
TLV_PREFIX_NEIGHBORS = 5         # Prefix Neighbors
TLV_IS_NEIGHBORS_VAR = 6         # IS Neighbors (variable length)
TLV_PADDING = 8                  # Padding
TLV_LSP_ENTRIES = 9              # LSP Entries
TLV_AUTHENTICATION = 10          # Authentication
TLV_CHECKSUM = 12                # Checksum
TLV_EXTENDED_IS_REACH = 22       # Extended IS Reachability (TE)
TLV_IP_INT_REACH = 128           # IP Internal Reachability
TLV_PROTOCOLS_SUPPORTED = 129    # Protocols Supported
TLV_IP_EXT_REACH = 130           # IP External Reachability
TLV_IDRP_INFO = 131              # IDRP Information
TLV_IP_INTERFACE_ADDR = 132      # IP Interface Address
TLV_HOSTNAME = 137               # Dynamic Hostname
TLV_TE_ROUTER_ID = 134           # TE Router ID
TLV_EXTENDED_IP_REACH = 135      # Extended IP Reachability
TLV_IPV6_INTERFACE_ADDR = 232    # IPv6 Interface Address
TLV_IPV6_REACH = 236             # IPv6 Reachability

# TLV Type Names
TLV_TYPE_NAMES = {
    TLV_AREA_ADDRESSES: "Area Addresses",
    TLV_IS_NEIGHBORS: "IS Neighbors",
    TLV_ES_NEIGHBORS: "ES Neighbors",
    TLV_PADDING: "Padding",
    TLV_LSP_ENTRIES: "LSP Entries",
    TLV_AUTHENTICATION: "Authentication",
    TLV_CHECKSUM: "Checksum",
    TLV_EXTENDED_IS_REACH: "Extended IS Reach",
    TLV_IP_INT_REACH: "IP Internal Reach",
    TLV_PROTOCOLS_SUPPORTED: "Protocols Supported",
    TLV_IP_EXT_REACH: "IP External Reach",
    TLV_IP_INTERFACE_ADDR: "IP Interface Address",
    TLV_HOSTNAME: "Hostname",
    TLV_TE_ROUTER_ID: "TE Router ID",
    TLV_EXTENDED_IP_REACH: "Extended IP Reach",
    TLV_IPV6_INTERFACE_ADDR: "IPv6 Interface Address",
    TLV_IPV6_REACH: "IPv6 Reachability",
}

# Adjacency States
ADJ_STATE_DOWN = 0
ADJ_STATE_INIT = 1
ADJ_STATE_UP = 2

ADJ_STATE_NAMES = {
    ADJ_STATE_DOWN: "Down",
    ADJ_STATE_INIT: "Initializing",
    ADJ_STATE_UP: "Up",
}

# Circuit Types
CIRCUIT_BROADCAST = 1
CIRCUIT_P2P = 2

CIRCUIT_TYPE_NAMES = {
    CIRCUIT_BROADCAST: "Broadcast",
    CIRCUIT_P2P: "Point-to-Point",
}

# Default Timer Values (in seconds)
DEFAULT_HELLO_INTERVAL = 10          # IIH transmission interval
DEFAULT_HELLO_MULTIPLIER = 3         # Hold time = hello_interval * multiplier
DEFAULT_CSNP_INTERVAL = 10           # CSNP transmission interval on broadcast
DEFAULT_PSNP_INTERVAL = 2            # PSNP transmission interval
DEFAULT_LSP_REFRESH_INTERVAL = 900   # LSP refresh before expiry
DEFAULT_LSP_LIFETIME = 1200          # Default LSP max age (20 minutes)
DEFAULT_SPF_DELAY = 5                # Wait before running SPF after LSP change
DEFAULT_SPF_INTERVAL = 10            # Minimum time between SPF runs
DEFAULT_MIN_LSP_TRANSMIT_INTERVAL = 5  # Minimum interval between LSP transmissions

# Priority
DEFAULT_PRIORITY = 64                # Default DIS priority
MAX_PRIORITY = 127                   # Maximum DIS priority

# LSP Constants
MAX_LSP_SIZE = 1492                  # Maximum LSP size
LSP_SEQUENCE_INITIAL = 1             # Initial sequence number
LSP_SEQUENCE_MAX = 0xFFFFFFFF        # Maximum sequence number

# Network Layer Protocol Identifiers (NLPID)
NLPID_IPV4 = 0xCC                    # IPv4
NLPID_IPV6 = 0x8E                    # IPv6
NLPID_CLNP = 0x81                    # CLNP (OSI)

# Metric Types
METRIC_DEFAULT = 0                   # Default metric
METRIC_DELAY = 1                     # Delay metric
METRIC_EXPENSE = 2                   # Expense metric
METRIC_ERROR = 3                     # Error metric

# Default Metric
DEFAULT_METRIC = 10                  # Default IS-IS metric

# Max values
MAX_AGE = 1200                       # Maximum LSP age in seconds
MAX_AREA_ADDRESSES = 3               # Maximum area addresses per router
MAX_PATH_METRIC = 0xFE               # Maximum narrow metric
MAX_WIDE_PATH_METRIC = 0xFFFFFF      # Maximum wide metric (24-bit)

# IS-IS Protocol Constants
ISIS_PROTOCOL_DISCRIMINATOR = 0x83   # ISO 10589 NLPID for IS-IS
ISIS_VERSION = 1                     # IS-IS version
ISIS_HEADER_LEN = 8                  # Common IS-IS header length

# System ID Length (6 bytes for standard IS-IS)
SYSTEM_ID_LEN = 6

# Area Address Formats
# NET (Network Entity Title) format: AFI.Area.SystemID.NSEL
# Example: 49.0001.0010.0100.1001.00
# - AFI (Authority Format Identifier): 49 (private)
# - Area ID: 0001
# - System ID: 0010.0100.1001 (6 bytes)
# - NSEL (N-Selector): 00 (always 00 for routers)
