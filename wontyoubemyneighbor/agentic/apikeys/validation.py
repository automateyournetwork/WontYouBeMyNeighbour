"""
API Key Validation

Provides:
- Key validation and verification
- Scope checking
- Rate limit integration
- Validation result handling
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum

from .key import APIKey, APIKeyStatus, get_key_manager


class ValidationErrorCode(Enum):
    """Validation error codes"""
    VALID = "valid"
    MISSING_KEY = "missing_key"
    INVALID_FORMAT = "invalid_format"
    KEY_NOT_FOUND = "key_not_found"
    KEY_EXPIRED = "key_expired"
    KEY_REVOKED = "key_revoked"
    KEY_SUSPENDED = "key_suspended"
    KEY_INACTIVE = "key_inactive"
    INSUFFICIENT_SCOPE = "insufficient_scope"
    RATE_LIMITED = "rate_limited"
    TENANT_MISMATCH = "tenant_mismatch"


@dataclass
class ValidationResult:
    """Result of key validation"""

    valid: bool
    error_code: ValidationErrorCode = ValidationErrorCode.VALID
    error_message: str = ""
    key: Optional[APIKey] = None
    missing_scopes: List[str] = field(default_factory=list)
    rate_limit_info: Optional[Dict[str, Any]] = None

    def to_dict(self) -> dict:
        """Serialize to dictionary"""
        result = {
            "valid": self.valid,
            "error_code": self.error_code.value,
            "error_message": self.error_message
        }
        if self.key:
            result["key_id"] = self.key.id
            result["key_name"] = self.key.name
            result["scopes"] = list(self.key.scopes)
        if self.missing_scopes:
            result["missing_scopes"] = self.missing_scopes
        if self.rate_limit_info:
            result["rate_limit_info"] = self.rate_limit_info
        return result


class KeyValidator:
    """Validates API keys"""

    def __init__(self):
        self.key_manager = get_key_manager()
        self.validation_log: List[Dict[str, Any]] = []
        self._max_log_size = 10000

    def validate(
        self,
        api_key: Optional[str],
        required_scopes: Optional[List[str]] = None,
        tenant_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        check_rate_limit: bool = True
    ) -> ValidationResult:
        """
        Validate an API key.

        Args:
            api_key: The plain text API key
            required_scopes: Scopes required for this request
            tenant_id: Expected tenant ID (if multi-tenant)
            ip_address: Client IP address for logging
            check_rate_limit: Whether to check rate limits

        Returns:
            ValidationResult with validation status
        """
        # Check if key is provided
        if not api_key:
            return self._create_result(
                False,
                ValidationErrorCode.MISSING_KEY,
                "API key is required"
            )

        # Check key format
        if not api_key.startswith("adn_"):
            return self._create_result(
                False,
                ValidationErrorCode.INVALID_FORMAT,
                "Invalid API key format"
            )

        # Look up key
        key = self.key_manager.get_key_by_value(api_key)
        if not key:
            self._log_validation(None, False, "not_found", ip_address)
            return self._create_result(
                False,
                ValidationErrorCode.KEY_NOT_FOUND,
                "API key not found"
            )

        # Check key status
        if key.status == APIKeyStatus.REVOKED:
            self._log_validation(key.id, False, "revoked", ip_address)
            return self._create_result(
                False,
                ValidationErrorCode.KEY_REVOKED,
                "API key has been revoked",
                key=key
            )

        if key.status == APIKeyStatus.SUSPENDED:
            self._log_validation(key.id, False, "suspended", ip_address)
            return self._create_result(
                False,
                ValidationErrorCode.KEY_SUSPENDED,
                "API key is suspended",
                key=key
            )

        if key.status == APIKeyStatus.INACTIVE:
            self._log_validation(key.id, False, "inactive", ip_address)
            return self._create_result(
                False,
                ValidationErrorCode.KEY_INACTIVE,
                "API key is inactive",
                key=key
            )

        # Check expiration
        if key.expires_at and datetime.now() > key.expires_at:
            self._log_validation(key.id, False, "expired", ip_address)
            return self._create_result(
                False,
                ValidationErrorCode.KEY_EXPIRED,
                "API key has expired",
                key=key
            )

        # Check tenant
        if tenant_id and key.tenant_id and key.tenant_id != tenant_id:
            self._log_validation(key.id, False, "tenant_mismatch", ip_address)
            return self._create_result(
                False,
                ValidationErrorCode.TENANT_MISMATCH,
                "API key does not belong to this tenant",
                key=key
            )

        # Check scopes
        if required_scopes:
            missing = [s for s in required_scopes if not key.has_scope(s)]
            if missing:
                self._log_validation(key.id, False, "insufficient_scope", ip_address)
                return self._create_result(
                    False,
                    ValidationErrorCode.INSUFFICIENT_SCOPE,
                    f"Missing required scopes: {', '.join(missing)}",
                    key=key,
                    missing_scopes=missing
                )

        # Check rate limit
        rate_limit_info = None
        if check_rate_limit:
            rate_limit_info = self._check_rate_limit(key)
            if rate_limit_info and not rate_limit_info.get("allowed", True):
                self._log_validation(key.id, False, "rate_limited", ip_address)
                return self._create_result(
                    False,
                    ValidationErrorCode.RATE_LIMITED,
                    "Rate limit exceeded",
                    key=key,
                    rate_limit_info=rate_limit_info
                )

        # Key is valid - record usage
        key.record_usage(ip_address)
        self._log_validation(key.id, True, "valid", ip_address)

        return self._create_result(
            True,
            ValidationErrorCode.VALID,
            "Key is valid",
            key=key,
            rate_limit_info=rate_limit_info
        )

    def validate_scope(
        self,
        api_key: str,
        scope: str
    ) -> bool:
        """Quick check if key has a specific scope"""
        key = self.key_manager.get_key_by_value(api_key)
        if not key or not key.is_valid():
            return False
        return key.has_scope(scope)

    def get_key_info(self, api_key: str) -> Optional[Dict[str, Any]]:
        """Get information about a key without full validation"""
        key = self.key_manager.get_key_by_value(api_key)
        if key:
            return key.to_dict()
        return None

    def get_validation_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent validation log entries"""
        return self.validation_log[-limit:]

    def get_statistics(self) -> dict:
        """Get validation statistics"""
        valid_count = len([v for v in self.validation_log if v["valid"]])
        invalid_count = len(self.validation_log) - valid_count

        # Group by error code
        error_counts: Dict[str, int] = {}
        for entry in self.validation_log:
            reason = entry.get("reason", "unknown")
            error_counts[reason] = error_counts.get(reason, 0) + 1

        return {
            "total_validations": len(self.validation_log),
            "valid_count": valid_count,
            "invalid_count": invalid_count,
            "success_rate": valid_count / len(self.validation_log)
            if self.validation_log else 0.0,
            "error_breakdown": error_counts
        }

    def _create_result(
        self,
        valid: bool,
        error_code: ValidationErrorCode,
        message: str,
        key: Optional[APIKey] = None,
        missing_scopes: Optional[List[str]] = None,
        rate_limit_info: Optional[Dict[str, Any]] = None
    ) -> ValidationResult:
        """Create a validation result"""
        return ValidationResult(
            valid=valid,
            error_code=error_code,
            error_message=message,
            key=key,
            missing_scopes=missing_scopes or [],
            rate_limit_info=rate_limit_info
        )

    def _check_rate_limit(self, key: APIKey) -> Optional[Dict[str, Any]]:
        """Check rate limit for a key"""
        try:
            from agentic.ratelimit import get_rate_limiter
            limiter = get_rate_limiter()
            result = limiter.consume(key.id, tier=key.rate_limit_tier)
            return result.to_dict()
        except ImportError:
            return None

    def _log_validation(
        self,
        key_id: Optional[str],
        valid: bool,
        reason: str,
        ip_address: Optional[str]
    ) -> None:
        """Log a validation attempt"""
        self.validation_log.append({
            "key_id": key_id,
            "valid": valid,
            "reason": reason,
            "ip_address": ip_address,
            "timestamp": datetime.now()
        })

        # Trim log if too large
        if len(self.validation_log) > self._max_log_size:
            self.validation_log = self.validation_log[-self._max_log_size // 2:]


# Global validator instance
_key_validator: Optional[KeyValidator] = None


def get_key_validator() -> KeyValidator:
    """Get or create the global key validator"""
    global _key_validator
    if _key_validator is None:
        _key_validator = KeyValidator()
    return _key_validator
