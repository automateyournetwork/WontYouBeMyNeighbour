"""
JWT Token Management

Provides:
- JWT token generation
- Token validation
- Token refresh
- Claims management
"""

import json
import hmac
import hashlib
import base64
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from enum import Enum


class TokenType(Enum):
    """Token types"""
    ACCESS = "access"
    REFRESH = "refresh"
    API_KEY = "api_key"
    PASSWORD_RESET = "password_reset"
    EMAIL_VERIFY = "email_verify"
    INVITE = "invite"


@dataclass
class TokenPayload:
    """JWT token payload"""

    sub: str  # Subject (user_id)
    iss: str = "adn-platform"  # Issuer
    aud: str = "adn-api"  # Audience
    exp: int = 0  # Expiration timestamp
    iat: int = 0  # Issued at timestamp
    nbf: int = 0  # Not before timestamp
    jti: str = ""  # JWT ID
    typ: str = "access"  # Token type
    tenant_id: Optional[str] = None
    session_id: Optional[str] = None
    roles: List[str] = field(default_factory=list)
    scopes: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        now = int(datetime.now().timestamp())
        if self.iat == 0:
            self.iat = now
        if self.nbf == 0:
            self.nbf = now

    def to_dict(self) -> dict:
        """Serialize to dictionary"""
        result = {
            "sub": self.sub,
            "iss": self.iss,
            "aud": self.aud,
            "exp": self.exp,
            "iat": self.iat,
            "nbf": self.nbf,
            "jti": self.jti,
            "typ": self.typ
        }
        if self.tenant_id:
            result["tenant_id"] = self.tenant_id
        if self.session_id:
            result["session_id"] = self.session_id
        if self.roles:
            result["roles"] = self.roles
        if self.scopes:
            result["scopes"] = self.scopes
        if self.metadata:
            result["metadata"] = self.metadata
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "TokenPayload":
        """Create from dictionary"""
        return cls(
            sub=data.get("sub", ""),
            iss=data.get("iss", "adn-platform"),
            aud=data.get("aud", "adn-api"),
            exp=data.get("exp", 0),
            iat=data.get("iat", 0),
            nbf=data.get("nbf", 0),
            jti=data.get("jti", ""),
            typ=data.get("typ", "access"),
            tenant_id=data.get("tenant_id"),
            session_id=data.get("session_id"),
            roles=data.get("roles", []),
            scopes=data.get("scopes", []),
            metadata=data.get("metadata", {})
        )

    @property
    def is_expired(self) -> bool:
        """Check if token is expired"""
        return datetime.now().timestamp() > self.exp

    @property
    def is_valid_time(self) -> bool:
        """Check if token is within valid time window"""
        now = datetime.now().timestamp()
        return self.nbf <= now <= self.exp


@dataclass
class TokenValidationResult:
    """Result of token validation"""

    valid: bool
    payload: Optional[TokenPayload] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "payload": self.payload.to_dict() if self.payload else None,
            "error": self.error
        }


class TokenManager:
    """Manages JWT tokens"""

    def __init__(self, secret_key: Optional[str] = None):
        self.secret_key = secret_key or "adn-platform-secret-key-change-in-production"
        self.algorithm = "HS256"

        # Token TTLs
        self.access_token_ttl = timedelta(minutes=15)
        self.refresh_token_ttl = timedelta(days=7)
        self.api_key_ttl = timedelta(days=365)
        self.password_reset_ttl = timedelta(hours=1)
        self.email_verify_ttl = timedelta(hours=24)
        self.invite_ttl = timedelta(days=7)

        # Revoked tokens (JTI)
        self.revoked_tokens: Dict[str, datetime] = {}

        # Token counter for JTI
        self._token_counter = 0

    def generate_token(
        self,
        user_id: str,
        token_type: TokenType = TokenType.ACCESS,
        tenant_id: Optional[str] = None,
        session_id: Optional[str] = None,
        roles: Optional[List[str]] = None,
        scopes: Optional[List[str]] = None,
        ttl: Optional[timedelta] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Generate a JWT token"""
        # Determine TTL
        if ttl is None:
            ttl = self._get_default_ttl(token_type)

        now = datetime.now()
        exp = now + ttl

        # Generate JTI
        self._token_counter += 1
        jti = f"{token_type.value}_{int(now.timestamp())}_{self._token_counter}"

        payload = TokenPayload(
            sub=user_id,
            exp=int(exp.timestamp()),
            iat=int(now.timestamp()),
            nbf=int(now.timestamp()),
            jti=jti,
            typ=token_type.value,
            tenant_id=tenant_id,
            session_id=session_id,
            roles=roles or [],
            scopes=scopes or [],
            metadata=metadata or {}
        )

        return self._encode(payload)

    def generate_access_token(
        self,
        user_id: str,
        tenant_id: Optional[str] = None,
        session_id: Optional[str] = None,
        roles: Optional[List[str]] = None,
        scopes: Optional[List[str]] = None
    ) -> str:
        """Generate an access token"""
        return self.generate_token(
            user_id=user_id,
            token_type=TokenType.ACCESS,
            tenant_id=tenant_id,
            session_id=session_id,
            roles=roles,
            scopes=scopes
        )

    def generate_refresh_token(
        self,
        user_id: str,
        tenant_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> str:
        """Generate a refresh token"""
        return self.generate_token(
            user_id=user_id,
            token_type=TokenType.REFRESH,
            tenant_id=tenant_id,
            session_id=session_id
        )

    def generate_token_pair(
        self,
        user_id: str,
        tenant_id: Optional[str] = None,
        session_id: Optional[str] = None,
        roles: Optional[List[str]] = None,
        scopes: Optional[List[str]] = None
    ) -> Dict[str, str]:
        """Generate access and refresh token pair"""
        return {
            "access_token": self.generate_access_token(
                user_id, tenant_id, session_id, roles, scopes
            ),
            "refresh_token": self.generate_refresh_token(
                user_id, tenant_id, session_id
            ),
            "token_type": "Bearer",
            "expires_in": int(self.access_token_ttl.total_seconds())
        }

    def validate_token(self, token: str) -> TokenValidationResult:
        """Validate a JWT token"""
        try:
            payload = self._decode(token)

            if not payload:
                return TokenValidationResult(valid=False, error="Invalid token format")

            # Check expiration
            if payload.is_expired:
                return TokenValidationResult(valid=False, error="Token expired")

            # Check not before
            if not payload.is_valid_time:
                return TokenValidationResult(valid=False, error="Token not yet valid")

            # Check revocation
            if payload.jti in self.revoked_tokens:
                return TokenValidationResult(valid=False, error="Token revoked")

            return TokenValidationResult(valid=True, payload=payload)

        except Exception as e:
            return TokenValidationResult(valid=False, error=str(e))

    def decode_token(self, token: str) -> Optional[TokenPayload]:
        """Decode a token without validation"""
        return self._decode(token)

    def refresh_access_token(self, refresh_token: str) -> Optional[Dict[str, str]]:
        """Refresh an access token using a refresh token"""
        result = self.validate_token(refresh_token)

        if not result.valid or not result.payload:
            return None

        if result.payload.typ != TokenType.REFRESH.value:
            return None

        # Generate new access token
        return {
            "access_token": self.generate_access_token(
                user_id=result.payload.sub,
                tenant_id=result.payload.tenant_id,
                session_id=result.payload.session_id,
                roles=result.payload.roles,
                scopes=result.payload.scopes
            ),
            "token_type": "Bearer",
            "expires_in": int(self.access_token_ttl.total_seconds())
        }

    def revoke_token(self, token: str) -> bool:
        """Revoke a token"""
        payload = self._decode(token)
        if not payload:
            return False

        self.revoked_tokens[payload.jti] = datetime.now()
        return True

    def revoke_by_jti(self, jti: str) -> bool:
        """Revoke a token by JTI"""
        self.revoked_tokens[jti] = datetime.now()
        return True

    def cleanup_revoked(self, max_age_hours: int = 24) -> int:
        """Clean up old revoked tokens"""
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        old_count = len(self.revoked_tokens)

        self.revoked_tokens = {
            jti: revoked_at
            for jti, revoked_at in self.revoked_tokens.items()
            if revoked_at > cutoff
        }

        return old_count - len(self.revoked_tokens)

    def get_statistics(self) -> dict:
        """Get token manager statistics"""
        return {
            "revoked_tokens": len(self.revoked_tokens),
            "tokens_generated": self._token_counter,
            "access_token_ttl_minutes": self.access_token_ttl.total_seconds() / 60,
            "refresh_token_ttl_days": self.refresh_token_ttl.total_seconds() / 86400,
            "algorithm": self.algorithm
        }

    def _get_default_ttl(self, token_type: TokenType) -> timedelta:
        """Get default TTL for token type"""
        ttls = {
            TokenType.ACCESS: self.access_token_ttl,
            TokenType.REFRESH: self.refresh_token_ttl,
            TokenType.API_KEY: self.api_key_ttl,
            TokenType.PASSWORD_RESET: self.password_reset_ttl,
            TokenType.EMAIL_VERIFY: self.email_verify_ttl,
            TokenType.INVITE: self.invite_ttl
        }
        return ttls.get(token_type, self.access_token_ttl)

    def _encode(self, payload: TokenPayload) -> str:
        """Encode payload to JWT"""
        # Header
        header = {"alg": self.algorithm, "typ": "JWT"}
        header_b64 = self._base64url_encode(json.dumps(header))

        # Payload
        payload_b64 = self._base64url_encode(json.dumps(payload.to_dict()))

        # Signature
        message = f"{header_b64}.{payload_b64}"
        signature = hmac.new(
            self.secret_key.encode(),
            message.encode(),
            hashlib.sha256
        ).digest()
        signature_b64 = self._base64url_encode_bytes(signature)

        return f"{header_b64}.{payload_b64}.{signature_b64}"

    def _decode(self, token: str) -> Optional[TokenPayload]:
        """Decode JWT to payload"""
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return None

            header_b64, payload_b64, signature_b64 = parts

            # Verify signature
            message = f"{header_b64}.{payload_b64}"
            expected_sig = hmac.new(
                self.secret_key.encode(),
                message.encode(),
                hashlib.sha256
            ).digest()

            actual_sig = self._base64url_decode_bytes(signature_b64)
            if not hmac.compare_digest(expected_sig, actual_sig):
                return None

            # Decode payload
            payload_json = self._base64url_decode(payload_b64)
            payload_data = json.loads(payload_json)

            return TokenPayload.from_dict(payload_data)

        except Exception:
            return None

    def _base64url_encode(self, data: str) -> str:
        """Base64URL encode string"""
        return base64.urlsafe_b64encode(data.encode()).rstrip(b"=").decode()

    def _base64url_encode_bytes(self, data: bytes) -> str:
        """Base64URL encode bytes"""
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    def _base64url_decode(self, data: str) -> str:
        """Base64URL decode to string"""
        # Add padding
        padding = 4 - (len(data) % 4)
        if padding != 4:
            data += "=" * padding
        return base64.urlsafe_b64decode(data).decode()

    def _base64url_decode_bytes(self, data: str) -> bytes:
        """Base64URL decode to bytes"""
        # Add padding
        padding = 4 - (len(data) % 4)
        if padding != 4:
            data += "=" * padding
        return base64.urlsafe_b64decode(data)


# Global token manager instance
_token_manager: Optional[TokenManager] = None


def get_token_manager() -> TokenManager:
    """Get or create the global token manager"""
    global _token_manager
    if _token_manager is None:
        _token_manager = TokenManager()
    return _token_manager
