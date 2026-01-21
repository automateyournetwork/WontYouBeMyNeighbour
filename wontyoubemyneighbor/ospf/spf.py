"""
OSPF SPF (Shortest Path First) Calculation
RFC 2328 Section 16 - Calculation of the routing table
Uses Dijkstra's algorithm
"""

import logging
from typing import Dict, List, Optional
import networkx as nx
from ospf.lsdb import LinkStateDatabase, LSA
from ospf.constants import (
    ROUTER_LSA, NETWORK_LSA, AS_EXTERNAL_LSA, NSSA_EXTERNAL_LSA,
    SUMMARY_LSA_NETWORK, SUMMARY_LSA_ASBR,
    LINK_TYPE_PTP, LINK_TYPE_TRANSIT, LINK_TYPE_STUB
)

logger = logging.getLogger(__name__)


class RouteEntry:
    """
    Routing table entry
    """

    def __init__(self, destination: str, cost: int, next_hop: Optional[str], path: List[str]):
        """
        Initialize route entry

        Args:
            destination: Destination network/router
            cost: Total path cost
            next_hop: Next hop router ID or IP
            path: Full path to destination
        """
        self.destination = destination
        self.cost = cost
        self.next_hop = next_hop
        self.path = path

    def __repr__(self) -> str:
        return (f"Route(dest={self.destination}, "
                f"cost={self.cost}, "
                f"next_hop={self.next_hop})")


class SPFCalculator:
    """
    Calculate shortest path first using Dijkstra's algorithm
    RFC 2328 Section 16
    """

    def __init__(self, router_id: str, lsdb: LinkStateDatabase):
        """
        Initialize SPF calculator

        Args:
            router_id: This router's ID
            lsdb: Link State Database
        """
        self.router_id = router_id
        self.lsdb = lsdb
        self.routing_table: Dict[str, RouteEntry] = {}
        self.graph: Optional[nx.Graph] = None

        logger.info(f"Initialized SPF calculator for {router_id}")

    def calculate(self) -> Dict[str, RouteEntry]:
        """
        Run SPF algorithm and build routing table

        Returns:
            Dictionary of destination -> RouteEntry
        """
        logger.info(f"Starting SPF calculation for {self.router_id}")

        # Step 1: Build network graph from LSDB
        self.graph = self._build_graph()

        if not self.graph or self.router_id not in self.graph:
            logger.warning("Cannot run SPF - router not in graph")
            return {}

        # Step 2: Run Dijkstra from our router
        try:
            shortest_paths = nx.single_source_dijkstra_path(
                self.graph, self.router_id, weight='weight'
            )
            shortest_costs = nx.single_source_dijkstra_path_length(
                self.graph, self.router_id, weight='weight'
            )
        except Exception as e:
            logger.error(f"Dijkstra calculation failed: {e}")
            return {}

        # Step 3: Build routing table from shortest paths
        self.routing_table.clear()

        for dest, cost in shortest_costs.items():
            if dest == self.router_id:
                continue  # Skip self

            path = shortest_paths.get(dest, [])

            # Determine next hop
            if len(path) > 1:
                next_hop = path[1]  # Second node in path
            else:
                next_hop = None

            self.routing_table[dest] = RouteEntry(
                destination=dest,
                cost=cost,
                next_hop=next_hop,
                path=path
            )

        # Step 4: Process Summary LSAs (Type 3/4) - RFC 2328 Section 16.2/16.3
        # Inter-area routes from ABRs
        self._process_summary_lsas(shortest_costs)

        # Step 5: Process External LSAs (Type 5) - RFC 2328 Section 16.4
        # External routes are added AFTER SPF tree is computed
        self._process_external_lsas(shortest_costs)

        # Step 6: Process NSSA External LSAs (Type 7) - RFC 3101
        # NSSA external routes within Not-So-Stubby Areas
        self._process_nssa_lsas(shortest_costs)

        logger.info(f"SPF calculation complete: {len(self.routing_table)} routes")
        return self.routing_table

    def _process_summary_lsas(self, shortest_costs: Dict[str, int]):
        """
        Process Summary LSAs (Type 3 and Type 4) for inter-area routes.

        Per RFC 2328 Section 16.2/16.3:
        - Type 3: Summary LSA for network routes from other areas
        - Type 4: ASBR Summary LSA for path to ASBRs in other areas

        The cost to an inter-area destination is:
        cost_to_ABR + summary_metric

        Args:
            shortest_costs: Dictionary of router_id -> cost from SPF
        """
        summary_lsas = self.lsdb.get_summary_lsas()

        if not summary_lsas:
            return

        logger.debug(f"Processing {len(summary_lsas)} Summary LSAs")

        for lsa in summary_lsas:
            try:
                # Get summary route details from LSA
                abr_id = lsa.header.advertising_router
                ls_type = lsa.header.ls_type
                destination = lsa.header.link_state_id

                # Skip if we can't reach the ABR
                if abr_id not in shortest_costs and abr_id != self.router_id:
                    logger.debug(f"Cannot reach ABR {abr_id} for summary route {destination}")
                    continue

                # Skip if this is from ourselves (we're the ABR)
                if abr_id == self.router_id:
                    continue

                # Get summary metric from LSA body
                if not lsa.body:
                    continue

                summary_metric = lsa.body.metric
                network_mask = lsa.body.network_mask

                # Calculate cost to ABR
                cost_to_abr = shortest_costs.get(abr_id, float('inf'))

                # Total cost = cost_to_ABR + summary_metric
                total_cost = cost_to_abr + summary_metric

                # Handle Type 3 (Network Summary) vs Type 4 (ASBR Summary)
                if ls_type == SUMMARY_LSA_NETWORK:
                    # Type 3: Inter-area network route
                    prefix = self._build_prefix(destination, network_mask)
                elif ls_type == SUMMARY_LSA_ASBR:
                    # Type 4: ASBR Summary - adds path to ASBR in another area
                    # This is used for external route calculation
                    prefix = destination  # ASBR router ID
                else:
                    continue

                # Determine next hop (same as path to ABR)
                if abr_id in self.routing_table:
                    next_hop = self.routing_table[abr_id].next_hop
                else:
                    next_hop = abr_id

                # Only add if we don't have a better intra-area route
                if prefix not in self.routing_table:
                    self.routing_table[prefix] = RouteEntry(
                        destination=prefix,
                        cost=total_cost,
                        next_hop=next_hop,
                        path=[self.router_id, abr_id] if abr_id != self.router_id else [self.router_id]
                    )
                    route_type = "IA" if ls_type == SUMMARY_LSA_NETWORK else "ASBR"
                    logger.debug(f"Added {route_type} route: {prefix} via {next_hop} (cost={total_cost})")

            except Exception as e:
                logger.warning(f"Error processing Summary LSA: {e}")

    def _process_external_lsas(self, shortest_costs: Dict[str, int]):
        """
        Process AS External LSAs (Type 5) and add external routes.

        Per RFC 2328 Section 16.4, external routes are calculated after
        the SPF tree is built. The cost to an external destination is:
        - Type 1: cost_to_ASBR + external_metric
        - Type 2: external_metric (ASBR cost used only as tiebreaker)

        Args:
            shortest_costs: Dictionary of router_id -> cost from SPF
        """
        external_lsas = self.lsdb.get_external_lsas()

        if not external_lsas:
            return

        logger.debug(f"Processing {len(external_lsas)} External LSAs")

        for lsa in external_lsas:
            try:
                # Get external route details from LSA
                asbr_id = lsa.header.advertising_router
                network = lsa.header.link_state_id

                # Skip if we can't reach the ASBR
                if asbr_id not in shortest_costs and asbr_id != self.router_id:
                    logger.debug(f"Cannot reach ASBR {asbr_id} for external route {network}")
                    continue

                # Get external metric from LSA body
                if not lsa.body:
                    continue

                external_metric = lsa.body.metric
                network_mask = lsa.body.network_mask
                e_bit = getattr(lsa.body, 'e_bit', 1)  # Default to Type 2

                # Calculate cost to ASBR
                if asbr_id == self.router_id:
                    cost_to_asbr = 0
                else:
                    cost_to_asbr = shortest_costs.get(asbr_id, float('inf'))

                # Calculate total cost based on external type
                if e_bit == 0:
                    # Type 1 external: cost = cost_to_ASBR + external_metric
                    total_cost = cost_to_asbr + external_metric
                else:
                    # Type 2 external: cost = external_metric (ASBR cost as tiebreaker)
                    total_cost = external_metric

                # Build prefix with mask
                prefix = self._build_prefix(network, network_mask)

                # Determine next hop
                if asbr_id == self.router_id:
                    next_hop = None  # Local route
                elif asbr_id in self.routing_table:
                    next_hop = self.routing_table[asbr_id].next_hop
                else:
                    next_hop = asbr_id

                # Add to routing table (external routes have lower preference)
                # Only add if we don't have a better internal route
                if prefix not in self.routing_table:
                    self.routing_table[prefix] = RouteEntry(
                        destination=prefix,
                        cost=total_cost,
                        next_hop=next_hop,
                        path=[self.router_id, asbr_id] if asbr_id != self.router_id else [self.router_id]
                    )
                    logger.debug(f"Added external route: {prefix} via {next_hop} (cost={total_cost}, type={'E1' if e_bit == 0 else 'E2'})")

            except Exception as e:
                logger.warning(f"Error processing External LSA: {e}")

    def _process_nssa_lsas(self, shortest_costs: Dict[str, int]):
        """
        Process NSSA External LSAs (Type 7) per RFC 3101.

        NSSA External LSAs are similar to AS External LSAs but are
        flooded only within the NSSA. They are converted to Type 5
        at the NSSA ABR for flooding to other areas.

        Args:
            shortest_costs: Dictionary of router_id -> cost from SPF
        """
        nssa_lsas = self.lsdb.get_nssa_lsas()

        if not nssa_lsas:
            return

        logger.debug(f"Processing {len(nssa_lsas)} NSSA External LSAs")

        for lsa in nssa_lsas:
            try:
                # Get NSSA route details from LSA
                asbr_id = lsa.header.advertising_router
                network = lsa.header.link_state_id

                # Skip if we can't reach the ASBR
                if asbr_id not in shortest_costs and asbr_id != self.router_id:
                    logger.debug(f"Cannot reach ASBR {asbr_id} for NSSA route {network}")
                    continue

                # Get external metric from LSA body
                if not lsa.body:
                    continue

                external_metric = lsa.body.metric
                network_mask = lsa.body.network_mask
                e_bit = getattr(lsa.body, 'e_bit', 1)

                # Calculate cost to ASBR
                if asbr_id == self.router_id:
                    cost_to_asbr = 0
                else:
                    cost_to_asbr = shortest_costs.get(asbr_id, float('inf'))

                # Calculate total cost based on external type
                if e_bit == 0:
                    # N1: cost = cost_to_ASBR + external_metric
                    total_cost = cost_to_asbr + external_metric
                else:
                    # N2: cost = external_metric
                    total_cost = external_metric

                # Build prefix with mask
                prefix = self._build_prefix(network, network_mask)

                # Determine next hop
                if asbr_id == self.router_id:
                    next_hop = None
                elif asbr_id in self.routing_table:
                    next_hop = self.routing_table[asbr_id].next_hop
                else:
                    next_hop = asbr_id

                # NSSA routes have lower priority than Type 5 external routes
                # Only add if we don't have a better route
                if prefix not in self.routing_table:
                    self.routing_table[prefix] = RouteEntry(
                        destination=prefix,
                        cost=total_cost,
                        next_hop=next_hop,
                        path=[self.router_id, asbr_id] if asbr_id != self.router_id else [self.router_id]
                    )
                    logger.debug(f"Added NSSA route: {prefix} via {next_hop} (cost={total_cost}, type={'N1' if e_bit == 0 else 'N2'})")

            except Exception as e:
                logger.warning(f"Error processing NSSA LSA: {e}")

    def _build_prefix(self, network: str, mask: str) -> str:
        """
        Build prefix string from network and mask.

        Args:
            network: Network address (e.g., "10.0.0.0")
            mask: Network mask (e.g., "255.0.0.0")

        Returns:
            Prefix string (e.g., "10.0.0.0/8")
        """
        try:
            # Convert mask to prefix length
            mask_octets = [int(o) for o in mask.split('.')]
            mask_int = (mask_octets[0] << 24) + (mask_octets[1] << 16) + (mask_octets[2] << 8) + mask_octets[3]
            prefix_len = bin(mask_int).count('1')
            return f"{network}/{prefix_len}"
        except Exception:
            return network

    def _build_graph(self) -> nx.Graph:
        """
        Build network graph from LSAs in LSDB

        Returns:
            NetworkX graph
        """
        graph = nx.Graph()

        # Process all LSAs
        for lsa in self.lsdb.get_all_lsas():
            if lsa.header.ls_type == ROUTER_LSA:
                self._process_router_lsa(graph, lsa)
            elif lsa.header.ls_type == NETWORK_LSA:
                self._process_network_lsa(graph, lsa)

        logger.debug(f"Built graph: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
        return graph

    def _process_router_lsa(self, graph: nx.Graph, lsa: LSA):
        """
        Add router and its links to graph

        Args:
            graph: NetworkX graph
            lsa: Router LSA
        """
        router_id = lsa.header.advertising_router

        # Add router node
        if router_id not in graph:
            graph.add_node(router_id)

        # Process links if we have the body
        if not lsa.body:
            return

        logger.debug(f"Processing {len(lsa.body.links)} links from Router LSA {router_id}")
        for link in lsa.body.links:
            logger.debug(f"  Link: type={link.link_type}, id={link.link_id}, data={link.link_data}, metric={link.metric}")
            if link.link_type == LINK_TYPE_PTP:
                # Point-to-point link to another router
                neighbor_id = link.link_id
                cost = link.metric

                # Add edge between routers
                if neighbor_id not in graph:
                    graph.add_node(neighbor_id)

                graph.add_edge(router_id, neighbor_id, weight=cost)
                logger.debug(f"Added P2P link: {router_id} <-> {neighbor_id} (cost={cost})")

            elif link.link_type == LINK_TYPE_TRANSIT:
                # Transit network (has DR)
                network_id = link.link_id
                cost = link.metric

                # Add network node
                if network_id not in graph:
                    graph.add_node(network_id)

                # Connect router to network
                graph.add_edge(router_id, network_id, weight=cost)
                logger.debug(f"Added transit link: {router_id} -> {network_id} (cost={cost})")

            elif link.link_type == LINK_TYPE_STUB:
                # Stub network (no further routing)
                network_id = link.link_id
                cost = link.metric

                # Add stub network node
                if network_id not in graph:
                    graph.add_node(network_id)

                graph.add_edge(router_id, network_id, weight=cost)
                logger.debug(f"Added stub link: {router_id} -> {network_id} (cost={cost})")

    def _process_network_lsa(self, graph: nx.Graph, lsa: LSA):
        """
        Add transit network to graph

        Args:
            graph: NetworkX graph
            lsa: Network LSA
        """
        network_id = lsa.header.link_state_id

        # Add network node
        if network_id not in graph:
            graph.add_node(network_id)

        # Process attached routers if we have the body
        if not lsa.body:
            return

        # Connect all attached routers to network with cost 0
        for router_id in lsa.body.attached_routers:
            if router_id not in graph:
                graph.add_node(router_id)

            if not graph.has_edge(network_id, router_id):
                graph.add_edge(network_id, router_id, weight=0)
                logger.debug(f"Added network link: {network_id} <-> {router_id}")

    def get_route(self, destination: str) -> Optional[RouteEntry]:
        """
        Get route to specific destination

        Args:
            destination: Destination router ID or network

        Returns:
            RouteEntry or None if not found
        """
        return self.routing_table.get(destination)

    def get_all_routes(self) -> Dict[str, RouteEntry]:
        """
        Get all routes

        Returns:
            Dictionary of destination -> RouteEntry
        """
        return self.routing_table.copy()

    def print_routing_table(self):
        """
        Print routing table in human-readable format
        """
        print(f"\n{'='*70}")
        print(f"Routing Table for {self.router_id}")
        print(f"{'='*70}")
        print(f"{'Destination':<30} {'Cost':<10} {'Next Hop':<30}")
        print(f"{'-'*70}")

        if not self.routing_table:
            print("(empty)")
        else:
            for dest, entry in sorted(self.routing_table.items()):
                next_hop_str = entry.next_hop or "local"
                print(f"{dest:<30} {entry.cost:<10} {next_hop_str:<30}")

        print(f"{'='*70}\n")

    def get_statistics(self) -> Dict[str, int]:
        """
        Get SPF statistics

        Returns:
            Dictionary with statistics
        """
        stats = {
            'routes': len(self.routing_table),
            'nodes': self.graph.number_of_nodes() if self.graph else 0,
            'edges': self.graph.number_of_edges() if self.graph else 0,
            'lsas': self.lsdb.get_size()
        }
        return stats

    def __repr__(self) -> str:
        return f"SPFCalculator(router_id={self.router_id}, routes={len(self.routing_table)})"
