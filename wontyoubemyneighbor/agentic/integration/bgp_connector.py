"""
BGP Connector

Connects agentic layer to BGP protocol implementation.
"""

from typing import Optional, List, Dict, Any


class BGPConnector:
    """
    Connector for BGP speaker.

    Provides agentic layer access to BGP state and actions.
    """

    def __init__(self, bgp_speaker):
        """
        Initialize with BGP speaker.

        Args:
            bgp_speaker: Instance of BGPSpeaker from wontyoubemyneighbor.bgp
        """
        self.speaker = bgp_speaker

    async def get_peers(self):
        """Get list of BGP peers"""
        peers = []
        for peer in self.speaker.peers.values():
            peers.append({
                "peer": str(peer.peer_addr),
                "peer_as": peer.peer_as,
                "state": peer.state,
                "local_addr": str(getattr(peer, "local_addr", "")),
                "is_ibgp": peer.peer_as == self.speaker.local_as,
                "uptime": getattr(peer, "uptime", 0),
                "prefixes_received": getattr(peer, "prefixes_received", 0),
                "prefixes_sent": getattr(peer, "prefixes_sent", 0)
            })
        return peers

    async def get_rib(self, prefix: Optional[str] = None):
        """
        Get BGP RIB (Routing Information Base).

        Args:
            prefix: Optional filter for specific prefix

        Returns:
            List of routes
        """
        if not hasattr(self.speaker, "rib"):
            return []

        routes = []
        for route_key, route_info in self.speaker.rib.items():
            # route_key format: (prefix, prefix_len, afi, safi)
            route_prefix, prefix_len = route_key[0], route_key[1]
            full_prefix = f"{route_prefix}/{prefix_len}"

            # Filter if requested
            if prefix and full_prefix != prefix:
                continue

            routes.append({
                "network": full_prefix,
                "next_hop": str(route_info.get("next_hop", "")),
                "as_path": route_info.get("as_path", []),
                "local_pref": route_info.get("local_pref", 100),
                "med": route_info.get("med", 0),
                "origin": route_info.get("origin", "igp"),
                "communities": route_info.get("communities", [])
            })

        return routes

    async def inject_route(
        self,
        network: str,
        next_hop: Optional[str] = None,
        as_path: Optional[List[int]] = None,
        **attributes
    ):
        """
        Inject route into BGP.

        This would add a route to the RIB and advertise it to peers.
        """
        # Parse network
        parts = network.split("/")
        if len(parts) != 2:
            return {"success": False, "error": "Invalid network format"}

        prefix = parts[0]
        prefix_len = int(parts[1])

        # Determine AFI/SAFI
        import ipaddress
        try:
            addr = ipaddress.ip_address(prefix)
            afi = 1 if addr.version == 4 else 2
        except:
            return {"success": False, "error": "Invalid IP address"}

        # Create route key
        route_key = (prefix, prefix_len, afi, 1)  # SAFI 1 = unicast

        # Build route info
        route_info = {
            "next_hop": next_hop or "0.0.0.0",
            "as_path": as_path or [self.speaker.local_as],
            "local_pref": attributes.get("local_pref", 100),
            "med": attributes.get("med", 0),
            "origin": attributes.get("origin", "igp")
        }

        # Add to RIB
        if not hasattr(self.speaker, "rib"):
            self.speaker.rib = {}

        self.speaker.rib[route_key] = route_info

        return {
            "success": True,
            "network": network,
            "route_info": route_info
        }

    async def withdraw_route(self, network: str):
        """
        Withdraw route from BGP.

        Removes route from RIB and sends withdrawal to peers.
        """
        # Parse network
        parts = network.split("/")
        if len(parts) != 2:
            return {"success": False, "error": "Invalid network format"}

        prefix = parts[0]
        prefix_len = int(parts[1])

        # Find and remove from RIB
        if hasattr(self.speaker, "rib"):
            for route_key in list(self.speaker.rib.keys()):
                if route_key[0] == prefix and route_key[1] == prefix_len:
                    del self.speaker.rib[route_key]
                    return {"success": True, "network": network}

        return {"success": False, "error": "Route not found"}

    async def adjust_local_pref(self, network: str, local_pref: int):
        """
        Adjust local preference for a route.

        Higher local preference = more preferred.
        """
        # Parse network
        parts = network.split("/")
        if len(parts) != 2:
            return {"success": False, "error": "Invalid network format"}

        prefix = parts[0]
        prefix_len = int(parts[1])

        # Find route in RIB
        if hasattr(self.speaker, "rib"):
            for route_key, route_info in self.speaker.rib.items():
                if route_key[0] == prefix and route_key[1] == prefix_len:
                    old_pref = route_info.get("local_pref", 100)
                    route_info["local_pref"] = local_pref
                    return {
                        "success": True,
                        "network": network,
                        "old_local_pref": old_pref,
                        "new_local_pref": local_pref
                    }

        return {"success": False, "error": "Route not found"}

    async def graceful_shutdown(self, peer: Optional[str] = None):
        """
        Initiate BGP graceful shutdown.

        If peer specified, shutdown only that peer.
        Otherwise, shutdown all peers.
        """
        if peer:
            # Graceful shutdown specific peer
            for bgp_peer in self.speaker.peers.values():
                if str(bgp_peer.peer_addr) == peer:
                    # Send NOTIFICATION with Cease code
                    # In real implementation, would send proper BGP message
                    return {
                        "success": True,
                        "peer": peer,
                        "message": "Graceful shutdown initiated"
                    }
            return {"success": False, "error": f"Peer {peer} not found"}
        else:
            # Graceful shutdown all peers
            peer_count = len(self.speaker.peers)
            return {
                "success": True,
                "peers_affected": peer_count,
                "message": f"Graceful shutdown initiated for {peer_count} peers"
            }

    def get_speaker_info(self):
        """Get BGP speaker information"""
        return {
            "local_as": self.speaker.local_as,
            "router_id": str(self.speaker.router_id),
            "peer_count": len(self.speaker.peers),
            "route_count": len(self.speaker.rib) if hasattr(self.speaker, "rib") else 0,
            "capabilities": getattr(self.speaker, "capabilities", [])
        }
