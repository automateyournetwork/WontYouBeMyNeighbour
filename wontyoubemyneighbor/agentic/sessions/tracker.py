"""
Session Activity Tracker

Provides:
- Activity tracking
- Session analytics
- Usage patterns
- Security monitoring
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from enum import Enum


class ActivityType(Enum):
    """Activity types"""
    LOGIN = "login"
    LOGOUT = "logout"
    API_CALL = "api_call"
    PAGE_VIEW = "page_view"
    ACTION = "action"
    ERROR = "error"
    SECURITY = "security"


@dataclass
class SessionActivity:
    """Represents a session activity"""

    session_id: str
    user_id: str
    activity_type: ActivityType
    timestamp: datetime = field(default_factory=datetime.now)
    endpoint: Optional[str] = None
    method: Optional[str] = None
    status_code: Optional[int] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    duration_ms: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to dictionary"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "activity_type": self.activity_type.value,
            "timestamp": self.timestamp.isoformat(),
            "endpoint": self.endpoint,
            "method": self.method,
            "status_code": self.status_code,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata
        }


class SessionTracker:
    """Tracks session activities"""

    def __init__(self):
        self.activities: List[SessionActivity] = []
        self._max_activities = 100000

        # Aggregated stats
        self.session_stats: Dict[str, Dict[str, Any]] = {}
        self.user_stats: Dict[str, Dict[str, Any]] = {}
        self.endpoint_stats: Dict[str, Dict[str, int]] = {}

    def track(
        self,
        session_id: str,
        user_id: str,
        activity_type: ActivityType,
        endpoint: Optional[str] = None,
        method: Optional[str] = None,
        status_code: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        duration_ms: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> SessionActivity:
        """Track an activity"""
        activity = SessionActivity(
            session_id=session_id,
            user_id=user_id,
            activity_type=activity_type,
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            ip_address=ip_address,
            user_agent=user_agent,
            duration_ms=duration_ms,
            metadata=metadata or {}
        )

        self.activities.append(activity)

        # Trim if needed
        if len(self.activities) > self._max_activities:
            self.activities = self.activities[-self._max_activities // 2:]

        # Update aggregated stats
        self._update_stats(activity)

        return activity

    def track_login(
        self,
        session_id: str,
        user_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> SessionActivity:
        """Track a login"""
        return self.track(
            session_id=session_id,
            user_id=user_id,
            activity_type=ActivityType.LOGIN,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata=metadata
        )

    def track_logout(
        self,
        session_id: str,
        user_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> SessionActivity:
        """Track a logout"""
        return self.track(
            session_id=session_id,
            user_id=user_id,
            activity_type=ActivityType.LOGOUT,
            metadata=metadata
        )

    def track_api_call(
        self,
        session_id: str,
        user_id: str,
        endpoint: str,
        method: str,
        status_code: int,
        duration_ms: int,
        ip_address: Optional[str] = None
    ) -> SessionActivity:
        """Track an API call"""
        return self.track(
            session_id=session_id,
            user_id=user_id,
            activity_type=ActivityType.API_CALL,
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            duration_ms=duration_ms,
            ip_address=ip_address
        )

    def track_error(
        self,
        session_id: str,
        user_id: str,
        error_type: str,
        error_message: str,
        endpoint: Optional[str] = None
    ) -> SessionActivity:
        """Track an error"""
        return self.track(
            session_id=session_id,
            user_id=user_id,
            activity_type=ActivityType.ERROR,
            endpoint=endpoint,
            metadata={"error_type": error_type, "error_message": error_message}
        )

    def track_security_event(
        self,
        session_id: str,
        user_id: str,
        event_type: str,
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> SessionActivity:
        """Track a security event"""
        return self.track(
            session_id=session_id,
            user_id=user_id,
            activity_type=ActivityType.SECURITY,
            ip_address=ip_address,
            metadata={"event_type": event_type, "details": details or {}}
        )

    def get_session_activities(
        self,
        session_id: str,
        limit: int = 100
    ) -> List[SessionActivity]:
        """Get activities for a session"""
        activities = [a for a in self.activities if a.session_id == session_id]
        return sorted(activities, key=lambda a: a.timestamp, reverse=True)[:limit]

    def get_user_activities(
        self,
        user_id: str,
        days: int = 7,
        limit: int = 100
    ) -> List[SessionActivity]:
        """Get activities for a user"""
        cutoff = datetime.now() - timedelta(days=days)
        activities = [
            a for a in self.activities
            if a.user_id == user_id and a.timestamp >= cutoff
        ]
        return sorted(activities, key=lambda a: a.timestamp, reverse=True)[:limit]

    def get_recent_activities(
        self,
        limit: int = 100,
        activity_type: Optional[ActivityType] = None
    ) -> List[SessionActivity]:
        """Get recent activities"""
        activities = self.activities
        if activity_type:
            activities = [a for a in activities if a.activity_type == activity_type]
        return sorted(activities, key=lambda a: a.timestamp, reverse=True)[:limit]

    def get_session_summary(self, session_id: str) -> Dict[str, Any]:
        """Get summary for a session"""
        activities = [a for a in self.activities if a.session_id == session_id]

        if not activities:
            return {"session_id": session_id, "activity_count": 0}

        # Calculate stats
        api_calls = [a for a in activities if a.activity_type == ActivityType.API_CALL]
        errors = [a for a in activities if a.activity_type == ActivityType.ERROR]
        security = [a for a in activities if a.activity_type == ActivityType.SECURITY]

        # Average response time
        avg_duration = 0
        if api_calls:
            durations = [a.duration_ms for a in api_calls if a.duration_ms]
            if durations:
                avg_duration = sum(durations) / len(durations)

        # Endpoint breakdown
        endpoints: Dict[str, int] = {}
        for activity in api_calls:
            if activity.endpoint:
                endpoints[activity.endpoint] = endpoints.get(activity.endpoint, 0) + 1

        # First and last activity
        sorted_activities = sorted(activities, key=lambda a: a.timestamp)
        first_activity = sorted_activities[0].timestamp
        last_activity = sorted_activities[-1].timestamp

        return {
            "session_id": session_id,
            "activity_count": len(activities),
            "api_calls": len(api_calls),
            "errors": len(errors),
            "security_events": len(security),
            "avg_response_ms": int(avg_duration),
            "top_endpoints": sorted(endpoints.items(), key=lambda x: x[1], reverse=True)[:5],
            "first_activity": first_activity.isoformat(),
            "last_activity": last_activity.isoformat(),
            "duration_seconds": int((last_activity - first_activity).total_seconds())
        }

    def get_user_summary(self, user_id: str, days: int = 30) -> Dict[str, Any]:
        """Get summary for a user"""
        cutoff = datetime.now() - timedelta(days=days)
        activities = [
            a for a in self.activities
            if a.user_id == user_id and a.timestamp >= cutoff
        ]

        if not activities:
            return {"user_id": user_id, "activity_count": 0, "period_days": days}

        # Unique sessions
        sessions = set(a.session_id for a in activities)

        # Activity type breakdown
        type_counts: Dict[str, int] = {}
        for activity in activities:
            type_counts[activity.activity_type.value] = type_counts.get(
                activity.activity_type.value, 0
            ) + 1

        # Daily breakdown
        daily_counts: Dict[str, int] = {}
        for activity in activities:
            day = activity.timestamp.strftime("%Y-%m-%d")
            daily_counts[day] = daily_counts.get(day, 0) + 1

        # IP addresses
        ips = set(a.ip_address for a in activities if a.ip_address)

        return {
            "user_id": user_id,
            "period_days": days,
            "activity_count": len(activities),
            "session_count": len(sessions),
            "unique_ips": list(ips),
            "by_type": type_counts,
            "daily_breakdown": daily_counts
        }

    def get_endpoint_stats(self, days: int = 7) -> Dict[str, Any]:
        """Get endpoint statistics"""
        cutoff = datetime.now() - timedelta(days=days)
        api_calls = [
            a for a in self.activities
            if a.activity_type == ActivityType.API_CALL and a.timestamp >= cutoff
        ]

        # Endpoint counts and durations
        endpoint_data: Dict[str, Dict[str, Any]] = {}
        for activity in api_calls:
            if not activity.endpoint:
                continue

            if activity.endpoint not in endpoint_data:
                endpoint_data[activity.endpoint] = {
                    "count": 0,
                    "total_duration_ms": 0,
                    "errors": 0,
                    "methods": {}
                }

            data = endpoint_data[activity.endpoint]
            data["count"] += 1
            if activity.duration_ms:
                data["total_duration_ms"] += activity.duration_ms
            if activity.status_code and activity.status_code >= 400:
                data["errors"] += 1
            if activity.method:
                data["methods"][activity.method] = data["methods"].get(activity.method, 0) + 1

        # Calculate averages
        result = []
        for endpoint, data in endpoint_data.items():
            avg_duration = data["total_duration_ms"] / data["count"] if data["count"] > 0 else 0
            error_rate = data["errors"] / data["count"] if data["count"] > 0 else 0
            result.append({
                "endpoint": endpoint,
                "count": data["count"],
                "avg_duration_ms": int(avg_duration),
                "error_rate": error_rate,
                "methods": data["methods"]
            })

        # Sort by count
        result.sort(key=lambda x: x["count"], reverse=True)

        return {
            "period_days": days,
            "total_calls": len(api_calls),
            "unique_endpoints": len(endpoint_data),
            "endpoints": result[:50]
        }

    def get_security_summary(self, days: int = 7) -> Dict[str, Any]:
        """Get security event summary"""
        cutoff = datetime.now() - timedelta(days=days)
        security_events = [
            a for a in self.activities
            if a.activity_type == ActivityType.SECURITY and a.timestamp >= cutoff
        ]

        # Event type breakdown
        event_types: Dict[str, int] = {}
        for activity in security_events:
            event_type = activity.metadata.get("event_type", "unknown")
            event_types[event_type] = event_types.get(event_type, 0) + 1

        # Users with security events
        users = set(a.user_id for a in security_events)

        # IP addresses
        ips = set(a.ip_address for a in security_events if a.ip_address)

        return {
            "period_days": days,
            "total_events": len(security_events),
            "by_type": event_types,
            "affected_users": len(users),
            "unique_ips": list(ips),
            "recent_events": [a.to_dict() for a in security_events[-10:]]
        }

    def get_error_summary(self, days: int = 7) -> Dict[str, Any]:
        """Get error summary"""
        cutoff = datetime.now() - timedelta(days=days)
        errors = [
            a for a in self.activities
            if a.activity_type == ActivityType.ERROR and a.timestamp >= cutoff
        ]

        # Error type breakdown
        error_types: Dict[str, int] = {}
        for activity in errors:
            error_type = activity.metadata.get("error_type", "unknown")
            error_types[error_type] = error_types.get(error_type, 0) + 1

        # Endpoint breakdown
        endpoints: Dict[str, int] = {}
        for activity in errors:
            if activity.endpoint:
                endpoints[activity.endpoint] = endpoints.get(activity.endpoint, 0) + 1

        return {
            "period_days": days,
            "total_errors": len(errors),
            "by_type": error_types,
            "by_endpoint": dict(sorted(endpoints.items(), key=lambda x: x[1], reverse=True)[:10]),
            "recent_errors": [a.to_dict() for a in errors[-10:]]
        }

    def get_statistics(self) -> dict:
        """Get tracker statistics"""
        now = datetime.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Count today's activities
        today_activities = [a for a in self.activities if a.timestamp >= today]

        # Activity type breakdown
        type_counts: Dict[str, int] = {}
        for activity in self.activities:
            type_counts[activity.activity_type.value] = type_counts.get(
                activity.activity_type.value, 0
            ) + 1

        return {
            "total_activities": len(self.activities),
            "max_activities": self._max_activities,
            "today_activities": len(today_activities),
            "unique_sessions": len(set(a.session_id for a in self.activities)),
            "unique_users": len(set(a.user_id for a in self.activities)),
            "by_type": type_counts
        }

    def _update_stats(self, activity: SessionActivity) -> None:
        """Update aggregated statistics"""
        # Session stats
        if activity.session_id not in self.session_stats:
            self.session_stats[activity.session_id] = {
                "activity_count": 0,
                "api_calls": 0,
                "errors": 0,
                "first_activity": activity.timestamp
            }

        stats = self.session_stats[activity.session_id]
        stats["activity_count"] += 1
        stats["last_activity"] = activity.timestamp

        if activity.activity_type == ActivityType.API_CALL:
            stats["api_calls"] += 1
        elif activity.activity_type == ActivityType.ERROR:
            stats["errors"] += 1

        # User stats
        if activity.user_id not in self.user_stats:
            self.user_stats[activity.user_id] = {
                "activity_count": 0,
                "session_count": 0,
                "sessions": set()
            }

        user_stats = self.user_stats[activity.user_id]
        user_stats["activity_count"] += 1
        if activity.session_id not in user_stats["sessions"]:
            user_stats["sessions"].add(activity.session_id)
            user_stats["session_count"] = len(user_stats["sessions"])

        # Endpoint stats
        if activity.endpoint:
            if activity.endpoint not in self.endpoint_stats:
                self.endpoint_stats[activity.endpoint] = {"count": 0, "errors": 0}

            self.endpoint_stats[activity.endpoint]["count"] += 1
            if activity.status_code and activity.status_code >= 400:
                self.endpoint_stats[activity.endpoint]["errors"] += 1

    def clear_old_activities(self, days: int = 30) -> int:
        """Clear activities older than specified days"""
        cutoff = datetime.now() - timedelta(days=days)
        old_count = len(self.activities)
        self.activities = [a for a in self.activities if a.timestamp >= cutoff]
        return old_count - len(self.activities)


# Global session tracker instance
_session_tracker: Optional[SessionTracker] = None


def get_session_tracker() -> SessionTracker:
    """Get or create the global session tracker"""
    global _session_tracker
    if _session_tracker is None:
        _session_tracker = SessionTracker()
    return _session_tracker
