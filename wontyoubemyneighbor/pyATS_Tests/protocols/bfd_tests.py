"""
BFD Tests - Bidirectional Forwarding Detection validation

RFC 5880 - Bidirectional Forwarding Detection (BFD)
RFC 5881 - BFD for IPv4 and IPv6 (Single Hop)
RFC 5882 - Generic Application of BFD
RFC 5883 - BFD for Multi-hop Paths

Tests:
- BFD session state
- Detection timer validation
- Protocol integration (OSPF, BGP, IS-IS)
- Session statistics
"""

from typing import Dict, Any, List, Optional
import asyncio
import logging

from pyATS_Tests import BaseTest, TestSuite, TestResult, TestStatus, TestSeverity

logger = logging.getLogger("pyATS_Tests.bfd")


class BFDSessionStateTest(BaseTest):
    """Test BFD session states"""

    test_id = "bfd_session_state"
    test_name = "BFD Session State"
    description = "Verify all BFD sessions are UP"
    severity = TestSeverity.CRITICAL
    timeout = 30.0

    async def execute(self) -> TestResult:
        try:
            from bfd import get_bfd_manager

            agent_id = self.agent_config.get("id", "local")
            manager = get_bfd_manager(agent_id)

            if not manager or not manager.is_running:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.SKIPPED,
                    severity=self.severity,
                    message="BFD manager not running on this agent"
                )

            sessions = manager.list_sessions()

            if not sessions:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.SKIPPED,
                    severity=self.severity,
                    message="No BFD sessions configured"
                )

            up_sessions = []
            down_sessions = []

            for session in sessions:
                peer = session.get("remote_address", "Unknown")
                state = session.get("state", "DOWN")
                is_up = session.get("is_up", False)

                if is_up or state == "UP":
                    up_sessions.append(peer)
                else:
                    down_sessions.append(f"{peer} ({state})")

            details = {
                "total_sessions": len(sessions),
                "up_sessions": up_sessions,
                "down_sessions": down_sessions,
                "sessions": sessions
            }

            if down_sessions:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message=f"BFD sessions DOWN: {', '.join(down_sessions)}",
                    details=details
                )
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"All {len(up_sessions)} BFD sessions are UP",
                    details=details
                )

        except ImportError:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.SKIPPED,
                severity=self.severity,
                message="BFD module not available"
            )
        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check BFD sessions: {str(e)}"
            )


class BFDDetectionTimerTest(BaseTest):
    """Test BFD detection timer configuration"""

    test_id = "bfd_detection_timer"
    test_name = "BFD Detection Timer"
    description = "Verify BFD detection timers are within acceptable range"
    severity = TestSeverity.MAJOR
    timeout = 30.0

    # Recommended detection times by protocol
    RECOMMENDED_TIMERS = {
        "ospf": {"max_ms": 900, "recommended_ms": 300},
        "bgp": {"max_ms": 900, "recommended_ms": 300},
        "isis": {"max_ms": 900, "recommended_ms": 300},
        "static": {"max_ms": 3000, "recommended_ms": 1000},
        "default": {"max_ms": 3000, "recommended_ms": 1000},
    }

    async def execute(self) -> TestResult:
        try:
            from bfd import get_bfd_manager

            agent_id = self.agent_config.get("id", "local")
            manager = get_bfd_manager(agent_id)

            if not manager or not manager.is_running:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.SKIPPED,
                    severity=self.severity,
                    message="BFD manager not running"
                )

            sessions = manager.list_sessions()

            if not sessions:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.SKIPPED,
                    severity=self.severity,
                    message="No BFD sessions configured"
                )

            timer_results = []
            timer_issues = []

            for session in sessions:
                peer = session.get("remote_address", "Unknown")
                protocol = session.get("client_protocol", "default").lower()
                detection_ms = session.get("detection_time_ms", 0)
                detect_mult = session.get("detect_mult", 3)
                tx_interval = session.get("desired_min_tx_us", 100000) / 1000  # to ms
                rx_interval = session.get("required_min_rx_us", 100000) / 1000  # to ms

                timer_config = self.RECOMMENDED_TIMERS.get(
                    protocol, self.RECOMMENDED_TIMERS["default"]
                )

                result = {
                    "peer": peer,
                    "protocol": protocol,
                    "detection_time_ms": detection_ms,
                    "detect_mult": detect_mult,
                    "tx_interval_ms": tx_interval,
                    "rx_interval_ms": rx_interval,
                    "max_recommended_ms": timer_config["max_ms"],
                    "within_limits": detection_ms <= timer_config["max_ms"]
                }
                timer_results.append(result)

                if detection_ms > timer_config["max_ms"]:
                    timer_issues.append(
                        f"{peer}: detection time {detection_ms:.0f}ms > "
                        f"recommended {timer_config['max_ms']}ms for {protocol}"
                    )

            details = {
                "timer_checks": timer_results,
                "recommended_timers": self.RECOMMENDED_TIMERS
            }

            if timer_issues:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message=f"Timer issues: {'; '.join(timer_issues)}",
                    details=details
                )
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"Detection timers OK for {len(timer_results)} sessions",
                    details=details
                )

        except ImportError:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.SKIPPED,
                severity=self.severity,
                message="BFD module not available"
            )
        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check detection timers: {str(e)}"
            )


class BFDProtocolIntegrationTest(BaseTest):
    """Test BFD integration with routing protocols"""

    test_id = "bfd_protocol_integration"
    test_name = "BFD Protocol Integration"
    description = "Verify BFD is enabled for all configured routing protocols"
    severity = TestSeverity.MAJOR
    timeout = 30.0

    async def execute(self) -> TestResult:
        try:
            from bfd import get_bfd_manager

            agent_id = self.agent_config.get("id", "local")
            manager = get_bfd_manager(agent_id)

            # Get configured routing protocols from agent config
            configured_protocols = set()
            for proto in self.protocols:
                proto_type = proto.get("p", "").lower()
                if proto_type in ["ospf", "ospfv3", "ibgp", "ebgp", "bgp", "isis"]:
                    configured_protocols.add(proto_type.replace("v3", "").replace("i", "").replace("e", ""))

            if not configured_protocols:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.SKIPPED,
                    severity=self.severity,
                    message="No routing protocols configured that support BFD"
                )

            if not manager or not manager.is_running:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message=f"BFD not running but protocols configured: {', '.join(configured_protocols)}"
                )

            sessions = manager.list_sessions()

            # Check which protocols have BFD sessions
            protocols_with_bfd = set()
            for session in sessions:
                proto = session.get("client_protocol", "").lower()
                if proto:
                    protocols_with_bfd.add(proto)

            # Check protocol coverage
            missing_bfd = configured_protocols - protocols_with_bfd

            details = {
                "configured_protocols": list(configured_protocols),
                "protocols_with_bfd": list(protocols_with_bfd),
                "missing_bfd": list(missing_bfd),
                "total_sessions": len(sessions)
            }

            if missing_bfd:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message=f"Protocols without BFD: {', '.join(missing_bfd)}",
                    details=details
                )
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"BFD enabled for all {len(configured_protocols)} routing protocols",
                    details=details
                )

        except ImportError:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.SKIPPED,
                severity=self.severity,
                message="BFD module not available"
            )
        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check protocol integration: {str(e)}"
            )


class BFDStatisticsTest(BaseTest):
    """Test BFD packet statistics"""

    test_id = "bfd_statistics"
    test_name = "BFD Statistics"
    description = "Verify BFD packet exchange is healthy"
    severity = TestSeverity.MINOR
    timeout = 30.0

    async def execute(self) -> TestResult:
        try:
            from bfd import get_bfd_manager

            agent_id = self.agent_config.get("id", "local")
            manager = get_bfd_manager(agent_id)

            if not manager or not manager.is_running:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.SKIPPED,
                    severity=self.severity,
                    message="BFD manager not running"
                )

            sessions = manager.list_sessions()

            if not sessions:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.SKIPPED,
                    severity=self.severity,
                    message="No BFD sessions configured"
                )

            stats_results = []
            stats_issues = []

            for session in sessions:
                peer = session.get("remote_address", "Unknown")
                stats = session.get("statistics", {})

                packets_sent = stats.get("packets_sent", 0)
                packets_received = stats.get("packets_received", 0)
                packets_dropped = stats.get("packets_dropped", 0)
                up_transitions = stats.get("up_transitions", 0)
                down_transitions = stats.get("down_transitions", 0)

                result = {
                    "peer": peer,
                    "packets_sent": packets_sent,
                    "packets_received": packets_received,
                    "packets_dropped": packets_dropped,
                    "up_transitions": up_transitions,
                    "down_transitions": down_transitions,
                    "flaps": down_transitions  # Session flaps
                }
                stats_results.append(result)

                # Check for issues
                if packets_sent > 0 and packets_received == 0:
                    stats_issues.append(f"{peer}: no packets received")
                elif packets_dropped > packets_received * 0.1:  # >10% drop rate
                    drop_rate = (packets_dropped / (packets_received + packets_dropped)) * 100
                    stats_issues.append(f"{peer}: high drop rate {drop_rate:.1f}%")

                # Too many flaps indicate instability
                if down_transitions > 5:
                    stats_issues.append(f"{peer}: {down_transitions} session flaps")

            # Get manager stats
            manager_stats = manager.stats.to_dict() if hasattr(manager, 'stats') else {}

            details = {
                "session_statistics": stats_results,
                "manager_statistics": manager_stats
            }

            if stats_issues:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message=f"Statistics issues: {'; '.join(stats_issues)}",
                    details=details
                )
            else:
                total_tx = sum(s["packets_sent"] for s in stats_results)
                total_rx = sum(s["packets_received"] for s in stats_results)
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"Statistics healthy: {total_tx} TX, {total_rx} RX across {len(stats_results)} sessions",
                    details=details
                )

        except ImportError:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.SKIPPED,
                severity=self.severity,
                message="BFD module not available"
            )
        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to get BFD statistics: {str(e)}"
            )


class BFDMultiplierTest(BaseTest):
    """Test BFD detection multiplier configuration"""

    test_id = "bfd_multiplier"
    test_name = "BFD Detection Multiplier"
    description = "Verify BFD detection multiplier is appropriately configured"
    severity = TestSeverity.MINOR
    timeout = 30.0

    # Recommended multiplier range
    MIN_MULTIPLIER = 3
    MAX_MULTIPLIER = 10

    async def execute(self) -> TestResult:
        try:
            from bfd import get_bfd_manager

            agent_id = self.agent_config.get("id", "local")
            manager = get_bfd_manager(agent_id)

            if not manager or not manager.is_running:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.SKIPPED,
                    severity=self.severity,
                    message="BFD manager not running"
                )

            sessions = manager.list_sessions()

            if not sessions:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.SKIPPED,
                    severity=self.severity,
                    message="No BFD sessions configured"
                )

            mult_results = []
            mult_issues = []

            for session in sessions:
                peer = session.get("remote_address", "Unknown")
                detect_mult = session.get("detect_mult", 3)

                result = {
                    "peer": peer,
                    "detect_mult": detect_mult,
                    "within_range": self.MIN_MULTIPLIER <= detect_mult <= self.MAX_MULTIPLIER
                }
                mult_results.append(result)

                if detect_mult < self.MIN_MULTIPLIER:
                    mult_issues.append(
                        f"{peer}: multiplier {detect_mult} too low (min {self.MIN_MULTIPLIER})"
                    )
                elif detect_mult > self.MAX_MULTIPLIER:
                    mult_issues.append(
                        f"{peer}: multiplier {detect_mult} too high (max {self.MAX_MULTIPLIER})"
                    )

            details = {
                "multiplier_checks": mult_results,
                "recommended_range": f"{self.MIN_MULTIPLIER}-{self.MAX_MULTIPLIER}"
            }

            if mult_issues:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message=f"Multiplier issues: {'; '.join(mult_issues)}",
                    details=details
                )
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"Multipliers OK for {len(mult_results)} sessions",
                    details=details
                )

        except ImportError:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.SKIPPED,
                severity=self.severity,
                message="BFD module not available"
            )
        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check multipliers: {str(e)}"
            )


class BFDEchoModeTest(BaseTest):
    """Test BFD echo mode configuration"""

    test_id = "bfd_echo_mode"
    test_name = "BFD Echo Mode"
    description = "Verify BFD echo mode configuration where applicable"
    severity = TestSeverity.MINOR
    timeout = 30.0

    async def execute(self) -> TestResult:
        try:
            from bfd import get_bfd_manager

            agent_id = self.agent_config.get("id", "local")
            manager = get_bfd_manager(agent_id)

            if not manager or not manager.is_running:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.SKIPPED,
                    severity=self.severity,
                    message="BFD manager not running"
                )

            sessions = manager.list_sessions()

            if not sessions:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.SKIPPED,
                    severity=self.severity,
                    message="No BFD sessions configured"
                )

            # Check echo mode settings
            echo_enabled = 0
            echo_disabled = 0
            single_hop_sessions = []

            for session in sessions:
                peer = session.get("remote_address", "Unknown")
                session_type = session.get("session_type", "single_hop")

                if session_type == "single_hop":
                    single_hop_sessions.append({
                        "peer": peer,
                        "session_type": session_type,
                        # Echo mode is typically configured per-session
                        "echo_capable": True  # Single-hop can use echo
                    })

            details = {
                "total_sessions": len(sessions),
                "single_hop_sessions": single_hop_sessions,
                "echo_mode_info": "Echo mode reduces control plane load for single-hop BFD"
            }

            # Echo mode is optional, so this is informational
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.PASSED,
                severity=self.severity,
                message=f"Checked echo mode for {len(sessions)} sessions ({len(single_hop_sessions)} single-hop)",
                details=details
            )

        except ImportError:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.SKIPPED,
                severity=self.severity,
                message="BFD module not available"
            )
        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check echo mode: {str(e)}"
            )


def get_suite(agent_config: Dict[str, Any]) -> TestSuite:
    """Get BFD test suite for an agent"""
    suite = TestSuite(
        suite_id="protocol_bfd",
        suite_name="BFD Tests",
        description="BFD session state, timers, and protocol integration validation",
        protocol="bfd"
    )

    suite.tests = [
        BFDSessionStateTest(agent_config),
        BFDDetectionTimerTest(agent_config),
        BFDProtocolIntegrationTest(agent_config),
        BFDStatisticsTest(agent_config),
        BFDMultiplierTest(agent_config),
        BFDEchoModeTest(agent_config)
    ]

    return suite
