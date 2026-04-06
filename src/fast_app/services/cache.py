"""Cache management for job application files."""

import hashlib
import json
import re
from pathlib import Path
from typing import Dict, Any, Optional, List


def sanitize_path_component(name: str) -> str:
    """Sanitize string for use as directory name."""
    name = name.strip()
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"[-\s]+", "-", name)
    return name[:50].strip("-") or "unknown"


def generate_job_id(url: str) -> str:
    """Generate unique job ID from URL hash."""
    return hashlib.md5(url.encode()).hexdigest()[:12]


class CacheManager:
    """Manages cached files for job applications."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir

    def _load_json(self, path: Path) -> Optional[Dict[str, Any]]:
        """Load JSON file if it exists."""
        if not path.exists():
            return None
        try:
            with open(path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    def _save_json(self, path: Path, data: Dict[str, Any]) -> None:
        """Save JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def get_job_dir(self, company: str, title: str, job_id: str, create: bool = False) -> Path:
        """Get or create job directory path."""
        company_dir = sanitize_path_component(company)
        title_dir = sanitize_path_component(title)

        job_dir = self.output_dir / company_dir / title_dir / job_id

        if create:
            job_dir.mkdir(parents=True, exist_ok=True)

        return job_dir

    def find_job_by_hash(self, job_id: str) -> Optional[Path]:
        """Find job directory by hash using depth-first search.

        Searches the entire directory tree for a directory with name matching
        the job_id hash that contains a job.json file.
        """
        if not self.output_dir.exists():
            return None

        def dfs_search(current_path: Path) -> Optional[Path]:
            """Recursive depth-first search for job_id directory."""
            try:
                for item in current_path.iterdir():
                    if not item.is_dir():
                        continue

                    if item.name == job_id:
                        job_json = item / "job.json"
                        if job_json.exists():
                            return item

                    result = dfs_search(item)
                    if result:
                        return result
            except PermissionError:
                pass

            return None

        return dfs_search(self.output_dir)

    def has_cached_job(self, job_url: str) -> Optional[Path]:
        """Find cached job by URL hash."""
        job_id = generate_job_id(job_url)
        return self.find_job_by_hash(job_id)

    def get_cached_job(self, job_dir: Path) -> Optional[Dict[str, Any]]:
        """Load job data from cache."""
        return self._load_json(job_dir / "job.json")

    def save_job(self, job_dir: Path, job_data: Dict[str, Any]) -> None:
        """Save job data to cache."""
        self._save_json(job_dir / "job.json", job_data)

    def get_cached_questions(self, job_dir: Path) -> Optional[List[str]]:
        """Load questions from cache."""
        data = self._load_json(job_dir / "questions.json")
        return data.get("questions") if data else None

    def save_questions(self, job_dir: Path, questions: List[str]) -> None:
        """Save questions to cache."""
        self._save_json(job_dir / "questions.json", {"questions": questions})

    def get_cached_answers(self, job_dir: Path) -> Optional[List[str]]:
        """Load answers from cache."""
        data = self._load_json(job_dir / "answers.json")
        return data.get("answers") if data else None

    def save_answers(self, job_dir: Path, answers: List[str]) -> None:
        """Save answers to cache."""
        self._save_json(job_dir / "answers.json", {"answers": answers})

    def get_cached_resume(self, job_dir: Path) -> Optional[Dict[str, Any]]:
        """Load resume data from cache."""
        return self._load_json(job_dir / "resume.json")

    def save_resume(self, job_dir: Path, resume_data: Dict[str, Any]) -> None:
        """Save resume data to cache."""
        self._save_json(job_dir / "resume.json", resume_data)

    def get_cached_reactive_resume(self, job_dir: Path) -> Optional[Dict[str, Any]]:
        """Load reactive resume metadata from cache."""
        return self._load_json(job_dir / "reactive_resume.json")

    def save_reactive_resume(self, job_dir: Path, reactive_data: Dict[str, Any]) -> None:
        """Save reactive resume metadata to cache."""
        self._save_json(job_dir / "reactive_resume.json", reactive_data)

    def get_cached_reactive_cover_letter(self, job_dir: Path) -> Optional[Dict[str, Any]]:
        """Load reactive cover letter metadata from cache."""
        return self._load_json(job_dir / "reactive_cover_letter.json")

    def save_reactive_cover_letter(self, job_dir: Path, reactive_data: Dict[str, Any]) -> None:
        """Save reactive cover letter metadata to cache."""
        self._save_json(job_dir / "reactive_cover_letter.json", reactive_data)

    def get_cached_cover_letter(self, job_dir: Path) -> Optional[Dict[str, Any]]:
        """Load cover letter data from cache."""
        return self._load_json(job_dir / "cover_letter.json")

    def save_cover_letter(self, job_dir: Path, cover_letter_data: Dict[str, Any]) -> None:
        """Save cover letter data to cache."""
        self._save_json(job_dir / "cover_letter.json", cover_letter_data)
