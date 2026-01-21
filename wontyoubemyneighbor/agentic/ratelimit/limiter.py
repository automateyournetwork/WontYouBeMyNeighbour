"""
Rate Limiter - High-Level Rate Limiting API

Provides:
- Unified rate limiting interface
- Multiple algorithm support
- Per-user and per-tenant limits
- Configurable rate tiers
- Rate limit headers for API responses
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum

from .bucket import TokenBucket, BucketManager, get_bucket_manager
from .window import (
    SlidingWindow, WindowManager, WindowConfig, WindowType,
    get_window_manager
)


class RateLimitAlgorithm(Enum):
    """Available rate limiting algorithms"""
    TOKEN_BUCKET = "token_bucket"
    SLIDING_WINDOW = "sliding_window"
    FIXED_WINDOW = "fixed_window"
    SLIDING_LOG = "sliding_log"


@dataclass
class RateLimitConfig:
    """Rate limit configuration"""

    name: str
    requests_per_second: float = 10.0
    requests_per_minute: float = 600.0
    requests_per_hour: float = 36000.0
    burst_size: int = 50
    algorithm: RateLimitAlgorithm = RateLimitAlgorithm.SLIDING_WINDOW

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "requests_per_second": self.requests_per_second,
            "requests_per_minute": self.requests_per_minute,
            "requests_per_hour": self.requests_per_hour,
            "burst_size": self.burst_size,
            "algorithm": self.algorithm.value
        }


@dataclass
class RateLimitResult:
    """Result of a rate limit check"""

    allowed: bool
    remaining: int
    limit: int
    reset_seconds: float
    retry_after: Optional[float] = None

    def to_dict(self) -> dict:
        result = {
            "allowed": self.allowed,
            "remaining": self.remaining,
            "limit": self.limit,
            "reset_seconds": self.reset_seconds
        }
        if self.retry_after is not None:
            result["retry_after"] = self.retry_after
        return result

    def get_headers(self) -> Dict[str, str]:
        """Get rate limit headers for API response"""
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(self.remaining),
            "X-RateLimit-Reset": str(int(self.reset_seconds))
        }
        if not self.allowed and self.retry_after is not None:
            headers["Retry-After"] = str(int(self.retry_after))
        return headers


class RateLimiter:
    """High-level rate limiter with multiple algorithm support"""

    # Default rate limit tiers
    DEFAULT_TIERS = {
        "free": RateLimitConfig(
            name="free",
            requests_per_second=1.0,
            requests_per_minute=60.0,
            requests_per_hour=1000.0,
            burst_size=10
        ),
        "basic": RateLimitConfig(
            name="basic",
            requests_per_second=5.0,
            requests_per_minute=300.0,
            requests_per_hour=5000.0,
            burst_size=25
        ),
        "standard": RateLimitConfig(
            name="standard",
            requests_per_second=10.0,
            requests_per_minute=600.0,
            requests_per_hour=20000.0,
            burst_size=50
        ),
        "premium": RateLimitConfig(
            name="premium",
            requests_per_second=50.0,
            requests_per_minute=3000.0,
            requests_per_hour=100000.0,
            burst_size=200
        ),
        "enterprise": RateLimitConfig(
            name="enterprise",
            requests_per_second=200.0,
            requests_per_minute=12000.0,
            requests_per_hour=500000.0,
            burst_size=1000
        )
    }

    def __init__(self):
        self.bucket_manager = get_bucket_manager()
        self.window_manager = get_window_manager()
        self.tiers: Dict[str, RateLimitConfig] = dict(self.DEFAULT_TIERS)
        self.user_tiers: Dict[str, str] = {}  # user_id -> tier_name
        self.tenant_tiers: Dict[str, str] = {}  # tenant_id -> tier_name
        self.blocked_keys: Dict[str, datetime] = {}  # Temporarily blocked keys
        self.request_log: List[Dict[str, Any]] = []
        self._max_log_size = 10000

    def check(
        self,
        key: str,
        tier: Optional[str] = None,
        cost: int = 1
    ) -> RateLimitResult:
        """Check rate limit without consuming"""
        config = self._get_config(key, tier)

        if self._is_blocked(key):
            return RateLimitResult(
                allowed=False,
                remaining=0,
                limit=int(config.requests_per_minute),
                reset_seconds=60.0,
                retry_after=60.0
            )

        if config.algorithm == RateLimitAlgorithm.TOKEN_BUCKET:
            result = self.bucket_manager.check(
                key,
                tokens=cost,
                capacity=config.burst_size,
                refill_rate=config.requests_per_second
            )
            return RateLimitResult(
                allowed=result["allowed"],
                remaining=result["remaining"],
                limit=config.burst_size,
                reset_seconds=config.burst_size / config.requests_per_second,
                retry_after=result.get("retry_after")
            )
        else:
            window_config = self._get_window_config(config)
            result = self.window_manager.check(key, window_config)
            return RateLimitResult(
                allowed=result["allowed"],
                remaining=result["remaining"],
                limit=result["limit"],
                reset_seconds=result["reset_in_seconds"],
                retry_after=result["reset_in_seconds"] if not result["allowed"] else None
            )

    def consume(
        self,
        key: str,
        tier: Optional[str] = None,
        cost: int = 1
    ) -> RateLimitResult:
        """Consume rate limit and return result"""
        config = self._get_config(key, tier)

        if self._is_blocked(key):
            self._log_request(key, False, config.name)
            return RateLimitResult(
                allowed=False,
                remaining=0,
                limit=int(config.requests_per_minute),
                reset_seconds=60.0,
                retry_after=60.0
            )

        if config.algorithm == RateLimitAlgorithm.TOKEN_BUCKET:
            allowed = self.bucket_manager.consume(
                key,
                tokens=cost,
                capacity=config.burst_size,
                refill_rate=config.requests_per_second
            )
            bucket = self.bucket_manager.get_bucket(key)
            remaining = bucket.available_tokens() if bucket else 0
            retry_after = bucket.time_until_tokens(cost) if bucket and not allowed else None

            result = RateLimitResult(
                allowed=allowed,
                remaining=remaining,
                limit=config.burst_size,
                reset_seconds=config.burst_size / config.requests_per_second,
                retry_after=retry_after
            )
        else:
            window_config = self._get_window_config(config)
            allowed = self.window_manager.is_allowed(key, window_config, cost)
            window = self.window_manager.get_window(key)
            remaining = window.get_remaining() if window else 0
            reset_seconds = window.get_reset_time() if window else 60.0

            result = RateLimitResult(
                allowed=allowed,
                remaining=remaining,
                limit=window_config.max_requests,
                reset_seconds=reset_seconds,
                retry_after=reset_seconds if not allowed else None
            )

        self._log_request(key, result.allowed, config.name)
        return result

    def set_user_tier(self, user_id: str, tier: str) -> bool:
        """Set rate limit tier for a user"""
        if tier in self.tiers:
            self.user_tiers[user_id] = tier
            return True
        return False

    def set_tenant_tier(self, tenant_id: str, tier: str) -> bool:
        """Set rate limit tier for a tenant"""
        if tier in self.tiers:
            self.tenant_tiers[tenant_id] = tier
            return True
        return False

    def get_user_tier(self, user_id: str) -> str:
        """Get rate limit tier for a user"""
        return self.user_tiers.get(user_id, "standard")

    def get_tenant_tier(self, tenant_id: str) -> str:
        """Get rate limit tier for a tenant"""
        return self.tenant_tiers.get(tenant_id, "standard")

    def add_tier(self, config: RateLimitConfig) -> None:
        """Add or update a rate limit tier"""
        self.tiers[config.name] = config

    def remove_tier(self, name: str) -> bool:
        """Remove a rate limit tier (except defaults)"""
        if name in self.DEFAULT_TIERS:
            return False
        if name in self.tiers:
            del self.tiers[name]
            return True
        return False

    def get_tier(self, name: str) -> Optional[RateLimitConfig]:
        """Get a rate limit tier by name"""
        return self.tiers.get(name)

    def list_tiers(self) -> List[Dict[str, Any]]:
        """List all rate limit tiers"""
        return [config.to_dict() for config in self.tiers.values()]

    def block_key(self, key: str, duration_seconds: int = 3600) -> None:
        """Temporarily block a key"""
        from datetime import timedelta
        self.blocked_keys[key] = datetime.now() + timedelta(seconds=duration_seconds)

    def unblock_key(self, key: str) -> bool:
        """Unblock a key"""
        if key in self.blocked_keys:
            del self.blocked_keys[key]
            return True
        return False

    def reset_key(self, key: str) -> bool:
        """Reset rate limit for a key"""
        bucket_reset = self.bucket_manager.reset_bucket(key)
        window_reset = self.window_manager.reset_window(key)
        return bucket_reset or window_reset

    def get_statistics(self) -> dict:
        """Get rate limiter statistics"""
        # Count recent requests
        recent_requests = len([r for r in self.request_log
                               if (datetime.now() - r["timestamp"]).total_seconds() < 60])
        allowed_count = len([r for r in self.request_log
                             if r["allowed"] and
                             (datetime.now() - r["timestamp"]).total_seconds() < 60])
        denied_count = recent_requests - allowed_count

        return {
            "tiers": len(self.tiers),
            "user_assignments": len(self.user_tiers),
            "tenant_assignments": len(self.tenant_tiers),
            "blocked_keys": len(self.blocked_keys),
            "bucket_stats": self.bucket_manager.get_statistics(),
            "window_stats": self.window_manager.get_statistics(),
            "requests_last_minute": recent_requests,
            "allowed_last_minute": allowed_count,
            "denied_last_minute": denied_count,
            "denial_rate": denied_count / recent_requests if recent_requests > 0 else 0.0
        }

    def get_request_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent request log"""
        return self.request_log[-limit:]

    def _get_config(self, key: str, tier: Optional[str]) -> RateLimitConfig:
        """Get rate limit config for a key"""
        if tier and tier in self.tiers:
            return self.tiers[tier]

        # Check if key is a user or tenant
        if key in self.user_tiers:
            return self.tiers[self.user_tiers[key]]
        if key in self.tenant_tiers:
            return self.tiers[self.tenant_tiers[key]]

        # Default to standard tier
        return self.tiers["standard"]

    def _get_window_config(self, config: RateLimitConfig) -> WindowConfig:
        """Convert rate limit config to window config"""
        window_type = WindowType.SLIDING
        if config.algorithm == RateLimitAlgorithm.FIXED_WINDOW:
            window_type = WindowType.FIXED
        elif config.algorithm == RateLimitAlgorithm.SLIDING_LOG:
            window_type = WindowType.SLIDING_LOG

        return WindowConfig(
            window_size_seconds=60,  # Use minute window
            max_requests=int(config.requests_per_minute),
            window_type=window_type,
            burst_multiplier=config.burst_size / config.requests_per_minute
            if config.requests_per_minute > 0 else 1.5
        )

    def _is_blocked(self, key: str) -> bool:
        """Check if a key is blocked"""
        if key not in self.blocked_keys:
            return False

        if datetime.now() > self.blocked_keys[key]:
            # Block expired
            del self.blocked_keys[key]
            return False

        return True

    def _log_request(self, key: str, allowed: bool, tier: str) -> None:
        """Log a rate limit request"""
        self.request_log.append({
            "key": key,
            "allowed": allowed,
            "tier": tier,
            "timestamp": datetime.now()
        })

        # Trim log if too large
        if len(self.request_log) > self._max_log_size:
            self.request_log = self.request_log[-self._max_log_size // 2:]


# Global rate limiter instance
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get or create the global rate limiter"""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter
