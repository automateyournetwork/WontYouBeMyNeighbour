"""
Progress Tracking Module - Track user progress through tutorials

Provides:
- Per-user progress tracking
- Step completion status
- Time spent tracking
- Completion statistics
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any

logger = logging.getLogger("ProgressTracker")


class CompletionStatus(str, Enum):
    """Step completion status"""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"


@dataclass
class StepCompletion:
    """
    Completion record for a tutorial step

    Attributes:
        step_id: Step identifier
        status: Completion status
        started_at: When step was started
        completed_at: When step was completed
        time_spent_seconds: Time spent on step
        attempts: Number of attempts
        score: Score if applicable (quiz)
        notes: User notes
    """
    step_id: str
    status: CompletionStatus = CompletionStatus.NOT_STARTED
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    time_spent_seconds: int = 0
    attempts: int = 0
    score: Optional[float] = None
    notes: str = ""

    def start(self):
        """Mark step as started"""
        if self.status == CompletionStatus.NOT_STARTED:
            self.status = CompletionStatus.IN_PROGRESS
            self.started_at = datetime.now()
            self.attempts += 1

    def complete(self, score: Optional[float] = None):
        """Mark step as completed"""
        self.status = CompletionStatus.COMPLETED
        self.completed_at = datetime.now()
        if self.started_at:
            self.time_spent_seconds = int(
                (self.completed_at - self.started_at).total_seconds()
            )
        if score is not None:
            self.score = score

    def skip(self):
        """Mark step as skipped"""
        self.status = CompletionStatus.SKIPPED
        self.completed_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "time_spent_seconds": self.time_spent_seconds,
            "attempts": self.attempts,
            "score": self.score,
            "notes": self.notes
        }


@dataclass
class TutorialProgress:
    """
    Progress for a single tutorial

    Attributes:
        tutorial_id: Tutorial identifier
        started_at: When tutorial was started
        completed_at: When tutorial was completed
        current_step: Current step ID
        steps: Step completion records
        overall_score: Overall score if applicable
    """
    tutorial_id: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    current_step: Optional[str] = None
    steps: Dict[str, StepCompletion] = field(default_factory=dict)
    overall_score: Optional[float] = None

    @property
    def is_completed(self) -> bool:
        """Check if tutorial is completed"""
        if not self.steps:
            return False
        return all(
            s.status in [CompletionStatus.COMPLETED, CompletionStatus.SKIPPED]
            for s in self.steps.values()
        )

    @property
    def completion_percentage(self) -> float:
        """Calculate completion percentage"""
        if not self.steps:
            return 0.0
        completed = sum(
            1 for s in self.steps.values()
            if s.status in [CompletionStatus.COMPLETED, CompletionStatus.SKIPPED]
        )
        return (completed / len(self.steps)) * 100

    @property
    def total_time_spent_seconds(self) -> int:
        """Total time spent on tutorial"""
        return sum(s.time_spent_seconds for s in self.steps.values())

    def start_tutorial(self, first_step_id: str):
        """Start the tutorial"""
        self.started_at = datetime.now()
        self.current_step = first_step_id
        self._ensure_step(first_step_id)
        self.steps[first_step_id].start()

    def start_step(self, step_id: str):
        """Start a step"""
        self._ensure_step(step_id)
        self.steps[step_id].start()
        self.current_step = step_id

    def complete_step(self, step_id: str, score: Optional[float] = None) -> bool:
        """Complete a step"""
        if step_id not in self.steps:
            return False
        self.steps[step_id].complete(score)
        return True

    def skip_step(self, step_id: str) -> bool:
        """Skip a step"""
        if step_id not in self.steps:
            self._ensure_step(step_id)
        self.steps[step_id].skip()
        return True

    def complete_tutorial(self):
        """Mark tutorial as completed"""
        self.completed_at = datetime.now()
        # Calculate overall score from quiz steps
        quiz_scores = [
            s.score for s in self.steps.values()
            if s.score is not None
        ]
        if quiz_scores:
            self.overall_score = sum(quiz_scores) / len(quiz_scores)

    def _ensure_step(self, step_id: str):
        """Ensure step exists in progress"""
        if step_id not in self.steps:
            self.steps[step_id] = StepCompletion(step_id=step_id)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tutorial_id": self.tutorial_id,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "current_step": self.current_step,
            "is_completed": self.is_completed,
            "completion_percentage": self.completion_percentage,
            "total_time_spent_seconds": self.total_time_spent_seconds,
            "overall_score": self.overall_score,
            "steps": {k: v.to_dict() for k, v in self.steps.items()}
        }


@dataclass
class UserProgress:
    """
    Complete progress record for a user

    Attributes:
        user_id: User identifier
        tutorials: Progress per tutorial
        achievements: Earned achievements
        total_tutorials_completed: Count of completed tutorials
        created_at: When record was created
        last_activity: Last activity timestamp
    """
    user_id: str
    tutorials: Dict[str, TutorialProgress] = field(default_factory=dict)
    achievements: List[str] = field(default_factory=list)
    total_tutorials_completed: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)

    def get_tutorial_progress(self, tutorial_id: str) -> Optional[TutorialProgress]:
        """Get progress for a specific tutorial"""
        return self.tutorials.get(tutorial_id)

    def start_tutorial(self, tutorial_id: str, first_step_id: str) -> TutorialProgress:
        """Start a tutorial"""
        if tutorial_id not in self.tutorials:
            self.tutorials[tutorial_id] = TutorialProgress(tutorial_id=tutorial_id)

        progress = self.tutorials[tutorial_id]
        progress.start_tutorial(first_step_id)
        self.last_activity = datetime.now()
        return progress

    def complete_tutorial(self, tutorial_id: str):
        """Complete a tutorial"""
        if tutorial_id in self.tutorials:
            self.tutorials[tutorial_id].complete_tutorial()
            self.total_tutorials_completed += 1
            self.last_activity = datetime.now()
            self._check_achievements()

    def _check_achievements(self):
        """Check and award achievements"""
        # First tutorial
        if self.total_tutorials_completed >= 1 and "first_tutorial" not in self.achievements:
            self.achievements.append("first_tutorial")

        # Five tutorials
        if self.total_tutorials_completed >= 5 and "five_tutorials" not in self.achievements:
            self.achievements.append("five_tutorials")

        # OSPF mastery
        ospf_tutorials = ["ospf-fundamentals"]
        if all(
            self.tutorials.get(t, TutorialProgress(t)).is_completed
            for t in ospf_tutorials
        ) and "ospf_master" not in self.achievements:
            self.achievements.append("ospf_master")

        # BGP mastery
        bgp_tutorials = ["bgp-fundamentals"]
        if all(
            self.tutorials.get(t, TutorialProgress(t)).is_completed
            for t in bgp_tutorials
        ) and "bgp_master" not in self.achievements:
            self.achievements.append("bgp_master")

    @property
    def completed_tutorials(self) -> List[str]:
        """Get list of completed tutorial IDs"""
        return [
            t_id for t_id, progress in self.tutorials.items()
            if progress.is_completed
        ]

    @property
    def in_progress_tutorials(self) -> List[str]:
        """Get list of in-progress tutorial IDs"""
        return [
            t_id for t_id, progress in self.tutorials.items()
            if not progress.is_completed and progress.started_at is not None
        ]

    @property
    def total_time_spent_seconds(self) -> int:
        """Total time spent across all tutorials"""
        return sum(p.total_time_spent_seconds for p in self.tutorials.values())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "tutorials": {k: v.to_dict() for k, v in self.tutorials.items()},
            "achievements": self.achievements,
            "total_tutorials_completed": self.total_tutorials_completed,
            "completed_tutorials": self.completed_tutorials,
            "in_progress_tutorials": self.in_progress_tutorials,
            "total_time_spent_seconds": self.total_time_spent_seconds,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat()
        }


class ProgressTracker:
    """
    Tracks progress for all users
    """

    def __init__(self):
        """Initialize progress tracker"""
        self._users: Dict[str, UserProgress] = {}

    def get_user_progress(self, user_id: str) -> UserProgress:
        """Get or create user progress"""
        if user_id not in self._users:
            self._users[user_id] = UserProgress(user_id=user_id)
        return self._users[user_id]

    def start_tutorial(
        self,
        user_id: str,
        tutorial_id: str,
        first_step_id: str
    ) -> TutorialProgress:
        """Start a tutorial for a user"""
        user = self.get_user_progress(user_id)
        return user.start_tutorial(tutorial_id, first_step_id)

    def start_step(
        self,
        user_id: str,
        tutorial_id: str,
        step_id: str
    ) -> bool:
        """Start a step in a tutorial"""
        user = self.get_user_progress(user_id)
        progress = user.get_tutorial_progress(tutorial_id)
        if not progress:
            return False
        progress.start_step(step_id)
        user.last_activity = datetime.now()
        return True

    def complete_step(
        self,
        user_id: str,
        tutorial_id: str,
        step_id: str,
        score: Optional[float] = None
    ) -> bool:
        """Complete a step in a tutorial"""
        user = self.get_user_progress(user_id)
        progress = user.get_tutorial_progress(tutorial_id)
        if not progress:
            return False
        result = progress.complete_step(step_id, score)
        user.last_activity = datetime.now()
        return result

    def skip_step(
        self,
        user_id: str,
        tutorial_id: str,
        step_id: str
    ) -> bool:
        """Skip a step in a tutorial"""
        user = self.get_user_progress(user_id)
        progress = user.get_tutorial_progress(tutorial_id)
        if not progress:
            return False
        result = progress.skip_step(step_id)
        user.last_activity = datetime.now()
        return result

    def complete_tutorial(self, user_id: str, tutorial_id: str) -> bool:
        """Complete a tutorial for a user"""
        user = self.get_user_progress(user_id)
        progress = user.get_tutorial_progress(tutorial_id)
        if not progress:
            return False
        user.complete_tutorial(tutorial_id)
        return True

    def get_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get leaderboard of top users"""
        users = list(self._users.values())
        users.sort(key=lambda u: u.total_tutorials_completed, reverse=True)

        return [
            {
                "user_id": u.user_id,
                "tutorials_completed": u.total_tutorials_completed,
                "achievements": len(u.achievements),
                "total_time_hours": u.total_time_spent_seconds / 3600
            }
            for u in users[:limit]
        ]

    def get_statistics(self) -> Dict[str, Any]:
        """Get overall statistics"""
        total_users = len(self._users)
        total_completions = sum(u.total_tutorials_completed for u in self._users.values())
        total_time = sum(u.total_time_spent_seconds for u in self._users.values())

        # Most popular tutorials
        tutorial_counts = {}
        for user in self._users.values():
            for t_id in user.completed_tutorials:
                tutorial_counts[t_id] = tutorial_counts.get(t_id, 0) + 1

        popular = sorted(tutorial_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            "total_users": total_users,
            "total_completions": total_completions,
            "total_time_hours": total_time / 3600,
            "average_tutorials_per_user": total_completions / total_users if total_users > 0 else 0,
            "most_popular_tutorials": [
                {"tutorial_id": t, "completions": c} for t, c in popular
            ]
        }


# Global progress tracker instance
_global_tracker: Optional[ProgressTracker] = None


def get_progress_tracker() -> ProgressTracker:
    """Get or create the global progress tracker"""
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = ProgressTracker()
    return _global_tracker
