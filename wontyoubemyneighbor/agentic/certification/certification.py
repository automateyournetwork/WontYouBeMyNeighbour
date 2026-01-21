"""
Certification Module - Certification tracking and progress

Provides:
- Certification definitions
- Progress tracking toward certification
- Skill validation
- Recommendations
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any

logger = logging.getLogger("CertificationManager")


class CertificationLevel(str, Enum):
    """Certification levels"""
    ASSOCIATE = "associate"    # CCNA
    PROFESSIONAL = "professional"  # CCNP
    EXPERT = "expert"          # CCIE
    SPECIALIST = "specialist"  # Specialty certifications


class CertificationTrack(str, Enum):
    """Certification tracks"""
    ENTERPRISE = "enterprise"
    DATA_CENTER = "data_center"
    SERVICE_PROVIDER = "service_provider"
    SECURITY = "security"
    COLLABORATION = "collaboration"
    DEVNET = "devnet"


@dataclass
class SkillRequirement:
    """A skill requirement for certification"""
    skill: str
    weight: int  # 1-10
    topic: str
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill": self.skill,
            "weight": self.weight,
            "topic": self.topic,
            "description": self.description
        }


@dataclass
class Certification:
    """
    A certification definition

    Attributes:
        id: Certification identifier
        name: Certification name (e.g., "CCNA")
        full_name: Full name
        level: Certification level
        track: Certification track
        description: Description
        exam_codes: Required exam codes
        skills: Required skills
        prerequisites: Prerequisite certifications
        validity_years: How long cert is valid
        labs: Associated lab IDs
        exams: Associated practice exam IDs
    """
    id: str
    name: str
    full_name: str
    level: CertificationLevel
    track: CertificationTrack
    description: str = ""
    exam_codes: List[str] = field(default_factory=list)
    skills: List[SkillRequirement] = field(default_factory=list)
    prerequisites: List[str] = field(default_factory=list)
    validity_years: int = 3
    labs: List[str] = field(default_factory=list)
    exams: List[str] = field(default_factory=list)

    @property
    def total_skill_weight(self) -> int:
        return sum(s.weight for s in self.skills)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "full_name": self.full_name,
            "level": self.level.value,
            "track": self.track.value,
            "description": self.description,
            "exam_codes": self.exam_codes,
            "skills": [s.to_dict() for s in self.skills],
            "prerequisites": self.prerequisites,
            "validity_years": self.validity_years,
            "labs": self.labs,
            "exams": self.exams
        }


@dataclass
class SkillScore:
    """Score for a specific skill"""
    skill: str
    score: float  # 0-100
    assessments: int
    last_assessed: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill": self.skill,
            "score": round(self.score, 2),
            "assessments": self.assessments,
            "last_assessed": self.last_assessed.isoformat() if self.last_assessed else None
        }


@dataclass
class CertificationProgress:
    """
    Progress toward a certification

    Attributes:
        user_id: User identifier
        certification_id: Certification identifier
        skill_scores: Scores by skill
        labs_completed: Completed lab IDs
        exams_passed: Passed practice exam IDs
        overall_readiness: Overall readiness percentage
        started_at: When user started
        last_activity: Last activity timestamp
        recommendations: Recommended next steps
    """
    user_id: str
    certification_id: str
    skill_scores: Dict[str, SkillScore] = field(default_factory=dict)
    labs_completed: List[str] = field(default_factory=list)
    exams_passed: List[str] = field(default_factory=list)
    overall_readiness: float = 0.0
    started_at: datetime = field(default_factory=datetime.now)
    last_activity: datetime = field(default_factory=datetime.now)
    recommendations: List[str] = field(default_factory=list)

    def update_skill(self, skill: str, score: float):
        """Update a skill score"""
        if skill not in self.skill_scores:
            self.skill_scores[skill] = SkillScore(skill=skill, score=score, assessments=1)
        else:
            existing = self.skill_scores[skill]
            # Weighted average favoring recent scores
            existing.score = (existing.score * 0.3) + (score * 0.7)
            existing.assessments += 1
        self.skill_scores[skill].last_assessed = datetime.now()
        self.last_activity = datetime.now()

    def add_lab_completion(self, lab_id: str):
        """Record lab completion"""
        if lab_id not in self.labs_completed:
            self.labs_completed.append(lab_id)
            self.last_activity = datetime.now()

    def add_exam_pass(self, exam_id: str):
        """Record exam pass"""
        if exam_id not in self.exams_passed:
            self.exams_passed.append(exam_id)
            self.last_activity = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "certification_id": self.certification_id,
            "skill_scores": {k: v.to_dict() for k, v in self.skill_scores.items()},
            "labs_completed": self.labs_completed,
            "exams_passed": self.exams_passed,
            "overall_readiness": round(self.overall_readiness, 2),
            "started_at": self.started_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "recommendations": self.recommendations
        }


class CertificationManager:
    """
    Manages certifications and user progress
    """

    def __init__(self):
        """Initialize with built-in certifications"""
        self._certifications: Dict[str, Certification] = {}
        self._progress: Dict[str, Dict[str, CertificationProgress]] = {}  # user_id -> cert_id -> progress
        self._load_builtin_certifications()

    def _load_builtin_certifications(self):
        """Load built-in certification definitions"""
        # CCNA
        self._certifications["ccna"] = Certification(
            id="ccna",
            name="CCNA",
            full_name="Cisco Certified Network Associate",
            level=CertificationLevel.ASSOCIATE,
            track=CertificationTrack.ENTERPRISE,
            description="Foundation-level certification covering networking fundamentals.",
            exam_codes=["200-301"],
            skills=[
                SkillRequirement("IP Addressing", 8, "Fundamentals", "IPv4 and IPv6 addressing"),
                SkillRequirement("Routing Concepts", 9, "Routing", "Static and dynamic routing"),
                SkillRequirement("OSPF", 7, "Routing", "Single-area OSPF"),
                SkillRequirement("Switching", 8, "Switching", "VLANs, STP, EtherChannel"),
                SkillRequirement("Network Security", 6, "Security", "Basic security concepts"),
                SkillRequirement("Automation", 5, "Automation", "REST APIs, Ansible basics")
            ],
            validity_years=3,
            labs=["ccna-ospf-basics", "ccna-bgp-basics", "ccna-troubleshoot-ospf"],
            exams=["ccna-practice"]
        )

        # CCNP Enterprise
        self._certifications["ccnp-enterprise"] = Certification(
            id="ccnp-enterprise",
            name="CCNP Enterprise",
            full_name="Cisco Certified Network Professional - Enterprise",
            level=CertificationLevel.PROFESSIONAL,
            track=CertificationTrack.ENTERPRISE,
            description="Professional-level certification for enterprise network infrastructure.",
            exam_codes=["350-401", "300-4xx"],
            prerequisites=["ccna"],
            skills=[
                SkillRequirement("Advanced OSPF", 9, "Routing", "Multi-area OSPF, tuning"),
                SkillRequirement("BGP", 10, "Routing", "eBGP/iBGP, path manipulation"),
                SkillRequirement("MPLS", 7, "WAN", "MPLS fundamentals"),
                SkillRequirement("SD-WAN", 8, "WAN", "Cisco SD-WAN"),
                SkillRequirement("Wireless", 6, "Wireless", "Enterprise wireless"),
                SkillRequirement("QoS", 7, "QoS", "QoS models and configuration"),
                SkillRequirement("Automation", 8, "Automation", "Python, NETCONF, RESTCONF")
            ],
            validity_years=3,
            labs=["ccnp-ospf-advanced", "ccnp-bgp-policy"],
            exams=["ccnp-practice"]
        )

        # CCNP Data Center
        self._certifications["ccnp-datacenter"] = Certification(
            id="ccnp-datacenter",
            name="CCNP Data Center",
            full_name="Cisco Certified Network Professional - Data Center",
            level=CertificationLevel.PROFESSIONAL,
            track=CertificationTrack.DATA_CENTER,
            description="Professional certification for data center networks.",
            exam_codes=["350-601", "300-6xx"],
            prerequisites=["ccna"],
            skills=[
                SkillRequirement("VXLAN", 9, "Overlay", "VXLAN fabric"),
                SkillRequirement("EVPN", 9, "Overlay", "EVPN control plane"),
                SkillRequirement("ACI", 8, "ACI", "Cisco ACI fabric"),
                SkillRequirement("SAN", 7, "Storage", "Fibre Channel, FCoE"),
                SkillRequirement("UCS", 6, "Compute", "Cisco UCS management")
            ],
            validity_years=3,
            labs=["vxlan-evpn-intro"],
            exams=[]
        )

        # CCIE Enterprise
        self._certifications["ccie-enterprise"] = Certification(
            id="ccie-enterprise",
            name="CCIE Enterprise Infrastructure",
            full_name="Cisco Certified Internetwork Expert - Enterprise Infrastructure",
            level=CertificationLevel.EXPERT,
            track=CertificationTrack.ENTERPRISE,
            description="Expert-level certification for complex enterprise networks.",
            exam_codes=["350-401", "Lab Exam"],
            prerequisites=["ccnp-enterprise"],
            skills=[
                SkillRequirement("Complex Routing", 10, "Routing", "Complex routing scenarios"),
                SkillRequirement("Troubleshooting", 10, "Troubleshooting", "Expert troubleshooting"),
                SkillRequirement("Network Design", 9, "Design", "Enterprise network design"),
                SkillRequirement("Automation", 9, "Automation", "Advanced automation")
            ],
            validity_years=3,
            labs=[],
            exams=[]
        )

        logger.info(f"Loaded {len(self._certifications)} certifications")

    def get_certification(self, cert_id: str) -> Optional[Certification]:
        """Get certification by ID"""
        return self._certifications.get(cert_id)

    def list_certifications(
        self,
        level: Optional[CertificationLevel] = None,
        track: Optional[CertificationTrack] = None
    ) -> List[Certification]:
        """List certifications with optional filters"""
        certs = list(self._certifications.values())

        if level:
            certs = [c for c in certs if c.level == level]

        if track:
            certs = [c for c in certs if c.track == track]

        return certs

    def start_certification(self, user_id: str, cert_id: str) -> Optional[CertificationProgress]:
        """Start tracking progress toward a certification"""
        cert = self.get_certification(cert_id)
        if not cert:
            return None

        if user_id not in self._progress:
            self._progress[user_id] = {}

        if cert_id not in self._progress[user_id]:
            progress = CertificationProgress(
                user_id=user_id,
                certification_id=cert_id
            )
            # Initialize skill scores
            for skill in cert.skills:
                progress.skill_scores[skill.skill] = SkillScore(
                    skill=skill.skill,
                    score=0.0,
                    assessments=0
                )
            self._progress[user_id][cert_id] = progress

        return self._progress[user_id][cert_id]

    def get_progress(self, user_id: str, cert_id: str) -> Optional[CertificationProgress]:
        """Get user's progress toward a certification"""
        return self._progress.get(user_id, {}).get(cert_id)

    def get_user_progress(self, user_id: str) -> List[CertificationProgress]:
        """Get all certification progress for a user"""
        return list(self._progress.get(user_id, {}).values())

    def update_skill_score(
        self,
        user_id: str,
        cert_id: str,
        skill: str,
        score: float
    ) -> Optional[CertificationProgress]:
        """Update a skill score for a user"""
        progress = self.get_progress(user_id, cert_id)
        if not progress:
            progress = self.start_certification(user_id, cert_id)
            if not progress:
                return None

        progress.update_skill(skill, score)
        self._calculate_readiness(progress)
        return progress

    def record_lab_completion(
        self,
        user_id: str,
        cert_id: str,
        lab_id: str,
        passed: bool
    ) -> Optional[CertificationProgress]:
        """Record a lab completion"""
        if not passed:
            return self.get_progress(user_id, cert_id)

        progress = self.get_progress(user_id, cert_id)
        if not progress:
            progress = self.start_certification(user_id, cert_id)
            if not progress:
                return None

        progress.add_lab_completion(lab_id)
        self._calculate_readiness(progress)
        return progress

    def record_exam_completion(
        self,
        user_id: str,
        cert_id: str,
        exam_id: str,
        passed: bool,
        score: float
    ) -> Optional[CertificationProgress]:
        """Record a practice exam completion"""
        progress = self.get_progress(user_id, cert_id)
        if not progress:
            progress = self.start_certification(user_id, cert_id)
            if not progress:
                return None

        if passed:
            progress.add_exam_pass(exam_id)

        # Update related skills based on exam score
        # This is a simplified approach
        cert = self.get_certification(cert_id)
        if cert:
            for skill in cert.skills:
                current = progress.skill_scores.get(skill.skill)
                if current and current.assessments < 5:  # Don't over-weight exam scores
                    progress.update_skill(skill.skill, score)

        self._calculate_readiness(progress)
        return progress

    def _calculate_readiness(self, progress: CertificationProgress):
        """Calculate overall certification readiness"""
        cert = self.get_certification(progress.certification_id)
        if not cert:
            return

        total_weight = cert.total_skill_weight
        weighted_score = 0

        for skill in cert.skills:
            skill_score = progress.skill_scores.get(skill.skill)
            if skill_score:
                weighted_score += (skill_score.score / 100) * skill.weight

        # Factor in labs and exams
        lab_factor = len(progress.labs_completed) / len(cert.labs) if cert.labs else 1.0
        exam_factor = len(progress.exams_passed) / len(cert.exams) if cert.exams else 1.0

        # Weighted readiness calculation
        skill_readiness = (weighted_score / total_weight) * 100 if total_weight > 0 else 0
        progress.overall_readiness = (skill_readiness * 0.6) + (lab_factor * 20) + (exam_factor * 20)

        # Generate recommendations
        progress.recommendations = self._generate_recommendations(progress, cert)

    def _generate_recommendations(
        self,
        progress: CertificationProgress,
        cert: Certification
    ) -> List[str]:
        """Generate study recommendations"""
        recommendations = []

        # Find weak skills
        weak_skills = []
        for skill in cert.skills:
            skill_score = progress.skill_scores.get(skill.skill)
            if skill_score and skill_score.score < 70:
                weak_skills.append((skill.skill, skill_score.score, skill.weight))

        # Sort by importance (weight * deficit)
        weak_skills.sort(key=lambda x: x[2] * (100 - x[1]), reverse=True)

        for skill, score, _ in weak_skills[:3]:
            recommendations.append(f"Focus on {skill} (current score: {score:.0f}%)")

        # Recommend labs
        incomplete_labs = [l for l in cert.labs if l not in progress.labs_completed]
        if incomplete_labs:
            recommendations.append(f"Complete lab: {incomplete_labs[0]}")

        # Recommend practice exams
        if not progress.exams_passed and cert.exams:
            recommendations.append(f"Take practice exam: {cert.exams[0]}")

        if progress.overall_readiness >= 80:
            recommendations.append("You may be ready to schedule your certification exam!")

        return recommendations

    def get_statistics(self) -> Dict[str, Any]:
        """Get certification statistics"""
        total_certs = len(self._certifications)
        total_users = len(self._progress)
        total_progress = sum(len(p) for p in self._progress.values())

        by_level = {}
        for cert in self._certifications.values():
            level = cert.level.value
            by_level[level] = by_level.get(level, 0) + 1

        return {
            "total_certifications": total_certs,
            "by_level": by_level,
            "users_tracking": total_users,
            "total_progress_records": total_progress
        }


# Global certification manager instance
_global_manager: Optional[CertificationManager] = None


def get_certification_manager() -> CertificationManager:
    """Get or create the global certification manager"""
    global _global_manager
    if _global_manager is None:
        _global_manager = CertificationManager()
    return _global_manager
