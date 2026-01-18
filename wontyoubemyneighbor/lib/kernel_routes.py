"""
Kernel Routing Table Management

Installs routes from routing protocols (OSPF, BGP) into the Linux kernel
routing table for actual packet forwarding.
"""

import subprocess
import logging
import asyncio
from typing import Optional, List


class KernelRouteManager:
    """
    Manages installation of routes into Linux kernel routing table
    """

    def __init__(self):
        self.logger = logging.getLogger("KernelRoutes")
        self.installed_routes = {}  # prefix -> next_hop
        self.forwarding_enabled = False
        self.last_forward_stats = {}  # Track forwarding counters

    def install_route(self, prefix: str, next_hop: str, metric: int = 100,
                     protocol: str = "static") -> bool:
        """
        Install route into kernel routing table

        Args:
            prefix: Route prefix (e.g., "10.10.10.1/32")
            next_hop: Next-hop IP address
            metric: Route metric/preference
            protocol: Source protocol (ospf, bgp, static)

        Returns:
            True if successful, False otherwise
        """
        try:
            # Check if route already installed with same next-hop
            if prefix in self.installed_routes:
                if self.installed_routes[prefix] == next_hop:
                    self.logger.debug(f"Route {prefix} via {next_hop} already installed")
                    return True
                else:
                    # Next-hop changed, remove old route first
                    self.remove_route(prefix)

            # Build ip route command
            cmd = ["ip", "route", "add", prefix, "via", next_hop, "metric", str(metric)]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)

            if result.returncode == 0:
                self.installed_routes[prefix] = next_hop
                self.logger.info(f"✓ Installed kernel route: {prefix} via {next_hop} ({protocol})")
                return True
            elif "File exists" in result.stderr:
                # Route already exists (maybe from another process)
                self.installed_routes[prefix] = next_hop
                self.logger.debug(f"Route {prefix} already exists in kernel")
                return True
            else:
                self.logger.warning(f"Failed to install route {prefix}: {result.stderr.strip()}")
                return False

        except subprocess.TimeoutExpired:
            self.logger.error(f"Timeout installing route {prefix}")
            return False
        except Exception as e:
            self.logger.error(f"Error installing route {prefix}: {e}")
            return False

    def remove_route(self, prefix: str) -> bool:
        """
        Remove route from kernel routing table

        Args:
            prefix: Route prefix to remove

        Returns:
            True if successful, False otherwise
        """
        try:
            cmd = ["ip", "route", "del", prefix]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)

            if result.returncode == 0:
                if prefix in self.installed_routes:
                    del self.installed_routes[prefix]
                self.logger.info(f"✓ Removed kernel route: {prefix}")
                return True
            elif "No such process" in result.stderr or "not found" in result.stderr:
                # Route doesn't exist
                if prefix in self.installed_routes:
                    del self.installed_routes[prefix]
                return True
            else:
                self.logger.warning(f"Failed to remove route {prefix}: {result.stderr.strip()}")
                return False

        except Exception as e:
            self.logger.error(f"Error removing route {prefix}: {e}")
            return False

    def get_installed_routes(self) -> List[str]:
        """Get list of prefixes installed in kernel"""
        return list(self.installed_routes.keys())

    def clear_all_routes(self):
        """Remove all routes managed by this instance"""
        prefixes = list(self.installed_routes.keys())
        for prefix in prefixes:
            self.remove_route(prefix)

    def setup_forwarding_logging(self, specific_prefixes: Optional[List[str]] = None):
        """
        Setup iptables rules to log packet forwarding

        Args:
            specific_prefixes: Optional list of prefixes to log (e.g., ["10.10.10.1/32", "20.20.20.1/32"])
        """
        try:
            # Clear any existing FORWARD logging rules
            subprocess.run(["iptables", "-D", "FORWARD", "-j", "LOG"],
                          capture_output=True, stderr=subprocess.DEVNULL)

            if specific_prefixes:
                # Log forwarding to specific destinations
                for prefix in specific_prefixes:
                    # Log packets TO this destination
                    cmd = ["iptables", "-A", "FORWARD", "-d", prefix,
                           "-j", "LOG", "--log-prefix", f"FWD→{prefix}: ", "--log-level", "6"]
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    if result.returncode == 0:
                        self.logger.info(f"✓ Logging forwarding to {prefix}")

                    # Log packets FROM this destination (replies)
                    cmd = ["iptables", "-A", "FORWARD", "-s", prefix,
                           "-j", "LOG", "--log-prefix", f"FWD←{prefix}: ", "--log-level", "6"]
                    subprocess.run(cmd, capture_output=True, text=True)
            else:
                # Log all forwarding
                cmd = ["iptables", "-A", "FORWARD", "-j", "LOG",
                       "--log-prefix", "FORWARD: ", "--log-level", "6"]
                result = subprocess.run(cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    self.logger.info("✓ Logging all packet forwarding")

            self.forwarding_enabled = True

        except Exception as e:
            self.logger.warning(f"Could not setup forwarding logging: {e}")

    def get_forwarding_stats(self):
        """
        Get packet forwarding statistics from kernel

        Returns:
            Dict with forwarding stats
        """
        try:
            # Get iptables FORWARD chain stats
            result = subprocess.run(["iptables", "-L", "FORWARD", "-v", "-n", "-x"],
                                   capture_output=True, text=True, timeout=5)

            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                stats = {'total_packets': 0, 'total_bytes': 0}

                for line in lines[2:]:  # Skip header lines
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 2:
                            try:
                                packets = int(parts[0])
                                bytes_val = int(parts[1])
                                stats['total_packets'] += packets
                                stats['total_bytes'] += bytes_val
                            except (ValueError, IndexError):
                                continue

                return stats

        except Exception as e:
            self.logger.debug(f"Error getting forwarding stats: {e}")

        return {'total_packets': 0, 'total_bytes': 0}

    async def monitor_forwarding(self, interval: int = 30):
        """
        Periodically log forwarding statistics

        Args:
            interval: Check interval in seconds
        """
        self.logger.info(f"Starting forwarding monitor (interval: {interval}s)")

        while True:
            await asyncio.sleep(interval)

            try:
                stats = self.get_forwarding_stats()

                # Calculate delta since last check
                if self.last_forward_stats:
                    delta_pkts = stats['total_packets'] - self.last_forward_stats.get('total_packets', 0)
                    delta_bytes = stats['total_bytes'] - self.last_forward_stats.get('total_bytes', 0)

                    if delta_pkts > 0:
                        self.logger.info(f"📦 Forwarded {delta_pkts} packets ({delta_bytes} bytes) in last {interval}s")
                        self.logger.info(f"   Total forwarded: {stats['total_packets']} packets ({stats['total_bytes']} bytes)")

                self.last_forward_stats = stats

            except Exception as e:
                self.logger.error(f"Error monitoring forwarding: {e}")
