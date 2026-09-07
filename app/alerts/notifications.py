"""Small configuration-driven SMTP notifier for cost alerts."""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage
from typing import Protocol

from app.alerts.models import Alert
from app.core.config import Settings, get_settings


class NotificationSender(Protocol):
    async def send(
        self,
        recipient: str,
        alert: Alert,
        subject_value: str,
        reason: str,
        details: str,
    ) -> None: ...


class NotificationError(RuntimeError):
    """Raised when an alert email cannot be delivered."""


class EmailNotificationService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def send(
        self,
        recipient: str,
        alert: Alert,
        subject_value: str,
        reason: str,
        details: str,
    ) -> None:
        config = self._settings
        if not config.alert_email_enabled:
            raise NotificationError("Alert email notifications are disabled")
        if not config.alert_smtp_host or not config.alert_email_from:
            raise NotificationError("Alert email SMTP configuration is incomplete")
        message = EmailMessage()
        message["Subject"] = f"Cost alert: {alert.name}"
        message["From"] = config.alert_email_from
        message["To"] = recipient
        message.set_content(
            f"Alert name: {alert.name}\n"
            f"Alert type: {alert.alert_type}\n"
            f"Provider: {alert.provider or 'all providers'}\n"
            f"Scope: account={alert.account_id or 'all'}, "
            f"service={alert.service or 'all'}, region={alert.region or 'all'}\n"
            f"Severity: {alert.severity}\n"
            f"Current value: {subject_value}\n"
            f"Reason: {reason}\n"
            f"Timestamp: {details}\n"
            "Review the Cost Detector dashboard before taking action.\n"
        )

        try:
            await asyncio.to_thread(self._send_sync, message)
        except Exception as error:
            raise NotificationError("Alert email delivery failed") from error

    def _send_sync(self, message: EmailMessage) -> None:
        config = self._settings
        with smtplib.SMTP(
            config.alert_smtp_host, config.alert_smtp_port, timeout=10
        ) as client:
            client.starttls()
            if config.alert_smtp_username and config.alert_smtp_password:
                client.login(config.alert_smtp_username, config.alert_smtp_password)
            client.send_message(message)
