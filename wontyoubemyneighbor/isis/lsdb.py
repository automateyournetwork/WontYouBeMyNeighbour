"""
IS-IS Link State Database (LSDB)

Manages the Link State PDU database for IS-IS protocol.
Supports separate Level 1 and Level 2 databases.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Any, Callable
from datetime import datetime
import hashlib
import struct

from .constants import (
    LEVEL_1, LEVEL_2, LEVEL_1_2,
    DEFAULT_LSP_LIFETIME, DEFAULT_LSP_REFRESH_INTERVAL,
    LSP_SEQUENCE_INITIAL, LSP_SEQUENCE_MAX,
    TLV_AREA_ADDRESSES, TLV_IS_NEIGHBORS, TLV_IP_INT_REACH,
    TLV_IP_INTERFACE_ADDR, TLV_HOSTNAME, TLV_EXTENDED_IP_REACH,
)


@dataclass
class TLV:
    """
    Type-Length-Value structure for IS-IS PDUs.

    IS-IS uses TLVs extensively for encoding variable-length data
    in Hello, LSP, and SNP packets.
    """
    type: int
    value: bytes

    @property
    def length(self) -> int:
        return len(self.value)

    def to_bytes(self) -> bytes:
        """Serialize TLV to bytes"""
        return bytes([self.type, self.length]) + self.value

    @classmethod
    def from_bytes(cls, data: bytes) -> tuple:
        """
        Parse TLV from bytes.

        Returns:
            Tuple of (TLV, remaining_bytes)
        """
        if len(data) < 2:
            raise ValueError("TLV too short")

        tlv_type = data[0]
        tlv_len = data[1]

        if len(data) < 2 + tlv_len:
            raise ValueError(f"TLV value truncated: expected {tlv_len}, got {len(data) - 2}")

        tlv_value = data[2:2 + tlv_len]
        remaining = data[2 + tlv_len:]

        return cls(type=tlv_type, value=tlv_value), remaining


@dataclass
class LSP:
    """
    Link State Protocol Data Unit (LSP).

    Represents a single LSP in the database.
    Each router originates its own LSP(s) and floods received LSPs.
    """
    # LSP ID: system_id (6 bytes) + pseudonode_id (1 byte) + fragment (1 byte)
    lsp_id: str  # Format: "AABB.CCDD.EEFF.PN-FF" (system_id.pseudonode-fragment)

    # Sequence number (32-bit, increases with each update)
    sequence_number: int

    # Remaining lifetime (decreases over time, starts at max_age)
    remaining_lifetime: int

    # LSP flags
    partition_repair: bool = False  # P bit
    attached: bool = False          # ATT bit (L1/L2 attachment)
    overload: bool = False          # OL bit (don't use for transit)
    is_type: int = LEVEL_1_2        # IS Type (1, 2, or 3)

    # TLVs
    tlvs: List[TLV] = field(default_factory=list)

    # Metadata
    level: int = LEVEL_1            # Database level this LSP belongs to
    received_from: Optional[str] = None  # System ID we received this from (or None if local)
    received_time: Optional[datetime] = None
    checksum: int = 0

    @property
    def system_id(self) -> str:
        """Extract system ID from LSP ID"""
        return self.lsp_id.split(".")[0:3]

    @property
    def is_local(self) -> bool:
        """Check if this is a locally originated LSP"""
        return self.received_from is None

    def is_newer_than(self, other: 'LSP') -> bool:
        """
        Compare LSPs by sequence number.
        Higher sequence number = newer LSP.
        """
        return self.sequence_number > other.sequence_number

    def is_expired(self) -> bool:
        """Check if LSP has expired (remaining_lifetime <= 0)"""
        return self.remaining_lifetime <= 0

    def decrement_lifetime(self, seconds: int = 1) -> None:
        """Decrease remaining lifetime"""
        self.remaining_lifetime = max(0, self.remaining_lifetime - seconds)

    def get_tlv(self, tlv_type: int) -> Optional[TLV]:
        """Get TLV by type"""
        for tlv in self.tlvs:
            if tlv.type == tlv_type:
                return tlv
        return None

    def get_tlvs(self, tlv_type: int) -> List[TLV]:
        """Get all TLVs of a specific type"""
        return [tlv for tlv in self.tlvs if tlv.type == tlv_type]

    def add_tlv(self, tlv: TLV) -> None:
        """Add a TLV to the LSP"""
        self.tlvs.append(tlv)

    def calculate_checksum(self) -> int:
        """
        Calculate Fletcher checksum for the LSP.
        Uses the same checksum algorithm as OSPF (Fletcher-16).
        """
        # Serialize LSP content (excluding checksum field)
        data = self._serialize_for_checksum()

        # Fletcher-16 checksum
        c0 = 0
        c1 = 0

        for byte in data:
            c0 = (c0 + byte) % 255
            c1 = (c1 + c0) % 255

        # Return checksum value
        return (c1 << 8) | c0

    def _serialize_for_checksum(self) -> bytes:
        """Serialize LSP data for checksum calculation"""
        data = bytearray()

        # LSP ID (8 bytes as string representation converted)
        # Simplified: use hash of lsp_id
        id_hash = hashlib.md5(self.lsp_id.encode()).digest()[:8]
        data.extend(id_hash)

        # Sequence number (4 bytes)
        data.extend(struct.pack("!I", self.sequence_number))

        # Remaining lifetime (2 bytes)
        data.extend(struct.pack("!H", self.remaining_lifetime))

        # TLVs
        for tlv in self.tlvs:
            data.extend(tlv.to_bytes())

        return bytes(data)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "lsp_id": self.lsp_id,
            "sequence_number": self.sequence_number,
            "remaining_lifetime": self.remaining_lifetime,
            "level": self.level,
            "overload": self.overload,
            "attached": self.attached,
            "is_type": self.is_type,
            "tlv_count": len(self.tlvs),
            "is_local": self.is_local,
            "received_from": self.received_from,
            "checksum": hex(self.checksum),
        }


class LSDB:
    """
    IS-IS Link State Database.

    Maintains separate databases for Level 1 and Level 2.
    Handles LSP installation, aging, and removal.
    """

    def __init__(self, system_id: str, level: int = LEVEL_1):
        """
        Initialize LSDB.

        Args:
            system_id: Local router's system ID
            level: Database level (LEVEL_1 or LEVEL_2)
        """
        self.system_id = system_id
        self.level = level

        # LSP storage: {lsp_id: LSP}
        self._lsps: Dict[str, LSP] = {}

        # SRM (Send Routing Message) flags per neighbor per LSP
        # {neighbor_system_id: set of lsp_ids to send}
        self._srm: Dict[str, Set[str]] = {}

        # SSN (Send Sequence Number) flags - for PSNP acknowledgments
        self._ssn: Dict[str, Set[str]] = {}

        # Callbacks
        self.on_lsp_change: Optional[Callable[[LSP], None]] = None
        self.on_lsp_expired: Optional[Callable[[str], None]] = None

        # Aging task
        self._aging_task: Optional[asyncio.Task] = None

        self.logger = logging.getLogger(f"LSDB-L{level}")

    def get_lsp(self, lsp_id: str) -> Optional[LSP]:
        """Get LSP by ID"""
        return self._lsps.get(lsp_id)

    def get_all_lsps(self) -> List[LSP]:
        """Get all LSPs in the database"""
        return list(self._lsps.values())

    def get_lsp_count(self) -> int:
        """Get number of LSPs in database"""
        return len(self._lsps)

    def install_lsp(self, lsp: LSP) -> bool:
        """
        Install or update an LSP in the database.

        Args:
            lsp: LSP to install

        Returns:
            True if installed (new or updated), False if rejected
        """
        existing = self._lsps.get(lsp.lsp_id)

        if existing:
            # Compare sequence numbers
            if lsp.sequence_number <= existing.sequence_number:
                self.logger.debug(f"Rejecting older LSP {lsp.lsp_id}: "
                                f"new seq={lsp.sequence_number}, existing={existing.sequence_number}")
                return False

            self.logger.debug(f"Updating LSP {lsp.lsp_id}: seq {existing.sequence_number} -> {lsp.sequence_number}")
        else:
            self.logger.debug(f"Installing new LSP {lsp.lsp_id} seq={lsp.sequence_number}")

        # Install LSP
        self._lsps[lsp.lsp_id] = lsp

        # Set SRM flags for all neighbors (flood the LSP)
        self._set_srm_all(lsp.lsp_id)

        # Trigger callback
        if self.on_lsp_change:
            self.on_lsp_change(lsp)

        return True

    def remove_lsp(self, lsp_id: str) -> bool:
        """
        Remove an LSP from the database.

        Args:
            lsp_id: ID of LSP to remove

        Returns:
            True if removed, False if not found
        """
        if lsp_id not in self._lsps:
            return False

        del self._lsps[lsp_id]

        # Clear SRM/SSN flags
        for neighbor_flags in self._srm.values():
            neighbor_flags.discard(lsp_id)
        for neighbor_flags in self._ssn.values():
            neighbor_flags.discard(lsp_id)

        self.logger.debug(f"Removed LSP {lsp_id}")
        return True

    def _set_srm_all(self, lsp_id: str) -> None:
        """Set SRM flag for all neighbors"""
        for neighbor_id in self._srm:
            self._srm[neighbor_id].add(lsp_id)

    def set_srm(self, neighbor_id: str, lsp_id: str) -> None:
        """Set SRM flag for specific neighbor"""
        if neighbor_id not in self._srm:
            self._srm[neighbor_id] = set()
        self._srm[neighbor_id].add(lsp_id)

    def clear_srm(self, neighbor_id: str, lsp_id: str) -> None:
        """Clear SRM flag (LSP was acknowledged)"""
        if neighbor_id in self._srm:
            self._srm[neighbor_id].discard(lsp_id)

    def get_srm_lsps(self, neighbor_id: str) -> List[LSP]:
        """Get LSPs pending transmission to neighbor"""
        lsp_ids = self._srm.get(neighbor_id, set())
        return [self._lsps[lid] for lid in lsp_ids if lid in self._lsps]

    def set_ssn(self, neighbor_id: str, lsp_id: str) -> None:
        """Set SSN flag (need to send PSNP acknowledgment)"""
        if neighbor_id not in self._ssn:
            self._ssn[neighbor_id] = set()
        self._ssn[neighbor_id].add(lsp_id)

    def clear_ssn(self, neighbor_id: str, lsp_id: str) -> None:
        """Clear SSN flag"""
        if neighbor_id in self._ssn:
            self._ssn[neighbor_id].discard(lsp_id)

    def get_ssn_lsps(self, neighbor_id: str) -> List[str]:
        """Get LSP IDs pending PSNP acknowledgment"""
        return list(self._ssn.get(neighbor_id, set()))

    def register_neighbor(self, neighbor_id: str) -> None:
        """Register a neighbor for flooding"""
        if neighbor_id not in self._srm:
            self._srm[neighbor_id] = set()
        if neighbor_id not in self._ssn:
            self._ssn[neighbor_id] = set()

    def unregister_neighbor(self, neighbor_id: str) -> None:
        """Unregister a neighbor"""
        self._srm.pop(neighbor_id, None)
        self._ssn.pop(neighbor_id, None)

    async def start_aging(self) -> None:
        """Start LSP aging task"""
        self._aging_task = asyncio.create_task(self._aging_loop())

    async def stop(self) -> None:
        """Stop LSDB operations"""
        if self._aging_task:
            self._aging_task.cancel()
            try:
                await self._aging_task
            except asyncio.CancelledError:
                pass

    async def _aging_loop(self) -> None:
        """Age LSPs every second"""
        while True:
            try:
                await asyncio.sleep(1)
                self._age_lsps()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in aging loop: {e}")

    def _age_lsps(self) -> None:
        """Decrement lifetime of all LSPs and remove expired ones"""
        expired = []

        for lsp_id, lsp in self._lsps.items():
            # Don't age local LSPs (we refresh them)
            if lsp.is_local:
                continue

            lsp.decrement_lifetime()

            if lsp.is_expired():
                expired.append(lsp_id)

        # Remove expired LSPs
        for lsp_id in expired:
            self.logger.info(f"LSP {lsp_id} expired")
            self.remove_lsp(lsp_id)
            if self.on_lsp_expired:
                self.on_lsp_expired(lsp_id)

    def get_csnp_entries(self) -> List[Dict[str, Any]]:
        """
        Get LSP summary entries for CSNP.

        Returns list of {lsp_id, sequence_number, remaining_lifetime, checksum}
        """
        entries = []
        for lsp_id, lsp in sorted(self._lsps.items()):
            entries.append({
                "lsp_id": lsp_id,
                "sequence_number": lsp.sequence_number,
                "remaining_lifetime": lsp.remaining_lifetime,
                "checksum": lsp.checksum,
            })
        return entries

    def compare_csnp(self, remote_entries: List[Dict[str, Any]]) -> tuple:
        """
        Compare received CSNP with our database.

        Args:
            remote_entries: List of LSP summaries from CSNP

        Returns:
            Tuple of (missing_locally, missing_remotely, different)
            - missing_locally: LSP IDs we need to request
            - missing_remotely: LSP IDs remote needs
            - different: LSP IDs where we have newer version
        """
        remote_dict = {e["lsp_id"]: e for e in remote_entries}
        local_ids = set(self._lsps.keys())
        remote_ids = set(remote_dict.keys())

        missing_locally = list(remote_ids - local_ids)
        missing_remotely = list(local_ids - remote_ids)
        different = []

        for lsp_id in local_ids & remote_ids:
            local_lsp = self._lsps[lsp_id]
            remote_entry = remote_dict[lsp_id]

            if local_lsp.sequence_number > remote_entry["sequence_number"]:
                different.append(lsp_id)

        return missing_locally, missing_remotely, different

    def get_statistics(self) -> Dict[str, Any]:
        """Get LSDB statistics"""
        local_count = sum(1 for lsp in self._lsps.values() if lsp.is_local)
        remote_count = len(self._lsps) - local_count

        return {
            "level": self.level,
            "total_lsps": len(self._lsps),
            "local_lsps": local_count,
            "remote_lsps": remote_count,
            "registered_neighbors": len(self._srm),
        }


class DualLSDB:
    """
    Manages both Level 1 and Level 2 LSDBs.

    Provides unified interface for L1/L2 routers.
    """

    def __init__(self, system_id: str, level: int = LEVEL_1_2):
        """
        Initialize dual LSDB.

        Args:
            system_id: Local router's system ID
            level: Router's IS-IS level (1, 2, or 3 for L1/L2)
        """
        self.system_id = system_id
        self.level = level

        # Create LSDBs based on level
        self.l1_lsdb: Optional[LSDB] = None
        self.l2_lsdb: Optional[LSDB] = None

        if level in (LEVEL_1, LEVEL_1_2):
            self.l1_lsdb = LSDB(system_id, LEVEL_1)

        if level in (LEVEL_2, LEVEL_1_2):
            self.l2_lsdb = LSDB(system_id, LEVEL_2)

        self.logger = logging.getLogger("DualLSDB")

    def get_lsdb(self, level: int) -> Optional[LSDB]:
        """Get LSDB for specific level"""
        if level == LEVEL_1:
            return self.l1_lsdb
        elif level == LEVEL_2:
            return self.l2_lsdb
        return None

    def install_lsp(self, lsp: LSP) -> bool:
        """Install LSP in appropriate database"""
        lsdb = self.get_lsdb(lsp.level)
        if lsdb:
            return lsdb.install_lsp(lsp)
        return False

    def get_lsp(self, lsp_id: str, level: int) -> Optional[LSP]:
        """Get LSP from specific level database"""
        lsdb = self.get_lsdb(level)
        if lsdb:
            return lsdb.get_lsp(lsp_id)
        return None

    async def start(self) -> None:
        """Start both LSDBs"""
        if self.l1_lsdb:
            await self.l1_lsdb.start_aging()
        if self.l2_lsdb:
            await self.l2_lsdb.start_aging()

    async def stop(self) -> None:
        """Stop both LSDBs"""
        if self.l1_lsdb:
            await self.l1_lsdb.stop()
        if self.l2_lsdb:
            await self.l2_lsdb.stop()

    def get_statistics(self) -> Dict[str, Any]:
        """Get combined statistics"""
        stats = {
            "system_id": self.system_id,
            "level": self.level,
        }

        if self.l1_lsdb:
            stats["level_1"] = self.l1_lsdb.get_statistics()

        if self.l2_lsdb:
            stats["level_2"] = self.l2_lsdb.get_statistics()

        return stats
