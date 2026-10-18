"""Small lifecycle coordinator for durable asynchronous archive operations."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

_LOGGER = logging.getLogger(__name__)


class ArchiveTaskQueue:
    """Track archive tasks, consume failures, and drain them before SQLite closes."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[Any]] = set()
        self._failures: list[BaseException] = []

    def create(self, coroutine: Coroutine[Any, Any, Any], *, name: str) -> asyncio.Task[Any]:
        return self.track(asyncio.create_task(coroutine, name=name))

    def track(self, task: asyncio.Task[Any]) -> asyncio.Task[Any]:
        """Track a task created by Home Assistant or asyncio."""

        self._tasks.add(task)
        task.add_done_callback(self._completed)
        return task

    def _completed(self, task: asyncio.Task[Any]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        try:
            task.result()
        except Exception as err:
            self._failures.append(err)
            _LOGGER.exception("Archive task failed: %s", task.get_name())

    async def cancel_and_wait(self, task: asyncio.Task[Any] | None) -> None:
        """Cancel a long-running producer and observe its completion."""

        if task is None or task.done():
            return
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    async def drain(self) -> tuple[BaseException, ...]:
        """Wait until all currently queued durable operations have finished."""

        while self._tasks:
            tasks = tuple(self._tasks)
            await asyncio.gather(*tasks, return_exceptions=True)
        failures = tuple(self._failures)
        self._failures.clear()
        return failures
