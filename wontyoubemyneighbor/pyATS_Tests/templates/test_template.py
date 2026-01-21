"""
Test Template - Example template for creating custom pyATS tests

Use this template as a starting point for creating custom test suites.
Copy this file and modify the tests to fit your specific requirements.

Example Usage:
    1. Copy this file to a new name (e.g., my_custom_tests.py)
    2. Rename the classes and modify the test logic
    3. Update get_suite() to return your custom tests
    4. Register your test suite in the test runner
"""

from typing import Dict, Any, List
import asyncio
import logging

from pyATS_Tests import BaseTest, TestSuite, TestResult, TestStatus, TestSeverity

logger = logging.getLogger("pyATS_Tests.custom")


class CustomTest1(BaseTest):
    """
    Template for a custom test

    Customize:
    - test_id: Unique identifier for this test
    - test_name: Human-readable name
    - description: What this test validates
    - severity: How critical is this test (CRITICAL, MAJOR, MINOR, INFO)
    - timeout: Maximum execution time in seconds
    """

    # Unique identifier for this test
    test_id = "custom_test_1"

    # Human-readable name shown in reports
    test_name = "Custom Test 1"

    # Description of what this test validates
    description = "Example custom test - modify for your needs"

    # Severity level determines reporting priority
    # TestSeverity.CRITICAL - Service affecting
    # TestSeverity.MAJOR - Significant issue
    # TestSeverity.MINOR - Non-critical issue
    # TestSeverity.INFO - Informational only
    severity = TestSeverity.MINOR

    # Maximum time for test execution (seconds)
    timeout = 30.0

    async def setup(self) -> None:
        """
        Optional: Pre-test setup

        Use this for:
        - Initializing connections
        - Preparing test data
        - Setting up prerequisites
        """
        # Example: Log test start
        logger.debug(f"Setting up {self.test_name}")
        pass

    async def execute(self) -> TestResult:
        """
        Main test execution logic

        Returns:
            TestResult with status, message, and details

        Available instance variables:
        - self.agent_config: Full agent TOON configuration
        - self.agent_id: Agent identifier
        - self.router_id: Agent's router ID
        - self.interfaces: List of interface configurations
        - self.protocols: List of protocol configurations
        """
        try:
            # =====================================================
            # CUSTOMIZE YOUR TEST LOGIC HERE
            # =====================================================

            # Example: Check something from agent config
            some_condition = True  # Replace with actual check

            # Example: Run a shell command
            proc = await asyncio.create_subprocess_exec(
                "echo", "test",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            command_output = stdout.decode().strip()

            # Example: Access agent configuration
            agent_name = self.agent_config.get("n", "unknown")
            protocol_count = len(self.protocols)

            # Prepare details dict for the result
            details = {
                "agent_name": agent_name,
                "protocol_count": protocol_count,
                "custom_data": command_output
            }

            # =====================================================
            # RETURN APPROPRIATE RESULT
            # =====================================================

            if some_condition:
                # Test passed
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.PASSED,
                    severity=self.severity,
                    message="Custom test passed successfully",
                    details=details
                )
            else:
                # Test failed
                return TestResult(
                    test_id=self.test_id,
                    test_name=self.test_name,
                    status=TestStatus.FAILED,
                    severity=self.severity,
                    message="Custom test failed - describe why",
                    details=details
                )

        except Exception as e:
            # Test errored
            return TestResult(
                test_id=self.test_id,
                test_name=self.test_name,
                status=TestStatus.ERROR,
                severity=self.severity,
                message=f"Test error: {str(e)}"
            )

    async def cleanup(self) -> None:
        """
        Optional: Post-test cleanup

        Use this for:
        - Closing connections
        - Cleaning up test artifacts
        - Restoring state
        """
        logger.debug(f"Cleaning up {self.test_name}")
        pass


class CustomTest2(BaseTest):
    """Another example test - copy and customize"""

    test_id = "custom_test_2"
    test_name = "Custom Test 2"
    description = "Another example custom test"
    severity = TestSeverity.INFO
    timeout = 10.0

    async def execute(self) -> TestResult:
        # Simple informational test example
        return TestResult(
            test_id=self.test_id,
            test_name=self.test_name,
            status=TestStatus.PASSED,
            severity=self.severity,
            message=f"Agent {self.agent_id} info collected",
            details={
                "router_id": self.router_id,
                "interface_count": len(self.interfaces),
                "protocol_count": len(self.protocols)
            }
        )


def get_suite(agent_config: Dict[str, Any]) -> TestSuite:
    """
    Create and return the custom test suite

    Args:
        agent_config: Agent TOON configuration dict

    Returns:
        TestSuite with all custom tests
    """
    suite = TestSuite(
        # Unique identifier for this test suite
        suite_id="custom_tests",

        # Human-readable suite name
        suite_name="Custom Test Suite",

        # Description of what this suite tests
        description="Template custom test suite - modify for your needs",

        # Optional: Associated protocol (None for general tests)
        protocol=None
    )

    # Add tests to the suite
    suite.tests = [
        CustomTest1(agent_config),
        CustomTest2(agent_config),
        # Add more tests here...
    ]

    return suite


# =====================================================
# USAGE EXAMPLE
# =====================================================
#
# To use this template:
#
# 1. Copy this file:
#    cp test_template.py my_tests.py
#
# 2. Edit my_tests.py:
#    - Rename CustomTest1/CustomTest2 classes
#    - Modify test_id, test_name, description
#    - Implement your test logic in execute()
#    - Update get_suite() with your tests
#
# 3. Register in pyATS_Tests/__init__.py:
#    from .templates import my_tests
#
#    def get_tests_for_agent(agent_config):
#        ...
#        # Add your custom suite
#        suites.append(my_tests.get_suite(agent_config))
#        ...
#
# 4. Run tests:
#    from pyATS_Tests import run_all_tests
#    results = await run_all_tests(agent_config)
