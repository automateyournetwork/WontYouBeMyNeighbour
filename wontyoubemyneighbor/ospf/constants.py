"""
OSPF Protocol Constants from RFC 2328
"""

# OSPF Version and Protocol
OSPF_VERSION = 2
OSPF_PROTOCOL_NUMBER = 89  # IP protocol number for OSPF

# Multicast Addresses
ALLSPFROUTERS = "224.0.0.5"  # All OSPF routers
ALLDROUTERS = "224.0.0.6"    # All Designated Routers

# OSPF Packet Types (RFC 2328 Section 4.3)
HELLO_PACKET = 1
DATABASE_DESCRIPTION = 2
LINK_STATE_REQUEST = 3
LINK_STATE_UPDATE = 4
LINK_STATE_ACK = 5

PACKET_TYPES = {
    1: "Hello",
    2: "Database Description",
    3: "Link State Request",
    4: "Link State Update",
    5: "Link State Acknowledgment"
}

# Neighbor States (RFC 2328 Section 10.1)
STATE_DOWN = 0
STATE_ATTEMPT = 1
STATE_INIT = 2
STATE_2WAY = 3
STATE_EXSTART = 4
STATE_EXCHANGE = 5
STATE_LOADING = 6
STATE_FULL = 7

STATE_NAMES = {
    0: "Down",
    1: "Attempt",
    2: "Init",
    3: "2-Way",
    4: "ExStart",
    5: "Exchange",
    6: "Loading",
    7: "Full"
}

# Neighbor Events (RFC 2328 Section 10.2)
EVENT_HELLO_RECEIVED = "HelloReceived"
EVENT_START = "Start"
EVENT_2WAY_RECEIVED = "2-WayReceived"
EVENT_NEGOTIATION_DONE = "NegotiationDone"
EVENT_EXCHANGE_DONE = "ExchangeDone"
EVENT_BAD_LS_REQ = "BadLSReq"
EVENT_LOADING_DONE = "LoadingDone"
EVENT_ADJ_OK = "AdjOK?"
EVENT_SEQ_NUMBER_MISMATCH = "SeqNumberMismatch"
EVENT_1WAY = "1-Way"
EVENT_KILL_NBR = "KillNbr"
EVENT_INACTIVITY_TIMER = "InactivityTimer"
EVENT_LL_DOWN = "LLDown"

# LSA Types (RFC 2328 Section 12.1, RFC 3101 for Type 7)
ROUTER_LSA = 1
NETWORK_LSA = 2
SUMMARY_LSA_NETWORK = 3
SUMMARY_LSA_ASBR = 4
AS_EXTERNAL_LSA = 5
NSSA_EXTERNAL_LSA = 7  # RFC 3101 - Not-So-Stubby Area External LSA

LSA_TYPE_NAMES = {
    1: "Router LSA",
    2: "Network LSA",
    3: "Summary LSA (IP network)",
    4: "Summary LSA (ASBR)",
    5: "AS External LSA",
    7: "NSSA External LSA"
}

# Router Link Types (RFC 2328 Section A.4.2)
LINK_TYPE_PTP = 1           # Point-to-point connection to another router
LINK_TYPE_TRANSIT = 2       # Connection to a transit network
LINK_TYPE_STUB = 3          # Connection to a stub network
LINK_TYPE_VIRTUAL = 4       # Virtual link

LINK_TYPE_NAMES = {
    1: "Point-to-point",
    2: "Transit network",
    3: "Stub network",
    4: "Virtual link"
}

# Authentication Types (RFC 2328 Appendix D)
AUTH_NULL = 0
AUTH_SIMPLE = 1
AUTH_CRYPTOGRAPHIC = 2

AUTH_TYPE_NAMES = {
    0: "Null",
    1: "Simple Password",
    2: "Cryptographic"
}

# OSPF Options (RFC 2328 Section A.2)
OPTION_E = 0x02   # External routing capability
OPTION_MC = 0x04  # Multicast capable
OPTION_NP = 0x08  # Type-7 LSA capable (NSSA)
OPTION_EA = 0x10  # External attributes LSA capable
OPTION_DC = 0x20  # Demand circuits capable

# DBD Packet Flags (RFC 2328 Section A.3.3)
DBD_FLAG_MS = 0x01   # Master/Slave bit (1 = Master)
DBD_FLAG_M = 0x02    # More bit (1 = more DBD packets follow)
DBD_FLAG_I = 0x04    # Init bit (1 = first packet)

# Timers (seconds) - RFC 2328 Appendix B
HELLO_INTERVAL = 10              # Seconds between Hello packets
ROUTER_DEAD_INTERVAL = 40        # Declare neighbor dead after this
RETRANSMIT_INTERVAL = 5          # Seconds between LSA retransmissions
INF_TRANS_DELAY = 1              # Estimated seconds to transmit LSA
LS_REFRESH_TIME = 1800           # 30 minutes - refresh LSAs
MAX_AGE = 3600                   # 1 hour - maximum LSA age
MAX_AGE_DIFF = 900               # 15 minutes - MaxAgeDiff

# LSA Sequence Numbers (RFC 2328 Section 12.1.6)
INITIAL_SEQUENCE_NUMBER = 0x80000001
MAX_SEQUENCE_NUMBER = 0x7FFFFFFF

# Network Types (RFC 2328 Section 9)
NETWORK_TYPE_BROADCAST = "broadcast"
NETWORK_TYPE_NBMA = "nbma"
NETWORK_TYPE_POINT_TO_POINT = "point-to-point"
NETWORK_TYPE_POINT_TO_MULTIPOINT = "point-to-multipoint"
NETWORK_TYPE_VIRTUAL_LINK = "virtual-link"

NETWORK_TYPES = {
    NETWORK_TYPE_BROADCAST,
    NETWORK_TYPE_NBMA,
    NETWORK_TYPE_POINT_TO_POINT,
    NETWORK_TYPE_POINT_TO_MULTIPOINT,
    NETWORK_TYPE_VIRTUAL_LINK
}

# Default Values
DEFAULT_INTERFACE_MTU = 1500
DEFAULT_ROUTER_PRIORITY = 1
DEFAULT_AREA_ID = "0.0.0.0"      # Backbone area
DEFAULT_NETWORK_TYPE = NETWORK_TYPE_BROADCAST

# Metric
INFINITE_METRIC = 0xFFFF

# Header Sizes (bytes)
OSPF_HEADER_SIZE = 24
LSA_HEADER_SIZE = 20

# IP Protocol and TTL
IP_PROTO_OSPF = 89
OSPF_MULTICAST_TTL = 1  # Link-local only
OSPF_UNICAST_TTL = 255  # Full TTL for unicast neighbors
