"""
MPLS Label Forwarding Information Base (LFIB)

Manages the label forwarding table for MPLS packet switching.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from datetime import datetime

from .label import Label, LabelStack, LabelAction, LABEL_IMPLICIT_NULL


class NextHopType(Enum):
    """Types of next hops in LFIB"""
    INTERFACE = "interface"    # Directly connected
    IP_NEXTHOP = "ip"          # IP next hop (needs ARP)
    LSP = "lsp"                # Another LSP (label stacking)
    DROP = "drop"              # Discard
    LOCAL = "local"            # Deliver locally


@dataclass
class LFIBEntry:
    """
    LFIB Entry representing a label forwarding decision.

    Each entry maps an incoming label to an action and next hop.
    """
    # Incoming label
    in_label: int

    # Action to perform
    action: LabelAction

    # Outgoing label(s) - depends on action
    # SWAP: single label
    # PUSH: one or more labels
    # POP: empty
    out_labels: List[int] = field(default_factory=list)

    # Next hop information
    next_hop_type: NextHopType = NextHopType.IP_NEXTHOP
    next_hop_ip: Optional[str] = None
    next_hop_interface: Optional[str] = None

    # FEC (Forwarding Equivalence Class) this entry is for
    fec_prefix: Optional[str] = None

    # Metadata
    owner: str = "static"             # Protocol that installed entry (ldp, bgp, static)
    installed_time: Optional[datetime] = None
    packets_switched: int = 0
    bytes_switched: int = 0

    def __post_init__(self):
        """Set installation time"""
        if self.installed_time is None:
            self.installed_time = datetime.now()

    def is_php(self) -> bool:
        """Check if this is a Penultimate Hop Pop entry"""
        return self.action == LabelAction.PHP or (
            self.action == LabelAction.SWAP and
            self.out_labels and
            self.out_labels[0] == LABEL_IMPLICIT_NULL
        )

    def update_stats(self, packet_size: int) -> None:
        """Update forwarding statistics"""
        self.packets_switched += 1
        self.bytes_switched += packet_size

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "in_label": self.in_label,
            "action": self.action.value,
            "out_labels": self.out_labels,
            "next_hop_type": self.next_hop_type.value,
            "next_hop_ip": self.next_hop_ip,
            "next_hop_interface": self.next_hop_interface,
            "fec_prefix": self.fec_prefix,
            "owner": self.owner,
            "packets_switched": self.packets_switched,
            "bytes_switched": self.bytes_switched,
        }


class LFIB:
    """
    Label Forwarding Information Base.

    The LFIB is the MPLS forwarding table that maps incoming labels
    to forwarding actions.
    """

    def __init__(self):
        """Initialize LFIB"""
        # Main table: {in_label: LFIBEntry}
        self._entries: Dict[int, LFIBEntry] = {}

        # Index by FEC: {prefix: [in_labels]}
        self._fec_index: Dict[str, List[int]] = {}

        # Index by next hop: {next_hop_ip: [in_labels]}
        self._nexthop_index: Dict[str, List[int]] = {}

        self.logger = logging.getLogger("LFIB")

    def install(self, entry: LFIBEntry) -> bool:
        """
        Install LFIB entry.

        Args:
            entry: LFIB entry to install

        Returns:
            True if installed (new or updated)
        """
        # Check for existing entry
        existing = self._entries.get(entry.in_label)

        if existing:
            # Remove from indexes
            self._remove_from_indexes(existing)

        # Install entry
        self._entries[entry.in_label] = entry
        self._add_to_indexes(entry)

        action_desc = f"{entry.action.value}"
        if entry.out_labels:
            action_desc += f" {entry.out_labels}"

        self.logger.debug(
            f"Installed LFIB: {entry.in_label} -> {action_desc} "
            f"via {entry.next_hop_ip or entry.next_hop_interface}"
        )

        return True

    def remove(self, in_label: int) -> Optional[LFIBEntry]:
        """
        Remove LFIB entry.

        Args:
            in_label: Incoming label

        Returns:
            Removed entry or None
        """
        entry = self._entries.pop(in_label, None)

        if entry:
            self._remove_from_indexes(entry)
            self.logger.debug(f"Removed LFIB entry for label {in_label}")

        return entry

    def lookup(self, in_label: int) -> Optional[LFIBEntry]:
        """
        Lookup LFIB entry by incoming label.

        Args:
            in_label: Incoming label

        Returns:
            LFIB entry or None
        """
        return self._entries.get(in_label)

    def lookup_by_fec(self, prefix: str) -> List[LFIBEntry]:
        """
        Get LFIB entries for a FEC.

        Args:
            prefix: FEC prefix

        Returns:
            List of LFIB entries
        """
        labels = self._fec_index.get(prefix, [])
        return [self._entries[l] for l in labels if l in self._entries]

    def lookup_by_nexthop(self, next_hop: str) -> List[LFIBEntry]:
        """
        Get LFIB entries for a next hop.

        Args:
            next_hop: Next hop IP

        Returns:
            List of LFIB entries
        """
        labels = self._nexthop_index.get(next_hop, [])
        return [self._entries[l] for l in labels if l in self._entries]

    def _add_to_indexes(self, entry: LFIBEntry) -> None:
        """Add entry to indexes"""
        if entry.fec_prefix:
            if entry.fec_prefix not in self._fec_index:
                self._fec_index[entry.fec_prefix] = []
            self._fec_index[entry.fec_prefix].append(entry.in_label)

        if entry.next_hop_ip:
            if entry.next_hop_ip not in self._nexthop_index:
                self._nexthop_index[entry.next_hop_ip] = []
            self._nexthop_index[entry.next_hop_ip].append(entry.in_label)

    def _remove_from_indexes(self, entry: LFIBEntry) -> None:
        """Remove entry from indexes"""
        if entry.fec_prefix and entry.fec_prefix in self._fec_index:
            try:
                self._fec_index[entry.fec_prefix].remove(entry.in_label)
            except ValueError:
                pass

        if entry.next_hop_ip and entry.next_hop_ip in self._nexthop_index:
            try:
                self._nexthop_index[entry.next_hop_ip].remove(entry.in_label)
            except ValueError:
                pass

    def get_all_entries(self) -> List[LFIBEntry]:
        """Get all LFIB entries"""
        return list(self._entries.values())

    def get_entry_count(self) -> int:
        """Get number of entries"""
        return len(self._entries)

    def clear(self, owner: Optional[str] = None) -> int:
        """
        Clear LFIB entries.

        Args:
            owner: Only clear entries from this owner (None = all)

        Returns:
            Number of entries removed
        """
        if owner is None:
            count = len(self._entries)
            self._entries.clear()
            self._fec_index.clear()
            self._nexthop_index.clear()
            return count

        to_remove = [
            label for label, entry in self._entries.items()
            if entry.owner == owner
        ]

        for label in to_remove:
            self.remove(label)

        return len(to_remove)

    def forward(self, in_label: int, packet_size: int = 0) -> Optional[Tuple[LabelAction, List[int], str]]:
        """
        Perform forwarding lookup.

        Args:
            in_label: Incoming label
            packet_size: Packet size for stats

        Returns:
            Tuple of (action, out_labels, next_hop) or None
        """
        entry = self._entries.get(in_label)

        if not entry:
            self.logger.debug(f"No LFIB entry for label {in_label}")
            return None

        # Update statistics
        entry.update_stats(packet_size)

        next_hop = entry.next_hop_ip or entry.next_hop_interface or "local"

        return (entry.action, entry.out_labels, next_hop)

    def get_statistics(self) -> Dict[str, Any]:
        """Get LFIB statistics"""
        total_packets = sum(e.packets_switched for e in self._entries.values())
        total_bytes = sum(e.bytes_switched for e in self._entries.values())

        by_owner = {}
        for entry in self._entries.values():
            by_owner[entry.owner] = by_owner.get(entry.owner, 0) + 1

        by_action = {}
        for entry in self._entries.values():
            action = entry.action.value
            by_action[action] = by_action.get(action, 0) + 1

        return {
            "total_entries": len(self._entries),
            "total_packets": total_packets,
            "total_bytes": total_bytes,
            "by_owner": by_owner,
            "by_action": by_action,
            "fec_count": len(self._fec_index),
            "nexthop_count": len(self._nexthop_index),
        }

    def dump(self) -> str:
        """Dump LFIB in human-readable format"""
        lines = ["LFIB:", "-" * 80]
        lines.append(f"{'In Label':<12} {'Action':<8} {'Out Labels':<20} {'Next Hop':<20} {'FEC':<20}")
        lines.append("-" * 80)

        for label in sorted(self._entries.keys()):
            entry = self._entries[label]
            out_labels = ",".join(str(l) for l in entry.out_labels) or "-"
            next_hop = entry.next_hop_ip or entry.next_hop_interface or "local"
            fec = entry.fec_prefix or "-"

            lines.append(
                f"{entry.in_label:<12} {entry.action.value:<8} {out_labels:<20} {next_hop:<20} {fec:<20}"
            )

        return "\n".join(lines)
