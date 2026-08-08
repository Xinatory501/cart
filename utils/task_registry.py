from __future__ import annotations
import asyncio
import logging
import uuid
from datetime import datetime
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)

class TaskInfo:
    def __init__(self, name: str, correlation_id: str):
        self.id = str(uuid.uuid4())
        self.name = name
        self.correlation_id = correlation_id
        self.started_at = datetime.utcnow()
        self.status = 'running'  # running, done, failed, cancelled
        self.error: Optional[str] = None
        self.task: Optional[asyncio.Task] = None

class TaskRegistry:
    """
    WEB-12: Central registry for background tasks.
    Allows tracking, cancellation, and error reporting.
    """
    def __init__(self):
        self._tasks: Dict[str, TaskInfo] = {}
    
    def register(self, coro, name: str, correlation_id: str = None) -> TaskInfo:
        """Register and start a background coroutine."""
        info = TaskInfo(name, correlation_id or str(uuid.uuid4()))
        
        async def _wrapper():
            try:
                await coro
                info.status = 'done'
            except asyncio.CancelledError:
                info.status = 'cancelled'
                raise
            except Exception as e:
                info.status = 'failed'
                info.error = str(e)
                logger.error('Task %s [%s] failed: %s', name, info.id, e)
            finally:
                # Auto-cleanup after 5 minutes
                await asyncio.sleep(300)
                self._tasks.pop(info.id, None)
        
        info.task = asyncio.create_task(_wrapper())
        self._tasks[info.id] = info
        logger.debug('Task registered: %s [%s]', name, info.id)
        return info
    
    def cancel(self, task_id: str) -> bool:
        info = self._tasks.get(task_id)
        if info and info.task and not info.task.done():
            info.task.cancel()
            return True
        return False
    
    def list_running(self) -> list:
        return [
            {'id': t.id, 'name': t.name, 'status': t.status,
             'started': t.started_at.isoformat(), 'correlation': t.correlation_id}
            for t in self._tasks.values()
            if t.status == 'running'
        ]
    
    async def graceful_shutdown(self, timeout: float = 10.0) -> None:
        """Cancel all running tasks and wait."""
        running = [t for t in self._tasks.values() if t.task and not t.task.done()]
        for info in running:
            info.task.cancel()
        if running:
            await asyncio.gather(*[t.task for t in running], return_exceptions=True)
        logger.info('TaskRegistry shutdown: cancelled %d tasks', len(running))

# Global singleton
task_registry = TaskRegistry()
