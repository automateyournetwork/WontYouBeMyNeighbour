"""
MPLS Forwarding Engine

Implements MPLS packet forwarding using the LFIB.
"""

import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple, List

from .label import Label, LabelStack, LabelAction
from .lfib import LFIB, LFIBEntry


@dataclass
class MPLSPacket:
    """
    MPLS Packet representation.

    Contains the label stack and inner payload.
    """
    label_stack: LabelStack
    payload: bytes
    inner_protocol: str = "ipv4"  # ipv4, ipv6, ethernet

    @property
    def top_label(self) -> Optional[Label]:
        """Get top label"""
        return self.label_stack.top()

    def is_labeled(self) -> bool:
        """Check if packet has labels"""
        return not self.label_stack.is_empty()


class MPLSForwarder:
    """
    MPLS Forwarding Engine.

    Performs label switching operations based on LFIB lookups.
    """

    def __init__(self, lfib: Optional[LFIB] = None):
        """
        Initialize MPLS forwarder.

        Args:
            lfib: LFIB instance (creates new if None)
        """
        self.lfib = lfib or LFIB()

        # Statistics
        self._packets_forwarded = 0
        self._packets_dropped = 0
        self._ttl_exceeded = 0
        self._no_route = 0

        self.logger = logging.getLogger("MPLSForwarder")

    def forward(self, packet: MPLSPacket) -> Tuple[Optional[MPLSPacket], Optional[str]]:
        """
        Forward MPLS packet.

        Args:
            packet: MPLS packet to forward

        Returns:
            Tuple of (forwarded packet, next hop) or (None, None) if dropped
        """
        if not packet.is_labeled():
            self.logger.warning("Received unlabeled packet")
            self._packets_dropped += 1
            return None, None

        top_label = packet.top_label
        if not top_label:
            return None, None

        # Lookup in LFIB
        result = self.lfib.forward(top_label.value, len(packet.payload))

        if result is None:
            self.logger.debug(f"No LFIB entry for label {top_label.value}")
            self._no_route += 1
            self._packets_dropped += 1
            return None, None

        action, out_labels, next_hop = result

        # Check TTL
        if not packet.label_stack.decrement_ttl():
            self.logger.debug("TTL exceeded")
            self._ttl_exceeded += 1
            self._packets_dropped += 1
            return None, None

        # Perform label operation
        if action == LabelAction.SWAP:
            self._perform_swap(packet, out_labels)
        elif action == LabelAction.POP:
            self._perform_pop(packet)
        elif action == LabelAction.PUSH:
            self._perform_push(packet, out_labels)
        elif action == LabelAction.PHP:
            self._perform_php(packet)

        self._packets_forwarded += 1

        return packet, next_hop

    def _perform_swap(self, packet: MPLSPacket, out_labels: List[int]) -> None:
        """Perform label swap operation"""
        if not out_labels:
            return

        old_label = packet.label_stack.top()
        if old_label:
            new_label = Label(value=out_labels[0], ttl=old_label.ttl, tc=old_label.tc)
            packet.label_stack.swap(new_label)
            self.logger.debug(f"SWAP: {old_label.value} -> {out_labels[0]}")

    def _perform_pop(self, packet: MPLSPacket) -> None:
        """Perform label pop operation"""
        popped = packet.label_stack.pop()
        if popped:
            self.logger.debug(f"POP: {popped.value}")

    def _perform_push(self, packet: MPLSPacket, out_labels: List[int]) -> None:
        """Perform label push operation"""
        # Push labels in reverse order (last label pushed first)
        for label_value in reversed(out_labels):
            label = Label(value=label_value, ttl=64)
            packet.label_stack.push(label)
            self.logger.debug(f"PUSH: {label_value}")

    def _perform_php(self, packet: MPLSPacket) -> None:
        """Perform Penultimate Hop Pop"""
        popped = packet.label_stack.pop()
        if popped:
            self.logger.debug(f"PHP: {popped.value}")

    def impose_labels(self, payload: bytes, labels: List[int], ttl: int = 64) -> MPLSPacket:
        """
        Impose labels on IP packet (ingress).

        Args:
            payload: Inner payload (IP packet)
            labels: Labels to impose (bottom to top)
            ttl: Initial TTL

        Returns:
            MPLS packet
        """
        stack = LabelStack()

        # Push labels (first label in list becomes bottom)
        for i, label_value in enumerate(labels):
            label = Label(value=label_value, ttl=ttl)
            stack.push(label)

        packet = MPLSPacket(
            label_stack=stack,
            payload=payload,
        )

        self.logger.debug(f"Imposed labels: {stack}")
        return packet

    def dispose_labels(self, packet: MPLSPacket) -> bytes:
        """
        Remove all labels (egress).

        Args:
            packet: MPLS packet

        Returns:
            Inner payload
        """
        # Pop all labels
        while not packet.label_stack.is_empty():
            packet.label_stack.pop()

        return packet.payload

    def get_statistics(self) -> Dict[str, Any]:
        """Get forwarding statistics"""
        return {
            "packets_forwarded": self._packets_forwarded,
            "packets_dropped": self._packets_dropped,
            "ttl_exceeded": self._ttl_exceeded,
            "no_route": self._no_route,
            "lfib_entries": self.lfib.get_entry_count(),
        }

    def reset_statistics(self) -> None:
        """Reset forwarding statistics"""
        self._packets_forwarded = 0
        self._packets_dropped = 0
        self._ttl_exceeded = 0
        self._no_route = 0
