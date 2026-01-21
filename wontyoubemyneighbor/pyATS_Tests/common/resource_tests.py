"""
Resource Tests - System resource utilization validation

Tests:
- CPU usage
- Memory usage
- Disk usage
- Process health
"""

from typing import Dict, Any
import asyncio
import logging

from pyATS_Tests import BaseTest, TestSuite, TestResult, TestStatus, TestSeverity

logger = logging.getLogger("pyATS_Tests.resource")


class CPUUsageTest(BaseTest):
    """Test CPU usage is within acceptable limits"""

    test_id = "resource_cpu"
    test_name = "CPU Usage"
    description = "Verify CPU usage is within acceptable limits"
    severity = TestSeverity.MAJOR
    timeout = 15.0

    # Configurable thresholds
    warning_threshold = 70.0  # percentage
    critical_threshold = 90.0  # percentage

    async def execute(self) -> TestResult:
        try:
            # Use /proc/stat for CPU usage (works in containers)
            proc = await asyncio.create_subprocess_shell(
                "cat /proc/stat | head -1",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout1, _ = await proc.communicate()

            # Wait a second to calculate delta
            await asyncio.sleep(1)

            proc = await asyncio.create_subprocess_shell(
                "cat /proc/stat | head -1",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout2, _ = await proc.communicate()

            # Parse CPU stats
            def parse_cpu_stat(line):
                parts = line.decode().strip().split()
                return {
                    "user": int(parts[1]),
                    "nice": int(parts[2]),
                    "system": int(parts[3]),
                    "idle": int(parts[4]),
                    "iowait": int(parts[5]) if len(parts) > 5 else 0
                }

            stats1 = parse_cpu_stat(stdout1)
            stats2 = parse_cpu_stat(stdout2)

            # Calculate usage
            total1 = sum(stats1.values())
            total2 = sum(stats2.values())
            idle1 = stats1["idle"]
            idle2 = stats2["idle"]

            total_diff = total2 - total1
            idle_diff = idle2 - idle1

            if total_diff > 0:
                cpu_usage = (1 - idle_diff / total_diff) * 100
            else:
                cpu_usage = 0.0

            cpu_usage = round(cpu_usage, 1)

            details = {
                "cpu_usage_percent": cpu_usage,
                "warning_threshold": self.warning_threshold,
                "critical_threshold": self.critical_threshold
            }

            if cpu_usage >= self.critical_threshold:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=TestSeverity.CRITICAL,
                    message=f"CPU usage critical: {cpu_usage}%",
                    details=details
                )
            elif cpu_usage >= self.warning_threshold:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=TestSeverity.MINOR,
                    message=f"CPU usage elevated but acceptable: {cpu_usage}%",
                    details=details
                )
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"CPU usage normal: {cpu_usage}%",
                    details=details
                )

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check CPU: {str(e)}"
            )


class MemoryUsageTest(BaseTest):
    """Test memory usage is within acceptable limits"""

    test_id = "resource_memory"
    test_name = "Memory Usage"
    description = "Verify memory usage is within acceptable limits"
    severity = TestSeverity.MAJOR
    timeout = 10.0

    warning_threshold = 80.0  # percentage
    critical_threshold = 95.0  # percentage

    async def execute(self) -> TestResult:
        try:
            # Read /proc/meminfo
            proc = await asyncio.create_subprocess_exec(
                "cat", "/proc/meminfo",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()

            # Parse memory info
            mem_info = {}
            for line in stdout.decode().split("\n"):
                if ":" in line:
                    key, value = line.split(":", 1)
                    # Extract numeric value (in kB)
                    value_parts = value.strip().split()
                    if value_parts:
                        mem_info[key] = int(value_parts[0])

            total = mem_info.get("MemTotal", 0)
            available = mem_info.get("MemAvailable", mem_info.get("MemFree", 0))

            if total > 0:
                used = total - available
                usage_percent = round((used / total) * 100, 1)
            else:
                usage_percent = 0.0

            details = {
                "memory_total_mb": round(total / 1024, 1),
                "memory_used_mb": round(used / 1024, 1) if total > 0 else 0,
                "memory_available_mb": round(available / 1024, 1),
                "memory_usage_percent": usage_percent,
                "warning_threshold": self.warning_threshold,
                "critical_threshold": self.critical_threshold
            }

            if usage_percent >= self.critical_threshold:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=TestSeverity.CRITICAL,
                    message=f"Memory usage critical: {usage_percent}%",
                    details=details
                )
            elif usage_percent >= self.warning_threshold:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=TestSeverity.MINOR,
                    message=f"Memory usage elevated: {usage_percent}%",
                    details=details
                )
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"Memory usage normal: {usage_percent}%",
                    details=details
                )

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check memory: {str(e)}"
            )


class DiskUsageTest(BaseTest):
    """Test disk usage on key filesystems"""

    test_id = "resource_disk"
    test_name = "Disk Usage"
    description = "Verify disk usage is within acceptable limits"
    severity = TestSeverity.MAJOR
    timeout = 10.0

    warning_threshold = 80.0  # percentage
    critical_threshold = 95.0  # percentage

    async def execute(self) -> TestResult:
        try:
            # Get disk usage with df
            proc = await asyncio.create_subprocess_exec(
                "df", "-P", "/",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()

            # Parse df output (skip header)
            lines = stdout.decode().strip().split("\n")
            if len(lines) < 2:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.ERROR,
                    severity=self.severity,
                    message="Could not parse disk usage"
                )

            # Parse data line
            parts = lines[1].split()
            if len(parts) >= 5:
                filesystem = parts[0]
                total_kb = int(parts[1])
                used_kb = int(parts[2])
                avail_kb = int(parts[3])
                usage_str = parts[4].rstrip("%")
                usage_percent = float(usage_str)
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.ERROR,
                    severity=self.severity,
                    message="Could not parse disk usage output"
                )

            details = {
                "filesystem": filesystem,
                "total_gb": round(total_kb / 1024 / 1024, 2),
                "used_gb": round(used_kb / 1024 / 1024, 2),
                "available_gb": round(avail_kb / 1024 / 1024, 2),
                "usage_percent": usage_percent,
                "warning_threshold": self.warning_threshold,
                "critical_threshold": self.critical_threshold
            }

            if usage_percent >= self.critical_threshold:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=TestSeverity.CRITICAL,
                    message=f"Disk usage critical: {usage_percent}%",
                    details=details
                )
            elif usage_percent >= self.warning_threshold:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=TestSeverity.MINOR,
                    message=f"Disk usage elevated: {usage_percent}%",
                    details=details
                )
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"Disk usage normal: {usage_percent}%",
                    details=details
                )

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check disk: {str(e)}"
            )


class ProcessHealthTest(BaseTest):
    """Test that critical agent processes are running"""

    test_id = "resource_processes"
    test_name = "Process Health"
    description = "Verify critical agent processes are running"
    severity = TestSeverity.CRITICAL
    timeout = 10.0

    # Critical processes to check based on protocol
    process_map = {
        "ospf": ["ospfd"],
        "ospfv3": ["ospf6d"],
        "ibgp": ["bgpd"],
        "ebgp": ["bgpd"],
        "isis": ["isisd"],
        "ldp": ["ldpd"],
        "mpls": ["ldpd", "zebra"],
        "vxlan": ["zebra"],
        "dhcp": ["dhcpd", "dhcrelay"],
        "dns": ["named", "dnsmasq"]
    }

    async def execute(self) -> TestResult:
        try:
            # Get list of running processes
            proc = await asyncio.create_subprocess_exec(
                "ps", "aux",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            ps_output = stdout.decode()

            # Determine which processes to check
            expected_processes = set()
            for proto_config in self.protocols:
                proto_type = proto_config.get("p", "").lower()
                if proto_type in self.process_map:
                    expected_processes.update(self.process_map[proto_type])

            # Always check zebra for FRR-based routing
            expected_processes.add("zebra")

            results = []
            failed = 0

            for proc_name in expected_processes:
                # Check if process is in ps output
                if proc_name in ps_output:
                    results.append({
                        "process": proc_name,
                        "status": "running"
                    })
                else:
                    results.append({
                        "process": proc_name,
                        "status": "not_found"
                    })
                    failed += 1

            details = {
                "processes": results,
                "expected": list(expected_processes)
            }

            if failed == 0:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"All {len(expected_processes)} critical processes running",
                    details=details
                )
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message=f"{failed} critical processes not running",
                    details=details
                )

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check processes: {str(e)}"
            )


class UptimeTest(BaseTest):
    """Test system uptime"""

    test_id = "resource_uptime"
    test_name = "System Uptime"
    description = "Check system uptime and stability"
    severity = TestSeverity.INFO
    timeout = 5.0

    async def execute(self) -> TestResult:
        try:
            # Read uptime from /proc/uptime
            proc = await asyncio.create_subprocess_exec(
                "cat", "/proc/uptime",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()

            uptime_seconds = float(stdout.decode().split()[0])

            # Convert to human-readable
            days = int(uptime_seconds // 86400)
            hours = int((uptime_seconds % 86400) // 3600)
            minutes = int((uptime_seconds % 3600) // 60)

            uptime_str = ""
            if days > 0:
                uptime_str += f"{days}d "
            uptime_str += f"{hours}h {minutes}m"

            details = {
                "uptime_seconds": uptime_seconds,
                "uptime_human": uptime_str.strip(),
                "days": days,
                "hours": hours,
                "minutes": minutes
            }

            # Warn if uptime is very short (possible recent crash/restart)
            if uptime_seconds < 60:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=TestSeverity.MINOR,
                    message=f"Agent recently started: {uptime_str}",
                    details=details
                )
            else:
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message=f"Agent uptime: {uptime_str}",
                    details=details
                )

        except Exception as e:
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Failed to check uptime: {str(e)}"
            )


def get_suite(agent_config: Dict[str, Any]) -> TestSuite:
    """Get resource test suite for an agent"""
    suite = TestSuite(
        suite_id="common_resource",
        suite_name="Resource Tests",
        description="System resource utilization validation",
        protocol=None  # Common to all agents
    )

    suite.tests = [
        CPUUsageTest(agent_config),
        MemoryUsageTest(agent_config),
        DiskUsageTest(agent_config),
        ProcessHealthTest(agent_config),
        UptimeTest(agent_config)
    ]

    return suite
