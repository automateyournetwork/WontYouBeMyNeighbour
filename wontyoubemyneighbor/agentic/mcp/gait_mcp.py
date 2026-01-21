"""
GAIT MCP Client - Conversation Audit Trail Integration

Provides integration with GAIT (Git-based AI Trail) for complete audit trails
of all agent interactions, decisions, and changes.

GAIT tracks:
- User prompts sent to agents
- Agent LLM responses
- MCP calls made by agents
- Configuration changes
- Test executions and results
- Protocol state changes (OSPF neighbor up/down, BGP peer changes)
"""

import asyncio
import logging
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
from datetime import datetime
import subprocess
import os

logger = logging.getLogger("GAIT_MCP")


class GAITEventType(Enum):
    """Types of events tracked by GAIT"""
    USER_PROMPT = "user_prompt"
    AGENT_RESPONSE = "agent_response"
    MCP_CALL = "mcp_call"
    CONFIG_CHANGE = "config_change"
    TEST_RUN = "test_run"
    TEST_RESULT = "test_result"
    PROTOCOL_STATE = "protocol_state"
    ERROR = "error"
    SYSTEM = "system"


class GAITActor(Enum):
    """Actor types for audit entries"""
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"
    MCP = "mcp"


@dataclass
class GAITCommit:
    """Represents a GAIT commit (audit entry)"""
    commit_id: str
    timestamp: str
    agent_id: str
    event_type: GAITEventType
    actor: GAITActor
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    parent_commit: Optional[str] = None
    files_changed: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "commit_id": self.commit_id,
            "timestamp": self.timestamp,
            "agent_id": self.agent_id,
            "event_type": self.event_type.value,
            "actor": self.actor.value,
            "message": self.message,
            "details": self.details,
            "parent_commit": self.parent_commit,
            "files_changed": self.files_changed,
        }


@dataclass
class GAITBranch:
    """Represents a GAIT branch (agent conversation thread)"""
    name: str
    head_commit: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    agent_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "head_commit": self.head_commit,
            "created_at": self.created_at,
            "agent_id": self.agent_id,
        }


@dataclass
class GAITMemoryItem:
    """Pinned memory item for context retention"""
    index: int
    commit_id: str
    note: str
    pinned_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "commit_id": self.commit_id,
            "note": self.note,
            "pinned_at": self.pinned_at,
        }


class GAITClient:
    """
    GAIT MCP Client for agent audit trails

    Provides methods to:
    - Initialize GAIT tracking for an agent
    - Record interactions and events
    - Query conversation history
    - Manage pinned memory items
    - Export audit reports
    """

    def __init__(self, agent_id: str, gait_dir: Optional[str] = None):
        """
        Initialize GAIT client for an agent

        Args:
            agent_id: Unique identifier for the agent
            gait_dir: Optional custom GAIT directory path
        """
        self.agent_id = agent_id
        self.gait_dir = gait_dir or f"/tmp/gait/{agent_id}"
        self._initialized = False
        self._commits: List[GAITCommit] = []
        self._memory: List[GAITMemoryItem] = []
        self._current_branch = "main"
        self._head_commit: Optional[str] = None
        self._event_handlers: Dict[GAITEventType, List[Callable]] = {
            event_type: [] for event_type in GAITEventType
        }

    async def init(self) -> Dict[str, Any]:
        """
        Initialize GAIT tracking for this agent

        Creates the .gait directory structure and initial commit.

        Returns:
            Status dict with initialization result
        """
        try:
            # Create GAIT directory structure
            os.makedirs(self.gait_dir, exist_ok=True)
            os.makedirs(f"{self.gait_dir}/objects", exist_ok=True)
            os.makedirs(f"{self.gait_dir}/refs/heads", exist_ok=True)
            os.makedirs(f"{self.gait_dir}/memory", exist_ok=True)

            # Create initial commit
            init_commit = GAITCommit(
                commit_id=self._generate_commit_id(),
                timestamp=datetime.now().isoformat(),
                agent_id=self.agent_id,
                event_type=GAITEventType.SYSTEM,
                actor=GAITActor.SYSTEM,
                message=f"GAIT initialized for agent {self.agent_id}",
                details={"gait_dir": self.gait_dir},
            )

            self._commits.append(init_commit)
            self._head_commit = init_commit.commit_id
            self._initialized = True

            # Save initial state
            await self._save_state()

            logger.info(f"GAIT initialized for agent {self.agent_id}")

            return {
                "success": True,
                "agent_id": self.agent_id,
                "gait_dir": self.gait_dir,
                "branch": self._current_branch,
                "head_commit": self._head_commit,
            }

        except Exception as e:
            logger.error(f"Failed to initialize GAIT: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def _generate_commit_id(self) -> str:
        """Generate a unique commit ID"""
        import hashlib
        import time
        data = f"{self.agent_id}-{time.time()}-{len(self._commits)}"
        return hashlib.sha256(data.encode()).hexdigest()[:12]

    async def record_turn(
        self,
        user_text: str = "",
        assistant_text: str = "",
        event_type: GAITEventType = GAITEventType.USER_PROMPT,
        actor: GAITActor = GAITActor.USER,
        artifacts: Optional[List[Dict[str, str]]] = None,
        note: str = ""
    ) -> GAITCommit:
        """
        Record a conversation turn

        Args:
            user_text: User's input text
            assistant_text: Agent's response text
            event_type: Type of event being recorded
            actor: Who initiated this turn
            artifacts: Optional list of files/artifacts created
            note: Optional note about this turn

        Returns:
            The created GAITCommit
        """
        commit = GAITCommit(
            commit_id=self._generate_commit_id(),
            timestamp=datetime.now().isoformat(),
            agent_id=self.agent_id,
            event_type=event_type,
            actor=actor,
            message=f"[{self.agent_id}] [{event_type.value}] {note or user_text[:50]}",
            details={
                "user_text": user_text,
                "assistant_text": assistant_text,
                "note": note,
                "artifacts": artifacts or [],
            },
            parent_commit=self._head_commit,
            files_changed=[a.get("path", "") for a in (artifacts or [])],
        )

        self._commits.append(commit)
        self._head_commit = commit.commit_id

        # Trigger event handlers
        for handler in self._event_handlers.get(event_type, []):
            try:
                await handler(commit)
            except Exception as e:
                logger.warning(f"Event handler failed: {e}")

        await self._save_state()

        return commit

    async def record_mcp_call(
        self,
        mcp_name: str,
        method: str,
        params: Dict[str, Any],
        response: Any,
        duration_ms: float = 0
    ) -> GAITCommit:
        """
        Record an MCP call made by the agent

        Args:
            mcp_name: Name of the MCP server called
            method: Method/tool called
            params: Parameters passed to the method
            response: Response received
            duration_ms: Call duration in milliseconds

        Returns:
            The created GAITCommit
        """
        return await self.record_turn(
            user_text=f"MCP: {mcp_name}.{method}",
            assistant_text=str(response)[:500],
            event_type=GAITEventType.MCP_CALL,
            actor=GAITActor.MCP,
            note=f"MCP call to {mcp_name}.{method}",
            artifacts=[{
                "type": "mcp_call",
                "mcp": mcp_name,
                "method": method,
                "params": json.dumps(params),
                "response": str(response)[:1000],
                "duration_ms": duration_ms,
            }]
        )

    async def record_config_change(
        self,
        change_type: str,
        old_config: Dict[str, Any],
        new_config: Dict[str, Any],
        changed_by: str = "agent"
    ) -> GAITCommit:
        """
        Record a configuration change

        Args:
            change_type: Type of configuration changed (e.g., "ospf", "bgp", "interface")
            old_config: Previous configuration
            new_config: New configuration
            changed_by: Who made the change

        Returns:
            The created GAITCommit
        """
        return await self.record_turn(
            user_text=f"Config change: {change_type}",
            assistant_text=f"Updated {change_type} configuration",
            event_type=GAITEventType.CONFIG_CHANGE,
            actor=GAITActor.AGENT if changed_by == "agent" else GAITActor.USER,
            note=f"Configuration change: {change_type}",
            artifacts=[{
                "type": "config_change",
                "change_type": change_type,
                "old_config": json.dumps(old_config),
                "new_config": json.dumps(new_config),
                "diff": self._generate_config_diff(old_config, new_config),
            }]
        )

    async def record_test_run(
        self,
        test_suite: str,
        tests_run: int,
        passed: int,
        failed: int,
        results: List[Dict[str, Any]]
    ) -> GAITCommit:
        """
        Record a test execution

        Args:
            test_suite: Name of the test suite executed
            tests_run: Total tests executed
            passed: Number of tests passed
            failed: Number of tests failed
            results: Detailed test results

        Returns:
            The created GAITCommit
        """
        status = "PASSED" if failed == 0 else "FAILED"
        return await self.record_turn(
            user_text=f"Test run: {test_suite}",
            assistant_text=f"Tests: {passed}/{tests_run} passed ({status})",
            event_type=GAITEventType.TEST_RUN,
            actor=GAITActor.AGENT,
            note=f"Test suite: {test_suite} - {status}",
            artifacts=[{
                "type": "test_run",
                "suite": test_suite,
                "total": tests_run,
                "passed": passed,
                "failed": failed,
                "pass_rate": round(passed / tests_run * 100, 1) if tests_run > 0 else 0,
                "results": results,
            }]
        )

    async def record_protocol_state(
        self,
        protocol: str,
        event: str,
        old_state: str,
        new_state: str,
        details: Dict[str, Any]
    ) -> GAITCommit:
        """
        Record a protocol state change

        Args:
            protocol: Protocol name (OSPF, BGP, etc.)
            event: Event description (e.g., "neighbor_up", "peer_down")
            old_state: Previous state
            new_state: New state
            details: Additional event details

        Returns:
            The created GAITCommit
        """
        return await self.record_turn(
            user_text=f"{protocol} state change: {event}",
            assistant_text=f"{old_state} -> {new_state}",
            event_type=GAITEventType.PROTOCOL_STATE,
            actor=GAITActor.SYSTEM,
            note=f"{protocol} {event}: {old_state} -> {new_state}",
            artifacts=[{
                "type": "protocol_state",
                "protocol": protocol,
                "event": event,
                "old_state": old_state,
                "new_state": new_state,
                **details,
            }]
        )

    async def record_error(
        self,
        error_type: str,
        message: str,
        stack_trace: str = "",
        context: Dict[str, Any] = None
    ) -> GAITCommit:
        """
        Record an error event

        Args:
            error_type: Type of error
            message: Error message
            stack_trace: Optional stack trace
            context: Additional context

        Returns:
            The created GAITCommit
        """
        return await self.record_turn(
            user_text=f"Error: {error_type}",
            assistant_text=message,
            event_type=GAITEventType.ERROR,
            actor=GAITActor.SYSTEM,
            note=f"Error: {error_type}",
            artifacts=[{
                "type": "error",
                "error_type": error_type,
                "message": message,
                "stack_trace": stack_trace,
                "context": context or {},
            }]
        )

    def _generate_config_diff(
        self,
        old_config: Dict[str, Any],
        new_config: Dict[str, Any]
    ) -> str:
        """Generate a simple diff between configs"""
        diff_lines = []
        all_keys = set(old_config.keys()) | set(new_config.keys())

        for key in sorted(all_keys):
            old_val = old_config.get(key)
            new_val = new_config.get(key)

            if old_val != new_val:
                if old_val is not None:
                    diff_lines.append(f"- {key}: {old_val}")
                if new_val is not None:
                    diff_lines.append(f"+ {key}: {new_val}")

        return "\n".join(diff_lines)

    async def get_history(
        self,
        limit: int = 50,
        event_type: Optional[GAITEventType] = None,
        actor: Optional[GAITActor] = None,
        since: Optional[str] = None
    ) -> List[GAITCommit]:
        """
        Get conversation history

        Args:
            limit: Maximum number of commits to return
            event_type: Filter by event type
            actor: Filter by actor
            since: Filter commits after this timestamp

        Returns:
            List of matching GAITCommit objects
        """
        commits = self._commits.copy()

        # Apply filters
        if event_type:
            commits = [c for c in commits if c.event_type == event_type]

        if actor:
            commits = [c for c in commits if c.actor == actor]

        if since:
            commits = [c for c in commits if c.timestamp >= since]

        # Sort by timestamp descending (most recent first)
        commits.sort(key=lambda c: c.timestamp, reverse=True)

        return commits[:limit]

    async def get_commit(self, commit_id: str) -> Optional[GAITCommit]:
        """
        Get a specific commit by ID

        Args:
            commit_id: Commit ID to retrieve

        Returns:
            GAITCommit if found, None otherwise
        """
        for commit in self._commits:
            if commit.commit_id == commit_id:
                return commit
        return None

    async def pin_memory(
        self,
        commit_id: Optional[str] = None,
        note: str = ""
    ) -> GAITMemoryItem:
        """
        Pin a commit to memory for context retention

        Args:
            commit_id: Commit to pin (uses HEAD if None)
            note: Note explaining why this is pinned

        Returns:
            The created GAITMemoryItem
        """
        target_commit = commit_id or self._head_commit

        memory_item = GAITMemoryItem(
            index=len(self._memory) + 1,
            commit_id=target_commit,
            note=note,
            pinned_at=datetime.now().isoformat(),
        )

        self._memory.append(memory_item)
        await self._save_state()

        return memory_item

    async def unpin_memory(self, index: int) -> bool:
        """
        Unpin a memory item

        Args:
            index: 1-based index of memory item to unpin

        Returns:
            True if unpinned, False if not found
        """
        if 1 <= index <= len(self._memory):
            self._memory.pop(index - 1)
            # Re-index remaining items
            for i, item in enumerate(self._memory):
                item.index = i + 1
            await self._save_state()
            return True
        return False

    async def get_memory(self) -> List[GAITMemoryItem]:
        """
        Get all pinned memory items

        Returns:
            List of GAITMemoryItem objects
        """
        return self._memory.copy()

    async def get_context(self, full: bool = False) -> Dict[str, Any]:
        """
        Build context bundle from pinned memory

        Args:
            full: If True, include full commit details

        Returns:
            Context bundle dictionary
        """
        context = {
            "agent_id": self.agent_id,
            "branch": self._current_branch,
            "head_commit": self._head_commit,
            "memory_items": [],
        }

        for item in self._memory:
            item_data = item.to_dict()
            if full:
                commit = await self.get_commit(item.commit_id)
                if commit:
                    item_data["commit"] = commit.to_dict()
            context["memory_items"].append(item_data)

        return context

    def on_event(
        self,
        event_type: GAITEventType,
        handler: Callable
    ) -> None:
        """
        Register an event handler

        Args:
            event_type: Event type to handle
            handler: Async callable to invoke on event
        """
        self._event_handlers[event_type].append(handler)

    async def export_report(
        self,
        format: str = "json",
        include_details: bool = True
    ) -> str:
        """
        Export audit report

        Args:
            format: Export format ("json", "csv", "markdown")
            include_details: Include full commit details

        Returns:
            Formatted report string
        """
        if format == "json":
            return await self._export_json(include_details)
        elif format == "csv":
            return await self._export_csv(include_details)
        elif format == "markdown":
            return await self._export_markdown(include_details)
        else:
            raise ValueError(f"Unknown format: {format}")

    async def _export_json(self, include_details: bool) -> str:
        """Export as JSON"""
        data = {
            "agent_id": self.agent_id,
            "export_timestamp": datetime.now().isoformat(),
            "total_commits": len(self._commits),
            "commits": [c.to_dict() for c in self._commits] if include_details else [],
            "memory": [m.to_dict() for m in self._memory],
        }
        return json.dumps(data, indent=2)

    async def _export_csv(self, include_details: bool) -> str:
        """Export as CSV"""
        lines = ["timestamp,event_type,actor,message"]
        for commit in self._commits:
            msg = commit.message.replace(",", ";").replace("\n", " ")
            lines.append(f"{commit.timestamp},{commit.event_type.value},{commit.actor.value},{msg}")
        return "\n".join(lines)

    async def _export_markdown(self, include_details: bool) -> str:
        """Export as Markdown"""
        lines = [
            f"# GAIT Audit Report: {self.agent_id}",
            f"",
            f"**Generated:** {datetime.now().isoformat()}",
            f"**Total Commits:** {len(self._commits)}",
            f"",
            "## Conversation History",
            "",
        ]

        for commit in reversed(self._commits[-50:]):  # Last 50
            lines.append(f"### {commit.timestamp}")
            lines.append(f"- **Event:** {commit.event_type.value}")
            lines.append(f"- **Actor:** {commit.actor.value}")
            lines.append(f"- **Message:** {commit.message}")
            if include_details and commit.details:
                lines.append(f"- **Details:** {json.dumps(commit.details)[:200]}")
            lines.append("")

        if self._memory:
            lines.append("## Pinned Memory")
            lines.append("")
            for item in self._memory:
                lines.append(f"- [{item.index}] {item.note} (commit: {item.commit_id})")

        return "\n".join(lines)

    async def _save_state(self) -> None:
        """Save current state to disk"""
        try:
            state = {
                "agent_id": self.agent_id,
                "branch": self._current_branch,
                "head_commit": self._head_commit,
                "commits": [c.to_dict() for c in self._commits],
                "memory": [m.to_dict() for m in self._memory],
            }

            state_file = f"{self.gait_dir}/state.json"
            with open(state_file, "w") as f:
                json.dump(state, f, indent=2)

        except Exception as e:
            logger.warning(f"Failed to save GAIT state: {e}")

    async def load_state(self) -> bool:
        """
        Load state from disk

        Returns:
            True if loaded successfully, False otherwise
        """
        try:
            state_file = f"{self.gait_dir}/state.json"
            if os.path.exists(state_file):
                with open(state_file, "r") as f:
                    state = json.load(f)

                self._current_branch = state.get("branch", "main")
                self._head_commit = state.get("head_commit")

                self._commits = []
                for c in state.get("commits", []):
                    commit = GAITCommit(
                        commit_id=c["commit_id"],
                        timestamp=c["timestamp"],
                        agent_id=c["agent_id"],
                        event_type=GAITEventType(c["event_type"]),
                        actor=GAITActor(c["actor"]),
                        message=c["message"],
                        details=c.get("details", {}),
                        parent_commit=c.get("parent_commit"),
                        files_changed=c.get("files_changed", []),
                    )
                    self._commits.append(commit)

                self._memory = []
                for m in state.get("memory", []):
                    item = GAITMemoryItem(
                        index=m["index"],
                        commit_id=m["commit_id"],
                        note=m["note"],
                        pinned_at=m["pinned_at"],
                    )
                    self._memory.append(item)

                self._initialized = True
                return True

        except Exception as e:
            logger.warning(f"Failed to load GAIT state: {e}")

        return False

    def get_status(self) -> Dict[str, Any]:
        """
        Get GAIT status

        Returns:
            Status dictionary
        """
        return {
            "agent_id": self.agent_id,
            "initialized": self._initialized,
            "gait_dir": self.gait_dir,
            "branch": self._current_branch,
            "head_commit": self._head_commit,
            "total_commits": len(self._commits),
            "pinned_memory": len(self._memory),
        }


# Global registry of GAIT clients per agent
_gait_clients: Dict[str, GAITClient] = {}


def get_gait_client(agent_id: str) -> GAITClient:
    """
    Get or create a GAIT client for an agent

    Args:
        agent_id: Agent identifier

    Returns:
        GAITClient instance
    """
    if agent_id not in _gait_clients:
        _gait_clients[agent_id] = GAITClient(agent_id)
    return _gait_clients[agent_id]


async def init_gait_for_agent(agent_id: str) -> Dict[str, Any]:
    """
    Initialize GAIT tracking for an agent

    Args:
        agent_id: Agent identifier

    Returns:
        Initialization result
    """
    client = get_gait_client(agent_id)
    return await client.init()
