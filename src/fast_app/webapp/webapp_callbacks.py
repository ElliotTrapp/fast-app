"""Webapp-specific pipeline callbacks using StateManager and WebSocket broadcast."""

import asyncio

from ..log import logger


class WebappCallbacks:
    """Pipeline callbacks for webapp (async + WebSocket) I/O."""

    def __init__(self, state, broadcast_callback):
        self.state = state
        self.broadcast = broadcast_callback

    async def on_state_change(self, old_state: str, new_state: str) -> None:
        await self.broadcast(
            {
                "type": "state_change",
                "old_state": old_state,
                "new_state": new_state,
            }
        )

    async def on_progress(self, step: str, progress: float) -> None:
        self.state.update_progress(step, progress)
        from .log_stream import log_broadcaster

        await log_broadcaster.broadcast_progress(step, progress)

    def on_job_extracted(self, job_title: str, company: str) -> None:
        logger.success(f"Found: {job_title} at {company}")
        self.state.company = company
        self.state.title = job_title
        self.state.save()

    def on_cache_hit(self, item: str, path: str) -> None:
        logger.cache_hit(item, path)

    def on_cache_save(self, item: str, path: str) -> None:
        logger.cache_save(item, path)

    async def collect_answers(self, questions: list[str]) -> list[str]:
        from .state import JobState

        self.state.set_waiting_questions(questions)
        await self.broadcast(
            {
                "type": "state_change",
                "old_state": "processing",
                "new_state": "waiting_questions",
            }
        )

        while self.state.state == JobState.WAITING_QUESTIONS:
            await asyncio.sleep(0.5)

        answers = self.state.answers

        await self.broadcast(
            {
                "type": "state_change",
                "old_state": "waiting_questions",
                "new_state": "processing",
            }
        )

        return answers

    def review_facts(self, facts: list) -> list | None:
        return facts

    def raise_already_exists(self, item_type: str, identifier: str) -> None:
        raise ValueError(f"{identifier} already exists. Use --overwrite-resume to replace.")
