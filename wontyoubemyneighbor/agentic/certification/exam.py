"""
Practice Exam Module - Certification practice exams

Provides:
- Multi-format practice exams
- Timed exam sessions
- Detailed scoring and feedback
- Question pools
"""

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any

logger = logging.getLogger("ExamEngine")


class QuestionType(str, Enum):
    """Types of exam questions"""
    MULTIPLE_CHOICE = "multiple_choice"
    MULTIPLE_SELECT = "multiple_select"
    DRAG_DROP = "drag_drop"
    SIMULATION = "simulation"
    FILL_BLANK = "fill_blank"


@dataclass
class ExamOption:
    """An option for multiple choice questions"""
    id: str
    text: str
    is_correct: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "text": self.text}

    def to_dict_with_answer(self) -> Dict[str, Any]:
        return {"id": self.id, "text": self.text, "is_correct": self.is_correct}


@dataclass
class ExamQuestion:
    """
    A practice exam question

    Attributes:
        id: Question identifier
        question_type: Type of question
        text: Question text
        options: Answer options
        correct_answer: Correct answer(s)
        explanation: Explanation of correct answer
        topic: Topic area
        difficulty: Question difficulty (1-5)
        points: Points for question
    """
    id: str
    question_type: QuestionType
    text: str
    options: List[ExamOption] = field(default_factory=list)
    correct_answer: Any = None
    explanation: str = ""
    topic: str = ""
    difficulty: int = 3
    points: int = 1

    def check_answer(self, answer: Any) -> tuple[bool, float, str]:
        """Check answer and return (is_correct, partial_score, feedback)"""
        if self.question_type == QuestionType.MULTIPLE_CHOICE:
            is_correct = answer == self.correct_answer
            return (is_correct, 1.0 if is_correct else 0.0, self.explanation)

        elif self.question_type == QuestionType.MULTIPLE_SELECT:
            if not isinstance(answer, list):
                return (False, 0.0, "Expected list of answers")
            correct_set = set(self.correct_answer)
            answer_set = set(answer)
            correct_selected = len(correct_set & answer_set)
            incorrect_selected = len(answer_set - correct_set)
            total_correct = len(correct_set)
            partial = max(0, (correct_selected - incorrect_selected) / total_correct)
            return (partial == 1.0, partial, self.explanation)

        elif self.question_type == QuestionType.FILL_BLANK:
            if isinstance(self.correct_answer, list):
                is_correct = answer.lower().strip() in [a.lower() for a in self.correct_answer]
            else:
                is_correct = answer.lower().strip() == self.correct_answer.lower().strip()
            return (is_correct, 1.0 if is_correct else 0.0, self.explanation)

        return (False, 0.0, "Unknown question type")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "question_type": self.question_type.value,
            "text": self.text,
            "options": [o.to_dict() for o in self.options],
            "topic": self.topic,
            "difficulty": self.difficulty,
            "points": self.points
        }


@dataclass
class PracticeExam:
    """
    A practice exam definition

    Attributes:
        id: Exam identifier
        title: Exam title
        certification: Target certification
        description: Exam description
        questions: Question pool
        question_count: Number of questions to present
        time_limit_minutes: Time limit
        passing_score: Passing percentage
        randomize: Whether to randomize questions
    """
    id: str
    title: str
    certification: str
    description: str = ""
    questions: List[ExamQuestion] = field(default_factory=list)
    question_count: int = 50
    time_limit_minutes: int = 90
    passing_score: float = 70.0
    randomize: bool = True

    @property
    def total_points(self) -> int:
        return sum(q.points for q in self.questions[:self.question_count])

    def get_questions(self) -> List[ExamQuestion]:
        """Get questions for exam (possibly randomized)"""
        questions = list(self.questions)
        if self.randomize:
            random.shuffle(questions)
        return questions[:self.question_count]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "certification": self.certification,
            "description": self.description,
            "question_count": self.question_count,
            "time_limit_minutes": self.time_limit_minutes,
            "passing_score": self.passing_score,
            "pool_size": len(self.questions)
        }


@dataclass
class ExamAttempt:
    """A user's exam attempt"""
    id: str
    user_id: str
    exam_id: str
    questions: List[ExamQuestion] = field(default_factory=list)
    answers: Dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    time_remaining_seconds: int = 0
    current_question: int = 0

    @property
    def is_complete(self) -> bool:
        return self.completed_at is not None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "exam_id": self.exam_id,
            "question_count": len(self.questions),
            "answers_submitted": len(self.answers),
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "time_remaining_seconds": self.time_remaining_seconds,
            "current_question": self.current_question,
            "is_complete": self.is_complete
        }


@dataclass
class ExamResult:
    """Result of an exam attempt"""
    attempt_id: str
    exam_id: str
    user_id: str
    score: float
    points_earned: int
    points_possible: int
    passed: bool
    correct_count: int
    incorrect_count: int
    duration_seconds: int
    by_topic: Dict[str, Dict[str, int]] = field(default_factory=dict)
    question_results: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "exam_id": self.exam_id,
            "user_id": self.user_id,
            "score": round(self.score, 2),
            "points_earned": self.points_earned,
            "points_possible": self.points_possible,
            "passed": self.passed,
            "correct_count": self.correct_count,
            "incorrect_count": self.incorrect_count,
            "duration_seconds": self.duration_seconds,
            "by_topic": self.by_topic,
            "question_results": self.question_results
        }


class ExamEngine:
    """
    Manages practice exams
    """

    def __init__(self):
        """Initialize with built-in exams"""
        self._exams: Dict[str, PracticeExam] = {}
        self._attempts: Dict[str, ExamAttempt] = {}
        self._results: Dict[str, List[ExamResult]] = {}
        self._attempt_counter = 0
        self._load_builtin_exams()

    def _load_builtin_exams(self):
        """Load built-in practice exams"""
        # CCNA Practice Exam
        ccna_questions = [
            ExamQuestion(
                id="ccna-q1",
                question_type=QuestionType.MULTIPLE_CHOICE,
                text="What is the default administrative distance of OSPF?",
                options=[
                    ExamOption("a", "90"),
                    ExamOption("b", "100"),
                    ExamOption("c", "110", is_correct=True),
                    ExamOption("d", "120")
                ],
                correct_answer="c",
                explanation="OSPF has a default AD of 110. EIGRP is 90, iBGP is 200.",
                topic="Routing",
                difficulty=2
            ),
            ExamQuestion(
                id="ccna-q2",
                question_type=QuestionType.MULTIPLE_CHOICE,
                text="Which protocol uses TCP port 179?",
                options=[
                    ExamOption("a", "OSPF"),
                    ExamOption("b", "EIGRP"),
                    ExamOption("c", "RIP"),
                    ExamOption("d", "BGP", is_correct=True)
                ],
                correct_answer="d",
                explanation="BGP uses TCP port 179. OSPF uses IP protocol 89.",
                topic="BGP",
                difficulty=2
            ),
            ExamQuestion(
                id="ccna-q3",
                question_type=QuestionType.MULTIPLE_SELECT,
                text="Which of the following are OSPF LSA types? (Select two)",
                options=[
                    ExamOption("a", "Type 1 - Router LSA", is_correct=True),
                    ExamOption("b", "Type 2 - Network LSA", is_correct=True),
                    ExamOption("c", "Type 6 - Multicast LSA"),
                    ExamOption("d", "Type 10 - Opaque LSA")
                ],
                correct_answer=["a", "b"],
                explanation="Type 1 (Router) and Type 2 (Network) are the most common OSPF LSA types.",
                topic="OSPF",
                difficulty=3
            ),
            ExamQuestion(
                id="ccna-q4",
                question_type=QuestionType.MULTIPLE_CHOICE,
                text="What is the subnet mask for a /26 network?",
                options=[
                    ExamOption("a", "255.255.255.128"),
                    ExamOption("b", "255.255.255.192", is_correct=True),
                    ExamOption("c", "255.255.255.224"),
                    ExamOption("d", "255.255.255.240")
                ],
                correct_answer="b",
                explanation="/26 = 255.255.255.192 (64 addresses per subnet)",
                topic="IP Addressing",
                difficulty=2
            ),
            ExamQuestion(
                id="ccna-q5",
                question_type=QuestionType.MULTIPLE_CHOICE,
                text="Which OSPF neighbor state indicates full adjacency?",
                options=[
                    ExamOption("a", "2-Way"),
                    ExamOption("b", "ExStart"),
                    ExamOption("c", "Loading"),
                    ExamOption("d", "Full", is_correct=True)
                ],
                correct_answer="d",
                explanation="Full state indicates complete LSDB synchronization.",
                topic="OSPF",
                difficulty=2
            ),
            ExamQuestion(
                id="ccna-q6",
                question_type=QuestionType.FILL_BLANK,
                text="The default OSPF hello interval on broadcast networks is ___ seconds.",
                correct_answer=["10", "ten"],
                explanation="Default hello is 10 seconds on broadcast, 30 on NBMA.",
                topic="OSPF",
                difficulty=1
            ),
            ExamQuestion(
                id="ccna-q7",
                question_type=QuestionType.MULTIPLE_CHOICE,
                text="What is the purpose of the BGP AS_PATH attribute?",
                options=[
                    ExamOption("a", "Indicate the metric to reach a destination"),
                    ExamOption("b", "List the autonomous systems traversed", is_correct=True),
                    ExamOption("c", "Specify the next-hop IP address"),
                    ExamOption("d", "Define the route origin")
                ],
                correct_answer="b",
                explanation="AS_PATH lists the ASNs the route has traversed, used for loop prevention and path selection.",
                topic="BGP",
                difficulty=2
            ),
            ExamQuestion(
                id="ccna-q8",
                question_type=QuestionType.MULTIPLE_CHOICE,
                text="Which command shows the OSPF neighbor table?",
                options=[
                    ExamOption("a", "show ip ospf neighbor", is_correct=True),
                    ExamOption("b", "show ospf neighbors"),
                    ExamOption("c", "show ip route ospf"),
                    ExamOption("d", "show ip ospf interface")
                ],
                correct_answer="a",
                explanation="'show ip ospf neighbor' displays the OSPF neighbor table.",
                topic="OSPF",
                difficulty=1
            )
        ]

        self._exams["ccna-practice"] = PracticeExam(
            id="ccna-practice",
            title="CCNA Practice Exam",
            certification="CCNA",
            description="Practice exam covering CCNA networking fundamentals.",
            questions=ccna_questions,
            question_count=8,
            time_limit_minutes=30,
            passing_score=70.0
        )

        # CCNP Practice Exam
        ccnp_questions = [
            ExamQuestion(
                id="ccnp-q1",
                question_type=QuestionType.MULTIPLE_CHOICE,
                text="What is the purpose of the BGP next-hop-self command?",
                options=[
                    ExamOption("a", "Set the MED attribute"),
                    ExamOption("b", "Override the next-hop for iBGP peers", is_correct=True),
                    ExamOption("c", "Change the AS path"),
                    ExamOption("d", "Modify local preference")
                ],
                correct_answer="b",
                explanation="next-hop-self changes the next-hop to the advertising router's IP for iBGP peers.",
                topic="BGP",
                difficulty=4
            ),
            ExamQuestion(
                id="ccnp-q2",
                question_type=QuestionType.MULTIPLE_SELECT,
                text="Which BGP attributes are well-known mandatory? (Select three)",
                options=[
                    ExamOption("a", "ORIGIN", is_correct=True),
                    ExamOption("b", "AS_PATH", is_correct=True),
                    ExamOption("c", "NEXT_HOP", is_correct=True),
                    ExamOption("d", "MED"),
                    ExamOption("e", "LOCAL_PREF")
                ],
                correct_answer=["a", "b", "c"],
                explanation="ORIGIN, AS_PATH, and NEXT_HOP are well-known mandatory. MED is optional transitive.",
                topic="BGP",
                difficulty=4
            ),
            ExamQuestion(
                id="ccnp-q3",
                question_type=QuestionType.MULTIPLE_CHOICE,
                text="Which OSPF LSA type is generated by an ASBR?",
                options=[
                    ExamOption("a", "Type 1"),
                    ExamOption("b", "Type 3"),
                    ExamOption("c", "Type 5", is_correct=True),
                    ExamOption("d", "Type 7")
                ],
                correct_answer="c",
                explanation="Type 5 LSAs are generated by ASBRs to advertise external routes.",
                topic="OSPF",
                difficulty=3
            ),
            ExamQuestion(
                id="ccnp-q4",
                question_type=QuestionType.MULTIPLE_CHOICE,
                text="What is the default OSPF reference bandwidth?",
                options=[
                    ExamOption("a", "10 Mbps"),
                    ExamOption("b", "100 Mbps", is_correct=True),
                    ExamOption("c", "1 Gbps"),
                    ExamOption("d", "10 Gbps")
                ],
                correct_answer="b",
                explanation="Default reference bandwidth is 100 Mbps (10^8). Should be increased for modern networks.",
                topic="OSPF",
                difficulty=3
            )
        ]

        self._exams["ccnp-practice"] = PracticeExam(
            id="ccnp-practice",
            title="CCNP ENCOR Practice Exam",
            certification="CCNP",
            description="Practice exam for CCNP Enterprise Core (ENCOR).",
            questions=ccnp_questions,
            question_count=4,
            time_limit_minutes=20,
            passing_score=75.0
        )

        logger.info(f"Loaded {len(self._exams)} practice exams")

    def get_exam(self, exam_id: str) -> Optional[PracticeExam]:
        """Get exam by ID"""
        return self._exams.get(exam_id)

    def list_exams(self, certification: Optional[str] = None) -> List[PracticeExam]:
        """List all exams"""
        exams = list(self._exams.values())
        if certification:
            exams = [e for e in exams if e.certification.upper() == certification.upper()]
        return exams

    def start_exam(self, user_id: str, exam_id: str) -> Optional[ExamAttempt]:
        """Start an exam attempt"""
        exam = self.get_exam(exam_id)
        if not exam:
            return None

        self._attempt_counter += 1
        attempt_id = f"exam-{self._attempt_counter:05d}"

        attempt = ExamAttempt(
            id=attempt_id,
            user_id=user_id,
            exam_id=exam_id,
            questions=exam.get_questions(),
            time_remaining_seconds=exam.time_limit_minutes * 60
        )

        self._attempts[attempt_id] = attempt
        logger.info(f"Started exam attempt {attempt_id}")
        return attempt

    def submit_answer(
        self,
        attempt_id: str,
        question_id: str,
        answer: Any
    ) -> bool:
        """Submit an answer for a question"""
        attempt = self._attempts.get(attempt_id)
        if not attempt or attempt.is_complete:
            return False

        attempt.answers[question_id] = answer
        return True

    def complete_exam(self, attempt_id: str) -> Optional[ExamResult]:
        """Complete an exam and calculate results"""
        attempt = self._attempts.get(attempt_id)
        if not attempt:
            return None

        exam = self.get_exam(attempt.exam_id)
        if not exam:
            return None

        attempt.completed_at = datetime.now()

        # Calculate score
        points_earned = 0
        points_possible = 0
        correct_count = 0
        by_topic: Dict[str, Dict[str, int]] = {}
        question_results = []

        for question in attempt.questions:
            points_possible += question.points
            answer = attempt.answers.get(question.id)

            if answer is not None:
                is_correct, partial, feedback = question.check_answer(answer)
                earned = int(question.points * partial)
                points_earned += earned

                if is_correct:
                    correct_count += 1

                # Track by topic
                topic = question.topic or "General"
                if topic not in by_topic:
                    by_topic[topic] = {"correct": 0, "total": 0}
                by_topic[topic]["total"] += 1
                if is_correct:
                    by_topic[topic]["correct"] += 1

                question_results.append({
                    "question_id": question.id,
                    "correct": is_correct,
                    "points_earned": earned,
                    "topic": topic
                })
            else:
                question_results.append({
                    "question_id": question.id,
                    "correct": False,
                    "points_earned": 0,
                    "topic": question.topic or "General",
                    "skipped": True
                })

        score = (points_earned / points_possible * 100) if points_possible > 0 else 0
        duration = int((attempt.completed_at - attempt.started_at).total_seconds())

        result = ExamResult(
            attempt_id=attempt_id,
            exam_id=attempt.exam_id,
            user_id=attempt.user_id,
            score=score,
            points_earned=points_earned,
            points_possible=points_possible,
            passed=score >= exam.passing_score,
            correct_count=correct_count,
            incorrect_count=len(attempt.questions) - correct_count,
            duration_seconds=duration,
            by_topic=by_topic,
            question_results=question_results
        )

        # Store result
        if attempt.user_id not in self._results:
            self._results[attempt.user_id] = []
        self._results[attempt.user_id].append(result)

        return result

    def get_attempt(self, attempt_id: str) -> Optional[ExamAttempt]:
        """Get attempt by ID"""
        return self._attempts.get(attempt_id)

    def get_user_results(
        self,
        user_id: str,
        exam_id: Optional[str] = None
    ) -> List[ExamResult]:
        """Get results for a user"""
        results = self._results.get(user_id, [])
        if exam_id:
            results = [r for r in results if r.exam_id == exam_id]
        return results

    def get_statistics(self) -> Dict[str, Any]:
        """Get exam statistics"""
        total_exams = len(self._exams)
        total_attempts = len(self._attempts)
        all_results = [r for results in self._results.values() for r in results]

        passed = sum(1 for r in all_results if r.passed)
        avg_score = sum(r.score for r in all_results) / len(all_results) if all_results else 0

        return {
            "total_exams": total_exams,
            "total_attempts": total_attempts,
            "total_completions": len(all_results),
            "pass_rate": round((passed / len(all_results) * 100) if all_results else 0, 2),
            "average_score": round(avg_score, 2)
        }


# Global exam engine instance
_global_engine: Optional[ExamEngine] = None


def get_exam_engine() -> ExamEngine:
    """Get or create the global exam engine"""
    global _global_engine
    if _global_engine is None:
        _global_engine = ExamEngine()
    return _global_engine
