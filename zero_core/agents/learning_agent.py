"""Learning Agent for ZERO (Milestone M18).

Tracks personalized learning progress, weak areas, curriculum roadmaps, and revision quizzes.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class LearningTopic:
    """Represents a tracked skill or learning topic."""
    topic_id: str
    title: str
    category: str
    mastery_score: float = 0.0  # 0.0 to 1.0
    quizzes_completed: int = 0
    weak_areas: List[str] = field(default_factory=list)
    last_reviewed: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class LearningAgent:
    """Native Learning Agent managing learning progress, revision quizzes, and study plans."""

    def __init__(self):
        self._topics: Dict[str, LearningTopic] = {}

    def track_topic(self, topic_id: str, title: str, category: str, score: float, weak_areas: Optional[List[str]] = None) -> LearningTopic:
        """Records or updates progress on a learning topic."""
        topic = self._topics.get(topic_id)
        if topic is None:
            topic = LearningTopic(
                topic_id=topic_id,
                title=title,
                category=category,
                mastery_score=max(0.0, min(1.0, score)),
                weak_areas=weak_areas or [],
            )
            self._topics[topic_id] = topic
        else:
            topic.mastery_score = max(0.0, min(1.0, score))
            if weak_areas:
                topic.weak_areas = weak_areas
            topic.last_reviewed = datetime.now(timezone.utc).isoformat()
        return topic

    def generate_quiz(self, topic_id: str) -> Dict[str, Any]:
        """Generates a diagnostic revision quiz for a topic."""
        topic = self._topics.get(topic_id)
        title = topic.title if topic else topic_id
        return {
            "quiz_id": f"quiz_{uuid.uuid4().hex[:8]}",
            "topic": title,
            "questions": [
                {
                    "q": f"What is the primary architectural principle of {title} in ZERO?",
                    "options": ["Monolithic coupling", "Decoupled state machines", "Hardcoded routing"],
                    "correct": 1,
                },
                {
                    "q": "How are high-risk mutations handled?",
                    "options": ["Auto-approved", "Human-in-the-loop approval gate", "Silently dropped"],
                    "correct": 1,
                },
            ],
        }

    def generate_learning_plan(self) -> str:
        """Generates a study roadmap based on current mastery levels."""
        if not self._topics:
            return "Learning Agent: No topics currently tracked. Start learning a new module!"

        lines = ["# 🎓 Personal Learning & Mastery Plan", ""]
        for t in self._topics.values():
            pct = int(t.mastery_score * 100)
            status = "🟢 Proficient" if pct >= 80 else ("🟡 In Progress" if pct >= 50 else "🔴 Focus Area")
            lines.append(f"### {t.title} ({t.category}) — {pct}% Mastery [{status}]")
            if t.weak_areas:
                lines.append(f"  - **Areas to strengthen**: {', '.join(t.weak_areas)}")
            lines.append(f"  - *Last reviewed*: {t.last_reviewed}")
        return "\n".join(lines)


# Global singleton instance
DEFAULT_LEARNING_AGENT = LearningAgent()
