"""
Token Bucket Algorithm Implementation

Provides:
- Token bucket rate limiting
- Configurable capacity and refill rate
- Burst allowance
- Per-key bucket management
"""

import time
from dataclasses import dataclass, field
from typing import Dict, Optional
from datetime import datetime


@dataclass
class TokenBucket:
    """Token bucket for rate limiting"""

    key: str
    capacity: int  # Maximum tokens
    refill_rate: float  # Tokens per second
    tokens: float = field(default=0.0)
    last_refill: float = field(default_factory=time.time)
    created_at: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """Initialize with full bucket"""
        if self.tokens == 0.0:
            self.tokens = float(self.capacity)

    def refill(self) -> None:
        """Refill tokens based on elapsed time"""
        now = time.time()
        elapsed = now - self.last_refill
        self.tokens = min(
            self.capacity,
            self.tokens + (elapsed * self.refill_rate)
        )
        self.last_refill = now

    def consume(self, tokens: int = 1) -> bool:
        """
        Try to consume tokens.
        Returns True if tokens were consumed, False if not enough tokens.
        """
        self.refill()

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def available_tokens(self) -> int:
        """Get current available tokens (after refill)"""
        self.refill()
        return int(self.tokens)

    def time_until_tokens(self, tokens: int = 1) -> float:
        """Calculate time until specified tokens are available"""
        self.refill()

        if self.tokens >= tokens:
            return 0.0

        needed = tokens - self.tokens
        return needed / self.refill_rate

    def reset(self) -> None:
        """Reset bucket to full capacity"""
        self.tokens = float(self.capacity)
        self.last_refill = time.time()

    def to_dict(self) -> dict:
        """Serialize to dictionary"""
        return {
            "key": self.key,
            "capacity": self.capacity,
            "refill_rate": self.refill_rate,
            "tokens": self.available_tokens(),
            "created_at": self.created_at.isoformat()
        }


class BucketManager:
    """Manages token buckets for rate limiting"""

    def __init__(self):
        self.buckets: Dict[str, TokenBucket] = {}
        self._cleanup_interval = 300  # 5 minutes
        self._last_cleanup = time.time()
        self._bucket_ttl = 3600  # 1 hour inactive TTL

    def get_or_create_bucket(
        self,
        key: str,
        capacity: int = 100,
        refill_rate: float = 10.0
    ) -> TokenBucket:
        """Get existing bucket or create new one"""
        self._maybe_cleanup()

        if key not in self.buckets:
            self.buckets[key] = TokenBucket(
                key=key,
                capacity=capacity,
                refill_rate=refill_rate
            )

        return self.buckets[key]

    def get_bucket(self, key: str) -> Optional[TokenBucket]:
        """Get bucket by key"""
        return self.buckets.get(key)

    def consume(
        self,
        key: str,
        tokens: int = 1,
        capacity: int = 100,
        refill_rate: float = 10.0
    ) -> bool:
        """Consume tokens from bucket (creating if needed)"""
        bucket = self.get_or_create_bucket(key, capacity, refill_rate)
        return bucket.consume(tokens)

    def check(
        self,
        key: str,
        tokens: int = 1,
        capacity: int = 100,
        refill_rate: float = 10.0
    ) -> dict:
        """Check if tokens are available without consuming"""
        bucket = self.get_or_create_bucket(key, capacity, refill_rate)
        bucket.refill()

        return {
            "allowed": bucket.tokens >= tokens,
            "remaining": int(bucket.tokens),
            "limit": bucket.capacity,
            "retry_after": bucket.time_until_tokens(tokens) if bucket.tokens < tokens else 0.0
        }

    def delete_bucket(self, key: str) -> bool:
        """Delete a bucket"""
        if key in self.buckets:
            del self.buckets[key]
            return True
        return False

    def reset_bucket(self, key: str) -> bool:
        """Reset a bucket to full capacity"""
        if key in self.buckets:
            self.buckets[key].reset()
            return True
        return False

    def list_buckets(self) -> list:
        """List all buckets"""
        return [bucket.to_dict() for bucket in self.buckets.values()]

    def get_statistics(self) -> dict:
        """Get bucket manager statistics"""
        total_capacity = sum(b.capacity for b in self.buckets.values())
        total_tokens = sum(b.available_tokens() for b in self.buckets.values())

        return {
            "bucket_count": len(self.buckets),
            "total_capacity": total_capacity,
            "total_available_tokens": total_tokens,
            "utilization": 1.0 - (total_tokens / total_capacity) if total_capacity > 0 else 0.0
        }

    def _maybe_cleanup(self) -> None:
        """Cleanup stale buckets periodically"""
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return

        self._last_cleanup = now
        stale_keys = []

        for key, bucket in self.buckets.items():
            # Remove buckets that haven't been used in TTL period
            if now - bucket.last_refill > self._bucket_ttl:
                stale_keys.append(key)

        for key in stale_keys:
            del self.buckets[key]


# Global bucket manager instance
_bucket_manager: Optional[BucketManager] = None


def get_bucket_manager() -> BucketManager:
    """Get or create the global bucket manager"""
    global _bucket_manager
    if _bucket_manager is None:
        _bucket_manager = BucketManager()
    return _bucket_manager
