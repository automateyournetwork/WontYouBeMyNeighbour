"""
Assessment Module - Quiz and knowledge check functionality

Provides:
- Quiz definitions with multiple question types
- Answer evaluation
- Score calculation
- Feedback generation
"""

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any

logger = logging.getLogger("AssessmentEngine")


class QuestionType(str, Enum):
    """Types of assessment questions"""
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    MULTIPLE_SELECT = "multiple_select"
    FILL_BLANK = "fill_blank"
    MATCHING = "matching"
    ORDERING = "ordering"


@dataclass
class QuestionOption:
    """
    An option for multiple choice questions

    Attributes:
        id: Option identifier
        text: Option text
        is_correct: Whether this is a correct answer
        feedback: Feedback if selected
    """
    id: str
    text: str
    is_correct: bool = False
    feedback: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            # Don't expose is_correct in serialization
            "feedback": self.feedback
        }

    def to_dict_with_answer(self) -> Dict[str, Any]:
        """Include answer for grading"""
        return {
            "id": self.id,
            "text": self.text,
            "is_correct": self.is_correct,
            "feedback": self.feedback
        }


@dataclass
class Question:
    """
    An assessment question

    Attributes:
        id: Question identifier
        question_type: Type of question
        text: Question text
        options: Answer options
        correct_answer: Correct answer(s)
        explanation: Explanation of correct answer
        points: Points for this question
        difficulty: Question difficulty (1-5)
        tags: Question tags
    """
    id: str
    question_type: QuestionType
    text: str
    options: List[QuestionOption] = field(default_factory=list)
    correct_answer: Any = None
    explanation: str = ""
    points: int = 1
    difficulty: int = 1
    tags: List[str] = field(default_factory=list)

    def check_answer(self, answer: Any) -> tuple[bool, float, str]:
        """
        Check if answer is correct

        Returns:
            Tuple of (is_correct, partial_score, feedback)
        """
        if self.question_type == QuestionType.MULTIPLE_CHOICE:
            is_correct = answer == self.correct_answer
            return (is_correct, 1.0 if is_correct else 0.0, self.explanation)

        elif self.question_type == QuestionType.TRUE_FALSE:
            is_correct = answer == self.correct_answer
            return (is_correct, 1.0 if is_correct else 0.0, self.explanation)

        elif self.question_type == QuestionType.MULTIPLE_SELECT:
            if not isinstance(answer, list):
                return (False, 0.0, "Expected list of answers")
            correct_set = set(self.correct_answer)
            answer_set = set(answer)
            # Partial credit for partially correct answers
            correct_selected = len(correct_set & answer_set)
            incorrect_selected = len(answer_set - correct_set)
            total_correct = len(correct_set)
            # Deduct for wrong selections
            partial = max(0, (correct_selected - incorrect_selected) / total_correct)
            is_correct = partial == 1.0
            return (is_correct, partial, self.explanation)

        elif self.question_type == QuestionType.FILL_BLANK:
            # Case-insensitive comparison
            if isinstance(self.correct_answer, list):
                is_correct = answer.lower().strip() in [
                    a.lower() for a in self.correct_answer
                ]
            else:
                is_correct = answer.lower().strip() == self.correct_answer.lower().strip()
            return (is_correct, 1.0 if is_correct else 0.0, self.explanation)

        elif self.question_type == QuestionType.ORDERING:
            if not isinstance(answer, list):
                return (False, 0.0, "Expected list of items in order")
            is_correct = answer == self.correct_answer
            # Partial credit based on position matches
            matches = sum(1 for i, a in enumerate(answer) if i < len(self.correct_answer) and a == self.correct_answer[i])
            partial = matches / len(self.correct_answer) if self.correct_answer else 0
            return (is_correct, partial, self.explanation)

        return (False, 0.0, "Unknown question type")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "question_type": self.question_type.value,
            "text": self.text,
            "options": [o.to_dict() for o in self.options],
            "points": self.points,
            "difficulty": self.difficulty,
            "tags": self.tags
        }


@dataclass
class Assessment:
    """
    A complete assessment (quiz)

    Attributes:
        id: Assessment identifier
        title: Assessment title
        description: Assessment description
        questions: List of questions
        time_limit_minutes: Time limit (0 = no limit)
        passing_score: Minimum passing score (0-100)
        shuffle_questions: Whether to shuffle questions
        shuffle_options: Whether to shuffle options
        show_feedback: When to show feedback
        max_attempts: Maximum attempts (0 = unlimited)
    """
    id: str
    title: str
    description: str = ""
    questions: List[Question] = field(default_factory=list)
    time_limit_minutes: int = 0
    passing_score: float = 70.0
    shuffle_questions: bool = False
    shuffle_options: bool = False
    show_feedback: str = "after_submit"  # immediate, after_submit, never
    max_attempts: int = 0

    @property
    def total_points(self) -> int:
        return sum(q.points for q in self.questions)

    @property
    def question_count(self) -> int:
        return len(self.questions)

    def get_questions(self, shuffle: bool = None) -> List[Question]:
        """Get questions, optionally shuffled"""
        questions = list(self.questions)
        if shuffle is None:
            shuffle = self.shuffle_questions
        if shuffle:
            random.shuffle(questions)
        return questions

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "questions": [q.to_dict() for q in self.questions],
            "time_limit_minutes": self.time_limit_minutes,
            "passing_score": self.passing_score,
            "total_points": self.total_points,
            "question_count": self.question_count,
            "show_feedback": self.show_feedback,
            "max_attempts": self.max_attempts
        }


@dataclass
class AnswerRecord:
    """Record of a single answer"""
    question_id: str
    answer: Any
    is_correct: bool
    partial_score: float
    points_earned: float
    feedback: str
    answered_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "question_id": self.question_id,
            "answer": self.answer,
            "is_correct": self.is_correct,
            "partial_score": self.partial_score,
            "points_earned": self.points_earned,
            "feedback": self.feedback,
            "answered_at": self.answered_at.isoformat()
        }


@dataclass
class AssessmentResult:
    """
    Result of an assessment attempt

    Attributes:
        assessment_id: Assessment identifier
        user_id: User identifier
        answers: Answer records
        score: Final score (0-100)
        points_earned: Total points earned
        points_possible: Total points possible
        passed: Whether passed
        started_at: Start timestamp
        completed_at: Completion timestamp
        attempt_number: Attempt number
    """
    assessment_id: str
    user_id: str
    answers: List[AnswerRecord] = field(default_factory=list)
    score: float = 0.0
    points_earned: float = 0.0
    points_possible: float = 0.0
    passed: bool = False
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    attempt_number: int = 1

    @property
    def is_complete(self) -> bool:
        return self.completed_at is not None

    @property
    def duration_seconds(self) -> int:
        if self.completed_at:
            return int((self.completed_at - self.started_at).total_seconds())
        return int((datetime.now() - self.started_at).total_seconds())

    @property
    def correct_count(self) -> int:
        return sum(1 for a in self.answers if a.is_correct)

    @property
    def incorrect_count(self) -> int:
        return len(self.answers) - self.correct_count

    def add_answer(self, record: AnswerRecord):
        """Add an answer record"""
        self.answers.append(record)
        self.points_earned += record.points_earned

    def complete(self, passing_score: float):
        """Complete the assessment"""
        self.completed_at = datetime.now()
        if self.points_possible > 0:
            self.score = (self.points_earned / self.points_possible) * 100
        self.passed = self.score >= passing_score

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "user_id": self.user_id,
            "answers": [a.to_dict() for a in self.answers],
            "score": round(self.score, 2),
            "points_earned": self.points_earned,
            "points_possible": self.points_possible,
            "passed": self.passed,
            "correct_count": self.correct_count,
            "incorrect_count": self.incorrect_count,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "attempt_number": self.attempt_number,
            "is_complete": self.is_complete
        }


class AssessmentEngine:
    """
    Manages assessments and grading
    """

    def __init__(self):
        """Initialize with built-in assessments"""
        self._assessments: Dict[str, Assessment] = {}
        self._results: Dict[str, List[AssessmentResult]] = {}  # user_id -> results
        self._active_attempts: Dict[str, AssessmentResult] = {}  # attempt_key -> result
        self._load_builtin_assessments()

    def _load_builtin_assessments(self):
        """Load built-in assessment library"""
        # OSPF Fundamentals Quiz
        self._assessments["ospf-fundamentals-quiz"] = Assessment(
            id="ospf-fundamentals-quiz",
            title="OSPF Fundamentals Quiz",
            description="Test your knowledge of OSPF basics",
            passing_score=70.0,
            time_limit_minutes=15,
            questions=[
                Question(
                    id="ospf-q1",
                    question_type=QuestionType.MULTIPLE_CHOICE,
                    text="Which algorithm does OSPF use to calculate the shortest path?",
                    options=[
                        QuestionOption("a", "Bellman-Ford", feedback="Bellman-Ford is used by distance vector protocols like RIP"),
                        QuestionOption("b", "Dijkstra", is_correct=True, feedback="Correct! OSPF uses Dijkstra's SPF algorithm"),
                        QuestionOption("c", "Floyd-Warshall", feedback="Floyd-Warshall is used for all-pairs shortest path"),
                        QuestionOption("d", "Kruskal", feedback="Kruskal is used for minimum spanning trees")
                    ],
                    correct_answer="b",
                    explanation="OSPF uses Dijkstra's Shortest Path First (SPF) algorithm to compute the best path to each destination.",
                    points=2,
                    difficulty=2
                ),
                Question(
                    id="ospf-q2",
                    question_type=QuestionType.MULTIPLE_CHOICE,
                    text="What is the default OSPF Hello interval on broadcast networks?",
                    options=[
                        QuestionOption("a", "5 seconds", feedback="5 seconds is not the default"),
                        QuestionOption("b", "10 seconds", is_correct=True, feedback="Correct!"),
                        QuestionOption("c", "30 seconds", feedback="30 seconds is the default for NBMA networks"),
                        QuestionOption("d", "40 seconds", feedback="40 seconds is the default Dead interval")
                    ],
                    correct_answer="b",
                    explanation="The default OSPF Hello interval is 10 seconds on broadcast and point-to-point networks, and 30 seconds on NBMA networks.",
                    points=1,
                    difficulty=1
                ),
                Question(
                    id="ospf-q3",
                    question_type=QuestionType.TRUE_FALSE,
                    text="OSPF is a classless routing protocol that supports VLSM.",
                    correct_answer=True,
                    explanation="OSPF is indeed classless and supports Variable Length Subnet Masks (VLSM) and CIDR.",
                    points=1,
                    difficulty=1
                ),
                Question(
                    id="ospf-q4",
                    question_type=QuestionType.MULTIPLE_SELECT,
                    text="Which OSPF neighbor states indicate a forming adjacency? (Select all that apply)",
                    options=[
                        QuestionOption("a", "ExStart", is_correct=True),
                        QuestionOption("b", "Exchange", is_correct=True),
                        QuestionOption("c", "Loading", is_correct=True),
                        QuestionOption("d", "2-Way"),
                        QuestionOption("e", "Full")
                    ],
                    correct_answer=["a", "b", "c"],
                    explanation="ExStart, Exchange, and Loading are the adjacency formation states. 2-Way indicates bidirectional communication but not full adjacency. Full means the adjacency is complete.",
                    points=3,
                    difficulty=3
                ),
                Question(
                    id="ospf-q5",
                    question_type=QuestionType.ORDERING,
                    text="Put the OSPF neighbor states in the correct order (first to last):",
                    options=[
                        QuestionOption("a", "Down"),
                        QuestionOption("b", "Init"),
                        QuestionOption("c", "2-Way"),
                        QuestionOption("d", "ExStart"),
                        QuestionOption("e", "Full")
                    ],
                    correct_answer=["a", "b", "c", "d", "e"],
                    explanation="The correct order is: Down -> Init -> 2-Way -> ExStart -> Exchange -> Loading -> Full",
                    points=2,
                    difficulty=2
                )
            ]
        )

        # BGP Fundamentals Quiz
        self._assessments["bgp-fundamentals-quiz"] = Assessment(
            id="bgp-fundamentals-quiz",
            title="BGP Fundamentals Quiz",
            description="Test your knowledge of BGP basics",
            passing_score=70.0,
            time_limit_minutes=20,
            questions=[
                Question(
                    id="bgp-q1",
                    question_type=QuestionType.MULTIPLE_CHOICE,
                    text="What transport protocol and port does BGP use?",
                    options=[
                        QuestionOption("a", "UDP port 179", feedback="BGP uses TCP, not UDP"),
                        QuestionOption("b", "TCP port 179", is_correct=True, feedback="Correct!"),
                        QuestionOption("c", "TCP port 89", feedback="Port 89 is used by OSPF"),
                        QuestionOption("d", "UDP port 520", feedback="Port 520 is used by RIP")
                    ],
                    correct_answer="b",
                    explanation="BGP uses TCP port 179 for reliable delivery of routing information.",
                    points=1,
                    difficulty=1
                ),
                Question(
                    id="bgp-q2",
                    question_type=QuestionType.MULTIPLE_CHOICE,
                    text="In BGP path selection, which attribute is checked first?",
                    options=[
                        QuestionOption("a", "AS Path length", feedback="AS Path is checked after Local Preference"),
                        QuestionOption("b", "MED", feedback="MED is checked later in the process"),
                        QuestionOption("c", "Weight (Cisco)", is_correct=True, feedback="Correct! Weight is checked first (Cisco-specific)"),
                        QuestionOption("d", "Origin", feedback="Origin is checked after AS Path")
                    ],
                    correct_answer="c",
                    explanation="The BGP best path selection process checks: Weight (highest) -> Local Pref (highest) -> Locally originated -> AS Path (shortest) -> Origin (i<e<?) -> MED (lowest) -> eBGP over iBGP -> IGP metric -> Age -> Router ID -> Neighbor IP",
                    points=2,
                    difficulty=2
                ),
                Question(
                    id="bgp-q3",
                    question_type=QuestionType.TRUE_FALSE,
                    text="iBGP peers must be directly connected.",
                    correct_answer=False,
                    explanation="iBGP peers do not need to be directly connected. They can be multiple hops apart as long as there is IP reachability (typically via IGP). This is different from eBGP which requires direct connectivity by default (but can use multihop).",
                    points=1,
                    difficulty=2
                ),
                Question(
                    id="bgp-q4",
                    question_type=QuestionType.MULTIPLE_SELECT,
                    text="Which are well-known mandatory BGP attributes? (Select all that apply)",
                    options=[
                        QuestionOption("a", "ORIGIN", is_correct=True),
                        QuestionOption("b", "AS_PATH", is_correct=True),
                        QuestionOption("c", "NEXT_HOP", is_correct=True),
                        QuestionOption("d", "MED"),
                        QuestionOption("e", "LOCAL_PREF")
                    ],
                    correct_answer=["a", "b", "c"],
                    explanation="ORIGIN, AS_PATH, and NEXT_HOP are well-known mandatory attributes. MED is optional transitive, and LOCAL_PREF is well-known discretionary.",
                    points=3,
                    difficulty=3
                ),
                Question(
                    id="bgp-q5",
                    question_type=QuestionType.FILL_BLANK,
                    text="The BGP FSM state where the router has received an OPEN message and is waiting for KEEPALIVE is called ________.",
                    correct_answer=["OpenConfirm", "openconfirm", "open confirm"],
                    explanation="After receiving a valid OPEN message, the router transitions to OpenConfirm state and waits for a KEEPALIVE message.",
                    points=2,
                    difficulty=2
                )
            ]
        )

        # Network Troubleshooting Quiz
        self._assessments["troubleshooting-basics-quiz"] = Assessment(
            id="troubleshooting-basics-quiz",
            title="Network Troubleshooting Quiz",
            description="Test your troubleshooting methodology",
            passing_score=60.0,
            time_limit_minutes=10,
            questions=[
                Question(
                    id="ts-q1",
                    question_type=QuestionType.MULTIPLE_CHOICE,
                    text="Which layer of the OSI model does the ping command primarily test?",
                    options=[
                        QuestionOption("a", "Layer 2 - Data Link", feedback="Ping uses IP, not MAC addresses"),
                        QuestionOption("b", "Layer 3 - Network", is_correct=True, feedback="Correct! Ping uses ICMP which operates at Layer 3"),
                        QuestionOption("c", "Layer 4 - Transport", feedback="Ping doesn't use TCP/UDP"),
                        QuestionOption("d", "Layer 7 - Application", feedback="Ping is not an application layer test")
                    ],
                    correct_answer="b",
                    explanation="Ping uses ICMP (Internet Control Message Protocol) which operates at Layer 3 (Network layer) of the OSI model.",
                    points=1,
                    difficulty=1
                ),
                Question(
                    id="ts-q2",
                    question_type=QuestionType.TRUE_FALSE,
                    text="A successful ping to the default gateway confirms end-to-end connectivity.",
                    correct_answer=False,
                    explanation="A successful ping to the default gateway only confirms local connectivity to the first hop. It does not verify end-to-end connectivity to the final destination.",
                    points=1,
                    difficulty=1
                )
            ]
        )

        logger.info(f"Loaded {len(self._assessments)} built-in assessments")

    def get_assessment(self, assessment_id: str) -> Optional[Assessment]:
        """Get assessment by ID"""
        return self._assessments.get(assessment_id)

    def list_assessments(self) -> List[Assessment]:
        """List all assessments"""
        return list(self._assessments.values())

    def start_attempt(
        self,
        user_id: str,
        assessment_id: str
    ) -> Optional[AssessmentResult]:
        """Start an assessment attempt"""
        assessment = self.get_assessment(assessment_id)
        if not assessment:
            return None

        # Check max attempts
        user_results = self._results.get(user_id, [])
        assessment_attempts = [
            r for r in user_results
            if r.assessment_id == assessment_id
        ]
        if assessment.max_attempts > 0 and len(assessment_attempts) >= assessment.max_attempts:
            logger.warning(f"User {user_id} exceeded max attempts for {assessment_id}")
            return None

        # Create new result
        result = AssessmentResult(
            assessment_id=assessment_id,
            user_id=user_id,
            points_possible=assessment.total_points,
            attempt_number=len(assessment_attempts) + 1
        )

        # Store active attempt
        attempt_key = f"{user_id}:{assessment_id}"
        self._active_attempts[attempt_key] = result

        return result

    def submit_answer(
        self,
        user_id: str,
        assessment_id: str,
        question_id: str,
        answer: Any
    ) -> Optional[AnswerRecord]:
        """Submit an answer for a question"""
        attempt_key = f"{user_id}:{assessment_id}"
        result = self._active_attempts.get(attempt_key)
        if not result:
            return None

        assessment = self.get_assessment(assessment_id)
        if not assessment:
            return None

        # Find question
        question = next(
            (q for q in assessment.questions if q.id == question_id),
            None
        )
        if not question:
            return None

        # Check answer
        is_correct, partial_score, feedback = question.check_answer(answer)
        points_earned = question.points * partial_score

        # Create answer record
        record = AnswerRecord(
            question_id=question_id,
            answer=answer,
            is_correct=is_correct,
            partial_score=partial_score,
            points_earned=points_earned,
            feedback=feedback
        )

        result.add_answer(record)
        return record

    def complete_attempt(
        self,
        user_id: str,
        assessment_id: str
    ) -> Optional[AssessmentResult]:
        """Complete an assessment attempt"""
        attempt_key = f"{user_id}:{assessment_id}"
        result = self._active_attempts.get(attempt_key)
        if not result:
            return None

        assessment = self.get_assessment(assessment_id)
        if not assessment:
            return None

        # Complete the result
        result.complete(assessment.passing_score)

        # Store in user results
        if user_id not in self._results:
            self._results[user_id] = []
        self._results[user_id].append(result)

        # Remove from active
        del self._active_attempts[attempt_key]

        return result

    def get_user_results(
        self,
        user_id: str,
        assessment_id: Optional[str] = None
    ) -> List[AssessmentResult]:
        """Get results for a user"""
        results = self._results.get(user_id, [])
        if assessment_id:
            results = [r for r in results if r.assessment_id == assessment_id]
        return results

    def get_statistics(self) -> Dict[str, Any]:
        """Get assessment statistics"""
        total_attempts = sum(len(r) for r in self._results.values())
        all_results = [r for results in self._results.values() for r in results]

        pass_count = sum(1 for r in all_results if r.passed)
        avg_score = sum(r.score for r in all_results) / len(all_results) if all_results else 0

        return {
            "total_assessments": len(self._assessments),
            "total_attempts": total_attempts,
            "total_users": len(self._results),
            "pass_rate": (pass_count / total_attempts * 100) if total_attempts > 0 else 0,
            "average_score": round(avg_score, 2),
            "active_attempts": len(self._active_attempts)
        }


# Global assessment engine instance
_global_engine: Optional[AssessmentEngine] = None


def get_assessment_engine() -> AssessmentEngine:
    """Get or create the global assessment engine"""
    global _global_engine
    if _global_engine is None:
        _global_engine = AssessmentEngine()
    return _global_engine
