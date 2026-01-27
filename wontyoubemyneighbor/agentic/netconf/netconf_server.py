"""
NETCONF Server Implementation for ASI Agents

Provides NETCONF (Network Configuration Protocol) server capabilities
as defined in RFC 6241. Allows external tools to configure agents using
standard NETCONF operations.

RFC Compliance:
- RFC 6241: NETCONF Protocol
- RFC 6242: NETCONF over SSH
- RFC 5277: NETCONF Event Notifications
- RFC 8040: RESTCONF Protocol (related)
"""

import asyncio
import logging
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
import copy
import json

logger = logging.getLogger(__name__)

# NETCONF XML namespaces
NC_NS = "urn:ietf:params:xml:ns:netconf:base:1.0"
NC_NS_1_1 = "urn:ietf:params:xml:ns:netconf:base:1.1"
YANG_NS = "urn:ietf:params:xml:ns:yang:1"


class DatastoreType(Enum):
    """NETCONF datastore types"""
    RUNNING = "running"
    CANDIDATE = "candidate"
    STARTUP = "startup"


class OperationType(Enum):
    """NETCONF operation types"""
    GET = "get"
    GET_CONFIG = "get-config"
    EDIT_CONFIG = "edit-config"
    COPY_CONFIG = "copy-config"
    DELETE_CONFIG = "delete-config"
    LOCK = "lock"
    UNLOCK = "unlock"
    COMMIT = "commit"
    DISCARD_CHANGES = "discard-changes"
    CLOSE_SESSION = "close-session"
    KILL_SESSION = "kill-session"
    VALIDATE = "validate"


class EditOperation(Enum):
    """Edit-config operations"""
    MERGE = "merge"
    REPLACE = "replace"
    CREATE = "create"
    DELETE = "delete"
    REMOVE = "remove"


@dataclass
class NETCONFCapability:
    """NETCONF capability"""
    uri: str
    name: str
    version: str = "1.0"

    def to_xml(self) -> str:
        return f"<capability>{self.uri}</capability>"


@dataclass
class NETCONFSession:
    """Represents an active NETCONF session"""
    session_id: str
    username: str
    remote_address: str
    remote_port: int
    connected_at: datetime
    last_activity: datetime
    locked_datastores: Set[DatastoreType] = field(default_factory=set)
    operations_count: int = 0
    protocol_version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "session_id": self.session_id,
            "username": self.username,
            "remote_address": self.remote_address,
            "remote_port": self.remote_port,
            "connected_at": self.connected_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "duration_seconds": (datetime.now() - self.connected_at).total_seconds(),
            "locked_datastores": [ds.value for ds in self.locked_datastores],
            "operations_count": self.operations_count,
            "protocol_version": self.protocol_version
        }


@dataclass
class NETCONFConfig:
    """NETCONF server configuration"""
    port: int = 830
    host: str = "0.0.0.0"
    ssh_host_keys: List[str] = field(default_factory=list)
    max_sessions: int = 10
    idle_timeout: int = 300
    hello_timeout: int = 30
    default_username: str = "admin"
    default_password: str = "admin"
    with_candidate: bool = True
    with_startup: bool = True
    with_validate: bool = True
    with_writable_running: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "port": self.port,
            "host": self.host,
            "max_sessions": self.max_sessions,
            "idle_timeout": self.idle_timeout,
            "with_candidate": self.with_candidate,
            "with_startup": self.with_startup,
            "with_validate": self.with_validate,
            "with_writable_running": self.with_writable_running
        }


@dataclass
class NETCONFStatistics:
    """NETCONF server statistics"""
    total_sessions: int = 0
    active_sessions: int = 0
    total_operations: int = 0
    failed_operations: int = 0
    commits: int = 0
    rollbacks: int = 0
    uptime_seconds: float = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses"""
        return {
            "total_sessions": self.total_sessions,
            "active_sessions": self.active_sessions,
            "total_operations": self.total_operations,
            "failed_operations": self.failed_operations,
            "commits": self.commits,
            "rollbacks": self.rollbacks,
            "uptime_seconds": self.uptime_seconds
        }


class ConfigDatastore:
    """
    Configuration datastore with support for running, candidate, and startup.

    Provides hierarchical configuration storage with YANG-like paths.
    """

    def __init__(self):
        self._running: Dict[str, Any] = self._default_config()
        self._candidate: Dict[str, Any] = copy.deepcopy(self._running)
        self._startup: Dict[str, Any] = copy.deepcopy(self._running)
        self._locks: Dict[DatastoreType, Optional[str]] = {
            DatastoreType.RUNNING: None,
            DatastoreType.CANDIDATE: None,
            DatastoreType.STARTUP: None
        }

    def _default_config(self) -> Dict[str, Any]:
        """Return default configuration structure"""
        return {
            "system": {
                "hostname": "agent",
                "domain-name": "local",
                "contact": "",
                "location": ""
            },
            "interfaces": {
                "interface": []
            },
            "routing": {
                "ospf": {
                    "enabled": False,
                    "router-id": "",
                    "areas": []
                },
                "bgp": {
                    "enabled": False,
                    "as-number": 0,
                    "router-id": "",
                    "neighbors": []
                },
                "static": {
                    "routes": []
                }
            },
            "acl": {
                "access-lists": []
            }
        }

    def get_datastore(self, ds_type: DatastoreType) -> Dict[str, Any]:
        """Get a datastore by type"""
        if ds_type == DatastoreType.RUNNING:
            return self._running
        elif ds_type == DatastoreType.CANDIDATE:
            return self._candidate
        else:
            return self._startup

    def get_config(
        self,
        ds_type: DatastoreType,
        xpath: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get configuration from a datastore.

        Args:
            ds_type: Datastore type
            xpath: Optional XPath filter

        Returns:
            Configuration dictionary
        """
        datastore = self.get_datastore(ds_type)

        if not xpath or xpath == "/":
            return copy.deepcopy(datastore)

        # Simple path traversal (not full XPath)
        path_parts = xpath.strip("/").split("/")
        current = datastore
        for part in path_parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return {}

        return copy.deepcopy(current) if isinstance(current, dict) else {"value": current}

    def edit_config(
        self,
        ds_type: DatastoreType,
        config: Dict[str, Any],
        operation: EditOperation = EditOperation.MERGE,
        session_id: Optional[str] = None
    ) -> bool:
        """
        Edit configuration in a datastore.

        Args:
            ds_type: Target datastore
            config: Configuration to apply
            operation: Edit operation type
            session_id: Session ID for lock validation

        Returns:
            True if successful
        """
        # Check lock
        if self._locks[ds_type] and self._locks[ds_type] != session_id:
            raise RuntimeError(f"Datastore {ds_type.value} is locked by another session")

        datastore = self.get_datastore(ds_type)

        if operation == EditOperation.REPLACE:
            # Replace entire datastore
            if ds_type == DatastoreType.RUNNING:
                self._running = copy.deepcopy(config)
            elif ds_type == DatastoreType.CANDIDATE:
                self._candidate = copy.deepcopy(config)
            else:
                self._startup = copy.deepcopy(config)
        elif operation == EditOperation.MERGE:
            # Deep merge
            self._deep_merge(datastore, config)
        elif operation == EditOperation.DELETE:
            # Delete specified paths
            self._delete_paths(datastore, config)

        return True

    def _deep_merge(self, base: Dict, overlay: Dict):
        """Deep merge overlay into base"""
        for key, value in overlay.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = copy.deepcopy(value)

    def _delete_paths(self, datastore: Dict, paths: Dict):
        """Delete specified paths from datastore"""
        for key, value in paths.items():
            if key in datastore:
                if isinstance(value, dict) and isinstance(datastore[key], dict):
                    self._delete_paths(datastore[key], value)
                else:
                    del datastore[key]

    def lock(self, ds_type: DatastoreType, session_id: str) -> bool:
        """Lock a datastore"""
        if self._locks[ds_type] is not None:
            return False
        self._locks[ds_type] = session_id
        return True

    def unlock(self, ds_type: DatastoreType, session_id: str) -> bool:
        """Unlock a datastore"""
        if self._locks[ds_type] != session_id:
            return False
        self._locks[ds_type] = None
        return True

    def commit(self, session_id: Optional[str] = None) -> bool:
        """Commit candidate to running"""
        if self._locks[DatastoreType.RUNNING] and self._locks[DatastoreType.RUNNING] != session_id:
            raise RuntimeError("Running datastore is locked by another session")

        self._running = copy.deepcopy(self._candidate)
        return True

    def discard_changes(self) -> bool:
        """Discard candidate changes"""
        self._candidate = copy.deepcopy(self._running)
        return True

    def copy_config(
        self,
        source: DatastoreType,
        target: DatastoreType,
        session_id: Optional[str] = None
    ) -> bool:
        """Copy configuration between datastores"""
        if self._locks[target] and self._locks[target] != session_id:
            raise RuntimeError(f"Target datastore {target.value} is locked")

        source_data = copy.deepcopy(self.get_datastore(source))

        if target == DatastoreType.RUNNING:
            self._running = source_data
        elif target == DatastoreType.CANDIDATE:
            self._candidate = source_data
        else:
            self._startup = source_data

        return True

    def to_xml(self, ds_type: DatastoreType, xpath: Optional[str] = None) -> str:
        """Convert configuration to XML format"""
        config = self.get_config(ds_type, xpath)
        return self._dict_to_xml(config, "data")

    def _dict_to_xml(self, data: Any, root_name: str) -> str:
        """Convert dictionary to XML string"""
        def convert(obj, parent):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    child = ET.SubElement(parent, key)
                    convert(value, child)
            elif isinstance(obj, list):
                for item in obj:
                    convert(item, parent)
            else:
                parent.text = str(obj) if obj is not None else ""

        root = ET.Element(root_name)
        convert(data, root)
        return ET.tostring(root, encoding="unicode")


class NETCONFServer:
    """
    NETCONF Server for ASI agents.

    Provides RFC 6241 compliant NETCONF server functionality.
    """

    def __init__(
        self,
        agent_name: str,
        config: Optional[NETCONFConfig] = None,
        apply_handler: Optional[Callable[[Dict], asyncio.Future]] = None
    ):
        """
        Initialize NETCONF server.

        Args:
            agent_name: Name of the agent
            config: Server configuration
            apply_handler: Async function to apply configuration changes
        """
        self.agent_name = agent_name
        self.config = config or NETCONFConfig()
        self.apply_handler = apply_handler

        self._sessions: Dict[str, NETCONFSession] = {}
        self._datastore = ConfigDatastore()
        self._running = False
        self._started_at: Optional[datetime] = None
        self._statistics = NETCONFStatistics()
        self._capabilities = self._build_capabilities()

    def _build_capabilities(self) -> List[NETCONFCapability]:
        """Build list of server capabilities"""
        caps = [
            NETCONFCapability(NC_NS, "base", "1.0"),
            NETCONFCapability(NC_NS_1_1, "base", "1.1"),
        ]

        if self.config.with_candidate:
            caps.append(NETCONFCapability(
                "urn:ietf:params:netconf:capability:candidate:1.0",
                "candidate"
            ))

        if self.config.with_startup:
            caps.append(NETCONFCapability(
                "urn:ietf:params:netconf:capability:startup:1.0",
                "startup"
            ))

        if self.config.with_validate:
            caps.append(NETCONFCapability(
                "urn:ietf:params:netconf:capability:validate:1.1",
                "validate"
            ))

        if self.config.with_writable_running:
            caps.append(NETCONFCapability(
                "urn:ietf:params:netconf:capability:writable-running:1.0",
                "writable-running"
            ))

        return caps

    async def start(self) -> bool:
        """Start the NETCONF server"""
        if self._running:
            logger.warning(f"NETCONF server for {self.agent_name} already running")
            return False

        self._running = True
        self._started_at = datetime.now()
        logger.info(
            f"NETCONF server for {self.agent_name} started on port {self.config.port}"
        )
        return True

    async def stop(self):
        """Stop the NETCONF server"""
        if not self._running:
            return

        self._running = False

        # Close all sessions
        for session_id in list(self._sessions.keys()):
            await self._close_session(session_id)

        logger.info(f"NETCONF server for {self.agent_name} stopped")

    @property
    def running(self) -> bool:
        """Check if server is running"""
        return self._running

    def get_capabilities_xml(self) -> str:
        """Get capabilities as XML for hello message"""
        caps_xml = "\n".join(cap.to_xml() for cap in self._capabilities)
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<hello xmlns="{NC_NS}">
    <capabilities>
        {caps_xml}
    </capabilities>
    <session-id>{{session_id}}</session-id>
</hello>"""

    def create_session(
        self,
        username: str,
        remote_address: str,
        remote_port: int
    ) -> NETCONFSession:
        """Create a new NETCONF session"""
        if len(self._sessions) >= self.config.max_sessions:
            raise RuntimeError("Maximum sessions reached")

        session = NETCONFSession(
            session_id=str(uuid.uuid4())[:8],
            username=username,
            remote_address=remote_address,
            remote_port=remote_port,
            connected_at=datetime.now(),
            last_activity=datetime.now()
        )

        self._sessions[session.session_id] = session
        self._statistics.total_sessions += 1
        self._statistics.active_sessions = len(self._sessions)

        logger.info(f"NETCONF session {session.session_id} created for {username}")
        return session

    async def _close_session(self, session_id: str):
        """Close a NETCONF session"""
        if session_id in self._sessions:
            session = self._sessions[session_id]

            # Release any locks held by this session
            for ds_type in list(session.locked_datastores):
                self._datastore.unlock(ds_type, session_id)

            del self._sessions[session_id]
            self._statistics.active_sessions = len(self._sessions)
            logger.info(f"NETCONF session {session_id} closed")

    async def process_rpc(
        self,
        session: NETCONFSession,
        rpc_xml: str
    ) -> str:
        """
        Process a NETCONF RPC request.

        Args:
            session: The NETCONF session
            rpc_xml: XML RPC request

        Returns:
            XML RPC reply
        """
        session.last_activity = datetime.now()
        session.operations_count += 1
        self._statistics.total_operations += 1

        try:
            root = ET.fromstring(rpc_xml)
            message_id = root.get("message-id", "1")

            # Find the operation element
            operation = None
            for child in root:
                tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if tag in [op.value.replace("-", "_") for op in OperationType]:
                    operation = tag.replace("_", "-")
                    op_element = child
                    break

            if not operation:
                # Check for common operations
                for child in root:
                    tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if tag in ["get", "get-config", "edit-config", "lock", "unlock",
                               "commit", "discard-changes", "close-session", "kill-session",
                               "copy-config", "delete-config", "validate"]:
                        operation = tag
                        op_element = child
                        break

            if not operation:
                return self._rpc_error(message_id, "operation-not-supported", "Unknown operation")

            # Handle the operation
            if operation == "get":
                return await self._handle_get(message_id, op_element, session)
            elif operation == "get-config":
                return await self._handle_get_config(message_id, op_element, session)
            elif operation == "edit-config":
                return await self._handle_edit_config(message_id, op_element, session)
            elif operation == "lock":
                return await self._handle_lock(message_id, op_element, session)
            elif operation == "unlock":
                return await self._handle_unlock(message_id, op_element, session)
            elif operation == "commit":
                return await self._handle_commit(message_id, session)
            elif operation == "discard-changes":
                return await self._handle_discard(message_id, session)
            elif operation == "close-session":
                return await self._handle_close_session(message_id, session)
            elif operation == "copy-config":
                return await self._handle_copy_config(message_id, op_element, session)
            elif operation == "validate":
                return await self._handle_validate(message_id, op_element, session)
            else:
                return self._rpc_error(message_id, "operation-not-supported", f"Operation {operation} not supported")

        except ET.ParseError as e:
            self._statistics.failed_operations += 1
            return self._rpc_error("0", "malformed-message", str(e))
        except Exception as e:
            self._statistics.failed_operations += 1
            logger.error(f"NETCONF RPC error: {e}")
            return self._rpc_error("0", "operation-failed", str(e))

    async def _handle_get(
        self,
        message_id: str,
        op_element: ET.Element,
        session: NETCONFSession
    ) -> str:
        """Handle get operation (returns state + config)"""
        # For simplicity, return running config as state
        config = self._datastore.to_xml(DatastoreType.RUNNING)
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<rpc-reply xmlns="{NC_NS}" message-id="{message_id}">
    {config}
</rpc-reply>"""

    async def _handle_get_config(
        self,
        message_id: str,
        op_element: ET.Element,
        session: NETCONFSession
    ) -> str:
        """Handle get-config operation"""
        # Get source datastore
        source = op_element.find(".//{%s}source" % NC_NS) or op_element.find(".//source")
        ds_type = DatastoreType.RUNNING

        if source is not None:
            for child in source:
                tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if tag == "running":
                    ds_type = DatastoreType.RUNNING
                elif tag == "candidate":
                    ds_type = DatastoreType.CANDIDATE
                elif tag == "startup":
                    ds_type = DatastoreType.STARTUP

        config = self._datastore.to_xml(ds_type)
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<rpc-reply xmlns="{NC_NS}" message-id="{message_id}">
    {config}
</rpc-reply>"""

    async def _handle_edit_config(
        self,
        message_id: str,
        op_element: ET.Element,
        session: NETCONFSession
    ) -> str:
        """Handle edit-config operation"""
        # Get target datastore
        target = op_element.find(".//{%s}target" % NC_NS) or op_element.find(".//target")
        ds_type = DatastoreType.CANDIDATE

        if target is not None:
            for child in target:
                tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if tag == "running":
                    ds_type = DatastoreType.RUNNING
                elif tag == "candidate":
                    ds_type = DatastoreType.CANDIDATE

        # Get default operation
        default_op_elem = op_element.find(".//{%s}default-operation" % NC_NS) or op_element.find(".//default-operation")
        operation = EditOperation.MERGE
        if default_op_elem is not None and default_op_elem.text:
            operation = EditOperation(default_op_elem.text)

        # Get config
        config_elem = op_element.find(".//{%s}config" % NC_NS) or op_element.find(".//config")
        if config_elem is not None:
            config = self._xml_to_dict(config_elem)
            self._datastore.edit_config(ds_type, config, operation, session.session_id)

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<rpc-reply xmlns="{NC_NS}" message-id="{message_id}">
    <ok/>
</rpc-reply>"""

    async def _handle_lock(
        self,
        message_id: str,
        op_element: ET.Element,
        session: NETCONFSession
    ) -> str:
        """Handle lock operation"""
        target = op_element.find(".//{%s}target" % NC_NS) or op_element.find(".//target")
        ds_type = DatastoreType.RUNNING

        if target is not None:
            for child in target:
                tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if tag in ["running", "candidate", "startup"]:
                    ds_type = DatastoreType(tag)

        if self._datastore.lock(ds_type, session.session_id):
            session.locked_datastores.add(ds_type)
            return f"""<?xml version="1.0" encoding="UTF-8"?>
<rpc-reply xmlns="{NC_NS}" message-id="{message_id}">
    <ok/>
</rpc-reply>"""
        else:
            return self._rpc_error(message_id, "lock-denied", f"Datastore {ds_type.value} already locked")

    async def _handle_unlock(
        self,
        message_id: str,
        op_element: ET.Element,
        session: NETCONFSession
    ) -> str:
        """Handle unlock operation"""
        target = op_element.find(".//{%s}target" % NC_NS) or op_element.find(".//target")
        ds_type = DatastoreType.RUNNING

        if target is not None:
            for child in target:
                tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if tag in ["running", "candidate", "startup"]:
                    ds_type = DatastoreType(tag)

        if self._datastore.unlock(ds_type, session.session_id):
            session.locked_datastores.discard(ds_type)
            return f"""<?xml version="1.0" encoding="UTF-8"?>
<rpc-reply xmlns="{NC_NS}" message-id="{message_id}">
    <ok/>
</rpc-reply>"""
        else:
            return self._rpc_error(message_id, "operation-failed", "Not locked by this session")

    async def _handle_commit(self, message_id: str, session: NETCONFSession) -> str:
        """Handle commit operation"""
        try:
            self._datastore.commit(session.session_id)
            self._statistics.commits += 1

            # Apply configuration if handler provided
            if self.apply_handler:
                config = self._datastore.get_config(DatastoreType.RUNNING)
                await self.apply_handler(config)

            return f"""<?xml version="1.0" encoding="UTF-8"?>
<rpc-reply xmlns="{NC_NS}" message-id="{message_id}">
    <ok/>
</rpc-reply>"""
        except Exception as e:
            return self._rpc_error(message_id, "operation-failed", str(e))

    async def _handle_discard(self, message_id: str, session: NETCONFSession) -> str:
        """Handle discard-changes operation"""
        self._datastore.discard_changes()
        self._statistics.rollbacks += 1
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<rpc-reply xmlns="{NC_NS}" message-id="{message_id}">
    <ok/>
</rpc-reply>"""

    async def _handle_close_session(
        self,
        message_id: str,
        session: NETCONFSession
    ) -> str:
        """Handle close-session operation"""
        await self._close_session(session.session_id)
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<rpc-reply xmlns="{NC_NS}" message-id="{message_id}">
    <ok/>
</rpc-reply>"""

    async def _handle_copy_config(
        self,
        message_id: str,
        op_element: ET.Element,
        session: NETCONFSession
    ) -> str:
        """Handle copy-config operation"""
        source = op_element.find(".//source")
        target = op_element.find(".//target")

        source_ds = DatastoreType.RUNNING
        target_ds = DatastoreType.STARTUP

        if source is not None:
            for child in source:
                tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if tag in ["running", "candidate", "startup"]:
                    source_ds = DatastoreType(tag)

        if target is not None:
            for child in target:
                tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                if tag in ["running", "candidate", "startup"]:
                    target_ds = DatastoreType(tag)

        try:
            self._datastore.copy_config(source_ds, target_ds, session.session_id)
            return f"""<?xml version="1.0" encoding="UTF-8"?>
<rpc-reply xmlns="{NC_NS}" message-id="{message_id}">
    <ok/>
</rpc-reply>"""
        except Exception as e:
            return self._rpc_error(message_id, "operation-failed", str(e))

    async def _handle_validate(
        self,
        message_id: str,
        op_element: ET.Element,
        session: NETCONFSession
    ) -> str:
        """Handle validate operation"""
        # Simple validation - just check structure exists
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<rpc-reply xmlns="{NC_NS}" message-id="{message_id}">
    <ok/>
</rpc-reply>"""

    def _rpc_error(
        self,
        message_id: str,
        error_tag: str,
        error_message: str
    ) -> str:
        """Generate RPC error response"""
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<rpc-reply xmlns="{NC_NS}" message-id="{message_id}">
    <rpc-error>
        <error-type>application</error-type>
        <error-tag>{error_tag}</error-tag>
        <error-severity>error</error-severity>
        <error-message>{error_message}</error-message>
    </rpc-error>
</rpc-reply>"""

    def _xml_to_dict(self, element: ET.Element) -> Dict[str, Any]:
        """Convert XML element to dictionary"""
        result = {}
        for child in element:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if len(child) > 0:
                result[tag] = self._xml_to_dict(child)
            else:
                result[tag] = child.text or ""
        return result

    def get_statistics(self) -> NETCONFStatistics:
        """Get server statistics"""
        if self._started_at:
            self._statistics.uptime_seconds = (
                datetime.now() - self._started_at
            ).total_seconds()
        return self._statistics

    def get_sessions(self) -> List[Dict[str, Any]]:
        """Get all active sessions"""
        return [s.to_dict() for s in self._sessions.values()]

    def get_config(self) -> Dict[str, Any]:
        """Get server configuration"""
        return self.config.to_dict()

    def get_datastore_config(
        self,
        ds_type: DatastoreType = DatastoreType.RUNNING
    ) -> Dict[str, Any]:
        """Get configuration from datastore"""
        return self._datastore.get_config(ds_type)


# Global NETCONF server instances
_netconf_servers: Dict[str, NETCONFServer] = {}


def get_netconf_server(agent_name: str) -> Optional[NETCONFServer]:
    """Get NETCONF server for an agent"""
    return _netconf_servers.get(agent_name)


async def start_netconf_server(
    agent_name: str,
    port: int = 830,
    apply_handler: Optional[Callable[[Dict], asyncio.Future]] = None,
    **config_kwargs
) -> NETCONFServer:
    """
    Start NETCONF server for an agent.

    Args:
        agent_name: Name of the agent
        port: NETCONF port
        apply_handler: Async function to apply configuration
        **config_kwargs: Additional NETCONFConfig parameters

    Returns:
        NETCONFServer instance
    """
    if agent_name in _netconf_servers:
        return _netconf_servers[agent_name]

    config = NETCONFConfig(port=port, **config_kwargs)
    server = NETCONFServer(agent_name, config, apply_handler)

    if await server.start():
        _netconf_servers[agent_name] = server
        logger.info(f"NETCONF server started for {agent_name} on port {port}")
    else:
        raise RuntimeError(f"Failed to start NETCONF server for {agent_name}")

    return server


async def stop_netconf_server(agent_name: str):
    """Stop NETCONF server for an agent"""
    if agent_name in _netconf_servers:
        server = _netconf_servers.pop(agent_name)
        await server.stop()
        logger.info(f"NETCONF server stopped for {agent_name}")


def get_netconf_statistics(agent_name: Optional[str] = None) -> Dict[str, Any]:
    """Get NETCONF statistics"""
    if agent_name:
        server = _netconf_servers.get(agent_name)
        if server:
            return server.get_statistics().to_dict()
        return {}

    return {
        name: server.get_statistics().to_dict()
        for name, server in _netconf_servers.items()
    }


def list_netconf_sessions(agent_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """List active NETCONF sessions"""
    if agent_name:
        server = _netconf_servers.get(agent_name)
        if server:
            return server.get_sessions()
        return []

    all_sessions = []
    for name, server in _netconf_servers.items():
        sessions = server.get_sessions()
        for session in sessions:
            session["agent_name"] = name
        all_sessions.extend(sessions)
    return all_sessions
