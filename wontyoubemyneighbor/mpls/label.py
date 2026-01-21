"""
MPLS Label Management

Defines MPLS label structures, operations, and label stack handling
per RFC 3032.
"""

import struct
from dataclasses import dataclass, field
from typing import List, Optional, Any, Dict
from enum import Enum


# Reserved Label Values (RFC 3032)
LABEL_IPV4_EXPLICIT_NULL = 0      # IPv4 Explicit NULL
LABEL_ROUTER_ALERT = 1            # Router Alert
LABEL_IPV6_EXPLICIT_NULL = 2      # IPv6 Explicit NULL
LABEL_IMPLICIT_NULL = 3           # Implicit NULL (PHP)
LABEL_ENTROPY = 7                 # Entropy Label Indicator

# Label value range
MIN_LABEL = 16                    # First usable label
MAX_LABEL = 1048575               # Maximum label (20 bits)

# Special label values for internal use
LABEL_UNASSIGNED = -1


class LabelAction(Enum):
    """MPLS label operations"""
    PUSH = "push"       # Push label onto stack
    POP = "pop"         # Pop label from stack
    SWAP = "swap"       # Swap top label
    PHP = "php"         # Penultimate Hop Pop


@dataclass
class Label:
    """
    MPLS Label Entry (32-bit MPLS header).

    MPLS Label Format (RFC 3032):
     0                   1                   2                   3
     0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    |                Label                  | TC  |S|       TTL     |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+

    Label: 20 bits - Label value
    TC: 3 bits - Traffic Class (formerly EXP)
    S: 1 bit - Bottom of Stack
    TTL: 8 bits - Time to Live
    """
    value: int                    # Label value (20 bits: 0-1048575)
    tc: int = 0                   # Traffic Class (3 bits: 0-7)
    s: bool = True                # Bottom of Stack flag
    ttl: int = 64                 # Time to Live

    def __post_init__(self):
        """Validate label values"""
        if not 0 <= self.value <= MAX_LABEL:
            raise ValueError(f"Label must be 0-{MAX_LABEL}, got {self.value}")
        if not 0 <= self.tc <= 7:
            raise ValueError(f"TC must be 0-7, got {self.tc}")
        if not 0 <= self.ttl <= 255:
            raise ValueError(f"TTL must be 0-255, got {self.ttl}")

    def is_reserved(self) -> bool:
        """Check if this is a reserved label"""
        return self.value < MIN_LABEL

    def is_explicit_null(self) -> bool:
        """Check if this is an explicit null label"""
        return self.value in (LABEL_IPV4_EXPLICIT_NULL, LABEL_IPV6_EXPLICIT_NULL)

    def is_implicit_null(self) -> bool:
        """Check if this is implicit null (PHP)"""
        return self.value == LABEL_IMPLICIT_NULL

    def to_bytes(self) -> bytes:
        """
        Serialize label to 4 bytes.

        Returns:
            4-byte MPLS header
        """
        # Pack: Label (20) | TC (3) | S (1) | TTL (8)
        header = (self.value << 12) | (self.tc << 9) | (int(self.s) << 8) | self.ttl
        return struct.pack("!I", header)

    @classmethod
    def from_bytes(cls, data: bytes) -> 'Label':
        """
        Parse label from 4 bytes.

        Args:
            data: 4-byte MPLS header

        Returns:
            Label instance
        """
        if len(data) < 4:
            raise ValueError(f"Need 4 bytes for MPLS label, got {len(data)}")

        header = struct.unpack("!I", data[:4])[0]

        value = (header >> 12) & 0xFFFFF  # 20 bits
        tc = (header >> 9) & 0x7          # 3 bits
        s = bool((header >> 8) & 0x1)     # 1 bit
        ttl = header & 0xFF               # 8 bits

        return cls(value=value, tc=tc, s=s, ttl=ttl)

    def decrement_ttl(self) -> bool:
        """
        Decrement TTL.

        Returns:
            True if TTL > 0 after decrement
        """
        if self.ttl > 0:
            self.ttl -= 1
        return self.ttl > 0

    def copy(self) -> 'Label':
        """Create a copy of this label"""
        return Label(value=self.value, tc=self.tc, s=self.s, ttl=self.ttl)

    def __str__(self) -> str:
        return f"Label({self.value}, tc={self.tc}, s={self.s}, ttl={self.ttl})"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "value": self.value,
            "tc": self.tc,
            "bottom_of_stack": self.s,
            "ttl": self.ttl,
        }


class LabelStack:
    """
    MPLS Label Stack.

    Manages a stack of MPLS labels for label stacking operations.
    The stack is ordered with the top label at index 0.
    """

    def __init__(self, labels: Optional[List[Label]] = None):
        """
        Initialize label stack.

        Args:
            labels: Initial labels (top to bottom)
        """
        self._stack: List[Label] = []

        if labels:
            for label in labels:
                self.push(label)

    @property
    def depth(self) -> int:
        """Get stack depth"""
        return len(self._stack)

    def is_empty(self) -> bool:
        """Check if stack is empty"""
        return len(self._stack) == 0

    def push(self, label: Label) -> None:
        """
        Push label onto stack.

        Args:
            label: Label to push
        """
        # Clear S bit on previous top (if any)
        if self._stack:
            self._stack[0].s = False

        # New label becomes top
        label_copy = label.copy()
        label_copy.s = (len(self._stack) == 0)  # S=1 only if this is the only label
        self._stack.insert(0, label_copy)

    def pop(self) -> Optional[Label]:
        """
        Pop top label from stack.

        Returns:
            Popped label or None if empty
        """
        if not self._stack:
            return None

        label = self._stack.pop(0)

        # Set S bit on new top if stack not empty
        if self._stack:
            self._stack[0].s = (len(self._stack) == 1)

        return label

    def swap(self, new_label: Label) -> Optional[Label]:
        """
        Swap top label.

        Args:
            new_label: New label value

        Returns:
            Old top label or None if empty
        """
        if not self._stack:
            return None

        old_label = self._stack[0]
        new_copy = new_label.copy()
        new_copy.s = old_label.s
        new_copy.ttl = old_label.ttl  # Preserve TTL
        self._stack[0] = new_copy

        return old_label

    def top(self) -> Optional[Label]:
        """Get top label without removing"""
        return self._stack[0] if self._stack else None

    def bottom(self) -> Optional[Label]:
        """Get bottom label"""
        return self._stack[-1] if self._stack else None

    def decrement_ttl(self) -> bool:
        """
        Decrement TTL of top label.

        Returns:
            True if TTL > 0 after decrement
        """
        if self._stack:
            return self._stack[0].decrement_ttl()
        return False

    def to_bytes(self) -> bytes:
        """
        Serialize entire label stack.

        Returns:
            Concatenated label bytes (top to bottom)
        """
        if not self._stack:
            return b""

        # Ensure S bits are correct
        for i, label in enumerate(self._stack):
            label.s = (i == len(self._stack) - 1)

        return b"".join(label.to_bytes() for label in self._stack)

    @classmethod
    def from_bytes(cls, data: bytes) -> 'LabelStack':
        """
        Parse label stack from bytes.

        Args:
            data: MPLS label data

        Returns:
            LabelStack instance
        """
        stack = cls()
        offset = 0

        while offset + 4 <= len(data):
            label = Label.from_bytes(data[offset:offset + 4])
            stack._stack.append(label)
            offset += 4

            if label.s:  # Bottom of stack
                break

        return stack

    def get_labels(self) -> List[Label]:
        """Get all labels (top to bottom)"""
        return list(self._stack)

    def __len__(self) -> int:
        return len(self._stack)

    def __str__(self) -> str:
        if not self._stack:
            return "LabelStack(empty)"
        labels = " -> ".join(str(l.value) for l in self._stack)
        return f"LabelStack({labels})"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "depth": self.depth,
            "labels": [l.to_dict() for l in self._stack],
        }


class LabelAllocator:
    """
    Manages label allocation from a pool.
    """

    def __init__(
        self,
        start: int = MIN_LABEL,
        end: int = MAX_LABEL,
    ):
        """
        Initialize label allocator.

        Args:
            start: Start of label range
            end: End of label range
        """
        self.start = start
        self.end = end

        # Available labels (using set for O(1) operations)
        self._available: set = set(range(start, end + 1))

        # Allocated labels: {label: purpose}
        self._allocated: Dict[int, str] = {}

    def allocate(self, purpose: str = "") -> int:
        """
        Allocate a label.

        Args:
            purpose: Description of allocation purpose

        Returns:
            Allocated label value

        Raises:
            ValueError: If no labels available
        """
        if not self._available:
            raise ValueError("No labels available")

        label = min(self._available)
        self._available.remove(label)
        self._allocated[label] = purpose

        return label

    def allocate_specific(self, label: int, purpose: str = "") -> bool:
        """
        Allocate a specific label.

        Args:
            label: Label value to allocate
            purpose: Description of allocation purpose

        Returns:
            True if allocated successfully
        """
        if label not in self._available:
            return False

        self._available.remove(label)
        self._allocated[label] = purpose

        return True

    def release(self, label: int) -> bool:
        """
        Release a label back to the pool.

        Args:
            label: Label to release

        Returns:
            True if released
        """
        if label not in self._allocated:
            return False

        del self._allocated[label]
        self._available.add(label)

        return True

    def is_allocated(self, label: int) -> bool:
        """Check if label is allocated"""
        return label in self._allocated

    def get_allocation_count(self) -> int:
        """Get number of allocated labels"""
        return len(self._allocated)

    def get_available_count(self) -> int:
        """Get number of available labels"""
        return len(self._available)

    def get_statistics(self) -> Dict[str, Any]:
        """Get allocator statistics"""
        return {
            "range_start": self.start,
            "range_end": self.end,
            "total_labels": self.end - self.start + 1,
            "allocated": len(self._allocated),
            "available": len(self._available),
        }
