"""
SMTP MCP - Email Notification Integration

Provides email capability for agents to send alerts, reports, and notifications.

Features:
- Send email notifications for events (neighbor down, test failures, etc.)
- Send periodic reports (daily/weekly summaries)
- Send test emails for configuration verification
- Email templates for common scenarios
- Email logging and history

Use Cases:
- pyATS test failures trigger email alerts
- Protocol neighbor state changes (OSPF/BGP down)
- Daily/weekly network health reports
- ServiceNow ticket notifications
"""

import asyncio
import logging
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
from datetime import datetime
import json
import time

logger = logging.getLogger("SMTP_MCP")

# Singleton client instance
_smtp_client: Optional["SMTPClient"] = None


class EmailPriority(Enum):
    """Email priority levels"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class EmailStatus(Enum):
    """Email delivery status"""
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    QUEUED = "queued"


class AlertType(Enum):
    """Types of alerts that trigger emails"""
    TEST_FAILURE = "test_failure"
    NEIGHBOR_DOWN = "neighbor_down"
    NEIGHBOR_UP = "neighbor_up"
    ROUTE_CHANGE = "route_change"
    INTERFACE_DOWN = "interface_down"
    HIGH_CPU = "high_cpu"
    HIGH_MEMORY = "high_memory"
    CUSTOM = "custom"


@dataclass
class SMTPConfig:
    """SMTP server configuration"""
    server: str = "localhost"
    port: int = 587
    username: str = ""
    password: str = ""
    use_tls: bool = True
    use_ssl: bool = False
    from_address: str = "agent@network.local"
    from_name: str = "Network Agent"
    timeout: int = 30

    def to_dict(self) -> Dict[str, Any]:
        return {
            "server": self.server,
            "port": self.port,
            "username": self.username,
            "use_tls": self.use_tls,
            "use_ssl": self.use_ssl,
            "from_address": self.from_address,
            "from_name": self.from_name,
            "timeout": self.timeout
        }


@dataclass
class EmailAttachment:
    """Email attachment"""
    filename: str
    content: bytes
    content_type: str = "application/octet-stream"


@dataclass
class Email:
    """Email message"""
    to: List[str]
    subject: str
    body: str
    html_body: Optional[str] = None
    cc: List[str] = field(default_factory=list)
    bcc: List[str] = field(default_factory=list)
    reply_to: Optional[str] = None
    priority: EmailPriority = EmailPriority.NORMAL
    attachments: List[EmailAttachment] = field(default_factory=list)
    headers: Dict[str, str] = field(default_factory=dict)

    # Metadata
    created_at: float = field(default_factory=time.time)
    sent_at: Optional[float] = None
    status: EmailStatus = EmailStatus.PENDING
    error_message: Optional[str] = None
    message_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "to": self.to,
            "subject": self.subject,
            "body": self.body[:200] + "..." if len(self.body) > 200 else self.body,
            "cc": self.cc,
            "bcc": self.bcc,
            "priority": self.priority.value,
            "attachment_count": len(self.attachments),
            "created_at": datetime.fromtimestamp(self.created_at).isoformat(),
            "sent_at": datetime.fromtimestamp(self.sent_at).isoformat() if self.sent_at else None,
            "status": self.status.value,
            "error_message": self.error_message,
            "message_id": self.message_id
        }


@dataclass
class AlertRule:
    """Rule for triggering email alerts"""
    name: str
    alert_type: AlertType
    recipients: List[str]
    enabled: bool = True
    subject_template: str = "[{agent}] {alert_type}: {summary}"
    body_template: str = ""
    priority: EmailPriority = EmailPriority.NORMAL
    cooldown_seconds: int = 300  # Prevent alert spam
    last_triggered: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "alert_type": self.alert_type.value,
            "recipients": self.recipients,
            "enabled": self.enabled,
            "priority": self.priority.value,
            "cooldown_seconds": self.cooldown_seconds,
            "last_triggered": datetime.fromtimestamp(self.last_triggered).isoformat() if self.last_triggered else None
        }


class EmailTemplates:
    """Pre-built email templates for common scenarios"""

    @staticmethod
    def test_failure(agent_name: str, test_name: str, details: str) -> tuple:
        """Template for pyATS test failure"""
        subject = f"[{agent_name}] Test Failed: {test_name}"
        body = f"""
Network Agent Test Failure Alert

Agent: {agent_name}
Test: {test_name}
Time: {datetime.now().isoformat()}

Details:
{details}

This is an automated alert from the Network Agent system.
Please investigate the test failure and take appropriate action.

---
Network Agent System
        """.strip()

        html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; padding: 20px;">
    <h2 style="color: #dc2626;">Test Failure Alert</h2>
    <table style="border-collapse: collapse; margin: 20px 0;">
        <tr>
            <td style="padding: 8px; font-weight: bold;">Agent:</td>
            <td style="padding: 8px;">{agent_name}</td>
        </tr>
        <tr>
            <td style="padding: 8px; font-weight: bold;">Test:</td>
            <td style="padding: 8px;">{test_name}</td>
        </tr>
        <tr>
            <td style="padding: 8px; font-weight: bold;">Time:</td>
            <td style="padding: 8px;">{datetime.now().isoformat()}</td>
        </tr>
    </table>
    <h3>Details:</h3>
    <pre style="background: #f3f4f6; padding: 15px; border-radius: 5px;">{details}</pre>
    <hr style="margin: 20px 0;">
    <p style="color: #6b7280; font-size: 12px;">This is an automated alert from the Network Agent system.</p>
</body>
</html>
        """.strip()

        return subject, body, html_body

    @staticmethod
    def neighbor_down(agent_name: str, protocol: str, neighbor_id: str, neighbor_ip: str) -> tuple:
        """Template for protocol neighbor down"""
        subject = f"[{agent_name}] {protocol} Neighbor Down: {neighbor_id}"
        body = f"""
Network Agent Protocol Alert

Agent: {agent_name}
Protocol: {protocol}
Event: Neighbor DOWN

Neighbor Details:
- Router ID: {neighbor_id}
- IP Address: {neighbor_ip}
- Time: {datetime.now().isoformat()}

This neighbor relationship has been lost. This may affect network connectivity.
Please investigate the cause of the neighbor loss.

---
Network Agent System
        """.strip()

        html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; padding: 20px;">
    <h2 style="color: #dc2626;">{protocol} Neighbor Down</h2>
    <table style="border-collapse: collapse; margin: 20px 0; border: 1px solid #e5e7eb;">
        <tr style="background: #f9fafb;">
            <td style="padding: 12px; font-weight: bold; border: 1px solid #e5e7eb;">Agent:</td>
            <td style="padding: 12px; border: 1px solid #e5e7eb;">{agent_name}</td>
        </tr>
        <tr>
            <td style="padding: 12px; font-weight: bold; border: 1px solid #e5e7eb;">Protocol:</td>
            <td style="padding: 12px; border: 1px solid #e5e7eb;">{protocol}</td>
        </tr>
        <tr style="background: #fef2f2;">
            <td style="padding: 12px; font-weight: bold; border: 1px solid #e5e7eb;">Status:</td>
            <td style="padding: 12px; border: 1px solid #e5e7eb; color: #dc2626; font-weight: bold;">DOWN</td>
        </tr>
        <tr>
            <td style="padding: 12px; font-weight: bold; border: 1px solid #e5e7eb;">Neighbor ID:</td>
            <td style="padding: 12px; border: 1px solid #e5e7eb;">{neighbor_id}</td>
        </tr>
        <tr>
            <td style="padding: 12px; font-weight: bold; border: 1px solid #e5e7eb;">Neighbor IP:</td>
            <td style="padding: 12px; border: 1px solid #e5e7eb;">{neighbor_ip}</td>
        </tr>
        <tr>
            <td style="padding: 12px; font-weight: bold; border: 1px solid #e5e7eb;">Time:</td>
            <td style="padding: 12px; border: 1px solid #e5e7eb;">{datetime.now().isoformat()}</td>
        </tr>
    </table>
    <p style="color: #6b7280;">This neighbor relationship has been lost. Please investigate.</p>
    <hr style="margin: 20px 0;">
    <p style="color: #6b7280; font-size: 12px;">Network Agent System</p>
</body>
</html>
        """.strip()

        return subject, body, html_body

    @staticmethod
    def neighbor_up(agent_name: str, protocol: str, neighbor_id: str, neighbor_ip: str) -> tuple:
        """Template for protocol neighbor up (recovery)"""
        subject = f"[{agent_name}] {protocol} Neighbor Up: {neighbor_id}"
        body = f"""
Network Agent Protocol Recovery

Agent: {agent_name}
Protocol: {protocol}
Event: Neighbor UP (Recovered)

Neighbor Details:
- Router ID: {neighbor_id}
- IP Address: {neighbor_ip}
- Time: {datetime.now().isoformat()}

The neighbor relationship has been restored.

---
Network Agent System
        """.strip()

        html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; padding: 20px;">
    <h2 style="color: #16a34a;">{protocol} Neighbor Up (Recovered)</h2>
    <table style="border-collapse: collapse; margin: 20px 0; border: 1px solid #e5e7eb;">
        <tr style="background: #f0fdf4;">
            <td style="padding: 12px; font-weight: bold; border: 1px solid #e5e7eb;">Status:</td>
            <td style="padding: 12px; border: 1px solid #e5e7eb; color: #16a34a; font-weight: bold;">UP (Recovered)</td>
        </tr>
        <tr>
            <td style="padding: 12px; font-weight: bold; border: 1px solid #e5e7eb;">Agent:</td>
            <td style="padding: 12px; border: 1px solid #e5e7eb;">{agent_name}</td>
        </tr>
        <tr>
            <td style="padding: 12px; font-weight: bold; border: 1px solid #e5e7eb;">Protocol:</td>
            <td style="padding: 12px; border: 1px solid #e5e7eb;">{protocol}</td>
        </tr>
        <tr>
            <td style="padding: 12px; font-weight: bold; border: 1px solid #e5e7eb;">Neighbor ID:</td>
            <td style="padding: 12px; border: 1px solid #e5e7eb;">{neighbor_id}</td>
        </tr>
        <tr>
            <td style="padding: 12px; font-weight: bold; border: 1px solid #e5e7eb;">Neighbor IP:</td>
            <td style="padding: 12px; border: 1px solid #e5e7eb;">{neighbor_ip}</td>
        </tr>
    </table>
    <hr style="margin: 20px 0;">
    <p style="color: #6b7280; font-size: 12px;">Network Agent System</p>
</body>
</html>
        """.strip()

        return subject, body, html_body

    @staticmethod
    def daily_report(agent_name: str, stats: Dict[str, Any]) -> tuple:
        """Template for daily summary report"""
        subject = f"[{agent_name}] Daily Network Report - {datetime.now().strftime('%Y-%m-%d')}"

        body = f"""
Daily Network Report

Agent: {agent_name}
Report Date: {datetime.now().strftime('%Y-%m-%d')}
Generated: {datetime.now().isoformat()}

=== Summary ===
Interfaces: {stats.get('interfaces', 0)} total, {stats.get('interfaces_up', 0)} up
OSPF Neighbors: {stats.get('ospf_neighbors', 0)}
BGP Peers: {stats.get('bgp_peers', 0)} ({stats.get('bgp_established', 0)} established)
Total Routes: {stats.get('total_routes', 0)}

=== Events (Last 24h) ===
Neighbor Flaps: {stats.get('neighbor_flaps', 0)}
Route Changes: {stats.get('route_changes', 0)}
Test Failures: {stats.get('test_failures', 0)}

=== Health Score ===
Overall: {stats.get('health_score', 100)}%

---
Network Agent System
        """.strip()

        return subject, body, None


class SMTPClient:
    """
    SMTP Client for sending emails.

    Manages SMTP connections, email queuing, and delivery tracking.
    """

    def __init__(self, agent_id: str, config: Optional[SMTPConfig] = None):
        self.agent_id = agent_id
        self.config = config or SMTPConfig()
        self._email_history: List[Email] = []
        self._alert_rules: Dict[str, AlertRule] = {}
        self._running = False
        self._queue: asyncio.Queue = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None
        self._max_history = 100

    async def start(self):
        """Start the SMTP client and queue processor"""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._process_queue())
        logger.info(f"SMTP client started for agent {self.agent_id}")

    async def stop(self):
        """Stop the SMTP client"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(f"SMTP client stopped for agent {self.agent_id}")

    async def _process_queue(self):
        """Process queued emails"""
        while self._running:
            try:
                email = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                await self._send_email(email)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Queue processing error: {e}")

    def configure(self, config: SMTPConfig):
        """Update SMTP configuration"""
        self.config = config
        logger.info(f"SMTP configuration updated: {config.server}:{config.port}")

    async def send(self, email: Email) -> bool:
        """
        Queue an email for sending.

        Args:
            email: Email object to send

        Returns:
            True if queued successfully
        """
        email.status = EmailStatus.QUEUED
        await self._queue.put(email)
        return True

    async def send_immediate(self, email: Email) -> bool:
        """
        Send an email immediately (bypass queue).

        Args:
            email: Email object to send

        Returns:
            True if sent successfully
        """
        return await self._send_email(email)

    async def _send_email(self, email: Email) -> bool:
        """Actually send the email via SMTP"""
        try:
            # Build the message
            if email.html_body:
                msg = MIMEMultipart("alternative")
                msg.attach(MIMEText(email.body, "plain"))
                msg.attach(MIMEText(email.html_body, "html"))
            else:
                msg = MIMEMultipart()
                msg.attach(MIMEText(email.body, "plain"))

            msg["Subject"] = email.subject
            msg["From"] = f"{self.config.from_name} <{self.config.from_address}>"
            msg["To"] = ", ".join(email.to)

            if email.cc:
                msg["Cc"] = ", ".join(email.cc)
            if email.reply_to:
                msg["Reply-To"] = email.reply_to

            # Set priority headers
            if email.priority == EmailPriority.HIGH:
                msg["X-Priority"] = "2"
            elif email.priority == EmailPriority.URGENT:
                msg["X-Priority"] = "1"
                msg["Importance"] = "high"

            # Add custom headers
            for key, value in email.headers.items():
                msg[key] = value

            # Add attachments
            for attachment in email.attachments:
                part = MIMEBase(*attachment.content_type.split("/", 1))
                part.set_payload(attachment.content)
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f"attachment; filename={attachment.filename}"
                )
                msg.attach(part)

            # Determine all recipients
            all_recipients = email.to + email.cc + email.bcc

            # Connect and send
            if self.config.use_ssl:
                context = ssl.create_default_context()
                server = smtplib.SMTP_SSL(
                    self.config.server,
                    self.config.port,
                    timeout=self.config.timeout,
                    context=context
                )
            else:
                server = smtplib.SMTP(
                    self.config.server,
                    self.config.port,
                    timeout=self.config.timeout
                )
                if self.config.use_tls:
                    server.starttls()

            try:
                if self.config.username and self.config.password:
                    server.login(self.config.username, self.config.password)

                server.sendmail(
                    self.config.from_address,
                    all_recipients,
                    msg.as_string()
                )

                email.status = EmailStatus.SENT
                email.sent_at = time.time()
                email.message_id = msg.get("Message-ID")
                logger.info(f"Email sent: {email.subject} to {email.to}")

            finally:
                server.quit()

            # Add to history
            self._add_to_history(email)
            return True

        except Exception as e:
            email.status = EmailStatus.FAILED
            email.error_message = str(e)
            logger.error(f"Failed to send email: {e}")
            self._add_to_history(email)
            return False

    def _add_to_history(self, email: Email):
        """Add email to history, maintaining max size"""
        self._email_history.append(email)
        if len(self._email_history) > self._max_history:
            self._email_history = self._email_history[-self._max_history:]

    async def send_test_email(self, recipient: str) -> bool:
        """
        Send a test email to verify configuration.

        Args:
            recipient: Email address to send test to

        Returns:
            True if sent successfully
        """
        email = Email(
            to=[recipient],
            subject=f"[{self.agent_id}] SMTP Test Email",
            body=f"""
This is a test email from Network Agent: {self.agent_id}

If you received this email, your SMTP configuration is working correctly.

Configuration:
- Server: {self.config.server}:{self.config.port}
- TLS: {self.config.use_tls}
- SSL: {self.config.use_ssl}
- From: {self.config.from_address}

Time: {datetime.now().isoformat()}

---
Network Agent System
            """.strip(),
            priority=EmailPriority.NORMAL
        )

        return await self.send_immediate(email)

    def add_alert_rule(self, rule: AlertRule):
        """Add an alert rule"""
        self._alert_rules[rule.name] = rule
        logger.info(f"Alert rule added: {rule.name}")

    def remove_alert_rule(self, rule_name: str) -> bool:
        """Remove an alert rule"""
        if rule_name in self._alert_rules:
            del self._alert_rules[rule_name]
            return True
        return False

    def get_alert_rules(self) -> List[AlertRule]:
        """Get all alert rules"""
        return list(self._alert_rules.values())

    async def trigger_alert(
        self,
        alert_type: AlertType,
        context: Dict[str, Any]
    ) -> bool:
        """
        Trigger an alert based on type and context.

        Args:
            alert_type: Type of alert
            context: Alert context data

        Returns:
            True if alert email was sent
        """
        # Find matching rules
        triggered = False
        now = time.time()

        for rule in self._alert_rules.values():
            if not rule.enabled:
                continue
            if rule.alert_type != alert_type:
                continue

            # Check cooldown
            if rule.last_triggered:
                if now - rule.last_triggered < rule.cooldown_seconds:
                    logger.debug(f"Alert rule {rule.name} in cooldown")
                    continue

            # Generate email from template
            email = self._create_alert_email(rule, context)
            if email:
                await self.send(email)
                rule.last_triggered = now
                triggered = True

        return triggered

    def _create_alert_email(self, rule: AlertRule, context: Dict[str, Any]) -> Optional[Email]:
        """Create an email from an alert rule and context"""
        try:
            alert_type = rule.alert_type

            if alert_type == AlertType.TEST_FAILURE:
                subject, body, html = EmailTemplates.test_failure(
                    self.agent_id,
                    context.get("test_name", "Unknown"),
                    context.get("details", "No details")
                )
            elif alert_type == AlertType.NEIGHBOR_DOWN:
                subject, body, html = EmailTemplates.neighbor_down(
                    self.agent_id,
                    context.get("protocol", "Unknown"),
                    context.get("neighbor_id", "Unknown"),
                    context.get("neighbor_ip", "Unknown")
                )
            elif alert_type == AlertType.NEIGHBOR_UP:
                subject, body, html = EmailTemplates.neighbor_up(
                    self.agent_id,
                    context.get("protocol", "Unknown"),
                    context.get("neighbor_id", "Unknown"),
                    context.get("neighbor_ip", "Unknown")
                )
            else:
                # Custom alert - use rule templates
                subject = rule.subject_template.format(
                    agent=self.agent_id,
                    alert_type=alert_type.value,
                    **context
                )
                body = rule.body_template.format(
                    agent=self.agent_id,
                    alert_type=alert_type.value,
                    **context
                ) if rule.body_template else f"Alert: {alert_type.value}\n\n{json.dumps(context, indent=2)}"
                html = None

            return Email(
                to=rule.recipients,
                subject=subject,
                body=body,
                html_body=html,
                priority=rule.priority
            )

        except Exception as e:
            logger.error(f"Failed to create alert email: {e}")
            return None

    def get_email_history(self, limit: int = 50, status: Optional[EmailStatus] = None) -> List[Dict[str, Any]]:
        """
        Get email history.

        Args:
            limit: Maximum emails to return
            status: Filter by status

        Returns:
            List of email dictionaries
        """
        emails = self._email_history
        if status:
            emails = [e for e in emails if e.status == status]
        return [e.to_dict() for e in emails[-limit:]]

    def get_statistics(self) -> Dict[str, Any]:
        """Get email statistics"""
        total = len(self._email_history)
        sent = sum(1 for e in self._email_history if e.status == EmailStatus.SENT)
        failed = sum(1 for e in self._email_history if e.status == EmailStatus.FAILED)

        return {
            "agent_id": self.agent_id,
            "running": self._running,
            "queue_size": self._queue.qsize(),
            "total_emails": total,
            "sent": sent,
            "failed": failed,
            "success_rate": (sent / total * 100) if total > 0 else 100,
            "alert_rules": len(self._alert_rules),
            "config": self.config.to_dict()
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert client state to dictionary"""
        return {
            "agent_id": self.agent_id,
            "running": self._running,
            "config": self.config.to_dict(),
            "statistics": self.get_statistics(),
            "alert_rules": [r.to_dict() for r in self._alert_rules.values()],
            "recent_emails": self.get_email_history(limit=10)
        }


def configure_smtp_from_mcp(config_dict: Dict[str, Any]) -> SMTPConfig:
    """
    Create SMTPConfig from wizard MCP configuration.

    Maps wizard config fields to SMTPConfig:
    - smtp_server -> server
    - smtp_port -> port
    - smtp_username -> username
    - smtp_password -> password
    - smtp_from -> from_address
    - smtp_use_tls -> use_tls

    Args:
        config_dict: Configuration from wizard MCP settings

    Returns:
        SMTPConfig configured from wizard values
    """
    # Sanitize password - remove non-breaking spaces and regular spaces
    # Google App Passwords are displayed with spaces for readability but should be entered without
    raw_password = config_dict.get("smtp_password", "")
    # Remove non-breaking spaces (\xa0), regular spaces, and other whitespace
    sanitized_password = raw_password.replace('\xa0', '').replace(' ', '').strip()

    return SMTPConfig(
        server=config_dict.get("smtp_server", "localhost"),
        port=int(config_dict.get("smtp_port", 587)),
        username=config_dict.get("smtp_username", ""),
        password=sanitized_password,
        from_address=config_dict.get("smtp_from", config_dict.get("smtp_username", "")),
        from_name=config_dict.get("smtp_from_name", "Network Agent"),
        use_tls=config_dict.get("smtp_use_tls", True),
        use_ssl=config_dict.get("smtp_use_ssl", False),
        timeout=int(config_dict.get("smtp_timeout", 30))
    )


def get_smtp_client(agent_id: str = "local") -> SMTPClient:
    """Get or create the SMTP client singleton"""
    global _smtp_client
    if _smtp_client is None:
        _smtp_client = SMTPClient(agent_id)
    return _smtp_client


async def start_smtp_client(agent_id: str, config: Optional[SMTPConfig] = None) -> SMTPClient:
    """Start the SMTP client for an agent"""
    global _smtp_client
    _smtp_client = SMTPClient(agent_id, config)
    await _smtp_client.start()
    return _smtp_client


async def stop_smtp_client():
    """Stop the SMTP client"""
    global _smtp_client
    if _smtp_client:
        await _smtp_client.stop()
        _smtp_client = None


def get_email_history(limit: int = 50) -> List[Dict[str, Any]]:
    """Get email history"""
    client = get_smtp_client()
    return client.get_email_history(limit)


def get_smtp_statistics() -> Dict[str, Any]:
    """Get SMTP statistics"""
    client = get_smtp_client()
    return client.get_statistics()
