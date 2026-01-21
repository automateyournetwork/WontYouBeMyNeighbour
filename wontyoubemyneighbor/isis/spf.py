"""
IS-IS SPF (Shortest Path First) Calculator

Implements Dijkstra's algorithm for IS-IS route computation.
Supports separate Level 1 and Level 2 SPF calculations.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any, Tuple
from datetime import datetime
import heapq

try:
    import networkx as nx
    NETWORKX_AVAILABLE = True
except ImportError:
    NETWORKX_AVAILABLE = False
    nx = None

from .constants import (
    LEVEL_1, LEVEL_2, LEVEL_1_2,
    DEFAULT_SPF_DELAY, DEFAULT_SPF_INTERVAL,
    DEFAULT_METRIC, MAX_PATH_METRIC,
    TLV_IS_NEIGHBORS, TLV_EXTENDED_IS_REACH,
    TLV_IP_INT_REACH, TLV_EXTENDED_IP_REACH,
)
from .lsdb import LSDB, LSP, DualLSDB


@dataclass
class SPFRoute:
    """
    Computed route from SPF calculation.

    Represents a reachable destination with path information.
    """
    prefix: str              # Destination prefix (e.g., "10.0.0.0/24")
    next_hop: str            # Next hop IP address
    metric: int              # Total path metric
    via_system_id: str       # Next hop system ID
    level: int               # Route level (L1 or L2)
    route_type: str = "internal"  # "internal" or "external"
    path: List[str] = field(default_factory=list)  # System IDs in path

    def __lt__(self, other: 'SPFRoute') -> bool:
        """Compare by metric for heap operations"""
        return self.metric < other.metric


@dataclass
class SPFVertex:
    """
    Vertex in SPF tree representing a router.
    """
    system_id: str
    distance: int = float('inf')
    parent: Optional[str] = None
    next_hop: Optional[str] = None
    processed: bool = False

    def __lt__(self, other: 'SPFVertex') -> bool:
        return self.distance < other.distance


class ISISSPFCalculator:
    """
    SPF calculator for IS-IS routing.

    Runs Dijkstra's algorithm over the LSDB to compute
    shortest paths to all reachable destinations.
    """

    def __init__(
        self,
        system_id: str,
        lsdb: LSDB,
        spf_delay: int = DEFAULT_SPF_DELAY,
        spf_interval: int = DEFAULT_SPF_INTERVAL,
    ):
        """
        Initialize SPF calculator.

        Args:
            system_id: Local router's system ID
            lsdb: Link State Database for this level
            spf_delay: Initial delay before running SPF
            spf_interval: Minimum interval between SPF runs
        """
        self.system_id = system_id
        self.lsdb = lsdb
        self.spf_delay = spf_delay
        self.spf_interval = spf_interval

        # Routing table: {prefix: SPFRoute}
        self.routing_table: Dict[str, SPFRoute] = {}

        # SPF tree: {system_id: SPFVertex}
        self._spf_tree: Dict[str, SPFVertex] = {}

        # SPF state
        self._spf_pending = False
        self._last_spf_time: Optional[datetime] = None
        self._spf_task: Optional[asyncio.Task] = None
        self._spf_scheduled = False

        # Statistics
        self._spf_runs = 0
        self._total_spf_time_ms = 0

        self.logger = logging.getLogger(f"SPF-L{lsdb.level}")

    def schedule_spf(self) -> None:
        """
        Schedule an SPF calculation.

        Implements SPF delay and throttling to prevent
        excessive computations during network instability.
        """
        if self._spf_scheduled:
            return

        self._spf_pending = True
        self._spf_scheduled = True

        # Calculate delay
        delay = self.spf_delay

        if self._last_spf_time:
            elapsed = (datetime.now() - self._last_spf_time).total_seconds()
            if elapsed < self.spf_interval:
                delay = max(delay, self.spf_interval - elapsed)

        self.logger.debug(f"SPF scheduled in {delay:.1f}s")

        # Schedule task
        asyncio.create_task(self._delayed_spf(delay))

    async def _delayed_spf(self, delay: float) -> None:
        """Run SPF after delay"""
        try:
            await asyncio.sleep(delay)
            self.run_spf()
        except asyncio.CancelledError:
            pass
        finally:
            self._spf_scheduled = False

    def run_spf(self) -> Dict[str, SPFRoute]:
        """
        Run SPF calculation.

        Computes shortest paths using Dijkstra's algorithm.

        Returns:
            New routing table
        """
        start_time = datetime.now()
        self._spf_pending = False
        self._last_spf_time = start_time

        self.logger.info(f"Starting SPF calculation (run #{self._spf_runs + 1})")

        # Build topology graph from LSDB
        if NETWORKX_AVAILABLE:
            routes = self._run_spf_networkx()
        else:
            routes = self._run_spf_native()

        # Update routing table
        self.routing_table = routes

        # Statistics
        elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000
        self._spf_runs += 1
        self._total_spf_time_ms += elapsed_ms

        self.logger.info(f"SPF complete: {len(routes)} routes, {elapsed_ms:.2f}ms")

        return routes

    def _run_spf_networkx(self) -> Dict[str, SPFRoute]:
        """Run SPF using NetworkX library"""
        # Build directed graph
        G = nx.DiGraph()

        # Add self
        G.add_node(self.system_id)

        # Process all LSPs to build topology
        for lsp in self.lsdb.get_all_lsps():
            source_id = self._extract_system_id(lsp.lsp_id)
            G.add_node(source_id)

            # Process IS neighbor TLVs
            for tlv in lsp.get_tlvs(TLV_IS_NEIGHBORS):
                neighbors = self._parse_is_neighbors_tlv(tlv.value)
                for neighbor_id, metric in neighbors:
                    G.add_edge(source_id, neighbor_id, weight=metric)

            # Process Extended IS Reachability TLVs (TE)
            for tlv in lsp.get_tlvs(TLV_EXTENDED_IS_REACH):
                neighbors = self._parse_extended_is_reach_tlv(tlv.value)
                for neighbor_id, metric in neighbors:
                    G.add_edge(source_id, neighbor_id, weight=metric)

        # Run Dijkstra
        try:
            lengths, paths = nx.single_source_dijkstra(G, self.system_id)
        except nx.NetworkXError as e:
            self.logger.error(f"SPF computation failed: {e}")
            return {}

        # Build routing table
        routes = {}

        # First, get IS-IS reachable systems
        for target, distance in lengths.items():
            if target == self.system_id:
                continue

            path = paths.get(target, [])
            if len(path) < 2:
                continue

            # Next hop is second node in path
            next_hop_system = path[1]

            # Get IP prefixes advertised by this system
            target_lsp_id = f"{target}.00-00"  # Main LSP
            target_lsp = self.lsdb.get_lsp(target_lsp_id)

            if target_lsp:
                prefixes = self._extract_ip_prefixes(target_lsp)
                for prefix, prefix_metric in prefixes:
                    total_metric = distance + prefix_metric
                    routes[prefix] = SPFRoute(
                        prefix=prefix,
                        next_hop=self._get_next_hop_ip(next_hop_system),
                        metric=total_metric,
                        via_system_id=next_hop_system,
                        level=self.lsdb.level,
                        path=path,
                    )

        return routes

    def _run_spf_native(self) -> Dict[str, SPFRoute]:
        """Run SPF using native Python implementation"""
        # Initialize
        vertices: Dict[str, SPFVertex] = {}
        vertices[self.system_id] = SPFVertex(
            system_id=self.system_id,
            distance=0,
            parent=None,
            next_hop=self.system_id,
        )

        # Build adjacency list from LSDB
        adjacencies: Dict[str, List[Tuple[str, int]]] = {}

        for lsp in self.lsdb.get_all_lsps():
            source_id = self._extract_system_id(lsp.lsp_id)

            if source_id not in adjacencies:
                adjacencies[source_id] = []

            for tlv in lsp.get_tlvs(TLV_IS_NEIGHBORS):
                neighbors = self._parse_is_neighbors_tlv(tlv.value)
                adjacencies[source_id].extend(neighbors)

            for tlv in lsp.get_tlvs(TLV_EXTENDED_IS_REACH):
                neighbors = self._parse_extended_is_reach_tlv(tlv.value)
                adjacencies[source_id].extend(neighbors)

        # Priority queue: (distance, system_id)
        pq = [(0, self.system_id)]

        while pq:
            dist, current = heapq.heappop(pq)

            if current not in vertices:
                vertices[current] = SPFVertex(system_id=current)

            vertex = vertices[current]

            if vertex.processed:
                continue

            vertex.processed = True
            vertex.distance = dist

            # Process neighbors
            for neighbor_id, metric in adjacencies.get(current, []):
                new_dist = dist + metric

                if neighbor_id not in vertices:
                    vertices[neighbor_id] = SPFVertex(system_id=neighbor_id)

                neighbor_vertex = vertices[neighbor_id]

                if new_dist < neighbor_vertex.distance:
                    neighbor_vertex.distance = new_dist
                    neighbor_vertex.parent = current

                    # Set next hop
                    if current == self.system_id:
                        neighbor_vertex.next_hop = neighbor_id
                    else:
                        neighbor_vertex.next_hop = vertex.next_hop

                    heapq.heappush(pq, (new_dist, neighbor_id))

        # Build routing table from SPF tree
        routes = {}

        for system_id, vertex in vertices.items():
            if system_id == self.system_id or not vertex.processed:
                continue

            # Get LSP for this system
            lsp_id = f"{system_id}.00-00"
            lsp = self.lsdb.get_lsp(lsp_id)

            if lsp:
                prefixes = self._extract_ip_prefixes(lsp)
                for prefix, prefix_metric in prefixes:
                    total_metric = vertex.distance + prefix_metric

                    routes[prefix] = SPFRoute(
                        prefix=prefix,
                        next_hop=self._get_next_hop_ip(vertex.next_hop),
                        metric=total_metric,
                        via_system_id=vertex.next_hop,
                        level=self.lsdb.level,
                        path=self._build_path(vertices, system_id),
                    )

        return routes

    def _extract_system_id(self, lsp_id: str) -> str:
        """Extract system ID from LSP ID"""
        # LSP ID format: "AABB.CCDD.EEFF.PN-FF"
        parts = lsp_id.split(".")
        if len(parts) >= 3:
            return ".".join(parts[:3])
        return lsp_id

    def _parse_is_neighbors_tlv(self, data: bytes) -> List[Tuple[str, int]]:
        """
        Parse IS Neighbors TLV (type 2).

        Returns list of (neighbor_system_id, metric) tuples.
        """
        neighbors = []

        # Old-style IS Neighbors format:
        # 1 byte: Virtual flag
        # For each neighbor:
        #   4 bytes: Default metric
        #   1 byte: Delay metric
        #   1 byte: Expense metric
        #   1 byte: Error metric
        #   7 bytes: Neighbor ID (system_id + pseudonode)

        offset = 1  # Skip virtual flag

        while offset + 11 <= len(data):
            default_metric = data[offset] & 0x3F  # 6-bit metric
            neighbor_id_bytes = data[offset + 4:offset + 11]

            # Convert neighbor ID bytes to string
            neighbor_id = ".".join(f"{b:02X}" for b in neighbor_id_bytes[:6])

            neighbors.append((neighbor_id, default_metric))
            offset += 11

        return neighbors

    def _parse_extended_is_reach_tlv(self, data: bytes) -> List[Tuple[str, int]]:
        """
        Parse Extended IS Reachability TLV (type 22).

        This is the "wide metrics" format supporting metrics > 63.
        """
        neighbors = []
        offset = 0

        while offset + 11 <= len(data):
            # 7 bytes: Neighbor ID
            neighbor_id_bytes = data[offset:offset + 7]
            neighbor_id = ".".join(f"{b:02X}" for b in neighbor_id_bytes[:6])

            # 3 bytes: Metric (24-bit)
            metric = (data[offset + 7] << 16) | (data[offset + 8] << 8) | data[offset + 9]

            # 1 byte: Sub-TLV length
            sub_tlv_len = data[offset + 10]

            neighbors.append((neighbor_id, metric))
            offset += 11 + sub_tlv_len

        return neighbors

    def _extract_ip_prefixes(self, lsp: LSP) -> List[Tuple[str, int]]:
        """
        Extract IP prefixes from LSP.

        Returns list of (prefix, metric) tuples.
        """
        prefixes = []

        # Internal IP Reachability (type 128)
        for tlv in lsp.get_tlvs(TLV_IP_INT_REACH):
            parsed = self._parse_ip_reach_tlv(tlv.value)
            prefixes.extend(parsed)

        # Extended IP Reachability (type 135)
        for tlv in lsp.get_tlvs(TLV_EXTENDED_IP_REACH):
            parsed = self._parse_extended_ip_reach_tlv(tlv.value)
            prefixes.extend(parsed)

        return prefixes

    def _parse_ip_reach_tlv(self, data: bytes) -> List[Tuple[str, int]]:
        """Parse IP Internal Reachability TLV (type 128)"""
        prefixes = []
        offset = 0

        while offset + 12 <= len(data):
            # 1 byte: Default metric
            metric = data[offset] & 0x3F

            # 4 bytes: IP address
            ip = ".".join(str(b) for b in data[offset + 4:offset + 8])

            # 4 bytes: Subnet mask
            mask_bytes = data[offset + 8:offset + 12]
            mask = sum(bin(b).count("1") for b in mask_bytes)

            prefix = f"{ip}/{mask}"
            prefixes.append((prefix, metric))
            offset += 12

        return prefixes

    def _parse_extended_ip_reach_tlv(self, data: bytes) -> List[Tuple[str, int]]:
        """Parse Extended IP Reachability TLV (type 135)"""
        prefixes = []
        offset = 0

        while offset + 5 <= len(data):
            # 4 bytes: Metric
            metric = (data[offset] << 24) | (data[offset + 1] << 16) | \
                     (data[offset + 2] << 8) | data[offset + 3]

            # 1 byte: Flags + prefix length
            control = data[offset + 4]
            prefix_len = control & 0x3F
            up_down = (control >> 7) & 1
            sub_tlv_present = (control >> 6) & 1

            # Calculate number of prefix bytes
            prefix_bytes = (prefix_len + 7) // 8

            if offset + 5 + prefix_bytes > len(data):
                break

            # Extract prefix
            prefix_data = data[offset + 5:offset + 5 + prefix_bytes]
            prefix_data = prefix_data + bytes(4 - len(prefix_data))
            ip = ".".join(str(b) for b in prefix_data)
            prefix = f"{ip}/{prefix_len}"

            prefixes.append((prefix, metric))
            offset += 5 + prefix_bytes

            # Skip sub-TLVs if present
            if sub_tlv_present and offset < len(data):
                sub_tlv_len = data[offset]
                offset += 1 + sub_tlv_len

        return prefixes

    def _get_next_hop_ip(self, system_id: str) -> str:
        """
        Get IP address for next hop system.

        Looks up IP Interface Address TLV from the neighbor's LSP.
        """
        lsp_id = f"{system_id}.00-00"
        lsp = self.lsdb.get_lsp(lsp_id)

        if lsp:
            from .constants import TLV_IP_INTERFACE_ADDR
            for tlv in lsp.get_tlvs(TLV_IP_INTERFACE_ADDR):
                if len(tlv.value) >= 4:
                    return ".".join(str(b) for b in tlv.value[:4])

        # Fallback: return system ID as placeholder
        return system_id

    def _build_path(self, vertices: Dict[str, SPFVertex], target: str) -> List[str]:
        """Build path from source to target"""
        path = []
        current = target

        while current:
            path.insert(0, current)
            vertex = vertices.get(current)
            if vertex:
                current = vertex.parent
            else:
                break

        return path

    def get_route(self, prefix: str) -> Optional[SPFRoute]:
        """Get route for specific prefix"""
        return self.routing_table.get(prefix)

    def get_all_routes(self) -> List[SPFRoute]:
        """Get all computed routes"""
        return list(self.routing_table.values())

    def get_statistics(self) -> Dict[str, Any]:
        """Get SPF statistics"""
        avg_time = 0
        if self._spf_runs > 0:
            avg_time = self._total_spf_time_ms / self._spf_runs

        return {
            "level": self.lsdb.level,
            "spf_runs": self._spf_runs,
            "total_routes": len(self.routing_table),
            "average_spf_time_ms": round(avg_time, 2),
            "last_spf_time": self._last_spf_time.isoformat() if self._last_spf_time else None,
            "spf_pending": self._spf_pending,
        }


class DualSPFCalculator:
    """
    Manages SPF calculation for both L1 and L2.
    """

    def __init__(
        self,
        system_id: str,
        dual_lsdb: DualLSDB,
    ):
        """
        Initialize dual SPF calculator.

        Args:
            system_id: Local router's system ID
            dual_lsdb: Dual-level LSDB
        """
        self.system_id = system_id
        self.dual_lsdb = dual_lsdb

        self.l1_spf: Optional[ISISSPFCalculator] = None
        self.l2_spf: Optional[ISISSPFCalculator] = None

        if dual_lsdb.l1_lsdb:
            self.l1_spf = ISISSPFCalculator(system_id, dual_lsdb.l1_lsdb)

        if dual_lsdb.l2_lsdb:
            self.l2_spf = ISISSPFCalculator(system_id, dual_lsdb.l2_lsdb)

        self.logger = logging.getLogger("DualSPF")

    def schedule_spf(self, level: int) -> None:
        """Schedule SPF for specific level"""
        if level == LEVEL_1 and self.l1_spf:
            self.l1_spf.schedule_spf()
        elif level == LEVEL_2 and self.l2_spf:
            self.l2_spf.schedule_spf()

    def get_combined_routing_table(self) -> Dict[str, SPFRoute]:
        """
        Get combined routing table from L1 and L2.

        L1 routes are preferred over L2 for intra-area destinations.
        """
        routes = {}

        # Add L2 routes first (lower priority)
        if self.l2_spf:
            routes.update(self.l2_spf.routing_table)

        # Add L1 routes (override L2 for same prefix)
        if self.l1_spf:
            routes.update(self.l1_spf.routing_table)

        return routes

    def get_statistics(self) -> Dict[str, Any]:
        """Get combined statistics"""
        stats = {"system_id": self.system_id}

        if self.l1_spf:
            stats["level_1"] = self.l1_spf.get_statistics()

        if self.l2_spf:
            stats["level_2"] = self.l2_spf.get_statistics()

        return stats
