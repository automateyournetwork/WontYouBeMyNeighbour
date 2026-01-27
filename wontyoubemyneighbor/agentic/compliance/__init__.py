"""
Network Compliance Module

This module provides network compliance checking including:
- Configuration compliance validation
- Best practice enforcement
- Security policy checks
- Regulatory compliance (PCI-DSS, HIPAA hints)
- Custom rule definition

Classes:
    ComplianceSeverity: Enum of compliance issue severities
    ComplianceCategory: Enum of compliance categories
    ComplianceRule: A compliance rule definition
    ComplianceViolation: A detected compliance violation
    ComplianceReport: A compliance check report
    ComplianceChecker: Main compliance checking engine

Functions:
    get_compliance_checker: Get the singleton ComplianceChecker instance
    run_compliance_check: Run compliance checks on the network
    get_compliance_rules: Get available compliance rules
"""

from .compliance_checker import (
    ComplianceSeverity,
    ComplianceCategory,
    ComplianceRule,
    ComplianceViolation,
    ComplianceReport,
    ComplianceChecker,
)


# Singleton instance
_checker_instance = None


def get_compliance_checker() -> ComplianceChecker:
    """Get the singleton ComplianceChecker instance."""
    global _checker_instance
    if _checker_instance is None:
        _checker_instance = ComplianceChecker()
    return _checker_instance


def run_compliance_check(
    categories: list = None,
    agents: list = None,
    rule_set: str = None
) -> ComplianceReport:
    """Run compliance checks on the network."""
    checker = get_compliance_checker()
    return checker.run_check(
        categories=categories,
        agents=agents,
        rule_set=rule_set
    )


def get_compliance_rules(category: str = None) -> list:
    """Get available compliance rules."""
    checker = get_compliance_checker()
    return checker.get_rules(category)


__all__ = [
    'ComplianceSeverity',
    'ComplianceCategory',
    'ComplianceRule',
    'ComplianceViolation',
    'ComplianceReport',
    'ComplianceChecker',
    'get_compliance_checker',
    'run_compliance_check',
    'get_compliance_rules',
]
