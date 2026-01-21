"""
Sliding Window Rate Limiting Implementation

Provides:
- Sliding window counter algorithm
- Fixed window fallback
- Per-key window management
- Configurable time windows
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime
from enum import Enum


class WindowType(Enum):
    """Window algorithm types"""
    FIXED = "fixed"
    SLIDING = "sliding"
    SLIDING_LOG = "sliding_log"


@dataclass
class WindowConfig:
    """Configuration for a rate limit window"""

    window_size_seconds: int  # Window duration
    max_requests: int  # Maximum requests per window
    window_type: WindowType = WindowType.SLIDING
    burst_multiplier: float = 1.5  # Allow bursts up to this multiplier

    def to_dict(self) -> dict:
        return {
            "window_size_seconds": self.window_size_seconds,
            "max_requests": self.max_requests,
            "window_type": self.window_type.value,
            "burst_multiplier": self.burst_multiplier
        }


@dataclass
class SlidingWindow:
    """Sliding window for rate limiting"""

    key: str
    config: WindowConfig
    # For sliding log: list of request timestamps
    request_log: List[float] = field(default_factory=list)
    # For fixed window: counter and window start
    fixed_counter: int = 0
    fixed_window_start: float = field(default_factory=time.time)
    # For sliding counter: current and previous window counts
    current_count: int = 0
    previous_count: int = 0
    current_window_start: float = field(default_factory=time.time)
    created_at: datetime = field(default_factory=datetime.now)

    def _clean_log(self) -> None:
        """Remove expired entries from log"""
        cutoff = time.time() - self.config.window_size_seconds
        self.request_log = [ts for ts in self.request_log if ts > cutoff]

    def _update_sliding_counter(self) -> None:
        """Update sliding window counters"""
        now = time.time()
        window_start = now - (now % self.config.window_size_seconds)

        # Check if we've moved to a new window
        if window_start > self.current_window_start:
            # Move current to previous
            self.previous_count = self.current_count
            self.current_count = 0
            self.current_window_start = window_start

    def is_allowed(self, cost: int = 1) -> bool:
        """Check if request is allowed"""
        if self.config.window_type == WindowType.FIXED:
            return self._is_allowed_fixed(cost)
        elif self.config.window_type == WindowType.SLIDING_LOG:
            return self._is_allowed_sliding_log(cost)
        else:  # SLIDING (counter)
            return self._is_allowed_sliding_counter(cost)

    def _is_allowed_fixed(self, cost: int) -> bool:
        """Fixed window algorithm"""
        now = time.time()

        # Check if window has expired
        if now - self.fixed_window_start >= self.config.window_size_seconds:
            self.fixed_counter = 0
            self.fixed_window_start = now

        if self.fixed_counter + cost <= self.config.max_requests:
            self.fixed_counter += cost
            return True
        return False

    def _is_allowed_sliding_log(self, cost: int) -> bool:
        """Sliding log algorithm (most accurate, more memory)"""
        self._clean_log()

        # Calculate effective limit with burst
        effective_limit = int(self.config.max_requests * self.config.burst_multiplier)

        if len(self.request_log) + cost <= effective_limit:
            # Add timestamps for cost
            now = time.time()
            for _ in range(cost):
                self.request_log.append(now)
            return True
        return False

    def _is_allowed_sliding_counter(self, cost: int) -> bool:
        """Sliding window counter algorithm (good accuracy, low memory)"""
        self._update_sliding_counter()

        now = time.time()
        window_progress = (now % self.config.window_size_seconds) / self.config.window_size_seconds

        # Weighted count from previous and current window
        weighted_count = (
            self.previous_count * (1 - window_progress) +
            self.current_count
        )

        # Calculate effective limit with burst
        effective_limit = self.config.max_requests * self.config.burst_multiplier

        if weighted_count + cost <= effective_limit:
            self.current_count += cost
            return True
        return False

    def get_remaining(self) -> int:
        """Get remaining requests in current window"""
        if self.config.window_type == WindowType.FIXED:
            return max(0, self.config.max_requests - self.fixed_counter)
        elif self.config.window_type == WindowType.SLIDING_LOG:
            self._clean_log()
            return max(0, self.config.max_requests - len(self.request_log))
        else:  # SLIDING counter
            self._update_sliding_counter()
            now = time.time()
            window_progress = (now % self.config.window_size_seconds) / self.config.window_size_seconds
            weighted_count = (
                self.previous_count * (1 - window_progress) +
                self.current_count
            )
            return max(0, int(self.config.max_requests - weighted_count))

    def get_reset_time(self) -> float:
        """Get seconds until window resets"""
        now = time.time()

        if self.config.window_type == WindowType.FIXED:
            elapsed = now - self.fixed_window_start
            return max(0, self.config.window_size_seconds - elapsed)
        else:
            # For sliding windows, reset is the window size
            return float(self.config.window_size_seconds)

    def reset(self) -> None:
        """Reset the window"""
        now = time.time()
        self.request_log = []
        self.fixed_counter = 0
        self.fixed_window_start = now
        self.current_count = 0
        self.previous_count = 0
        self.current_window_start = now

    def to_dict(self) -> dict:
        """Serialize to dictionary"""
        return {
            "key": self.key,
            "config": self.config.to_dict(),
            "remaining": self.get_remaining(),
            "reset_in_seconds": self.get_reset_time(),
            "created_at": self.created_at.isoformat()
        }


class WindowManager:
    """Manages sliding windows for rate limiting"""

    def __init__(self):
        self.windows: Dict[str, SlidingWindow] = {}
        self._cleanup_interval = 300  # 5 minutes
        self._last_cleanup = time.time()
        self._window_ttl = 3600  # 1 hour inactive TTL

    def get_or_create_window(
        self,
        key: str,
        config: WindowConfig
    ) -> SlidingWindow:
        """Get existing window or create new one"""
        self._maybe_cleanup()

        if key not in self.windows:
            self.windows[key] = SlidingWindow(key=key, config=config)

        return self.windows[key]

    def get_window(self, key: str) -> Optional[SlidingWindow]:
        """Get window by key"""
        return self.windows.get(key)

    def is_allowed(
        self,
        key: str,
        config: WindowConfig,
        cost: int = 1
    ) -> bool:
        """Check if request is allowed"""
        window = self.get_or_create_window(key, config)
        return window.is_allowed(cost)

    def check(
        self,
        key: str,
        config: WindowConfig
    ) -> dict:
        """Check rate limit status without consuming"""
        window = self.get_or_create_window(key, config)

        return {
            "allowed": window.get_remaining() > 0,
            "remaining": window.get_remaining(),
            "limit": config.max_requests,
            "reset_in_seconds": window.get_reset_time()
        }

    def delete_window(self, key: str) -> bool:
        """Delete a window"""
        if key in self.windows:
            del self.windows[key]
            return True
        return False

    def reset_window(self, key: str) -> bool:
        """Reset a window"""
        if key in self.windows:
            self.windows[key].reset()
            return True
        return False

    def list_windows(self) -> list:
        """List all windows"""
        return [window.to_dict() for window in self.windows.values()]

    def get_statistics(self) -> dict:
        """Get window manager statistics"""
        total_remaining = sum(w.get_remaining() for w in self.windows.values())
        total_limit = sum(w.config.max_requests for w in self.windows.values())

        return {
            "window_count": len(self.windows),
            "total_limit": total_limit,
            "total_remaining": total_remaining,
            "utilization": 1.0 - (total_remaining / total_limit) if total_limit > 0 else 0.0
        }

    def _maybe_cleanup(self) -> None:
        """Cleanup stale windows periodically"""
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return

        self._last_cleanup = now
        stale_keys = []

        for key, window in self.windows.items():
            # Remove windows that have been fully reset for TTL period
            if now - window.current_window_start > self._window_ttl:
                stale_keys.append(key)

        for key in stale_keys:
            del self.windows[key]


# Global window manager instance
_window_manager: Optional[WindowManager] = None


def get_window_manager() -> WindowManager:
    """Get or create the global window manager"""
    global _window_manager
    if _window_manager is None:
        _window_manager = WindowManager()
    return _window_manager
