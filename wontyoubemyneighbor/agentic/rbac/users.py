"""
User Management - User accounts for RBAC

Provides:
- User creation and management
- User status tracking
- User-role associations
- User metadata and preferences
"""

import logging
import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Set

logger = logging.getLogger("UserManager")


class UserStatus(Enum):
    """User account status"""
    PENDING = "pending"           # Account created, awaiting verification
    ACTIVE = "active"             # Account active and usable
    SUSPENDED = "suspended"       # Account temporarily suspended
    LOCKED = "locked"             # Account locked (too many failed attempts)
    DISABLED = "disabled"         # Account disabled


@dataclass
class UserSession:
    """
    User session information

    Attributes:
        session_id: Unique session identifier
        user_id: User this session belongs to
        created_at: Session creation time
        expires_at: Session expiration time
        ip_address: Client IP address
        user_agent: Client user agent
    """
    session_id: str
    user_id: str
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime = field(default_factory=lambda: datetime.now() + timedelta(hours=8))
    ip_address: str = ""
    user_agent: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "is_expired": self.is_expired,
            "ip_address": self.ip_address,
            "metadata": self.metadata
        }


@dataclass
class User:
    """
    A user account

    Attributes:
        user_id: Unique identifier
        username: Login username
        email: User email address
        display_name: Display name
        status: Account status
        role_ids: Assigned role IDs
        tenant_id: Associated tenant
    """
    user_id: str
    username: str
    email: str
    display_name: str = ""
    status: UserStatus = UserStatus.PENDING
    role_ids: Set[str] = field(default_factory=set)
    tenant_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    last_login: Optional[datetime] = None
    failed_login_attempts: int = 0
    password_hash: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE

    @property
    def is_locked(self) -> bool:
        return self.status == UserStatus.LOCKED

    def has_role(self, role_id: str) -> bool:
        """Check if user has a specific role"""
        return role_id in self.role_ids

    def add_role(self, role_id: str):
        """Add a role to the user"""
        self.role_ids.add(role_id)

    def remove_role(self, role_id: str):
        """Remove a role from the user"""
        self.role_ids.discard(role_id)

    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        result = {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "display_name": self.display_name,
            "status": self.status.value,
            "role_ids": list(self.role_ids),
            "tenant_id": self.tenant_id,
            "created_at": self.created_at.isoformat(),
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "metadata": self.metadata
        }
        if include_sensitive:
            result["failed_login_attempts"] = self.failed_login_attempts
        return result


class UserManager:
    """
    Manages user accounts
    """

    def __init__(self, max_failed_attempts: int = 5):
        """
        Initialize user manager

        Args:
            max_failed_attempts: Max failed logins before lock
        """
        self._users: Dict[str, User] = {}
        self._sessions: Dict[str, UserSession] = {}
        self._user_counter = 0
        self._max_failed_attempts = max_failed_attempts

        # Create default admin user
        self._create_default_admin()

    def _generate_user_id(self) -> str:
        """Generate unique user ID"""
        self._user_counter += 1
        return f"user-{self._user_counter:06d}"

    def _generate_session_id(self) -> str:
        """Generate secure session ID"""
        return secrets.token_urlsafe(32)

    def _hash_password(self, password: str) -> str:
        """Hash a password"""
        salt = "asi-salt"  # In production, use per-user salt
        return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()

    def _create_default_admin(self):
        """Create default admin user"""
        admin = User(
            user_id="user-admin",
            username="admin",
            email="admin@localhost",
            display_name="Administrator",
            status=UserStatus.ACTIVE,
            role_ids={"role-admin"},
            password_hash=self._hash_password("admin")
        )
        self._users[admin.user_id] = admin
        self._users[admin.username] = admin  # Index by username too
        logger.info("Created default admin user")

    def create_user(
        self,
        username: str,
        email: str,
        password: str,
        display_name: str = "",
        role_ids: Optional[Set[str]] = None,
        tenant_id: Optional[str] = None,
        auto_activate: bool = False
    ) -> User:
        """
        Create a new user

        Args:
            username: Login username
            email: Email address
            password: Password (will be hashed)
            display_name: Display name
            role_ids: Initial roles
            tenant_id: Associated tenant
            auto_activate: Activate immediately

        Returns:
            Created User
        """
        user = User(
            user_id=self._generate_user_id(),
            username=username,
            email=email,
            display_name=display_name or username,
            status=UserStatus.ACTIVE if auto_activate else UserStatus.PENDING,
            role_ids=role_ids or {"role-viewer"},
            tenant_id=tenant_id,
            password_hash=self._hash_password(password)
        )

        self._users[user.user_id] = user
        self._users[username] = user  # Index by username
        logger.info(f"Created user: {username}")
        return user

    def get_user(self, user_id: str) -> Optional[User]:
        """Get a user by ID or username"""
        return self._users.get(user_id)

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get a user by email"""
        for user in self._users.values():
            if isinstance(user, User) and user.email == email:
                return user
        return None

    def get_all_users(self) -> List[User]:
        """Get all users"""
        return [u for u in self._users.values() if isinstance(u, User)]

    def get_users_by_tenant(self, tenant_id: str) -> List[User]:
        """Get users for a tenant"""
        return [
            u for u in self._users.values()
            if isinstance(u, User) and u.tenant_id == tenant_id
        ]

    def authenticate(
        self,
        username: str,
        password: str,
        ip_address: str = "",
        user_agent: str = ""
    ) -> Optional[UserSession]:
        """
        Authenticate a user

        Args:
            username: Username
            password: Password
            ip_address: Client IP
            user_agent: Client user agent

        Returns:
            UserSession if successful, None otherwise
        """
        user = self._users.get(username)
        if not user or not isinstance(user, User):
            return None

        # Check if locked
        if user.is_locked:
            logger.warning(f"Login attempt on locked account: {username}")
            return None

        # Check if active
        if not user.is_active:
            logger.warning(f"Login attempt on inactive account: {username}")
            return None

        # Verify password
        if self._hash_password(password) != user.password_hash:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= self._max_failed_attempts:
                user.status = UserStatus.LOCKED
                logger.warning(f"Account locked due to failed attempts: {username}")
            return None

        # Successful login
        user.failed_login_attempts = 0
        user.last_login = datetime.now()

        # Create session
        session = UserSession(
            session_id=self._generate_session_id(),
            user_id=user.user_id,
            ip_address=ip_address,
            user_agent=user_agent
        )
        self._sessions[session.session_id] = session

        logger.info(f"User authenticated: {username}")
        return session

    def validate_session(self, session_id: str) -> Optional[User]:
        """
        Validate a session and return the user

        Args:
            session_id: Session ID to validate

        Returns:
            User if session valid, None otherwise
        """
        session = self._sessions.get(session_id)
        if not session or session.is_expired:
            return None

        return self._users.get(session.user_id)

    def logout(self, session_id: str) -> bool:
        """
        Logout a session

        Args:
            session_id: Session to logout

        Returns:
            True if session existed
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def activate_user(self, user_id: str) -> bool:
        """Activate a user account"""
        user = self._users.get(user_id)
        if not user or not isinstance(user, User):
            return False
        user.status = UserStatus.ACTIVE
        user.failed_login_attempts = 0
        logger.info(f"Activated user: {user.username}")
        return True

    def suspend_user(self, user_id: str) -> bool:
        """Suspend a user account"""
        user = self._users.get(user_id)
        if not user or not isinstance(user, User):
            return False
        user.status = UserStatus.SUSPENDED
        logger.info(f"Suspended user: {user.username}")
        return True

    def unlock_user(self, user_id: str) -> bool:
        """Unlock a locked user account"""
        user = self._users.get(user_id)
        if not user or not isinstance(user, User):
            return False
        if user.status == UserStatus.LOCKED:
            user.status = UserStatus.ACTIVE
            user.failed_login_attempts = 0
            logger.info(f"Unlocked user: {user.username}")
            return True
        return False

    def change_password(self, user_id: str, new_password: str) -> bool:
        """Change a user's password"""
        user = self._users.get(user_id)
        if not user or not isinstance(user, User):
            return False
        user.password_hash = self._hash_password(new_password)
        logger.info(f"Changed password for user: {user.username}")
        return True

    def assign_role(self, user_id: str, role_id: str) -> bool:
        """Assign a role to a user"""
        user = self._users.get(user_id)
        if not user or not isinstance(user, User):
            return False
        user.add_role(role_id)
        logger.info(f"Assigned role {role_id} to {user.username}")
        return True

    def revoke_role(self, user_id: str, role_id: str) -> bool:
        """Revoke a role from a user"""
        user = self._users.get(user_id)
        if not user or not isinstance(user, User):
            return False
        user.remove_role(role_id)
        logger.info(f"Revoked role {role_id} from {user.username}")
        return True

    def cleanup_expired_sessions(self):
        """Remove expired sessions"""
        expired = [sid for sid, s in self._sessions.items() if s.is_expired]
        for sid in expired:
            del self._sessions[sid]
        if expired:
            logger.debug(f"Cleaned up {len(expired)} expired sessions")

    def get_statistics(self) -> Dict[str, Any]:
        """Get user manager statistics"""
        users = self.get_all_users()
        by_status = {}
        for user in users:
            status = user.status.value
            by_status[status] = by_status.get(status, 0) + 1

        return {
            "total_users": len(users),
            "active_sessions": len([s for s in self._sessions.values() if not s.is_expired]),
            "users_by_status": by_status
        }


# Global manager instance
_global_manager: Optional[UserManager] = None


def get_user_manager() -> UserManager:
    """Get or create the global user manager"""
    global _global_manager
    if _global_manager is None:
        _global_manager = UserManager()
    return _global_manager
