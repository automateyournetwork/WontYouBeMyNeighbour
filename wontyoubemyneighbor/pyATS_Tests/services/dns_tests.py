"""
DNS Tests - DNS server validation

Tests:
- Zone loading
- Query resolution
"""

from typing import Dict, Any
import asyncio
import re
import logging

from pyATS_Tests import BaseTest, TestSuite, TestResult, TestStatus, TestSeverity

logger = logging.getLogger("pyATS_Tests.dns")


class DNSServiceTest(BaseTest):
    """Test DNS service is running"""

    test_id = "dns_service"
    test_name = "DNS Service"
    description = "Verify DNS service is operational"
    severity = TestSeverity.CRITICAL
    timeout = 15.0

    async def execute(self) -> TestResult:
        try:
            # Check if DNS service is running
            dns_processes = ["named", "dnsmasq", "unbound"]
            running = None

            for proc_name in dns_processes:
                proc = await asyncio.create_subprocess_exec(
                    "pgrep", "-x", proc_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                await proc.communicate()

                if proc.returncode == 0:
                    running = proc_name
                    break

            details = {"dns_process": running}

            if running:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"DNS service ({running}) is running",
                    details=details
                )
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message="No DNS service running",
                    details=details
                )

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check DNS service: {str(e)}"
            )


class DNSZoneLoadingTest(BaseTest):
    """Test DNS zone loading"""

    test_id = "dns_zone_loading"
    test_name = "DNS Zone Loading"
    description = "Verify DNS zones are loaded"
    severity = TestSeverity.MAJOR
    timeout = 20.0

    async def execute(self) -> TestResult:
        try:
            # Get expected zone from config
            zone_name = None
            for proto in self.protocols:
                if proto.get("p") == "dns":
                    zone_name = proto.get("zone")
                    break

            # Check zone with rndc (BIND) or zone files
            proc = await asyncio.create_subprocess_exec(
                "rndc", "status",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()

            if proc.returncode == 0:
                output = stdout.decode()
                zones_match = re.search(r"number of zones:\s*(\d+)", output)
                zone_count = int(zones_match.group(1)) if zones_match else 0

                details = {"zone_count": zone_count, "bind_status": output[:200]}

                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"{zone_count} DNS zones loaded",
                    details=details
                )
            else:
                # rndc not available, check zone files
                proc = await asyncio.create_subprocess_shell(
                    "ls /etc/bind/zones/* 2>/dev/null || ls /var/named/*.zone 2>/dev/null || echo 'none'",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await proc.communicate()

                zones = [z for z in stdout.decode().split("\n") if z.strip() and z != "none"]

                details = {"zone_files": zones}

                if zones:
                    return TestResult(
                        test_id=self.test_id,
                        test_name=self.test_name,
                        status=TestStatus.PASSED,
                        severity=self.severity,
                        message=f"Found {len(zones)} zone files",
                        details=details
                    )
                else:
                    return TestResult(
                        test_id=self.test_id,
                        test_name=self.test_name,
                        status=TestStatus.SKIPPED,
                        severity=self.severity,
                        message="No zone files found (may be using forwarders)",
                        details=details
                    )

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check zones: {str(e)}"
            )


class DNSQueryResolutionTest(BaseTest):
    """Test DNS query resolution"""

    test_id = "dns_query"
    test_name = "DNS Query Resolution"
    description = "Verify DNS queries are resolved"
    severity = TestSeverity.CRITICAL
    timeout = 15.0

    async def execute(self) -> TestResult:
        try:
            # Test DNS resolution using dig or host
            test_queries = [
                ("localhost", "127.0.0.1"),
            ]

            # Get configured zone if any
            for proto in self.protocols:
                if proto.get("p") == "dns":
                    zone = proto.get("zone")
                    if zone:
                        test_queries.append((f"ns.{zone}", None))

            results = []

            for query, expected in test_queries:
                proc = await asyncio.create_subprocess_exec(
                    "dig", "+short", query, "@127.0.0.1",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await proc.communicate()

                answer = stdout.decode().strip()

                result = {
                    "query": query,
                    "answer": answer if answer else "NXDOMAIN",
                    "success": bool(answer)
                }

                if expected and answer:
                    result["expected"] = expected
                    result["success"] = expected in answer

                results.append(result)

            details = {"queries": results}
            successful = [r for r in results if r["success"]]

            if len(successful) == len(results):
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"All {len(results)} DNS queries resolved",
                    details=details
                )
            elif successful:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=TestSeverity.MINOR,
                    message=f"{len(successful)}/{len(results)} queries resolved",
                    details=details
                )
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message="DNS resolution failing",
                    details=details
                )

        except FileNotFoundError:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message="dig command not found"
            )
        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to test DNS: {str(e)}"
            )


def get_suite(agent_config: Dict[str, Any]) -> TestSuite:
    """Get DNS test suite for an agent"""
    suite = TestSuite(
        suite_id="service_dns",
        suite_name="DNS Service Tests",
        description="DNS server validation",
        protocol="dns"
    )

    suite.tests = [
        DNSServiceTest(agent_config),
        DNSZoneLoadingTest(agent_config),
        DNSQueryResolutionTest(agent_config)
    ]

    return suite
