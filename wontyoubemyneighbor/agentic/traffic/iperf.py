"""
iPerf Integration - Network bandwidth testing using iPerf-style interface

Provides:
- iPerf3-compatible server/client operations
- TCP and UDP bandwidth testing
- Bidirectional and reverse mode tests
- JSON result parsing and reporting
"""

import logging
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any
import random
import json

logger = logging.getLogger("iPerf")


class IPerfProtocol(Enum):
    """Protocol for iPerf tests"""
    TCP = "tcp"
    UDP = "udp"
    SCTP = "sctp"


class IPerfMode(Enum):
    """iPerf operation mode"""
    NORMAL = "normal"       # Client sends to server
    REVERSE = "reverse"     # Server sends to client
    BIDIRECTIONAL = "bidirectional"  # Both directions


@dataclass
class IPerfStream:
    """
    Data for a single iPerf stream

    Attributes:
        stream_id: Stream identifier
        socket: Socket number
        start_time: Start of stream
        end_time: End of stream
        bytes_transferred: Total bytes
        bits_per_second: Throughput in bps
        retransmits: TCP retransmits (TCP only)
        jitter_ms: Jitter in milliseconds (UDP only)
        lost_packets: Lost packets (UDP only)
        packets_sent: Total packets sent (UDP only)
    """
    stream_id: int
    socket: int = 0
    start_time: float = 0.0
    end_time: float = 0.0
    bytes_transferred: int = 0
    bits_per_second: float = 0.0
    retransmits: int = 0
    jitter_ms: float = 0.0
    lost_packets: int = 0
    packets_sent: int = 0

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    @property
    def mbps(self) -> float:
        return self.bits_per_second / 1_000_000

    @property
    def gbps(self) -> float:
        return self.bits_per_second / 1_000_000_000

    @property
    def loss_percent(self) -> float:
        if self.packets_sent == 0:
            return 0.0
        return (self.lost_packets / self.packets_sent) * 100

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stream_id": self.stream_id,
            "socket": self.socket,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "bytes_transferred": self.bytes_transferred,
            "bits_per_second": self.bits_per_second,
            "mbps": self.mbps,
            "gbps": self.gbps,
            "retransmits": self.retransmits,
            "jitter_ms": self.jitter_ms,
            "lost_packets": self.lost_packets,
            "packets_sent": self.packets_sent,
            "loss_percent": self.loss_percent
        }


@dataclass
class IPerfResult:
    """
    Complete iPerf test result

    Attributes:
        test_id: Unique test identifier
        client_ip: Client IP address
        server_ip: Server IP address
        server_port: Server port
        protocol: Test protocol
        mode: Test mode
        duration_seconds: Test duration
        parallel_streams: Number of parallel streams
        streams: Individual stream results
        cpu_utilization_local: Local CPU usage
        cpu_utilization_remote: Remote CPU usage
        error: Error message if test failed
    """
    test_id: str
    client_ip: str
    server_ip: str
    server_port: int
    protocol: IPerfProtocol
    mode: IPerfMode = IPerfMode.NORMAL
    duration_seconds: float = 10.0
    parallel_streams: int = 1
    streams: List[IPerfStream] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    cpu_utilization_local: float = 0.0
    cpu_utilization_remote: float = 0.0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        return self.error is None and len(self.streams) > 0

    @property
    def total_bytes(self) -> int:
        return sum(s.bytes_transferred for s in self.streams)

    @property
    def total_bits_per_second(self) -> float:
        return sum(s.bits_per_second for s in self.streams)

    @property
    def total_mbps(self) -> float:
        return self.total_bits_per_second / 1_000_000

    @property
    def total_gbps(self) -> float:
        return self.total_bits_per_second / 1_000_000_000

    @property
    def avg_jitter_ms(self) -> float:
        if not self.streams:
            return 0.0
        return sum(s.jitter_ms for s in self.streams) / len(self.streams)

    @property
    def total_retransmits(self) -> int:
        return sum(s.retransmits for s in self.streams)

    @property
    def total_packet_loss(self) -> float:
        total_sent = sum(s.packets_sent for s in self.streams)
        total_lost = sum(s.lost_packets for s in self.streams)
        if total_sent == 0:
            return 0.0
        return (total_lost / total_sent) * 100

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "client_ip": self.client_ip,
            "server_ip": self.server_ip,
            "server_port": self.server_port,
            "protocol": self.protocol.value,
            "mode": self.mode.value,
            "duration_seconds": self.duration_seconds,
            "parallel_streams": self.parallel_streams,
            "streams": [s.to_dict() for s in self.streams],
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "is_success": self.is_success,
            "total_bytes": self.total_bytes,
            "total_mbps": self.total_mbps,
            "total_gbps": self.total_gbps,
            "avg_jitter_ms": self.avg_jitter_ms,
            "total_retransmits": self.total_retransmits,
            "total_packet_loss": self.total_packet_loss,
            "cpu_utilization_local": self.cpu_utilization_local,
            "cpu_utilization_remote": self.cpu_utilization_remote,
            "error": self.error,
            "metadata": self.metadata
        }

    def to_json(self) -> str:
        """Export as iPerf3-compatible JSON"""
        return json.dumps(self.to_dict(), indent=2)


class IPerfServer:
    """
    iPerf server simulation

    Listens for incoming iPerf tests and records results
    """

    def __init__(self, bind_ip: str = "0.0.0.0", port: int = 5201):
        """
        Initialize iPerf server

        Args:
            bind_ip: IP address to bind to
            port: Port to listen on
        """
        self.bind_ip = bind_ip
        self.port = port
        self.running = False
        self._results: List[IPerfResult] = []
        self._server_id = f"iperf-server-{port}"

    async def start(self):
        """Start the iPerf server"""
        self.running = True
        logger.info(f"iPerf server started on {self.bind_ip}:{self.port}")

    async def stop(self):
        """Stop the iPerf server"""
        self.running = False
        logger.info(f"iPerf server stopped on {self.bind_ip}:{self.port}")

    def get_results(self) -> List[IPerfResult]:
        """Get all test results"""
        return self._results

    def add_result(self, result: IPerfResult):
        """Add a test result"""
        self._results.append(result)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "server_id": self._server_id,
            "bind_ip": self.bind_ip,
            "port": self.port,
            "running": self.running,
            "result_count": len(self._results)
        }


class IPerfClient:
    """
    iPerf client simulation

    Runs bandwidth tests against iPerf servers
    """

    def __init__(self, client_ip: str = "0.0.0.0"):
        """
        Initialize iPerf client

        Args:
            client_ip: Client IP address
        """
        self.client_ip = client_ip
        self._test_counter = 0
        self._results: List[IPerfResult] = []

    def _generate_test_id(self) -> str:
        """Generate unique test ID"""
        self._test_counter += 1
        return f"iperf-test-{self._test_counter:06d}"

    async def run_test(
        self,
        server_ip: str,
        server_port: int = 5201,
        duration: float = 10.0,
        protocol: IPerfProtocol = IPerfProtocol.TCP,
        mode: IPerfMode = IPerfMode.NORMAL,
        parallel: int = 1,
        bandwidth_limit_mbps: Optional[float] = None,
        packet_size: int = 1500,
        simulate: bool = True
    ) -> IPerfResult:
        """
        Run an iPerf bandwidth test

        Args:
            server_ip: Server IP address
            server_port: Server port
            duration: Test duration in seconds
            protocol: Test protocol
            mode: Test mode
            parallel: Number of parallel streams
            bandwidth_limit_mbps: Bandwidth limit (UDP only)
            packet_size: Packet size
            simulate: Simulate results (True) or attempt real test (False)

        Returns:
            IPerfResult with test results
        """
        result = IPerfResult(
            test_id=self._generate_test_id(),
            client_ip=self.client_ip,
            server_ip=server_ip,
            server_port=server_port,
            protocol=protocol,
            mode=mode,
            duration_seconds=duration,
            parallel_streams=parallel
        )

        if simulate:
            # Simulate realistic test results
            result = await self._simulate_test(result, bandwidth_limit_mbps, packet_size)
        else:
            # Attempt real iPerf test (would require actual iperf3 binary)
            result.error = "Real iPerf testing not implemented - use simulate=True"

        self._results.append(result)
        return result

    async def _simulate_test(
        self,
        result: IPerfResult,
        bandwidth_limit_mbps: Optional[float],
        packet_size: int
    ) -> IPerfResult:
        """
        Simulate iPerf test with realistic results

        Args:
            result: Result object to populate
            bandwidth_limit_mbps: Bandwidth limit
            packet_size: Packet size

        Returns:
            Populated result
        """
        try:
            # Simulate test duration
            await asyncio.sleep(min(result.duration_seconds, 2.0))  # Cap simulation time

            # Generate realistic throughput based on protocol
            if result.protocol == IPerfProtocol.TCP:
                # TCP typically achieves 90-98% of link capacity
                base_throughput = bandwidth_limit_mbps or random.uniform(100, 1000)
                efficiency = random.uniform(0.90, 0.98)
                throughput_mbps = base_throughput * efficiency

                # Generate streams
                for i in range(result.parallel_streams):
                    stream_throughput = throughput_mbps / result.parallel_streams
                    bytes_transferred = int((stream_throughput * 1_000_000 / 8) * result.duration_seconds)

                    stream = IPerfStream(
                        stream_id=i,
                        socket=5 + i,
                        start_time=0.0,
                        end_time=result.duration_seconds,
                        bytes_transferred=bytes_transferred,
                        bits_per_second=stream_throughput * 1_000_000,
                        retransmits=random.randint(0, 50)
                    )
                    result.streams.append(stream)

            else:  # UDP or SCTP
                # UDP has more variation and potential loss
                base_throughput = bandwidth_limit_mbps or random.uniform(50, 500)
                jitter_base = random.uniform(0.1, 2.0)
                loss_base = random.uniform(0, 2.0)  # 0-2% base loss

                for i in range(result.parallel_streams):
                    stream_throughput = base_throughput / result.parallel_streams
                    bytes_transferred = int((stream_throughput * 1_000_000 / 8) * result.duration_seconds)
                    packets_sent = bytes_transferred // packet_size

                    stream = IPerfStream(
                        stream_id=i,
                        socket=5 + i,
                        start_time=0.0,
                        end_time=result.duration_seconds,
                        bytes_transferred=bytes_transferred,
                        bits_per_second=stream_throughput * 1_000_000,
                        jitter_ms=jitter_base + random.uniform(-0.5, 0.5),
                        packets_sent=packets_sent,
                        lost_packets=int(packets_sent * (loss_base / 100))
                    )
                    result.streams.append(stream)

            # CPU utilization
            result.cpu_utilization_local = random.uniform(5, 30)
            result.cpu_utilization_remote = random.uniform(5, 30)

            result.end_time = datetime.now()
            logger.info(f"iPerf test completed: {result.test_id}, {result.total_mbps:.2f} Mbps")

        except Exception as e:
            result.error = str(e)
            result.end_time = datetime.now()
            logger.error(f"iPerf test failed: {result.test_id}: {e}")

        return result

    def get_results(self) -> List[IPerfResult]:
        """Get all test results"""
        return self._results

    def get_result(self, test_id: str) -> Optional[IPerfResult]:
        """Get a specific test result"""
        for result in self._results:
            if result.test_id == test_id:
                return result
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "client_ip": self.client_ip,
            "test_count": len(self._results)
        }


class IPerfManager:
    """
    Manages iPerf servers and clients across the network
    """

    def __init__(self):
        """Initialize iPerf manager"""
        self._servers: Dict[str, IPerfServer] = {}
        self._clients: Dict[str, IPerfClient] = {}
        self._all_results: List[IPerfResult] = []

    def create_server(
        self,
        server_id: str,
        bind_ip: str = "0.0.0.0",
        port: int = 5201
    ) -> IPerfServer:
        """
        Create an iPerf server

        Args:
            server_id: Unique server identifier
            bind_ip: IP to bind to
            port: Port to listen on

        Returns:
            Created IPerfServer
        """
        server = IPerfServer(bind_ip=bind_ip, port=port)
        self._servers[server_id] = server
        logger.info(f"Created iPerf server: {server_id}")
        return server

    def create_client(
        self,
        client_id: str,
        client_ip: str = "0.0.0.0"
    ) -> IPerfClient:
        """
        Create an iPerf client

        Args:
            client_id: Unique client identifier
            client_ip: Client IP address

        Returns:
            Created IPerfClient
        """
        client = IPerfClient(client_ip=client_ip)
        self._clients[client_id] = client
        logger.info(f"Created iPerf client: {client_id}")
        return client

    def get_server(self, server_id: str) -> Optional[IPerfServer]:
        """Get a server by ID"""
        return self._servers.get(server_id)

    def get_client(self, client_id: str) -> Optional[IPerfClient]:
        """Get a client by ID"""
        return self._clients.get(client_id)

    async def run_test(
        self,
        client_id: str,
        server_ip: str,
        server_port: int = 5201,
        **kwargs
    ) -> Optional[IPerfResult]:
        """
        Run an iPerf test using a managed client

        Args:
            client_id: Client to use
            server_ip: Server IP address
            server_port: Server port
            **kwargs: Additional test parameters

        Returns:
            IPerfResult or None if client not found
        """
        client = self._clients.get(client_id)
        if not client:
            logger.warning(f"Client not found: {client_id}")
            return None

        result = await client.run_test(
            server_ip=server_ip,
            server_port=server_port,
            **kwargs
        )

        self._all_results.append(result)
        return result

    async def run_mesh_test(
        self,
        endpoints: List[Dict[str, str]],
        duration: float = 10.0,
        protocol: IPerfProtocol = IPerfProtocol.TCP
    ) -> List[IPerfResult]:
        """
        Run bandwidth tests between all endpoint pairs

        Args:
            endpoints: List of {id, ip} dictionaries
            duration: Test duration
            protocol: Test protocol

        Returns:
            List of all test results
        """
        results = []

        for i, source in enumerate(endpoints):
            for j, dest in enumerate(endpoints):
                if i == j:
                    continue

                # Ensure client exists
                client_id = source.get("id", f"client-{i}")
                if client_id not in self._clients:
                    self.create_client(client_id, source.get("ip", "0.0.0.0"))

                result = await self.run_test(
                    client_id=client_id,
                    server_ip=dest.get("ip", "0.0.0.0"),
                    duration=duration,
                    protocol=protocol
                )
                if result:
                    results.append(result)

        return results

    def get_all_results(self) -> List[IPerfResult]:
        """Get all test results"""
        return self._all_results

    def get_statistics(self) -> Dict[str, Any]:
        """Get manager statistics"""
        successful = len([r for r in self._all_results if r.is_success])
        failed = len([r for r in self._all_results if not r.is_success])

        avg_throughput = 0.0
        if successful > 0:
            avg_throughput = sum(r.total_mbps for r in self._all_results if r.is_success) / successful

        return {
            "total_servers": len(self._servers),
            "total_clients": len(self._clients),
            "total_tests": len(self._all_results),
            "successful_tests": successful,
            "failed_tests": failed,
            "avg_throughput_mbps": avg_throughput
        }


# Global manager instance
_global_manager: Optional[IPerfManager] = None


def get_iperf_manager() -> IPerfManager:
    """Get or create the global iPerf manager"""
    global _global_manager
    if _global_manager is None:
        _global_manager = IPerfManager()
    return _global_manager
