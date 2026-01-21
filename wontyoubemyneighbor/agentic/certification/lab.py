"""
Lab Module - Certification lab scenarios

Provides:
- Pre-built lab scenarios for certification prep
- Task-based lab exercises
- Validation and grading
- Topology deployment
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any

logger = logging.getLogger("LabManager")


class LabDifficulty(str, Enum):
    """Lab difficulty levels"""
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    EXPERT = "expert"


class LabStatus(str, Enum):
    """Lab status"""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class TaskStatus(str, Enum):
    """Task completion status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class LabTask:
    """
    A single task within a lab

    Attributes:
        id: Task identifier
        title: Task title
        description: Task description
        instructions: Step-by-step instructions
        points: Points for this task
        required: Whether task is required
        verification: Verification criteria
        hints: Help hints
        order: Task order in lab
    """
    id: str
    title: str
    description: str
    instructions: List[str] = field(default_factory=list)
    points: int = 10
    required: bool = True
    verification: Dict[str, Any] = field(default_factory=dict)
    hints: List[str] = field(default_factory=list)
    order: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "instructions": self.instructions,
            "points": self.points,
            "required": self.required,
            "verification": self.verification,
            "hints": self.hints,
            "order": self.order
        }


@dataclass
class Lab:
    """
    A certification lab scenario

    Attributes:
        id: Lab identifier
        title: Lab title
        description: Lab description
        certification: Target certification (CCNA, CCNP, etc.)
        topics: Topics covered
        difficulty: Lab difficulty
        time_limit_minutes: Time limit for lab
        tasks: List of lab tasks
        topology: Required topology
        objectives: Learning objectives
        prerequisites: Required knowledge
        points_total: Total available points
        passing_score: Minimum passing score
    """
    id: str
    title: str
    description: str
    certification: str
    topics: List[str] = field(default_factory=list)
    difficulty: LabDifficulty = LabDifficulty.MEDIUM
    time_limit_minutes: int = 60
    tasks: List[LabTask] = field(default_factory=list)
    topology: Dict[str, Any] = field(default_factory=dict)
    objectives: List[str] = field(default_factory=list)
    prerequisites: List[str] = field(default_factory=list)
    points_total: int = 100
    passing_score: int = 70

    @property
    def task_count(self) -> int:
        return len(self.tasks)

    def get_task(self, task_id: str) -> Optional[LabTask]:
        """Get task by ID"""
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "certification": self.certification,
            "topics": self.topics,
            "difficulty": self.difficulty.value,
            "time_limit_minutes": self.time_limit_minutes,
            "tasks": [t.to_dict() for t in self.tasks],
            "topology": self.topology,
            "objectives": self.objectives,
            "prerequisites": self.prerequisites,
            "points_total": self.points_total,
            "passing_score": self.passing_score,
            "task_count": self.task_count
        }

    def to_summary(self) -> Dict[str, Any]:
        """Get summary without full task details"""
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "certification": self.certification,
            "topics": self.topics,
            "difficulty": self.difficulty.value,
            "time_limit_minutes": self.time_limit_minutes,
            "task_count": self.task_count,
            "points_total": self.points_total,
            "passing_score": self.passing_score
        }


@dataclass
class LabAttempt:
    """
    A user's attempt at a lab

    Attributes:
        id: Attempt identifier
        user_id: User identifier
        lab_id: Lab identifier
        status: Attempt status
        started_at: Start timestamp
        completed_at: Completion timestamp
        time_remaining_seconds: Time remaining
        task_status: Status of each task
        points_earned: Points earned
        score: Final score percentage
        passed: Whether lab was passed
    """
    id: str
    user_id: str
    lab_id: str
    status: LabStatus = LabStatus.NOT_STARTED
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    time_remaining_seconds: int = 0
    task_status: Dict[str, TaskStatus] = field(default_factory=dict)
    task_points: Dict[str, int] = field(default_factory=dict)
    points_earned: int = 0
    score: float = 0.0
    passed: bool = False
    feedback: str = ""

    @property
    def duration_seconds(self) -> int:
        if self.started_at and self.completed_at:
            return int((self.completed_at - self.started_at).total_seconds())
        return 0

    @property
    def completed_tasks(self) -> int:
        return sum(1 for s in self.task_status.values() if s == TaskStatus.COMPLETED)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "lab_id": self.lab_id,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "time_remaining_seconds": self.time_remaining_seconds,
            "task_status": {k: v.value for k, v in self.task_status.items()},
            "task_points": self.task_points,
            "completed_tasks": self.completed_tasks,
            "points_earned": self.points_earned,
            "score": round(self.score, 2),
            "passed": self.passed,
            "feedback": self.feedback
        }


class LabManager:
    """
    Manages certification lab scenarios
    """

    def __init__(self):
        """Initialize with built-in labs"""
        self._labs: Dict[str, Lab] = {}
        self._attempts: Dict[str, LabAttempt] = {}
        self._attempt_counter = 0
        self._load_builtin_labs()

    def _load_builtin_labs(self):
        """Load built-in lab scenarios"""
        # CCNA OSPF Lab
        self._labs["ccna-ospf-basics"] = Lab(
            id="ccna-ospf-basics",
            title="CCNA: OSPF Basic Configuration",
            description="Configure OSPF on a multi-router topology and verify neighbor adjacencies.",
            certification="CCNA",
            topics=["OSPF", "Routing", "IGP"],
            difficulty=LabDifficulty.EASY,
            time_limit_minutes=45,
            objectives=[
                "Configure OSPF process on multiple routers",
                "Establish OSPF neighbor relationships",
                "Verify OSPF routing table entries",
                "Understand OSPF cost calculation"
            ],
            prerequisites=["IP addressing", "Basic routing concepts"],
            points_total=100,
            passing_score=70,
            topology={
                "agents": 3,
                "type": "linear",
                "protocols": ["ospf"]
            },
            tasks=[
                LabTask(
                    id="task-1",
                    title="Configure OSPF on R1",
                    description="Enable OSPF process 1 on R1 and add interfaces to area 0.",
                    instructions=[
                        "Configure OSPF process ID 1",
                        "Set router ID to 1.1.1.1",
                        "Add Ethernet0 to area 0",
                        "Add Loopback0 to area 0"
                    ],
                    points=25,
                    verification={
                        "check": "ospf_process",
                        "expected": {"process_id": 1, "area": 0}
                    },
                    hints=["Use 'router ospf 1' to start OSPF process"],
                    order=1
                ),
                LabTask(
                    id="task-2",
                    title="Configure OSPF on R2",
                    description="Enable OSPF on R2 with correct area assignments.",
                    instructions=[
                        "Configure OSPF process ID 1",
                        "Set router ID to 2.2.2.2",
                        "Add all interfaces to area 0"
                    ],
                    points=25,
                    verification={"check": "ospf_process"},
                    order=2
                ),
                LabTask(
                    id="task-3",
                    title="Verify OSPF Neighbors",
                    description="Verify that OSPF neighbor relationships are established.",
                    instructions=[
                        "Check OSPF neighbor table on R1",
                        "Verify neighbor state is FULL",
                        "Identify the DR and BDR"
                    ],
                    points=25,
                    verification={"check": "ospf_neighbor", "expected_state": "FULL"},
                    order=3
                ),
                LabTask(
                    id="task-4",
                    title="Verify Routing Table",
                    description="Verify OSPF routes are installed in the routing table.",
                    instructions=[
                        "Check routing table for OSPF routes",
                        "Verify routes to remote networks",
                        "Test connectivity with ping"
                    ],
                    points=25,
                    verification={"check": "routing_table", "route_count_min": 2},
                    order=4
                )
            ]
        )

        # CCNA BGP Lab
        self._labs["ccna-bgp-basics"] = Lab(
            id="ccna-bgp-basics",
            title="CCNA: BGP Peering Configuration",
            description="Configure eBGP peering between two autonomous systems.",
            certification="CCNA",
            topics=["BGP", "Routing", "EGP"],
            difficulty=LabDifficulty.MEDIUM,
            time_limit_minutes=60,
            objectives=[
                "Configure eBGP between different ASNs",
                "Advertise networks via BGP",
                "Verify BGP neighbor relationships",
                "Understand BGP path selection basics"
            ],
            prerequisites=["IP addressing", "Basic routing", "AS concept"],
            points_total=100,
            passing_score=70,
            topology={
                "agents": 2,
                "type": "point_to_point",
                "protocols": ["bgp"]
            },
            tasks=[
                LabTask(
                    id="task-1",
                    title="Configure BGP on R1",
                    description="Configure BGP AS 65001 on R1.",
                    instructions=[
                        "Configure BGP with AS 65001",
                        "Add neighbor 10.0.0.2 in AS 65002",
                        "Advertise network 192.168.1.0/24"
                    ],
                    points=30,
                    verification={"check": "bgp_config", "asn": 65001},
                    order=1
                ),
                LabTask(
                    id="task-2",
                    title="Configure BGP on R2",
                    description="Configure BGP AS 65002 on R2.",
                    instructions=[
                        "Configure BGP with AS 65002",
                        "Add neighbor 10.0.0.1 in AS 65001",
                        "Advertise network 192.168.2.0/24"
                    ],
                    points=30,
                    verification={"check": "bgp_config", "asn": 65002},
                    order=2
                ),
                LabTask(
                    id="task-3",
                    title="Verify BGP Session",
                    description="Verify BGP session is established.",
                    instructions=[
                        "Check BGP neighbor status",
                        "Verify state is Established",
                        "Check received prefixes"
                    ],
                    points=20,
                    verification={"check": "bgp_neighbor", "expected_state": "Established"},
                    order=3
                ),
                LabTask(
                    id="task-4",
                    title="Test Connectivity",
                    description="Verify end-to-end connectivity.",
                    instructions=[
                        "Ping from R1 to R2's loopback",
                        "Verify BGP routes in routing table"
                    ],
                    points=20,
                    verification={"check": "connectivity"},
                    order=4
                )
            ]
        )

        # CCNP OSPF Advanced Lab
        self._labs["ccnp-ospf-advanced"] = Lab(
            id="ccnp-ospf-advanced",
            title="CCNP: OSPF Multi-Area Design",
            description="Design and implement a multi-area OSPF network with route summarization.",
            certification="CCNP",
            topics=["OSPF", "Multi-area", "Summarization", "Stub areas"],
            difficulty=LabDifficulty.HARD,
            time_limit_minutes=90,
            objectives=[
                "Configure multi-area OSPF",
                "Implement route summarization",
                "Configure stub and totally stubby areas",
                "Verify LSA database"
            ],
            prerequisites=["OSPF basics", "Subnetting", "LSA types"],
            points_total=150,
            passing_score=75,
            topology={
                "agents": 5,
                "type": "hub_and_spoke",
                "protocols": ["ospf"]
            },
            tasks=[
                LabTask(
                    id="task-1",
                    title="Configure Area 0 Backbone",
                    description="Configure the backbone area with ABRs.",
                    points=30,
                    order=1
                ),
                LabTask(
                    id="task-2",
                    title="Configure Area 1 as Stub",
                    description="Configure Area 1 as a stub area.",
                    points=30,
                    order=2
                ),
                LabTask(
                    id="task-3",
                    title="Implement Summarization",
                    description="Configure route summarization on ABRs.",
                    points=40,
                    order=3
                ),
                LabTask(
                    id="task-4",
                    title="Verify LSA Database",
                    description="Verify the LSDB shows correct LSA types.",
                    points=25,
                    order=4
                ),
                LabTask(
                    id="task-5",
                    title="Test Convergence",
                    description="Simulate a link failure and verify convergence.",
                    points=25,
                    order=5
                )
            ]
        )

        # CCNP BGP Advanced Lab
        self._labs["ccnp-bgp-policy"] = Lab(
            id="ccnp-bgp-policy",
            title="CCNP: BGP Route Manipulation",
            description="Implement BGP route manipulation using attributes and policies.",
            certification="CCNP",
            topics=["BGP", "Route policy", "Path attributes", "Communities"],
            difficulty=LabDifficulty.HARD,
            time_limit_minutes=90,
            objectives=[
                "Configure BGP path attributes",
                "Implement route maps for policy",
                "Use communities for traffic engineering",
                "Configure route filtering"
            ],
            prerequisites=["BGP basics", "Route maps", "Prefix lists"],
            points_total=150,
            passing_score=75,
            topology={
                "agents": 4,
                "type": "full_mesh",
                "protocols": ["bgp"]
            },
            tasks=[
                LabTask(
                    id="task-1",
                    title="Configure iBGP Full Mesh",
                    description="Establish iBGP sessions between all routers.",
                    points=30,
                    order=1
                ),
                LabTask(
                    id="task-2",
                    title="Manipulate Local Preference",
                    description="Use local preference to influence outbound traffic.",
                    points=30,
                    order=2
                ),
                LabTask(
                    id="task-3",
                    title="Configure AS Path Prepending",
                    description="Use AS path prepending to influence inbound traffic.",
                    points=30,
                    order=3
                ),
                LabTask(
                    id="task-4",
                    title="Implement Communities",
                    description="Tag routes with communities and filter based on them.",
                    points=30,
                    order=4
                ),
                LabTask(
                    id="task-5",
                    title="Verify Policy Application",
                    description="Verify all policies are correctly applied.",
                    points=30,
                    order=5
                )
            ]
        )

        # CCNA Troubleshooting Lab
        self._labs["ccna-troubleshoot-ospf"] = Lab(
            id="ccna-troubleshoot-ospf",
            title="CCNA: OSPF Troubleshooting",
            description="Identify and fix OSPF configuration issues in a broken network.",
            certification="CCNA",
            topics=["OSPF", "Troubleshooting"],
            difficulty=LabDifficulty.MEDIUM,
            time_limit_minutes=45,
            objectives=[
                "Identify OSPF configuration errors",
                "Fix neighbor relationship issues",
                "Verify correct operation after fixes"
            ],
            prerequisites=["OSPF configuration", "Show commands"],
            points_total=100,
            passing_score=70,
            topology={
                "agents": 3,
                "type": "triangle",
                "protocols": ["ospf"],
                "has_errors": True
            },
            tasks=[
                LabTask(
                    id="task-1",
                    title="Identify Issues",
                    description="Use show commands to identify OSPF issues.",
                    points=20,
                    order=1
                ),
                LabTask(
                    id="task-2",
                    title="Fix Area Mismatch",
                    description="Correct the area mismatch between R1 and R2.",
                    points=30,
                    order=2
                ),
                LabTask(
                    id="task-3",
                    title="Fix Timer Mismatch",
                    description="Correct the hello/dead timer mismatch.",
                    points=25,
                    order=3
                ),
                LabTask(
                    id="task-4",
                    title="Verify Operation",
                    description="Verify all neighbors are in FULL state.",
                    points=25,
                    order=4
                )
            ]
        )

        logger.info(f"Loaded {len(self._labs)} built-in labs")

    def get_lab(self, lab_id: str) -> Optional[Lab]:
        """Get lab by ID"""
        return self._labs.get(lab_id)

    def list_labs(
        self,
        certification: Optional[str] = None,
        difficulty: Optional[LabDifficulty] = None,
        topics: Optional[List[str]] = None
    ) -> List[Lab]:
        """List labs with optional filters"""
        labs = list(self._labs.values())

        if certification:
            labs = [l for l in labs if l.certification.upper() == certification.upper()]

        if difficulty:
            labs = [l for l in labs if l.difficulty == difficulty]

        if topics:
            labs = [
                l for l in labs
                if any(t.lower() in [topic.lower() for topic in l.topics] for t in topics)
            ]

        return labs

    def start_lab(self, user_id: str, lab_id: str) -> Optional[LabAttempt]:
        """Start a lab attempt"""
        lab = self.get_lab(lab_id)
        if not lab:
            return None

        self._attempt_counter += 1
        attempt_id = f"attempt-{self._attempt_counter:05d}"

        attempt = LabAttempt(
            id=attempt_id,
            user_id=user_id,
            lab_id=lab_id,
            status=LabStatus.IN_PROGRESS,
            started_at=datetime.now(),
            time_remaining_seconds=lab.time_limit_minutes * 60
        )

        # Initialize task status
        for task in lab.tasks:
            attempt.task_status[task.id] = TaskStatus.PENDING
            attempt.task_points[task.id] = 0

        self._attempts[attempt_id] = attempt
        logger.info(f"Started lab attempt {attempt_id} for user {user_id}")
        return attempt

    def complete_task(
        self,
        attempt_id: str,
        task_id: str,
        passed: bool,
        points: Optional[int] = None
    ) -> Optional[LabAttempt]:
        """Mark a task as completed"""
        attempt = self._attempts.get(attempt_id)
        if not attempt:
            return None

        lab = self.get_lab(attempt.lab_id)
        if not lab:
            return None

        task = lab.get_task(task_id)
        if not task:
            return None

        if passed:
            attempt.task_status[task_id] = TaskStatus.COMPLETED
            earned = points if points is not None else task.points
            attempt.task_points[task_id] = earned
            attempt.points_earned += earned
        else:
            attempt.task_status[task_id] = TaskStatus.FAILED
            attempt.task_points[task_id] = 0

        return attempt

    def complete_lab(self, attempt_id: str) -> Optional[LabAttempt]:
        """Complete a lab attempt"""
        attempt = self._attempts.get(attempt_id)
        if not attempt:
            return None

        lab = self.get_lab(attempt.lab_id)
        if not lab:
            return None

        attempt.completed_at = datetime.now()
        attempt.score = (attempt.points_earned / lab.points_total) * 100
        attempt.passed = attempt.score >= lab.passing_score

        if attempt.passed:
            attempt.status = LabStatus.COMPLETED
            attempt.feedback = "Congratulations! You passed the lab."
        else:
            attempt.status = LabStatus.FAILED
            attempt.feedback = f"You scored {attempt.score:.1f}%. Required: {lab.passing_score}%"

        logger.info(f"Lab attempt {attempt_id} completed: {'passed' if attempt.passed else 'failed'}")
        return attempt

    def get_attempt(self, attempt_id: str) -> Optional[LabAttempt]:
        """Get attempt by ID"""
        return self._attempts.get(attempt_id)

    def get_user_attempts(self, user_id: str, lab_id: Optional[str] = None) -> List[LabAttempt]:
        """Get attempts for a user"""
        attempts = [a for a in self._attempts.values() if a.user_id == user_id]
        if lab_id:
            attempts = [a for a in attempts if a.lab_id == lab_id]
        attempts.sort(key=lambda a: a.started_at or datetime.min, reverse=True)
        return attempts

    def get_statistics(self) -> Dict[str, Any]:
        """Get lab statistics"""
        total_labs = len(self._labs)
        by_cert = {}
        by_diff = {}

        for lab in self._labs.values():
            cert = lab.certification
            diff = lab.difficulty.value

            by_cert[cert] = by_cert.get(cert, 0) + 1
            by_diff[diff] = by_diff.get(diff, 0) + 1

        total_attempts = len(self._attempts)
        passed = sum(1 for a in self._attempts.values() if a.passed)

        return {
            "total_labs": total_labs,
            "by_certification": by_cert,
            "by_difficulty": by_diff,
            "total_attempts": total_attempts,
            "passed_attempts": passed,
            "pass_rate": round((passed / total_attempts * 100) if total_attempts > 0 else 0, 2)
        }


# Global lab manager instance
_global_manager: Optional[LabManager] = None


def get_lab_manager() -> LabManager:
    """Get or create the global lab manager"""
    global _global_manager
    if _global_manager is None:
        _global_manager = LabManager()
    return _global_manager
