"""State management for webapp job processing."""

import json
from enum import Enum
from pathlib import Path
from typing import Any


class JobState(str, Enum):
    """Job processing states."""

    IDLE = "idle"
    PROCESSING = "processing"
    WAITING_QUESTIONS = "waiting_questions"
    COMPLETE = "complete"
    ERROR = "error"


class StateManager:
    """Manages persistent state for job processing."""

    def __init__(self, state_dir: Path | None = None):
        self.state_dir = state_dir or Path.home() / ".fast-app"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir = self.state_dir / "logs"
        self.logs_dir.mkdir(exist_ok=True)
        self.state_file = self.state_dir / "state.json"

        # State fields
        self.state: JobState = JobState.IDLE
        self.job_id: str | None = None
        self.url: str | None = None
        self.company: str | None = None
        self.title: str | None = None
        self.flags: dict[str, bool] = {}
        self.current_step: str = ""
        self.progress: float = 0.0

        # Question tracking
        self.questions: list[str] = []
        self.answers: list[str] = []
        self.current_question_index: int = 0

        # Results
        self.resume_url: str | None = None
        self.cover_letter_url: str | None = None
        self.error_message: str | None = None

        # Log file
        self.log_file: Path | None = None

        # Load existing state
        self.load()

    def load(self) -> bool:
        """Load state from disk. Returns True if state loaded."""
        if not self.state_file.exists():
            return False

        try:
            with open(self.state_file) as f:
                data = json.load(f)

            self.state = JobState(data.get("state", JobState.IDLE))
            self.job_id = data.get("job_id")
            self.url = data.get("url")
            self.company = data.get("company")
            self.title = data.get("title")
            self.flags = data.get("flags", {})
            self.current_step = data.get("current_step", "")
            self.progress = data.get("progress", 0.0)
            self.questions = data.get("questions", [])
            self.answers = data.get("answers", [])
            self.current_question_index = data.get("current_question_index", 0)
            self.resume_url = data.get("resume_url")
            self.cover_letter_url = data.get("cover_letter_url")
            self.error_message = data.get("error_message")

            # Setup log file
            if self.job_id:
                self.log_file = self.logs_dir / f"{self.job_id}.log"

            return True
        except (json.JSONDecodeError, KeyError, ValueError):
            return False

    def save(self) -> None:
        """Persist state to disk."""
        data = {
            "state": self.state.value,
            "job_id": self.job_id,
            "url": self.url,
            "company": self.company,
            "title": self.title,
            "flags": self.flags,
            "current_step": self.current_step,
            "progress": self.progress,
            "questions": self.questions,
            "answers": self.answers,
            "current_question_index": self.current_question_index,
            "resume_url": self.resume_url,
            "cover_letter_url": self.cover_letter_url,
            "error_message": self.error_message,
        }

        with open(self.state_file, "w") as f:
            json.dump(data, f, indent=2)

    def reset(self) -> None:
        """Reset state to idle."""
        self.state = JobState.IDLE
        self.job_id = None
        self.url = None
        self.company = None
        self.title = None
        self.flags = {}
        self.current_step = ""
        self.progress = 0.0
        self.questions = []
        self.answers = []
        self.current_question_index = 0
        self.resume_url = None
        self.cover_letter_url = None
        self.error_message = None
        self.log_file = None
        self.save()

    def start_job(self, job_id: str, url: str, flags: dict[str, bool]) -> None:
        """Initialize a new job."""
        self.state = JobState.PROCESSING
        self.job_id = job_id
        self.url = url
        self.flags = flags
        self.progress = 0.0
        self.current_step = "Initializing"
        self.log_file = self.logs_dir / f"{job_id}.log"
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self.save()

    def update_progress(self, step: str, progress: float) -> None:
        """Update current step and progress."""
        self.current_step = step
        self.progress = progress
        self.save()

    def set_waiting_questions(self, questions: list[str]) -> None:
        """Transition to waiting_questions state."""
        self.state = JobState.WAITING_QUESTIONS
        self.questions = questions
        self.answers = []
        self.current_question_index = 0
        self.current_step = f"Question 1 of {len(questions)}"
        self.progress = 0.4
        self.save()

    def submit_answer(self, answer: str) -> bool:
        """Submit an answer. Returns True if all questions answered."""
        self.answers.append(answer)
        self.current_question_index += 1

        if self.current_question_index >= len(self.questions):
            # All questions answered
            self.state = JobState.PROCESSING
            self.current_step = "Generating resume"
            self.progress = 0.5
            self.save()
            return True
        else:
            # More questions remaining
            self.current_step = (
                f"Question {self.current_question_index + 1} of {len(self.questions)}"
            )
            self.save()
            return False

    def set_complete(self, resume_url: str, cover_letter_url: str | None) -> None:
        """Mark job as complete."""
        self.state = JobState.COMPLETE
        self.progress = 1.0
        self.current_step = "Complete"
        self.resume_url = resume_url
        self.cover_letter_url = cover_letter_url
        self.save()

    def set_error(self, error_message: str) -> None:
        """Mark job as error."""
        self.state = JobState.ERROR
        self.error_message = error_message
        self.save()

    def to_dict(self) -> dict[str, Any]:
        """Convert state to dictionary for API responses."""
        return {
            "state": self.state.value,
            "job_id": self.job_id,
            "url": self.url,
            "company": self.company,
            "title": self.title,
            "current_step": self.current_step,
            "progress": self.progress,
            "questions_count": len(self.questions),
            "questions_answered": len(self.answers),
            "current_question_index": self.current_question_index,
            "resume_url": self.resume_url,
            "cover_letter_url": self.cover_letter_url,
            "error": self.error_message,
        }

    def append_log(self, message: str) -> None:
        """Append a log message to the log file."""
        if self.log_file:
            from datetime import datetime

            timestamp = datetime.now().isoformat()
            with open(self.log_file, "a") as f:
                f.write(f"{timestamp} {message}\n")

    def is_active(self) -> bool:
        """Check if there's an active job (not idle, complete, or error)."""
        return self.state in (JobState.PROCESSING, JobState.WAITING_QUESTIONS)


# Global state manager instance
state_manager = StateManager()
