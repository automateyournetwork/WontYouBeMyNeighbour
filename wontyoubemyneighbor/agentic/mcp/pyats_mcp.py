"""
pyATS MCP Client - Network Testing and Validation

Provides integration with the pyATS MCP server for network device
testing, command execution, and configuration management.

Features:
- Device listing and discovery
- Show command execution with optional parsing
- Safe configuration application
- Running config and logging retrieval
- Ping testing from network devices
- Linux command execution on compatible devices
- Dynamic pyATS test execution

GitHub: https://github.com/automateyournetwork/pyATS_MCP
"""

import asyncio
import json
import logging
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union
from enum import Enum
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("PYATS_MCP")


class CommandType(Enum):
    """Types of commands that can be executed"""
    SHOW = "show"
    PING = "ping"
    CONFIGURE = "configure"
    LINUX = "linux"


class ParseMode(Enum):
    """Output parsing modes"""
    PARSED = "parsed"  # Genie-parsed structured output
    RAW = "raw"        # Raw text output


@dataclass
class DeviceInfo:
    """Information about a network device"""
    name: str
    os: str
    device_type: str
    platform: Optional[str] = None
    connections: Dict[str, Any] = field(default_factory=dict)
    custom: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DeviceInfo":
        return cls(
            name=data.get("name", "unknown"),
            os=data.get("os", "unknown"),
            device_type=data.get("type", "unknown"),
            platform=data.get("platform"),
            connections=data.get("connections", {}),
            custom=data.get("custom", {}),
        )


@dataclass
class CommandResult:
    """Result from command execution"""
    device: str
    command: str
    success: bool
    output: Any  # Can be dict (parsed) or str (raw)
    parsed: bool = False
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device": self.device,
            "command": self.command,
            "success": self.success,
            "output": self.output,
            "parsed": self.parsed,
            "error": self.error,
            "timestamp": self.timestamp,
        }


@dataclass
class PingResult:
    """Result from ping command execution"""
    device: str
    destination: str
    success: bool
    packets_sent: int = 0
    packets_received: int = 0
    packet_loss_percent: float = 0.0
    min_rtt: Optional[float] = None
    avg_rtt: Optional[float] = None
    max_rtt: Optional[float] = None
    raw_output: Optional[str] = None
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device": self.device,
            "destination": self.destination,
            "success": self.success,
            "packets_sent": self.packets_sent,
            "packets_received": self.packets_received,
            "packet_loss_percent": self.packet_loss_percent,
            "min_rtt_ms": self.min_rtt,
            "avg_rtt_ms": self.avg_rtt,
            "max_rtt_ms": self.max_rtt,
            "raw_output": self.raw_output,
            "error": self.error,
            "timestamp": self.timestamp,
        }


@dataclass
class ConfigResult:
    """Result from configuration application"""
    device: str
    commands_applied: List[str]
    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "device": self.device,
            "commands_applied": self.commands_applied,
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "timestamp": self.timestamp,
        }


@dataclass
class TestResult:
    """Result from dynamic test execution"""
    test_name: str
    success: bool
    passed: int = 0
    failed: int = 0
    errored: int = 0
    sections: List[Dict[str, Any]] = field(default_factory=list)
    output: Optional[str] = None
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_name": self.test_name,
            "success": self.success,
            "passed": self.passed,
            "failed": self.failed,
            "errored": self.errored,
            "sections": self.sections,
            "output": self.output,
            "error": self.error,
            "timestamp": self.timestamp,
        }


class PyATSMCPClient:
    """
    pyATS MCP Client for network device testing and validation

    Connects to the pyATS MCP server via JSON-RPC over stdio to provide:
    - Device discovery and listing
    - Show command execution with Genie parsing
    - Safe configuration application
    - Running config and log retrieval
    - Network ping testing
    - Dynamic pyATS test execution
    """

    def __init__(
        self,
        server_path: Optional[str] = None,
        testbed_path: Optional[str] = None,
        docker_mode: bool = False,
        docker_image: str = "pyats-mcp-server",
    ):
        """
        Initialize pyATS MCP client

        Args:
            server_path: Path to pyats_mcp_server.py
            testbed_path: Path to pyATS testbed.yaml
            docker_mode: Use Docker container instead of direct Python
            docker_image: Docker image name if docker_mode is True
        """
        self.server_path = server_path
        self.testbed_path = testbed_path
        self.docker_mode = docker_mode
        self.docker_image = docker_image
        self._process: Optional[subprocess.Popen] = None
        self._request_id = 0
        self._connected = False
        self._devices_cache: Dict[str, DeviceInfo] = {}

    async def connect(self) -> bool:
        """
        Start connection to pyATS MCP server

        Returns:
            True if connected successfully
        """
        if self._connected:
            return True

        try:
            env = {}
            if self.testbed_path:
                env["PYATS_TESTBED_PATH"] = self.testbed_path

            if self.docker_mode:
                cmd = [
                    "docker", "run", "-i", "--rm",
                    "-e", f"PYATS_TESTBED_PATH={self.testbed_path or '/app/testbed.yaml'}",
                ]
                if self.testbed_path:
                    testbed_dir = str(Path(self.testbed_path).parent)
                    cmd.extend(["-v", f"{testbed_dir}:/app"])
                cmd.append(self.docker_image)
            else:
                if not self.server_path:
                    logger.error("server_path required for non-Docker mode")
                    return False
                cmd = ["python3", "-u", self.server_path]

            import os
            full_env = os.environ.copy()
            full_env.update(env)

            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=full_env,
            )
            self._connected = True
            logger.info("Connected to pyATS MCP server")

            # Discover available tools
            await self._discover_tools()

            return True

        except Exception as e:
            logger.error(f"Failed to connect to pyATS MCP server: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from pyATS MCP server"""
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
        self._connected = False
        logger.info("Disconnected from pyATS MCP server")

    async def _send_request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send JSON-RPC request to MCP server

        Args:
            method: JSON-RPC method name
            params: Optional parameters

        Returns:
            Response dictionary
        """
        if not self._connected or not self._process:
            raise ConnectionError("Not connected to pyATS MCP server")

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
        }
        if params:
            request["params"] = params

        request_str = json.dumps(request) + "\n"

        try:
            self._process.stdin.write(request_str.encode())
            self._process.stdin.flush()

            # Read response
            response_line = await asyncio.get_event_loop().run_in_executor(
                None, self._process.stdout.readline
            )

            if not response_line:
                raise ConnectionError("No response from server")

            response = json.loads(response_line.decode())

            if "error" in response:
                error = response["error"]
                raise RuntimeError(f"MCP Error: {error.get('message', 'Unknown error')}")

            return response.get("result", {})

        except Exception as e:
            logger.error(f"Request failed: {e}")
            raise

    async def _discover_tools(self) -> List[Dict[str, Any]]:
        """Discover available tools from MCP server"""
        try:
            result = await self._send_request("tools/discover")
            return result.get("tools", [])
        except Exception as e:
            logger.warning(f"Tool discovery failed: {e}")
            return []

    async def _call_tool(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Call a tool on the MCP server

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool result
        """
        params = {"name": tool_name}
        if arguments:
            params["arguments"] = arguments

        result = await self._send_request("tools/call", params)
        return result

    # =========================================================================
    # Device Operations
    # =========================================================================

    async def list_devices(self, refresh: bool = False) -> List[DeviceInfo]:
        """
        List all devices in the testbed

        Args:
            refresh: Force refresh from server

        Returns:
            List of DeviceInfo objects
        """
        if self._devices_cache and not refresh:
            return list(self._devices_cache.values())

        try:
            result = await self._call_tool("pyats_list_devices")
            devices = []

            for device_data in result.get("devices", []):
                device = DeviceInfo.from_dict(device_data)
                devices.append(device)
                self._devices_cache[device.name] = device

            logger.info(f"Discovered {len(devices)} devices")
            return devices

        except Exception as e:
            logger.error(f"Failed to list devices: {e}")
            return []

    async def get_device(self, device_name: str) -> Optional[DeviceInfo]:
        """
        Get information about a specific device

        Args:
            device_name: Name of the device

        Returns:
            DeviceInfo or None if not found
        """
        if device_name in self._devices_cache:
            return self._devices_cache[device_name]

        await self.list_devices(refresh=True)
        return self._devices_cache.get(device_name)

    # =========================================================================
    # Show Commands
    # =========================================================================

    async def run_show_command(
        self,
        device_name: str,
        command: str,
        parse: bool = True
    ) -> CommandResult:
        """
        Execute a show command on a device

        Args:
            device_name: Name of the device
            command: Show command to execute
            parse: Attempt to parse output with Genie

        Returns:
            CommandResult with output
        """
        try:
            result = await self._call_tool(
                "pyats_run_show_command",
                {"device_name": device_name, "command": command}
            )

            # Determine if output was parsed
            output = result.get("output", result.get("raw_output", ""))
            parsed = isinstance(output, dict)

            return CommandResult(
                device=device_name,
                command=command,
                success=True,
                output=output,
                parsed=parsed,
            )

        except Exception as e:
            return CommandResult(
                device=device_name,
                command=command,
                success=False,
                output=None,
                error=str(e),
            )

    async def get_running_config(self, device_name: str) -> CommandResult:
        """
        Get running configuration from a device

        Args:
            device_name: Name of the device

        Returns:
            CommandResult with configuration
        """
        try:
            result = await self._call_tool(
                "pyats_show_running_config",
                {"device_name": device_name}
            )

            return CommandResult(
                device=device_name,
                command="show running-config",
                success=True,
                output=result.get("config", result.get("output", "")),
                parsed=False,
            )

        except Exception as e:
            return CommandResult(
                device=device_name,
                command="show running-config",
                success=False,
                output=None,
                error=str(e),
            )

    async def get_logging(self, device_name: str) -> CommandResult:
        """
        Get system logs from a device

        Args:
            device_name: Name of the device

        Returns:
            CommandResult with logs
        """
        try:
            result = await self._call_tool(
                "pyats_show_logging",
                {"device_name": device_name}
            )

            return CommandResult(
                device=device_name,
                command="show logging",
                success=True,
                output=result.get("logs", result.get("output", "")),
                parsed=False,
            )

        except Exception as e:
            return CommandResult(
                device=device_name,
                command="show logging",
                success=False,
                output=None,
                error=str(e),
            )

    # =========================================================================
    # Ping Operations
    # =========================================================================

    async def ping(
        self,
        device_name: str,
        destination: str,
        count: int = 5,
        source: Optional[str] = None,
        vrf: Optional[str] = None,
    ) -> PingResult:
        """
        Execute ping from a network device

        Args:
            device_name: Name of the source device
            destination: IP address or hostname to ping
            count: Number of ping packets
            source: Source interface or IP
            vrf: VRF name for ping

        Returns:
            PingResult with statistics
        """
        # Build ping command
        cmd = f"ping {destination}"
        if count != 5:
            cmd += f" count {count}"
        if source:
            cmd += f" source {source}"
        if vrf:
            cmd += f" vrf {vrf}"

        try:
            result = await self._call_tool(
                "pyats_ping_from_network_device",
                {"device_name": device_name, "command": cmd}
            )

            # Parse ping statistics from result
            stats = result.get("statistics", {})

            return PingResult(
                device=device_name,
                destination=destination,
                success=result.get("success", False),
                packets_sent=stats.get("packets_sent", count),
                packets_received=stats.get("packets_received", 0),
                packet_loss_percent=stats.get("packet_loss_percent", 100.0),
                min_rtt=stats.get("min_rtt"),
                avg_rtt=stats.get("avg_rtt"),
                max_rtt=stats.get("max_rtt"),
                raw_output=result.get("raw_output"),
            )

        except Exception as e:
            return PingResult(
                device=device_name,
                destination=destination,
                success=False,
                error=str(e),
            )

    # =========================================================================
    # Configuration Operations
    # =========================================================================

    async def configure(
        self,
        device_name: str,
        commands: Union[str, List[str]]
    ) -> ConfigResult:
        """
        Apply configuration to a device

        Args:
            device_name: Name of the device
            commands: Configuration commands (string or list)

        Returns:
            ConfigResult with status
        """
        # Normalize commands to list
        if isinstance(commands, str):
            cmd_list = [c.strip() for c in commands.split("\n") if c.strip()]
        else:
            cmd_list = commands

        try:
            result = await self._call_tool(
                "pyats_configure_device",
                {"device_name": device_name, "config_commands": cmd_list}
            )

            return ConfigResult(
                device=device_name,
                commands_applied=cmd_list,
                success=result.get("success", True),
                output=result.get("output"),
            )

        except Exception as e:
            return ConfigResult(
                device=device_name,
                commands_applied=cmd_list,
                success=False,
                error=str(e),
            )

    # =========================================================================
    # Linux Commands (for compatible devices)
    # =========================================================================

    async def run_linux_command(
        self,
        device_name: str,
        command: str
    ) -> CommandResult:
        """
        Run a Linux command on a compatible device

        Args:
            device_name: Name of the device
            command: Linux command to execute

        Returns:
            CommandResult with output
        """
        try:
            result = await self._call_tool(
                "pyats_run_linux_command",
                {"device_name": device_name, "command": command}
            )

            return CommandResult(
                device=device_name,
                command=command,
                success=True,
                output=result.get("output", ""),
                parsed=False,
            )

        except Exception as e:
            return CommandResult(
                device=device_name,
                command=command,
                success=False,
                output=None,
                error=str(e),
            )

    # =========================================================================
    # Dynamic Test Execution
    # =========================================================================

    async def run_test(self, test_script: str) -> TestResult:
        """
        Execute a dynamic pyATS test script

        The script must be a valid pyATS AEtest script with an embedded
        TEST_DATA dictionary containing test parameters.

        Args:
            test_script: Python test script content

        Returns:
            TestResult with pass/fail statistics
        """
        try:
            result = await self._call_tool(
                "pyats_run_dynamic_test",
                {"test_script_content": test_script}
            )

            return TestResult(
                test_name=result.get("test_name", "dynamic_test"),
                success=result.get("success", False),
                passed=result.get("passed", 0),
                failed=result.get("failed", 0),
                errored=result.get("errored", 0),
                sections=result.get("sections", []),
                output=result.get("output"),
            )

        except Exception as e:
            return TestResult(
                test_name="dynamic_test",
                success=False,
                error=str(e),
            )

    # =========================================================================
    # Convenience Methods for Agent Integration
    # =========================================================================

    async def verify_connectivity(
        self,
        source_device: str,
        destinations: List[str]
    ) -> Dict[str, PingResult]:
        """
        Verify connectivity from a device to multiple destinations

        Args:
            source_device: Source device name
            destinations: List of destination IPs/hostnames

        Returns:
            Dictionary mapping destination to PingResult
        """
        results = {}
        for dest in destinations:
            results[dest] = await self.ping(source_device, dest)
        return results

    async def collect_device_state(
        self,
        device_name: str,
        commands: Optional[List[str]] = None
    ) -> Dict[str, CommandResult]:
        """
        Collect state from a device using multiple show commands

        Args:
            device_name: Device to collect from
            commands: List of show commands (defaults to common ones)

        Returns:
            Dictionary mapping command to result
        """
        if commands is None:
            commands = [
                "show version",
                "show ip interface brief",
                "show ip route",
                "show interfaces status",
            ]

        results = {}
        for cmd in commands:
            results[cmd] = await self.run_show_command(device_name, cmd)
        return results

    async def compare_configs(
        self,
        device_name: str,
        expected_config: str
    ) -> Dict[str, Any]:
        """
        Compare running config against expected configuration

        Args:
            device_name: Device to check
            expected_config: Expected configuration snippet

        Returns:
            Comparison result with missing/extra lines
        """
        result = await self.get_running_config(device_name)

        if not result.success:
            return {
                "success": False,
                "error": result.error,
                "matches": False,
            }

        running = set(result.output.strip().split("\n"))
        expected = set(expected_config.strip().split("\n"))

        missing = expected - running
        extra = running - expected

        return {
            "success": True,
            "matches": len(missing) == 0,
            "missing_lines": list(missing),
            "extra_lines": list(extra),
        }


# Global client instance
_pyats_client: Optional[PyATSMCPClient] = None


def get_pyats_client() -> PyATSMCPClient:
    """Get or create the global pyATS MCP client instance"""
    global _pyats_client
    if _pyats_client is None:
        _pyats_client = PyATSMCPClient()
    return _pyats_client


async def init_pyats_for_agent(
    server_path: Optional[str] = None,
    testbed_path: Optional[str] = None,
    docker_mode: bool = False,
) -> PyATSMCPClient:
    """
    Initialize pyATS MCP client for an agent

    Args:
        server_path: Path to pyats_mcp_server.py
        testbed_path: Path to pyATS testbed.yaml
        docker_mode: Use Docker container

    Returns:
        Connected PyATSMCPClient
    """
    global _pyats_client
    _pyats_client = PyATSMCPClient(
        server_path=server_path,
        testbed_path=testbed_path,
        docker_mode=docker_mode,
    )
    await _pyats_client.connect()
    return _pyats_client
