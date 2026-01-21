"""
Hook System

Provides:
- Hook definition
- Hook registration
- Hook execution
"""

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Awaitable, Union
from datetime import datetime
from enum import Enum
import asyncio


class HookType(Enum):
    """Types of hooks"""
    # Lifecycle hooks
    PRE_START = "pre_start"
    POST_START = "post_start"
    PRE_STOP = "pre_stop"
    POST_STOP = "post_stop"

    # Protocol hooks
    PRE_NEIGHBOR_UP = "pre_neighbor_up"
    POST_NEIGHBOR_UP = "post_neighbor_up"
    PRE_NEIGHBOR_DOWN = "pre_neighbor_down"
    POST_NEIGHBOR_DOWN = "post_neighbor_down"
    ROUTE_RECEIVED = "route_received"
    ROUTE_ADVERTISED = "route_advertised"

    # API hooks
    PRE_REQUEST = "pre_request"
    POST_REQUEST = "post_request"
    PRE_AUTH = "pre_auth"
    POST_AUTH = "post_auth"

    # Notification hooks
    PRE_NOTIFICATION = "pre_notification"
    POST_NOTIFICATION = "post_notification"

    # Job hooks
    PRE_JOB_RUN = "pre_job_run"
    POST_JOB_RUN = "post_job_run"

    # Config hooks
    PRE_CONFIG_CHANGE = "pre_config_change"
    POST_CONFIG_CHANGE = "post_config_change"

    # Custom hooks
    CUSTOM = "custom"


@dataclass
class HookResult:
    """Result of a hook execution"""

    hook_name: str
    success: bool
    modified_data: Optional[Any] = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    handler_name: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "hook_name": self.hook_name,
            "success": self.success,
            "modified_data": str(self.modified_data) if self.modified_data else None,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "handler_name": self.handler_name
        }


@dataclass
class Hook:
    """Hook definition"""

    id: str
    name: str
    hook_type: HookType
    description: str = ""
    plugin_id: Optional[str] = None
    priority: int = 100  # Lower = higher priority
    enabled: bool = True
    can_modify_data: bool = True
    can_prevent_action: bool = False
    handler: Optional[Callable] = None
    created_at: datetime = field(default_factory=datetime.now)
    last_executed_at: Optional[datetime] = None
    execution_count: int = 0
    failure_count: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "hook_type": self.hook_type.value,
            "description": self.description,
            "plugin_id": self.plugin_id,
            "priority": self.priority,
            "enabled": self.enabled,
            "can_modify_data": self.can_modify_data,
            "can_prevent_action": self.can_prevent_action,
            "created_at": self.created_at.isoformat(),
            "last_executed_at": self.last_executed_at.isoformat() if self.last_executed_at else None,
            "execution_count": self.execution_count,
            "failure_count": self.failure_count
        }


class HookManager:
    """Manages hooks for extensibility"""

    def __init__(self):
        self.hooks: Dict[str, Hook] = {}
        self._handlers: Dict[str, List[Hook]] = {}  # hook_type -> hooks

    def register_hook(
        self,
        name: str,
        hook_type: HookType,
        handler: Callable,
        description: str = "",
        plugin_id: Optional[str] = None,
        priority: int = 100,
        can_modify_data: bool = True,
        can_prevent_action: bool = False
    ) -> Hook:
        """Register a new hook"""
        hook_id = f"hook_{uuid.uuid4().hex[:8]}"

        hook = Hook(
            id=hook_id,
            name=name,
            hook_type=hook_type,
            description=description,
            plugin_id=plugin_id,
            priority=priority,
            can_modify_data=can_modify_data,
            can_prevent_action=can_prevent_action,
            handler=handler
        )

        self.hooks[hook_id] = hook

        # Add to type handlers
        type_key = hook_type.value
        if type_key not in self._handlers:
            self._handlers[type_key] = []
        self._handlers[type_key].append(hook)

        # Sort by priority
        self._handlers[type_key].sort(key=lambda h: h.priority)

        return hook

    def unregister_hook(self, hook_id: str) -> bool:
        """Unregister a hook"""
        hook = self.hooks.get(hook_id)
        if not hook:
            return False

        # Remove from type handlers
        type_key = hook.hook_type.value
        if type_key in self._handlers:
            self._handlers[type_key] = [h for h in self._handlers[type_key] if h.id != hook_id]

        del self.hooks[hook_id]
        return True

    def get_hook(self, hook_id: str) -> Optional[Hook]:
        """Get hook by ID"""
        return self.hooks.get(hook_id)

    def enable_hook(self, hook_id: str) -> bool:
        """Enable a hook"""
        hook = self.hooks.get(hook_id)
        if hook:
            hook.enabled = True
            return True
        return False

    def disable_hook(self, hook_id: str) -> bool:
        """Disable a hook"""
        hook = self.hooks.get(hook_id)
        if hook:
            hook.enabled = False
            return True
        return False

    def get_hooks_for_type(self, hook_type: HookType) -> List[Hook]:
        """Get all hooks for a type"""
        return self._handlers.get(hook_type.value, [])

    def get_hooks_for_plugin(self, plugin_id: str) -> List[Hook]:
        """Get all hooks for a plugin"""
        return [h for h in self.hooks.values() if h.plugin_id == plugin_id]

    async def execute(
        self,
        hook_type: HookType,
        data: Any = None,
        context: Optional[Dict[str, Any]] = None
    ) -> List[HookResult]:
        """Execute all hooks of a type"""
        results = []
        hooks = self.get_hooks_for_type(hook_type)

        modified_data = data
        for hook in hooks:
            if not hook.enabled:
                continue

            result = await self._execute_hook(hook, modified_data, context)
            results.append(result)

            # Update modified data if allowed
            if result.success and hook.can_modify_data and result.modified_data is not None:
                modified_data = result.modified_data

            # Check for prevention
            if not result.success and hook.can_prevent_action:
                # Stop execution chain
                break

        return results

    async def _execute_hook(
        self,
        hook: Hook,
        data: Any,
        context: Optional[Dict[str, Any]]
    ) -> HookResult:
        """Execute a single hook"""
        if not hook.handler:
            return HookResult(
                hook_name=hook.name,
                success=False,
                error="No handler defined"
            )

        start_time = datetime.now()
        try:
            # Check if handler is async
            if asyncio.iscoroutinefunction(hook.handler):
                result_data = await hook.handler(data, context or {})
            else:
                result_data = hook.handler(data, context or {})

            duration = (datetime.now() - start_time).total_seconds() * 1000

            hook.last_executed_at = datetime.now()
            hook.execution_count += 1

            return HookResult(
                hook_name=hook.name,
                success=True,
                modified_data=result_data,
                duration_ms=duration,
                handler_name=hook.name
            )

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds() * 1000
            hook.failure_count += 1

            return HookResult(
                hook_name=hook.name,
                success=False,
                error=str(e),
                duration_ms=duration,
                handler_name=hook.name
            )

    def execute_sync(
        self,
        hook_type: HookType,
        data: Any = None,
        context: Optional[Dict[str, Any]] = None
    ) -> List[HookResult]:
        """Execute hooks synchronously"""
        results = []
        hooks = self.get_hooks_for_type(hook_type)

        modified_data = data
        for hook in hooks:
            if not hook.enabled or not hook.handler:
                continue

            start_time = datetime.now()
            try:
                result_data = hook.handler(data, context or {})
                duration = (datetime.now() - start_time).total_seconds() * 1000

                hook.last_executed_at = datetime.now()
                hook.execution_count += 1

                result = HookResult(
                    hook_name=hook.name,
                    success=True,
                    modified_data=result_data,
                    duration_ms=duration,
                    handler_name=hook.name
                )

                if hook.can_modify_data and result_data is not None:
                    modified_data = result_data

            except Exception as e:
                duration = (datetime.now() - start_time).total_seconds() * 1000
                hook.failure_count += 1

                result = HookResult(
                    hook_name=hook.name,
                    success=False,
                    error=str(e),
                    duration_ms=duration,
                    handler_name=hook.name
                )

            results.append(result)

            if not result.success and hook.can_prevent_action:
                break

        return results

    def get_hooks(
        self,
        hook_type: Optional[HookType] = None,
        plugin_id: Optional[str] = None,
        enabled_only: bool = False
    ) -> List[Hook]:
        """Get hooks with filtering"""
        hooks = list(self.hooks.values())

        if hook_type:
            hooks = [h for h in hooks if h.hook_type == hook_type]
        if plugin_id:
            hooks = [h for h in hooks if h.plugin_id == plugin_id]
        if enabled_only:
            hooks = [h for h in hooks if h.enabled]

        return hooks

    def get_statistics(self) -> dict:
        """Get hook statistics"""
        by_type = {}
        total_executions = 0
        total_failures = 0

        for hook in self.hooks.values():
            by_type[hook.hook_type.value] = by_type.get(hook.hook_type.value, 0) + 1
            total_executions += hook.execution_count
            total_failures += hook.failure_count

        return {
            "total_hooks": len(self.hooks),
            "enabled_hooks": len([h for h in self.hooks.values() if h.enabled]),
            "by_type": by_type,
            "total_executions": total_executions,
            "total_failures": total_failures,
            "success_rate": (total_executions - total_failures) / total_executions if total_executions > 0 else 1.0
        }


# Global hook manager instance
_hook_manager: Optional[HookManager] = None


def get_hook_manager() -> HookManager:
    """Get or create the global hook manager"""
    global _hook_manager
    if _hook_manager is None:
        _hook_manager = HookManager()
    return _hook_manager
