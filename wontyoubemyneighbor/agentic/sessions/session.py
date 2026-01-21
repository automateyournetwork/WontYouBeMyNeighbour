"""
Session Management

Provides:
- Session lifecycle management
- Multi-device sessions
- Session metadata
- Expiration handling
"""

import uuid
import hashlib
import secrets
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from enum import Enum


class SessionStatus(Enum):
    """Session status"""
    ACTIVE = "active"
    IDLE = "idle"
    EXPIRED = "expired"
    REVOKED = "revoked"
    LOCKED = "locked"


@dataclass
class Session:
    """Represents a user session"""

    id: str
    user_id: str
    tenant_id: Optional[str] = None
    status: SessionStatus = SessionStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    device_id: Optional[str] = None
    device_type: str = "unknown"  # web, mobile, api, cli
    location: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    refresh_token: Optional[str] = None
    access_count: int = 0

    @property
    def is_active(self) -> bool:
        """Check if session is active"""
        if self.status != SessionStatus.ACTIVE:
            return False
        if self.expires_at and datetime.now() > self.expires_at:
            return False
        return True

    @property
    def is_expired(self) -> bool:
        """Check if session is expired"""
        if self.status == SessionStatus.EXPIRED:
            return True
        if self.expires_at and datetime.now() > self.expires_at:
            return True
        return False

    @property
    def duration_seconds(self) -> int:
        """Get session duration in seconds"""
        return int((datetime.now() - self.created_at).total_seconds())

    @property
    def idle_seconds(self) -> int:
        """Get idle time in seconds"""
        return int((datetime.now() - self.last_activity).total_seconds())

    def touch(self) -> None:
        """Update last activity"""
        self.last_activity = datetime.now()
        self.access_count += 1

    def to_dict(self) -> dict:
        """Serialize to dictionary"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "device_id": self.device_id,
            "device_type": self.device_type,
            "location": self.location,
            "metadata": self.metadata,
            "access_count": self.access_count,
            "is_active": self.is_active,
            "duration_seconds": self.duration_seconds,
            "idle_seconds": self.idle_seconds
        }


class SessionManager:
    """Manages user sessions"""

    def __init__(self):
        self.sessions: Dict[str, Session] = {}
        self.user_sessions: Dict[str, List[str]] = {}  # user_id -> [session_ids]
        self.device_sessions: Dict[str, str] = {}  # device_id -> session_id

        # Configuration
        self.default_ttl = timedelta(hours=24)
        self.idle_timeout = timedelta(hours=1)
        self.max_sessions_per_user = 10
        self.allow_concurrent = True

    def create_session(
        self,
        user_id: str,
        tenant_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        device_id: Optional[str] = None,
        device_type: str = "web",
        ttl: Optional[timedelta] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Session:
        """Create a new session"""
        # Check concurrent session limit
        user_session_ids = self.user_sessions.get(user_id, [])
        active_sessions = [
            self.sessions[sid] for sid in user_session_ids
            if sid in self.sessions and self.sessions[sid].is_active
        ]

        if not self.allow_concurrent and active_sessions:
            # Revoke existing sessions
            for session in active_sessions:
                self.revoke_session(session.id)

        elif len(active_sessions) >= self.max_sessions_per_user:
            # Revoke oldest session
            oldest = min(active_sessions, key=lambda s: s.created_at)
            self.revoke_session(oldest.id)

        # Handle device-based sessions
        if device_id and device_id in self.device_sessions:
            existing_session_id = self.device_sessions[device_id]
            if existing_session_id in self.sessions:
                self.revoke_session(existing_session_id)

        # Generate session ID
        session_id = f"ses_{uuid.uuid4().hex[:16]}"

        # Generate refresh token
        refresh_token = secrets.token_urlsafe(32)

        # Calculate expiration
        session_ttl = ttl or self.default_ttl
        expires_at = datetime.now() + session_ttl

        session = Session(
            id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
            status=SessionStatus.ACTIVE,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
            device_id=device_id,
            device_type=device_type,
            metadata=metadata or {},
            refresh_token=refresh_token
        )

        self.sessions[session_id] = session

        # Track user sessions
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = []
        self.user_sessions[user_id].append(session_id)

        # Track device sessions
        if device_id:
            self.device_sessions[device_id] = session_id

        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get session by ID"""
        session = self.sessions.get(session_id)
        if session:
            # Check expiration
            if session.is_expired and session.status == SessionStatus.ACTIVE:
                session.status = SessionStatus.EXPIRED
            # Check idle timeout
            elif (session.idle_seconds > self.idle_timeout.total_seconds() and
                  session.status == SessionStatus.ACTIVE):
                session.status = SessionStatus.IDLE
        return session

    def validate_session(self, session_id: str) -> tuple[bool, Optional[str]]:
        """Validate a session, returns (valid, reason)"""
        session = self.get_session(session_id)

        if not session:
            return False, "Session not found"

        if session.status == SessionStatus.EXPIRED:
            return False, "Session expired"

        if session.status == SessionStatus.REVOKED:
            return False, "Session revoked"

        if session.status == SessionStatus.LOCKED:
            return False, "Session locked"

        if session.status == SessionStatus.IDLE:
            # Allow reactivation on validation
            session.status = SessionStatus.ACTIVE

        if not session.is_active:
            return False, "Session not active"

        # Touch session
        session.touch()

        return True, None

    def refresh_session(
        self,
        session_id: str,
        refresh_token: str,
        ttl: Optional[timedelta] = None
    ) -> Optional[Session]:
        """Refresh a session using refresh token"""
        session = self.get_session(session_id)

        if not session:
            return None

        if session.refresh_token != refresh_token:
            return None

        if session.status == SessionStatus.REVOKED:
            return None

        # Refresh
        session_ttl = ttl or self.default_ttl
        session.expires_at = datetime.now() + session_ttl
        session.refresh_token = secrets.token_urlsafe(32)
        session.status = SessionStatus.ACTIVE
        session.touch()

        return session

    def revoke_session(self, session_id: str, reason: str = "") -> bool:
        """Revoke a session"""
        session = self.get_session(session_id)

        if not session:
            return False

        session.status = SessionStatus.REVOKED
        session.metadata["revoked_reason"] = reason
        session.metadata["revoked_at"] = datetime.now().isoformat()

        return True

    def lock_session(self, session_id: str, reason: str = "") -> bool:
        """Lock a session (requires re-authentication)"""
        session = self.get_session(session_id)

        if not session:
            return False

        session.status = SessionStatus.LOCKED
        session.metadata["locked_reason"] = reason
        session.metadata["locked_at"] = datetime.now().isoformat()

        return True

    def unlock_session(self, session_id: str) -> bool:
        """Unlock a session"""
        session = self.get_session(session_id)

        if not session:
            return False

        if session.status != SessionStatus.LOCKED:
            return False

        session.status = SessionStatus.ACTIVE
        session.metadata["unlocked_at"] = datetime.now().isoformat()

        return True

    def get_user_sessions(self, user_id: str, active_only: bool = True) -> List[Session]:
        """Get all sessions for a user"""
        session_ids = self.user_sessions.get(user_id, [])
        sessions = [self.sessions[sid] for sid in session_ids if sid in self.sessions]

        if active_only:
            sessions = [s for s in sessions if s.is_active]

        return sorted(sessions, key=lambda s: s.last_activity, reverse=True)

    def revoke_user_sessions(self, user_id: str, except_session: Optional[str] = None) -> int:
        """Revoke all sessions for a user"""
        count = 0
        for session in self.get_user_sessions(user_id, active_only=False):
            if session.id != except_session:
                if self.revoke_session(session.id, "User-initiated revocation"):
                    count += 1
        return count

    def revoke_tenant_sessions(self, tenant_id: str) -> int:
        """Revoke all sessions for a tenant"""
        count = 0
        for session in self.sessions.values():
            if session.tenant_id == tenant_id and session.is_active:
                if self.revoke_session(session.id, "Tenant-initiated revocation"):
                    count += 1
        return count

    def cleanup_expired(self) -> int:
        """Clean up expired sessions"""
        count = 0
        for session_id, session in list(self.sessions.items()):
            if session.is_expired:
                session.status = SessionStatus.EXPIRED
                count += 1
        return count

    def get_active_session_count(self) -> int:
        """Get count of active sessions"""
        return len([s for s in self.sessions.values() if s.is_active])

    def get_statistics(self) -> dict:
        """Get session statistics"""
        sessions = list(self.sessions.values())
        active = [s for s in sessions if s.status == SessionStatus.ACTIVE]
        idle = [s for s in sessions if s.status == SessionStatus.IDLE]
        expired = [s for s in sessions if s.status == SessionStatus.EXPIRED]
        revoked = [s for s in sessions if s.status == SessionStatus.REVOKED]
        locked = [s for s in sessions if s.status == SessionStatus.LOCKED]

        # Device type breakdown
        device_types: Dict[str, int] = {}
        for session in active:
            device_types[session.device_type] = device_types.get(session.device_type, 0) + 1

        # Average session duration
        avg_duration = 0
        if active:
            avg_duration = sum(s.duration_seconds for s in active) / len(active)

        return {
            "total_sessions": len(sessions),
            "active": len(active),
            "idle": len(idle),
            "expired": len(expired),
            "revoked": len(revoked),
            "locked": len(locked),
            "unique_users": len(set(s.user_id for s in active)),
            "by_device_type": device_types,
            "avg_duration_seconds": int(avg_duration),
            "max_sessions_per_user": self.max_sessions_per_user,
            "default_ttl_hours": self.default_ttl.total_seconds() / 3600,
            "idle_timeout_minutes": self.idle_timeout.total_seconds() / 60
        }


# Global session manager instance
_session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    """Get or create the global session manager"""
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager
