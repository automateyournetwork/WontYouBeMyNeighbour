"""
OSPF Link State Database
RFC 2328 Section 12 - The Link State Advertisement
"""

import time
import logging
from typing import Dict, List, Optional, Tuple
from ospf.packets import LSAHeader, RouterLSA, NetworkLSA, RouterLink
from ospf.constants import (
    ROUTER_LSA, INITIAL_SEQUENCE_NUMBER, MAX_AGE,
    LINK_TYPE_STUB
)

logger = logging.getLogger(__name__)


class LSA:
    """
    Link State Advertisement container
    """

    def __init__(self, header: LSAHeader, body: Optional[object] = None):
        """
        Initialize LSA

        Args:
            header: LSA header
            body: LSA body (RouterLSA, NetworkLSA, etc.)
        """
        self.header = header
        self.body = body
        self.install_time = time.time()
        self.age = header.ls_age

    def get_key(self) -> Tuple[int, str, str]:
        """
        Get unique key for this LSA

        Returns:
            Tuple of (ls_type, link_state_id, advertising_router)
        """
        return (
            self.header.ls_type,
            self.header.link_state_id,
            self.header.advertising_router
        )

    def increment_age(self, seconds: int = 1):
        """
        Increment LSA age

        Args:
            seconds: Seconds to increment
        """
        self.age += seconds
        if self.age > MAX_AGE:
            self.age = MAX_AGE

    def is_maxage(self) -> bool:
        """
        Check if LSA has reached MaxAge

        Returns:
            True if age >= MAX_AGE
        """
        return self.age >= MAX_AGE

    def __repr__(self) -> str:
        return (f"LSA(type={self.header.ls_type}, "
                f"id={self.header.link_state_id}, "
                f"adv={self.header.advertising_router}, "
                f"seq={hex(self.header.ls_sequence_number)}, "
                f"age={self.age})")


class LinkStateDatabase:
    """
    OSPF Link State Database - stores all LSAs for an area
    """

    def __init__(self, area_id: str):
        """
        Initialize LSDB

        Args:
            area_id: OSPF area ID
        """
        self.area_id = area_id
        self.database: Dict[Tuple[int, str, str], LSA] = {}
        self.last_age_time = time.time()

        logger.info(f"Initialized LSDB for area {area_id}")

    def add_lsa(self, lsa_header: LSAHeader, lsa_body: Optional[object] = None) -> bool:
        """
        Add or update LSA in database

        Args:
            lsa_header: LSA header
            lsa_body: LSA body (optional)

        Returns:
            True if LSA was added/updated (newer), False if discarded (older/same)
        """
        key = (lsa_header.ls_type, lsa_header.link_state_id, lsa_header.advertising_router)

        # Check if we already have this LSA
        if key in self.database:
            existing = self.database[key]

            # Compare sequence numbers (RFC 2328 Section 13.1)
            if self._is_newer(lsa_header, existing.header):
                # New LSA is newer, replace
                self.database[key] = LSA(lsa_header, lsa_body)
                logger.info(f"Updated LSA in LSDB: {key}")
                return True
            else:
                # Existing LSA is newer or same, discard
                logger.debug(f"Discarded older/duplicate LSA: {key}")
                return False
        else:
            # New LSA
            self.database[key] = LSA(lsa_header, lsa_body)
            logger.info(f"Added new LSA to LSDB: {key}")
            return True

    def get_lsa(self, ls_type: int, ls_id: str, adv_router: str) -> Optional[LSA]:
        """
        Retrieve specific LSA from database

        Args:
            ls_type: LSA type
            ls_id: Link state ID
            adv_router: Advertising router

        Returns:
            LSA object or None if not found
        """
        key = (ls_type, ls_id, adv_router)
        return self.database.get(key)

    def get_all_lsas(self) -> List[LSA]:
        """
        Get all LSAs in database

        Returns:
            List of LSA objects
        """
        return list(self.database.values())

    def get_lsa_headers(self) -> List[LSAHeader]:
        """
        Get headers of all LSAs (for DBD exchange)

        For DBD exchange, we need to return headers with correct length values.
        The length should be the full LSA length (header + body).

        Returns:
            List of LSA headers with correct length values
        """
        headers = []
        for lsa in self.database.values():
            # Build a complete LSA to get correct length
            full_lsa = lsa.header / lsa.body
            full_lsa_bytes = bytes(full_lsa)
            lsa_length = len(full_lsa_bytes)

            # Create a new header with the correct length
            header = LSAHeader(
                ls_age=lsa.age,
                options=lsa.header.options,
                ls_type=lsa.header.ls_type,
                link_state_id=lsa.header.link_state_id,
                advertising_router=lsa.header.advertising_router,
                ls_sequence_number=lsa.header.ls_sequence_number,
                ls_checksum=lsa.header.ls_checksum,  # Keep original checksum
                length=lsa_length
            )
            headers.append(header)
        return headers

    def age_lsas(self) -> int:
        """
        Age all LSAs, remove MaxAge LSAs

        Returns:
            Number of LSAs aged out
        """
        now = time.time()
        elapsed = int(now - self.last_age_time)

        if elapsed < 1:
            return 0

        self.last_age_time = now
        max_age_lsas = []

        # Age all LSAs
        for key, lsa in self.database.items():
            lsa.increment_age(elapsed)

            if lsa.is_maxage():
                max_age_lsas.append(key)

        # Remove MaxAge LSAs
        for key in max_age_lsas:
            logger.info(f"Removing MaxAge LSA: {key}")
            del self.database[key]

        return len(max_age_lsas)

    def is_lsa_newer(self, lsa_header: LSAHeader) -> bool:
        """
        Check if given LSA is newer than what we have in LSDB

        Args:
            lsa_header: LSA header to check

        Returns:
            True if LSA is newer than what we have (or we don't have it)
        """
        key = (lsa_header.ls_type, lsa_header.link_state_id, lsa_header.advertising_router)

        # If we don't have this LSA, it's "newer" (we need it)
        if key not in self.database:
            return True

        # Compare with existing LSA
        existing = self.database[key]
        return self._is_newer(lsa_header, existing.header)

    def _is_newer(self, lsa1_header: LSAHeader, lsa2_header: LSAHeader) -> bool:
        """
        Determine if lsa1 is newer than lsa2 (RFC 2328 Section 13.1)

        Args:
            lsa1_header: First LSA header
            lsa2_header: Second LSA header

        Returns:
            True if lsa1 is newer
        """
        seq1 = lsa1_header.ls_sequence_number
        seq2 = lsa2_header.ls_sequence_number

        # Compare sequence numbers (higher = newer)
        if seq1 > seq2:
            return True
        elif seq1 < seq2:
            return False
        else:
            # Same sequence number, check checksum
            ck1 = lsa1_header.ls_checksum
            ck2 = lsa2_header.ls_checksum
            return ck1 > ck2

    def create_router_lsa(self, router_id: str, links: List[dict],
                         sequence_number: Optional[int] = None) -> Tuple[LSAHeader, RouterLSA]:
        """
        Generate Router LSA for this router

        Args:
            router_id: Router ID
            links: List of link dictionaries
            sequence_number: LSA sequence number (or None for initial)

        Returns:
            Tuple of (LSAHeader, RouterLSA)
        """
        if sequence_number is None:
            # Check if we have existing Router LSA
            existing = self.get_lsa(ROUTER_LSA, router_id, router_id)
            if existing:
                sequence_number = existing.header.ls_sequence_number + 1
            else:
                sequence_number = INITIAL_SEQUENCE_NUMBER

        # Build router links
        router_links = []
        for link in links:
            router_link = RouterLink(
                link_id=link.get('link_id', '0.0.0.0'),
                link_data=link.get('link_data', '0.0.0.0'),
                link_type=link.get('link_type', LINK_TYPE_STUB),
                metric=link.get('metric', 1)
            )
            router_links.append(router_link)

        # Build Router LSA body
        lsa_body = RouterLSA(
            v_bit=0,  # Not a virtual link endpoint
            e_bit=0,  # Not an AS boundary router
            b_bit=0,  # Not an area border router
            links=router_links
        )

        # Build LSA Header (length and checksum will be auto-calculated)
        lsa_header = LSAHeader(
            ls_age=0,
            ls_type=ROUTER_LSA,
            link_state_id=router_id,
            advertising_router=router_id,
            ls_sequence_number=sequence_number,
            length=None,  # Will be calculated when serialized
            ls_checksum=None  # Will be calculated when serialized
        )

        logger.info(f"Created Router LSA for {router_id} with {len(router_links)} links, seq={hex(sequence_number)}")

        return (lsa_header, lsa_body)

    def install_router_lsa(self, router_id: str, links: List[dict]) -> bool:
        """
        Create and install Router LSA in LSDB

        Args:
            router_id: Router ID
            links: List of link dictionaries

        Returns:
            True if installed successfully
        """
        lsa_header, lsa_body = self.create_router_lsa(router_id, links)
        return self.add_lsa(lsa_header, lsa_body)

    def get_size(self) -> int:
        """
        Get number of LSAs in database

        Returns:
            LSA count
        """
        return len(self.database)

    def get_router_lsas(self) -> List[LSA]:
        """
        Get all Router LSAs

        Returns:
            List of Router LSAs
        """
        return [lsa for lsa in self.database.values()
                if lsa.header.ls_type == ROUTER_LSA]

    def clear(self):
        """
        Clear all LSAs from database
        """
        count = len(self.database)
        self.database.clear()
        logger.info(f"Cleared {count} LSAs from LSDB")

    def __repr__(self) -> str:
        return f"LSDB(area={self.area_id}, lsas={len(self.database)})"
