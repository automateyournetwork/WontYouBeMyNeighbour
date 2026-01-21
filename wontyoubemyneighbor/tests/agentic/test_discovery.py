"""Tests for service discovery module"""

import pytest
from agentic.discovery import (
    Service, ServiceStatus, ServiceType, ServiceInstance, ServiceRegistry, get_service_registry,
    HealthCheck, HealthStatus, HealthCheckType, HealthChecker, get_health_checker,
    LoadBalancer, LoadBalanceStrategy, ServiceEndpoint, get_load_balancer
)


class TestServiceRegistry:
    """Tests for ServiceRegistry"""

    def test_register_service(self):
        """Test service registration"""
        registry = ServiceRegistry()
        service = registry.register_service(
            name="test-service",
            service_type=ServiceType.API,
            description="Test service"
        )
        assert service.name == "test-service"
        assert service.service_type == ServiceType.API

    def test_register_instance(self):
        """Test instance registration"""
        registry = ServiceRegistry()
        instance = registry.register_instance(
            service_name="test-service",
            host="localhost",
            port=8080
        )
        assert instance.host == "localhost"
        assert instance.port == 8080
        assert instance.is_available()

    def test_discover_service(self):
        """Test service discovery"""
        registry = ServiceRegistry()
        registry.register_instance("test-service", "host1", 8080)
        registry.register_instance("test-service", "host2", 8081)

        instances = registry.discover("test-service", healthy_only=False)
        assert len(instances) == 2

    def test_heartbeat(self):
        """Test instance heartbeat"""
        registry = ServiceRegistry()
        instance = registry.register_instance("test-service", "localhost", 8080)
        old_seen = instance.last_seen_at

        registry.heartbeat("test-service", instance.id)
        assert instance.last_seen_at >= old_seen

    def test_deregister_instance(self):
        """Test instance deregistration"""
        registry = ServiceRegistry()
        instance = registry.register_instance("test-service", "localhost", 8080)

        assert registry.deregister_instance("test-service", instance.id)
        assert len(registry.discover("test-service", healthy_only=False)) == 0


class TestHealthChecker:
    """Tests for HealthChecker"""

    def test_create_check(self):
        """Test health check creation"""
        checker = HealthChecker()
        check = checker.create_check(
            name="test-check",
            target="test-service",
            check_type=HealthCheckType.HTTP,
            http_url="http://localhost:8080/health"
        )
        assert check.name == "test-check"
        assert check.check_type == HealthCheckType.HTTP

    def test_execute_check(self):
        """Test health check execution"""
        checker = HealthChecker()
        check = checker.create_check(
            name="test-check",
            target="test-service",
            check_type=HealthCheckType.HTTP
        )

        result = checker.execute_check(check.id)
        assert result is not None
        assert result.status in [HealthStatus.HEALTHY, HealthStatus.UNHEALTHY]

    def test_enable_disable_check(self):
        """Test enabling/disabling checks"""
        checker = HealthChecker()
        check = checker.create_check("test", "target", HealthCheckType.TCP)

        assert checker.disable_check(check.id)
        assert not check.enabled

        assert checker.enable_check(check.id)
        assert check.enabled

    def test_delete_check(self):
        """Test check deletion"""
        checker = HealthChecker()
        check = checker.create_check("test", "target", HealthCheckType.HTTP)

        assert checker.delete_check(check.id)
        assert checker.get_check(check.id) is None


class TestLoadBalancer:
    """Tests for LoadBalancer"""

    def test_select_round_robin(self):
        """Test round robin selection"""
        lb = LoadBalancer()
        lb.config.strategy = LoadBalanceStrategy.ROUND_ROBIN

        # Create a fresh registry for this test
        registry = ServiceRegistry()
        inst1 = registry.register_instance("test-lb-rr", "host1", 8080)
        inst2 = registry.register_instance("test-lb-rr", "host2", 8081)

        # Mark instances as healthy
        inst1.mark_healthy()
        inst2.mark_healthy()

        # Manually set endpoints for testing
        lb._endpoints["test-lb-rr"] = {
            inst1.id: ServiceEndpoint(instance_id=inst1.id, address=inst1.address, weight=100),
            inst2.id: ServiceEndpoint(instance_id=inst2.id, address=inst2.address, weight=100)
        }

        # Select should work
        endpoint1 = lb.select("test-lb-rr")
        endpoint2 = lb.select("test-lb-rr")

        # With round robin, should cycle through endpoints
        assert endpoint1 is not None
        assert endpoint2 is not None

    def test_set_strategy(self):
        """Test setting load balance strategy"""
        lb = LoadBalancer()
        lb.set_strategy(LoadBalanceStrategy.RANDOM)
        assert lb.config.strategy == LoadBalanceStrategy.RANDOM

        lb.set_strategy(LoadBalanceStrategy.LEAST_CONNECTIONS)
        assert lb.config.strategy == LoadBalanceStrategy.LEAST_CONNECTIONS

    def test_clear_sessions(self):
        """Test clearing sticky sessions"""
        lb = LoadBalancer()
        lb._sessions["session1"] = "instance1"
        lb._sessions["session2"] = "instance2"

        cleared = lb.clear_sessions()
        assert cleared == 2
        assert len(lb._sessions) == 0


class TestServiceEndpoint:
    """Tests for ServiceEndpoint"""

    def test_use_and_release(self):
        """Test endpoint use and release"""
        endpoint = ServiceEndpoint(
            instance_id="test-1",
            address="http://localhost:8080"
        )

        endpoint.use()
        assert endpoint.connections == 1
        assert endpoint.request_count == 1

        endpoint.release(success=True, response_time_ms=10.0)
        assert endpoint.connections == 0
        assert endpoint.error_count == 0

    def test_success_rate(self):
        """Test success rate calculation"""
        endpoint = ServiceEndpoint(
            instance_id="test-1",
            address="http://localhost:8080"
        )

        # Initial rate should be 1.0
        assert endpoint.success_rate == 1.0

        # Record some requests
        for _ in range(8):
            endpoint.use()
            endpoint.release(success=True)

        for _ in range(2):
            endpoint.use()
            endpoint.release(success=False)

        # 8 out of 10 successful
        assert endpoint.success_rate == 0.8


class TestHealthCheck:
    """Tests for HealthCheck dataclass"""

    def test_is_due(self):
        """Test check due logic"""
        check = HealthCheck(
            id="hc-1",
            name="test",
            target="service",
            interval_seconds=10
        )

        # Should be due initially (no last check)
        assert check.is_due()

        # Disable and should not be due
        check.enabled = False
        assert not check.is_due()

    def test_record_result(self):
        """Test recording results"""
        check = HealthCheck(id="hc-1", name="test", target="service")

        from agentic.discovery.health import HealthCheckResult
        result = HealthCheckResult(
            check_id="hc-1",
            status=HealthStatus.HEALTHY,
            latency_ms=5.0
        )

        check.record_result(result)
        assert check.last_status == HealthStatus.HEALTHY
        assert check.consecutive_successes == 1
        assert len(check.history) == 1
