"""
Certification Prep Module

Provides certification preparation features:
- Lab scenarios for CCNA/CCNP/CCIE
- Practice exams
- Skill validation
- Progress tracking toward certification
"""

from .lab import (
    Lab,
    LabTask,
    LabDifficulty,
    LabStatus,
    LabManager,
    get_lab_manager
)

from .exam import (
    PracticeExam,
    ExamQuestion,
    ExamAttempt,
    ExamResult,
    ExamEngine,
    get_exam_engine
)

from .certification import (
    Certification,
    CertificationLevel,
    CertificationTrack,
    CertificationProgress,
    CertificationManager,
    get_certification_manager
)

__all__ = [
    # Lab
    "Lab",
    "LabTask",
    "LabDifficulty",
    "LabStatus",
    "LabManager",
    "get_lab_manager",
    # Exam
    "PracticeExam",
    "ExamQuestion",
    "ExamAttempt",
    "ExamResult",
    "ExamEngine",
    "get_exam_engine",
    # Certification
    "Certification",
    "CertificationLevel",
    "CertificationTrack",
    "CertificationProgress",
    "CertificationManager",
    "get_certification_manager"
]
