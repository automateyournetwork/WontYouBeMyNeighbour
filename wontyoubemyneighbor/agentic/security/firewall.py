"""
Firewall and ACL Management

Provides firewall and access control list capabilities for agents.
Supports both iptables-style rules and Cisco-style ACLs.

Features:
- Standard and Extended ACLs
- Firewall rules per interface (inbound/outbound)
- Protocol filtering (TCP, UDP, ICMP, etc.)
- Port-based filtering
- Packet counters and statistics
- Rule ordering and priorities
- Enable/disable rules without deletion
"""

import asyncio
import logging
import subprocess
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from datetime import datetime
import time
import ipaddress

logger = logging.getLogger("Firewall")

# Singleton manager instance
_firewall_manager: Optional["FirewallManager"] = None


class FirewallAction(Enum):
    """Firewall rule actions"""
    PERMIT = "permit"
    DENY = "deny"
    DROP = "drop"      # Silent drop (no ICMP response)
    REJECT = "reject"  # Drop with ICMP response
    LOG = "log"        # Log and continue
    LOG_DROP = "log_drop"  # Log then drop


class Protocol(Enum):
    """Network protocols for filtering"""
    ANY = "any"
    TCP = "tcp"
    UDP = "udp"
    ICMP = "icmp"
    ICMPV6 = "icmpv6"
    GRE = "gre"
    ESP = "esp"
    AH = "ah"
    OSPF = "ospf"
    EIGRP = "eigrp"
    VRRP = "vrrp"
    PIM = "pim"


class Direction(Enum):
    """Traffic direction"""
    INBOUND = "in"
    OUTBOUND = "out"
    BOTH = "both"


class FirewallChain(Enum):
    """iptables chains"""
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"
    FORWARD = "FORWARD"
    PREROUTING = "PREROUTING"
    POSTROUTING = "POSTROUTING"


@dataclass
class RuleStatistics:
    """Statistics for a firewall rule"""
    packets_matched: int = 0
    bytes_matched: int = 0
    last_hit: Optional[float] = None
    hit_rate_per_second: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "packets_matched": self.packets_matched,
            "bytes_matched": self.bytes_matched,
            "last_hit": datetime.fromtimestamp(self.last_hit).isoformat() if self.last_hit else None,
            "hit_rate_per_second": round(self.hit_rate_per_second, 2)
        }


@dataclass
class ACLEntry:
    """
    A single ACL entry (Access Control Entry - ACE).

    Represents one line in an ACL with match criteria and action.
    """
    # Identity
    sequence: int  # Rule sequence number (for ordering)
    name: str = ""  # Optional description

    # Action
    action: FirewallAction = FirewallAction.PERMIT

    # Source matching
    source_ip: str = "any"  # IP/network or "any"
    source_wildcard: str = ""  # Wildcard mask (Cisco-style)
    source_port: Optional[str] = None  # Port or range (e.g., "80", "1024-65535")
    source_port_operator: str = "eq"  # eq, neq, gt, lt, range

    # Destination matching
    dest_ip: str = "any"
    dest_wildcard: str = ""
    dest_port: Optional[str] = None
    dest_port_operator: str = "eq"

    # Protocol
    protocol: Protocol = Protocol.ANY

    # Additional options
    established: bool = False  # Match established connections only
    log: bool = False  # Log matching packets
    enabled: bool = True

    # Statistics
    statistics: RuleStatistics = field(default_factory=RuleStatistics)

    # Timestamps
    created_at: float = field(default_factory=time.time)
    modified_at: float = field(default_factory=time.time)

    def matches(self, src_ip: str, dst_ip: str, proto: str, src_port: int, dst_port: int) -> bool:
        """Check if this rule matches the given packet parameters"""
        if not self.enabled:
            return False

        # Protocol check
        if self.protocol != Protocol.ANY:
            if self.protocol.value.lower() != proto.lower():
                return False

        # Source IP check
        if self.source_ip != "any":
            if not self._ip_matches(src_ip, self.source_ip, self.source_wildcard):
                return False

        # Destination IP check
        if self.dest_ip != "any":
            if not self._ip_matches(dst_ip, self.dest_ip, self.dest_wildcard):
                return False

        # Source port check
        if self.source_port and src_port:
            if not self._port_matches(src_port, self.source_port, self.source_port_operator):
                return False

        # Destination port check
        if self.dest_port and dst_port:
            if not self._port_matches(dst_port, self.dest_port, self.dest_port_operator):
                return False

        return True

    def _ip_matches(self, ip: str, match_ip: str, wildcard: str) -> bool:
        """Check if IP matches with optional wildcard"""
        try:
            if "/" in match_ip:
                # CIDR notation
                network = ipaddress.ip_network(match_ip, strict=False)
                return ipaddress.ip_address(ip) in network
            elif wildcard:
                # Wildcard mask (invert for netmask)
                # Simplified check - convert to network
                ip_int = int(ipaddress.ip_address(ip))
                match_int = int(ipaddress.ip_address(match_ip))
                wild_int = int(ipaddress.ip_address(wildcard))
                return (ip_int & ~wild_int) == (match_int & ~wild_int)
            else:
                return ip == match_ip
        except Exception:
            return False

    def _port_matches(self, port: int, match_port: str, operator: str) -> bool:
        """Check if port matches with operator"""
        try:
            if "-" in match_port:
                # Range
                start, end = match_port.split("-")
                return int(start) <= port <= int(end)
            else:
                match_p = int(match_port)
                if operator == "eq":
                    return port == match_p
                elif operator == "neq":
                    return port != match_p
                elif operator == "gt":
                    return port > match_p
                elif operator == "lt":
                    return port < match_p
                return port == match_p
        except Exception:
            return False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sequence": self.sequence,
            "name": self.name,
            "action": self.action.value,
            "source_ip": self.source_ip,
            "source_wildcard": self.source_wildcard,
            "source_port": self.source_port,
            "dest_ip": self.dest_ip,
            "dest_wildcard": self.dest_wildcard,
            "dest_port": self.dest_port,
            "protocol": self.protocol.value,
            "established": self.established,
            "log": self.log,
            "enabled": self.enabled,
            "statistics": self.statistics.to_dict(),
            "created_at": datetime.fromtimestamp(self.created_at).isoformat(),
            "modified_at": datetime.fromtimestamp(self.modified_at).isoformat()
        }

    def to_cisco_format(self) -> str:
        """Format as Cisco IOS ACL syntax"""
        parts = [str(self.sequence), self.action.value]

        if self.protocol != Protocol.ANY:
            parts.append(self.protocol.value)
        else:
            parts.append("ip")

        # Source
        if self.source_ip == "any":
            parts.append("any")
        else:
            parts.append(self.source_ip)
            if self.source_wildcard:
                parts.append(self.source_wildcard)

        if self.source_port:
            parts.extend([self.source_port_operator, self.source_port])

        # Destination
        if self.dest_ip == "any":
            parts.append("any")
        else:
            parts.append(self.dest_ip)
            if self.dest_wildcard:
                parts.append(self.dest_wildcard)

        if self.dest_port:
            parts.extend([self.dest_port_operator, self.dest_port])

        if self.established:
            parts.append("established")
        if self.log:
            parts.append("log")

        return " ".join(parts)

    def to_iptables_format(self, chain: str = "INPUT") -> str:
        """Format as iptables rule"""
        parts = ["-A", chain]

        # Protocol
        if self.protocol != Protocol.ANY:
            parts.extend(["-p", self.protocol.value])

        # Source
        if self.source_ip != "any":
            if self.source_wildcard:
                # Convert wildcard to CIDR (simplified)
                parts.extend(["-s", self.source_ip])
            else:
                parts.extend(["-s", self.source_ip])

        if self.source_port:
            parts.extend(["--sport", self.source_port])

        # Destination
        if self.dest_ip != "any":
            parts.extend(["-d", self.dest_ip])

        if self.dest_port:
            parts.extend(["--dport", self.dest_port])

        # Established
        if self.established:
            parts.extend(["-m", "state", "--state", "ESTABLISHED,RELATED"])

        # Action
        if self.action in [FirewallAction.PERMIT]:
            parts.extend(["-j", "ACCEPT"])
        elif self.action in [FirewallAction.DROP, FirewallAction.DENY]:
            parts.extend(["-j", "DROP"])
        elif self.action == FirewallAction.REJECT:
            parts.extend(["-j", "REJECT"])
        elif self.action == FirewallAction.LOG:
            parts.extend(["-j", "LOG", "--log-prefix", f"ACL-{self.sequence}: "])
        elif self.action == FirewallAction.LOG_DROP:
            # Need two rules for log then drop
            parts.extend(["-j", "LOG", "--log-prefix", f"ACL-{self.sequence}: "])

        return " ".join(parts)


@dataclass
class ACLRule:
    """
    An Access Control List containing multiple entries.

    Groups ACL entries together with a name and can be applied to interfaces.
    """
    name: str
    description: str = ""
    acl_type: str = "extended"  # standard or extended
    entries: List[ACLEntry] = field(default_factory=list)

    # Interface bindings
    interfaces: Dict[str, Direction] = field(default_factory=dict)  # interface -> direction

    # State
    enabled: bool = True
    created_at: float = field(default_factory=time.time)

    def add_entry(self, entry: ACLEntry) -> bool:
        """Add an entry to the ACL"""
        # Check for duplicate sequence
        if any(e.sequence == entry.sequence for e in self.entries):
            return False
        self.entries.append(entry)
        self.entries.sort(key=lambda e: e.sequence)
        return True

    def remove_entry(self, sequence: int) -> bool:
        """Remove an entry by sequence number"""
        for i, entry in enumerate(self.entries):
            if entry.sequence == sequence:
                self.entries.pop(i)
                return True
        return False

    def get_entry(self, sequence: int) -> Optional[ACLEntry]:
        """Get an entry by sequence number"""
        for entry in self.entries:
            if entry.sequence == sequence:
                return entry
        return None

    def resequence(self, start: int = 10, increment: int = 10):
        """Resequence all entries"""
        for i, entry in enumerate(self.entries):
            entry.sequence = start + (i * increment)
            entry.modified_at = time.time()

    def apply_to_interface(self, interface: str, direction: Direction):
        """Apply ACL to an interface"""
        self.interfaces[interface] = direction

    def remove_from_interface(self, interface: str):
        """Remove ACL from an interface"""
        if interface in self.interfaces:
            del self.interfaces[interface]

    def evaluate(self, src_ip: str, dst_ip: str, proto: str,
                 src_port: int = 0, dst_port: int = 0) -> Tuple[FirewallAction, Optional[ACLEntry]]:
        """
        Evaluate packet against ACL entries.

        Returns the action and matching entry, or (DENY, None) if no match (implicit deny).
        """
        if not self.enabled:
            return (FirewallAction.PERMIT, None)

        for entry in self.entries:
            if entry.matches(src_ip, dst_ip, proto, src_port, dst_port):
                # Update statistics
                entry.statistics.packets_matched += 1
                entry.statistics.last_hit = time.time()
                return (entry.action, entry)

        # Implicit deny at end
        return (FirewallAction.DENY, None)

    def get_statistics(self) -> Dict[str, Any]:
        """Get ACL statistics"""
        total_hits = sum(e.statistics.packets_matched for e in self.entries)
        enabled_rules = sum(1 for e in self.entries if e.enabled)
        return {
            "total_entries": len(self.entries),
            "enabled_entries": enabled_rules,
            "total_hits": total_hits,
            "applied_interfaces": list(self.interfaces.keys())
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "acl_type": self.acl_type,
            "entry_count": len(self.entries),
            "entries": [e.to_dict() for e in self.entries],
            "interfaces": {k: v.value for k, v in self.interfaces.items()},
            "enabled": self.enabled,
            "statistics": self.get_statistics(),
            "created_at": datetime.fromtimestamp(self.created_at).isoformat()
        }

    def to_cisco_format(self) -> str:
        """Export as Cisco IOS configuration"""
        lines = [f"ip access-list {self.acl_type} {self.name}"]
        if self.description:
            lines.append(f" remark {self.description}")
        for entry in self.entries:
            lines.append(f" {entry.to_cisco_format()}")
        return "\n".join(lines)


class FirewallManager:
    """
    Manages all ACLs and firewall rules for an agent.

    Handles:
    - ACL creation and management
    - Rule application to interfaces
    - Statistics collection
    - iptables integration (optional)
    """

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.acls: Dict[str, ACLRule] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._blocked_traffic_log: List[Dict[str, Any]] = []
        self._allowed_traffic_log: List[Dict[str, Any]] = []
        self._max_log_entries = 1000

    async def start(self):
        """Start the firewall manager"""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info(f"Firewall manager started for agent {self.agent_id}")

    async def stop(self):
        """Stop the firewall manager"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(f"Firewall manager stopped for agent {self.agent_id}")

    async def _monitor_loop(self):
        """Monitor and update statistics"""
        while self._running:
            try:
                await self._update_statistics()
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Firewall monitor error: {e}")
                await asyncio.sleep(10)

    async def _update_statistics(self):
        """Update rule statistics from iptables counters"""
        try:
            result = subprocess.run(
                ["iptables", "-L", "-v", "-n", "--line-numbers"],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                # Parse iptables output for counters
                # This is a simplified version - full parsing would be more complex
                pass
        except Exception as e:
            logger.debug(f"Statistics update error: {e}")

    def create_acl(
        self,
        name: str,
        description: str = "",
        acl_type: str = "extended"
    ) -> ACLRule:
        """
        Create a new ACL.

        Args:
            name: ACL name (must be unique)
            description: Optional description
            acl_type: "standard" or "extended"

        Returns:
            Created ACL
        """
        if name in self.acls:
            raise ValueError(f"ACL {name} already exists")

        acl = ACLRule(
            name=name,
            description=description,
            acl_type=acl_type
        )
        self.acls[name] = acl
        logger.info(f"Created ACL: {name}")
        return acl

    def delete_acl(self, name: str) -> bool:
        """Delete an ACL"""
        if name in self.acls:
            # Remove from any interfaces first
            acl = self.acls[name]
            for interface in list(acl.interfaces.keys()):
                self._unapply_from_interface(acl, interface)
            del self.acls[name]
            logger.info(f"Deleted ACL: {name}")
            return True
        return False

    def get_acl(self, name: str) -> Optional[ACLRule]:
        """Get an ACL by name"""
        return self.acls.get(name)

    def list_acls(self) -> List[ACLRule]:
        """List all ACLs"""
        return list(self.acls.values())

    def add_rule(
        self,
        acl_name: str,
        sequence: int,
        action: str,
        protocol: str = "any",
        source_ip: str = "any",
        source_port: Optional[str] = None,
        dest_ip: str = "any",
        dest_port: Optional[str] = None,
        description: str = "",
        log: bool = False
    ) -> ACLEntry:
        """
        Add a rule to an ACL.

        Args:
            acl_name: ACL to add rule to
            sequence: Rule sequence number
            action: permit, deny, drop, reject
            protocol: any, tcp, udp, icmp, etc.
            source_ip: Source IP/network or "any"
            source_port: Source port (optional)
            dest_ip: Destination IP/network or "any"
            dest_port: Destination port (optional)
            description: Rule description
            log: Log matching packets

        Returns:
            Created ACL entry
        """
        if acl_name not in self.acls:
            raise ValueError(f"ACL {acl_name} not found")

        acl = self.acls[acl_name]

        entry = ACLEntry(
            sequence=sequence,
            name=description,
            action=FirewallAction(action),
            protocol=Protocol(protocol),
            source_ip=source_ip,
            source_port=source_port,
            dest_ip=dest_ip,
            dest_port=dest_port,
            log=log
        )

        if not acl.add_entry(entry):
            raise ValueError(f"Sequence {sequence} already exists in ACL {acl_name}")

        logger.info(f"Added rule {sequence} to ACL {acl_name}")
        return entry

    def remove_rule(self, acl_name: str, sequence: int) -> bool:
        """Remove a rule from an ACL"""
        if acl_name not in self.acls:
            return False
        return self.acls[acl_name].remove_entry(sequence)

    def update_rule(
        self,
        acl_name: str,
        sequence: int,
        enabled: Optional[bool] = None,
        action: Optional[str] = None
    ) -> bool:
        """Update a rule in an ACL"""
        if acl_name not in self.acls:
            return False

        entry = self.acls[acl_name].get_entry(sequence)
        if not entry:
            return False

        if enabled is not None:
            entry.enabled = enabled
        if action is not None:
            entry.action = FirewallAction(action)

        entry.modified_at = time.time()
        return True

    def apply_acl(self, acl_name: str, interface: str, direction: str) -> bool:
        """
        Apply an ACL to an interface.

        Args:
            acl_name: ACL to apply
            interface: Interface name
            direction: "in", "out", or "both"

        Returns:
            True if successful
        """
        if acl_name not in self.acls:
            return False

        acl = self.acls[acl_name]
        dir_enum = Direction(direction)
        acl.apply_to_interface(interface, dir_enum)

        # Apply to system (iptables)
        self._apply_to_interface(acl, interface, dir_enum)

        logger.info(f"Applied ACL {acl_name} to {interface} ({direction})")
        return True

    def remove_acl_from_interface(self, acl_name: str, interface: str) -> bool:
        """Remove an ACL from an interface"""
        if acl_name not in self.acls:
            return False

        acl = self.acls[acl_name]
        self._unapply_from_interface(acl, interface)
        acl.remove_from_interface(interface)
        return True

    def _apply_to_interface(self, acl: ACLRule, interface: str, direction: Direction):
        """Apply ACL rules to system via iptables"""
        try:
            chain = "INPUT" if direction in [Direction.INBOUND, Direction.BOTH] else "OUTPUT"

            for entry in acl.entries:
                if not entry.enabled:
                    continue

                # Build iptables command
                cmd = ["iptables"]
                cmd.extend(["-A", chain])
                cmd.extend(["-i" if chain == "INPUT" else "-o", interface])

                if entry.protocol != Protocol.ANY:
                    cmd.extend(["-p", entry.protocol.value])

                if entry.source_ip != "any":
                    cmd.extend(["-s", entry.source_ip])

                if entry.dest_ip != "any":
                    cmd.extend(["-d", entry.dest_ip])

                if entry.source_port:
                    cmd.extend(["--sport", entry.source_port])

                if entry.dest_port:
                    cmd.extend(["--dport", entry.dest_port])

                # Action
                if entry.action == FirewallAction.PERMIT:
                    cmd.extend(["-j", "ACCEPT"])
                elif entry.action in [FirewallAction.DENY, FirewallAction.DROP]:
                    cmd.extend(["-j", "DROP"])
                elif entry.action == FirewallAction.REJECT:
                    cmd.extend(["-j", "REJECT"])

                # Execute (in simulation mode, just log)
                logger.debug(f"Would execute: {' '.join(cmd)}")

        except Exception as e:
            logger.warning(f"Failed to apply ACL to interface: {e}")

    def _unapply_from_interface(self, acl: ACLRule, interface: str):
        """Remove ACL rules from system"""
        # In a real implementation, would remove iptables rules
        logger.debug(f"Would remove ACL {acl.name} from interface {interface}")

    def evaluate_packet(
        self,
        interface: str,
        direction: str,
        src_ip: str,
        dst_ip: str,
        protocol: str,
        src_port: int = 0,
        dst_port: int = 0
    ) -> FirewallAction:
        """
        Evaluate a packet against all applicable ACLs.

        Args:
            interface: Interface the packet arrived on
            direction: "in" or "out"
            src_ip: Source IP
            dst_ip: Destination IP
            protocol: Protocol (tcp, udp, icmp, etc.)
            src_port: Source port
            dst_port: Destination port

        Returns:
            Firewall action (permit/deny)
        """
        dir_enum = Direction(direction)

        for acl in self.acls.values():
            if interface not in acl.interfaces:
                continue

            acl_dir = acl.interfaces[interface]
            if acl_dir != Direction.BOTH and acl_dir != dir_enum:
                continue

            action, entry = acl.evaluate(src_ip, dst_ip, protocol, src_port, dst_port)

            # Log the decision
            log_entry = {
                "timestamp": time.time(),
                "interface": interface,
                "direction": direction,
                "src_ip": src_ip,
                "dst_ip": dst_ip,
                "protocol": protocol,
                "src_port": src_port,
                "dst_port": dst_port,
                "acl": acl.name,
                "rule": entry.sequence if entry else None,
                "action": action.value
            }

            if action in [FirewallAction.PERMIT]:
                self._allowed_traffic_log.append(log_entry)
                if len(self._allowed_traffic_log) > self._max_log_entries:
                    self._allowed_traffic_log = self._allowed_traffic_log[-self._max_log_entries:]
            else:
                self._blocked_traffic_log.append(log_entry)
                if len(self._blocked_traffic_log) > self._max_log_entries:
                    self._blocked_traffic_log = self._blocked_traffic_log[-self._max_log_entries:]

            return action

        # No matching ACL - default permit
        return FirewallAction.PERMIT

    def get_blocked_traffic(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent blocked traffic log"""
        return self._blocked_traffic_log[-limit:]

    def get_allowed_traffic(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent allowed traffic log"""
        return self._allowed_traffic_log[-limit:]

    def get_statistics(self) -> Dict[str, Any]:
        """Get firewall manager statistics"""
        total_rules = sum(len(acl.entries) for acl in self.acls.values())
        enabled_rules = sum(
            sum(1 for e in acl.entries if e.enabled)
            for acl in self.acls.values()
        )
        total_hits = sum(
            sum(e.statistics.packets_matched for e in acl.entries)
            for acl in self.acls.values()
        )

        return {
            "agent_id": self.agent_id,
            "running": self._running,
            "total_acls": len(self.acls),
            "total_rules": total_rules,
            "enabled_rules": enabled_rules,
            "total_hits": total_hits,
            "blocked_packets": len(self._blocked_traffic_log),
            "allowed_packets": len(self._allowed_traffic_log)
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert manager state to dictionary"""
        return {
            "agent_id": self.agent_id,
            "running": self._running,
            "acls": {name: acl.to_dict() for name, acl in self.acls.items()},
            "statistics": self.get_statistics()
        }


def get_firewall_manager(agent_id: str = "local") -> FirewallManager:
    """Get or create the firewall manager singleton"""
    global _firewall_manager
    if _firewall_manager is None:
        _firewall_manager = FirewallManager(agent_id)
    return _firewall_manager


async def start_firewall_manager(agent_id: str) -> FirewallManager:
    """Start the firewall manager for an agent"""
    global _firewall_manager
    _firewall_manager = FirewallManager(agent_id)
    await _firewall_manager.start()
    return _firewall_manager


async def stop_firewall_manager():
    """Stop the firewall manager"""
    global _firewall_manager
    if _firewall_manager:
        await _firewall_manager.stop()
        _firewall_manager = None


def list_acl_rules() -> List[Dict[str, Any]]:
    """List all ACLs as dictionaries"""
    manager = get_firewall_manager()
    return [acl.to_dict() for acl in manager.list_acls()]


def get_firewall_statistics() -> Dict[str, Any]:
    """Get firewall manager statistics"""
    manager = get_firewall_manager()
    return manager.get_statistics()
