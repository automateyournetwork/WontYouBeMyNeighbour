"""
API Key Management

Provides:
- API key generation
- Key storage and retrieval
- Key rotation
- Scope management
"""

import secrets
import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta
from enum import Enum


class APIKeyScope(Enum):
    """API key permission scopes"""
    # Read scopes
    READ_AGENTS = "read:agents"
    READ_NETWORKS = "read:networks"
    READ_PROTOCOLS = "read:protocols"
    READ_ROUTES = "read:routes"
    READ_HEALTH = "read:health"
    READ_LOGS = "read:logs"
    READ_METRICS = "read:metrics"
    READ_CONFIG = "read:config"

    # Write scopes
    WRITE_AGENTS = "write:agents"
    WRITE_NETWORKS = "write:networks"
    WRITE_CONFIG = "write:config"

    # Execute scopes
    EXEC_TESTS = "exec:tests"
    EXEC_CHAOS = "exec:chaos"
    EXEC_TRAFFIC = "exec:traffic"
    EXEC_REMEDIATION = "exec:remediation"

    # Admin scopes
    ADMIN_USERS = "admin:users"
    ADMIN_TENANTS = "admin:tenants"
    ADMIN_KEYS = "admin:keys"
    ADMIN_ALL = "admin:*"

    # Wildcard scopes
    READ_ALL = "read:*"
    WRITE_ALL = "write:*"
    EXEC_ALL = "exec:*"
    ALL = "*"


class APIKeyStatus(Enum):
    """API key status"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    EXPIRED = "expired"
    REVOKED = "revoked"
    SUSPENDED = "suspended"


@dataclass
class APIKey:
    """API key representation"""

    id: str
    name: str
    key_hash: str  # Hashed key (never store plain text)
    key_prefix: str  # First 8 chars for identification
    owner_id: str  # User or service account ID
    tenant_id: Optional[str] = None
    scopes: Set[str] = field(default_factory=set)
    status: APIKeyStatus = APIKeyStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    last_used_ip: Optional[str] = None
    description: str = ""
    metadata: Dict[str, str] = field(default_factory=dict)
    rate_limit_tier: str = "standard"
    usage_count: int = 0

    def is_valid(self) -> bool:
        """Check if key is valid for use"""
        if self.status != APIKeyStatus.ACTIVE:
            return False
        if self.expires_at and datetime.now() > self.expires_at:
            return False
        return True

    def has_scope(self, required_scope: str) -> bool:
        """Check if key has required scope"""
        # Check for wildcard
        if APIKeyScope.ALL.value in self.scopes:
            return True

        # Check category wildcard (e.g., read:* covers read:agents)
        category = required_scope.split(":")[0] if ":" in required_scope else None
        if category:
            wildcard = f"{category}:*"
            if wildcard in self.scopes:
                return True

        # Check exact match
        return required_scope in self.scopes

    def has_any_scope(self, scopes: List[str]) -> bool:
        """Check if key has any of the required scopes"""
        return any(self.has_scope(s) for s in scopes)

    def has_all_scopes(self, scopes: List[str]) -> bool:
        """Check if key has all required scopes"""
        return all(self.has_scope(s) for s in scopes)

    def record_usage(self, ip_address: Optional[str] = None) -> None:
        """Record key usage"""
        self.last_used_at = datetime.now()
        self.last_used_ip = ip_address
        self.usage_count += 1

    def to_dict(self, include_sensitive: bool = False) -> dict:
        """Serialize to dictionary"""
        result = {
            "id": self.id,
            "name": self.name,
            "key_prefix": self.key_prefix,
            "owner_id": self.owner_id,
            "tenant_id": self.tenant_id,
            "scopes": list(self.scopes),
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "description": self.description,
            "rate_limit_tier": self.rate_limit_tier,
            "usage_count": self.usage_count,
            "is_valid": self.is_valid()
        }
        if include_sensitive:
            result["last_used_ip"] = self.last_used_ip
            result["metadata"] = self.metadata
        return result


class KeyManager:
    """Manages API keys"""

    # Default scope sets
    SCOPE_PRESETS = {
        "read_only": {
            APIKeyScope.READ_AGENTS.value,
            APIKeyScope.READ_NETWORKS.value,
            APIKeyScope.READ_PROTOCOLS.value,
            APIKeyScope.READ_ROUTES.value,
            APIKeyScope.READ_HEALTH.value,
            APIKeyScope.READ_LOGS.value,
            APIKeyScope.READ_METRICS.value
        },
        "operator": {
            APIKeyScope.READ_ALL.value,
            APIKeyScope.EXEC_TESTS.value,
            APIKeyScope.EXEC_TRAFFIC.value
        },
        "developer": {
            APIKeyScope.READ_ALL.value,
            APIKeyScope.WRITE_AGENTS.value,
            APIKeyScope.WRITE_NETWORKS.value,
            APIKeyScope.EXEC_TESTS.value
        },
        "admin": {
            APIKeyScope.ALL.value
        },
        "service": {
            APIKeyScope.READ_ALL.value,
            APIKeyScope.EXEC_ALL.value
        }
    }

    def __init__(self):
        self.keys: Dict[str, APIKey] = {}
        self._key_index: Dict[str, str] = {}  # key_hash -> key_id
        self._owner_index: Dict[str, List[str]] = {}  # owner_id -> [key_ids]

    def generate_key(
        self,
        name: str,
        owner_id: str,
        scopes: Optional[Set[str]] = None,
        preset: Optional[str] = None,
        tenant_id: Optional[str] = None,
        expires_in_days: Optional[int] = None,
        description: str = "",
        rate_limit_tier: str = "standard",
        metadata: Optional[Dict[str, str]] = None
    ) -> tuple:
        """
        Generate a new API key.
        Returns (APIKey, plain_text_key) - plain key only shown once!
        """
        # Generate secure key
        plain_key = f"adn_{secrets.token_urlsafe(32)}"
        key_hash = self._hash_key(plain_key)
        key_prefix = plain_key[:12]

        # Generate unique ID
        key_id = f"key_{secrets.token_hex(8)}"

        # Determine scopes
        if preset and preset in self.SCOPE_PRESETS:
            key_scopes = set(self.SCOPE_PRESETS[preset])
        elif scopes:
            key_scopes = scopes
        else:
            key_scopes = set(self.SCOPE_PRESETS["read_only"])

        # Calculate expiration
        expires_at = None
        if expires_in_days:
            expires_at = datetime.now() + timedelta(days=expires_in_days)

        # Create key object
        api_key = APIKey(
            id=key_id,
            name=name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            owner_id=owner_id,
            tenant_id=tenant_id,
            scopes=key_scopes,
            expires_at=expires_at,
            description=description,
            rate_limit_tier=rate_limit_tier,
            metadata=metadata or {}
        )

        # Store key
        self.keys[key_id] = api_key
        self._key_index[key_hash] = key_id

        # Update owner index
        if owner_id not in self._owner_index:
            self._owner_index[owner_id] = []
        self._owner_index[owner_id].append(key_id)

        return api_key, plain_key

    def get_key(self, key_id: str) -> Optional[APIKey]:
        """Get key by ID"""
        return self.keys.get(key_id)

    def get_key_by_value(self, plain_key: str) -> Optional[APIKey]:
        """Get key by plain text value"""
        key_hash = self._hash_key(plain_key)
        key_id = self._key_index.get(key_hash)
        return self.keys.get(key_id) if key_id else None

    def list_keys(
        self,
        owner_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        status: Optional[APIKeyStatus] = None,
        include_expired: bool = False
    ) -> List[APIKey]:
        """List API keys with optional filters"""
        keys = list(self.keys.values())

        if owner_id:
            keys = [k for k in keys if k.owner_id == owner_id]

        if tenant_id:
            keys = [k for k in keys if k.tenant_id == tenant_id]

        if status:
            keys = [k for k in keys if k.status == status]

        if not include_expired:
            keys = [k for k in keys if k.is_valid() or k.status != APIKeyStatus.EXPIRED]

        return keys

    def get_keys_by_owner(self, owner_id: str) -> List[APIKey]:
        """Get all keys for an owner"""
        key_ids = self._owner_index.get(owner_id, [])
        return [self.keys[kid] for kid in key_ids if kid in self.keys]

    def revoke_key(self, key_id: str, reason: str = "") -> bool:
        """Revoke an API key"""
        if key_id not in self.keys:
            return False

        key = self.keys[key_id]
        key.status = APIKeyStatus.REVOKED
        key.metadata["revoked_reason"] = reason
        key.metadata["revoked_at"] = datetime.now().isoformat()
        return True

    def suspend_key(self, key_id: str, reason: str = "") -> bool:
        """Suspend an API key temporarily"""
        if key_id not in self.keys:
            return False

        key = self.keys[key_id]
        key.status = APIKeyStatus.SUSPENDED
        key.metadata["suspended_reason"] = reason
        key.metadata["suspended_at"] = datetime.now().isoformat()
        return True

    def reactivate_key(self, key_id: str) -> bool:
        """Reactivate a suspended key"""
        if key_id not in self.keys:
            return False

        key = self.keys[key_id]
        if key.status != APIKeyStatus.SUSPENDED:
            return False

        key.status = APIKeyStatus.ACTIVE
        key.metadata["reactivated_at"] = datetime.now().isoformat()
        return True

    def rotate_key(self, key_id: str) -> Optional[tuple]:
        """
        Rotate a key - creates new key, revokes old one.
        Returns (new_APIKey, plain_text_key) or None if failed.
        """
        if key_id not in self.keys:
            return None

        old_key = self.keys[key_id]

        # Create new key with same properties
        new_key, plain_key = self.generate_key(
            name=f"{old_key.name} (rotated)",
            owner_id=old_key.owner_id,
            scopes=old_key.scopes,
            tenant_id=old_key.tenant_id,
            description=old_key.description,
            rate_limit_tier=old_key.rate_limit_tier,
            metadata={"rotated_from": key_id}
        )

        # Revoke old key
        self.revoke_key(key_id, "Rotated")

        return new_key, plain_key

    def update_scopes(self, key_id: str, scopes: Set[str]) -> bool:
        """Update key scopes"""
        if key_id not in self.keys:
            return False

        self.keys[key_id].scopes = scopes
        return True

    def add_scopes(self, key_id: str, scopes: Set[str]) -> bool:
        """Add scopes to key"""
        if key_id not in self.keys:
            return False

        self.keys[key_id].scopes.update(scopes)
        return True

    def remove_scopes(self, key_id: str, scopes: Set[str]) -> bool:
        """Remove scopes from key"""
        if key_id not in self.keys:
            return False

        self.keys[key_id].scopes -= scopes
        return True

    def extend_expiration(self, key_id: str, days: int) -> bool:
        """Extend key expiration"""
        if key_id not in self.keys:
            return False

        key = self.keys[key_id]
        if key.expires_at:
            key.expires_at = key.expires_at + timedelta(days=days)
        else:
            key.expires_at = datetime.now() + timedelta(days=days)
        return True

    def delete_key(self, key_id: str) -> bool:
        """Permanently delete a key"""
        if key_id not in self.keys:
            return False

        key = self.keys[key_id]

        # Remove from indexes
        if key.key_hash in self._key_index:
            del self._key_index[key.key_hash]

        if key.owner_id in self._owner_index:
            self._owner_index[key.owner_id] = [
                k for k in self._owner_index[key.owner_id] if k != key_id
            ]

        del self.keys[key_id]
        return True

    def get_scope_presets(self) -> Dict[str, List[str]]:
        """Get available scope presets"""
        return {name: list(scopes) for name, scopes in self.SCOPE_PRESETS.items()}

    def get_all_scopes(self) -> List[dict]:
        """Get all available scopes"""
        return [
            {"value": scope.value, "name": scope.name}
            for scope in APIKeyScope
        ]

    def get_statistics(self) -> dict:
        """Get key manager statistics"""
        active_keys = [k for k in self.keys.values() if k.status == APIKeyStatus.ACTIVE]
        expired_keys = [k for k in self.keys.values()
                        if k.expires_at and datetime.now() > k.expires_at]

        return {
            "total_keys": len(self.keys),
            "active_keys": len(active_keys),
            "expired_keys": len(expired_keys),
            "revoked_keys": len([k for k in self.keys.values()
                                 if k.status == APIKeyStatus.REVOKED]),
            "suspended_keys": len([k for k in self.keys.values()
                                   if k.status == APIKeyStatus.SUSPENDED]),
            "unique_owners": len(self._owner_index),
            "total_usage": sum(k.usage_count for k in self.keys.values())
        }

    def cleanup_expired(self) -> int:
        """Mark expired keys and return count"""
        count = 0
        now = datetime.now()

        for key in self.keys.values():
            if (key.status == APIKeyStatus.ACTIVE and
                    key.expires_at and now > key.expires_at):
                key.status = APIKeyStatus.EXPIRED
                count += 1

        return count

    def _hash_key(self, plain_key: str) -> str:
        """Hash a plain text key"""
        return hashlib.sha256(plain_key.encode()).hexdigest()


# Global key manager instance
_key_manager: Optional[KeyManager] = None


def get_key_manager() -> KeyManager:
    """Get or create the global key manager"""
    global _key_manager
    if _key_manager is None:
        _key_manager = KeyManager()
    return _key_manager
