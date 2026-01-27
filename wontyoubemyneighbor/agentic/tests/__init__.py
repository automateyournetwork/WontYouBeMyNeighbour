"""
Unit Tests and Dynamic Test Generation for ASI Agentic Network Router

Test suite covering all major components:
- LLM interfaces (test_llm_interface.py)
- Reasoning engine (test_reasoning.py)
- Action executor (test_actions.py)
- Multi-agent coordination (test_multi_agent.py)
- LLDP neighbor discovery (test_lldp.py)
- LACP link aggregation (test_lacp.py)
- Firewall/ACL management (test_firewall.py)
- Subinterface/VLAN management (test_subinterface.py)
- Agent messaging/collaboration (test_messaging.py)

Dynamic Test Generation (Self-Testing Network):
- DynamicTestGenerator: Agents generate pyATS AEtest scripts
- SelfTestingAgent: Autonomous test execution via pyATS MCP
- TestCategory: Connectivity, Protocol, Interface, Routing tests
- TestTrigger: Scheduled, State Change, Anomaly, Self-Assessment

Run tests with:
    pytest wontyoubemyneighbor/agentic/tests/ -v

Run specific test file:
    pytest wontyoubemyneighbor/agentic/tests/test_lldp.py -v

Run with coverage:
    pytest wontyoubemyneighbor/agentic/tests/ --cov=wontyoubemyneighbor.agentic
"""

from .dynamic_test_generator import (
    DynamicTestGenerator,
    SelfTestingAgent,
    GeneratedTest,
    TestExecutionResult,
    TestCategory,
    TestTrigger,
)

__all__ = [
    # Dynamic Test Generation (Self-Testing Network)
    'DynamicTestGenerator',
    'SelfTestingAgent',
    'GeneratedTest',
    'TestExecutionResult',
    'TestCategory',
    'TestTrigger',
]
