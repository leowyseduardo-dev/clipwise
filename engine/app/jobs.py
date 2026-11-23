from __future__ import annotations

import logging
import queue
import threading

from . import db, pipeline

logger = logging.getLogger(__name__)

_queue: "queue.Queue[tuple[str, str]]" = queue.Queue()
_started = False
_start_lock = threading.Lock()


def _worker_loop() -> None:
    while True:
        kind, identifier = _queue.get()
        try:
            if kind == "job":
                pipeline.process_job(identifier)
            elif kind == "clip":
                pipeline.process_clip_render(identifier)
        except Exception:
            logger.exception("Error no controlado procesando %s %s", kind, identifier)
        finally:
            _queue.task_done()


def start_worker() -> None:
    global _started
    with _start_lock:
        if _started:
            return
        db.init_db()
        stale = db.reset_stale_jobs()
        if stale:
            logger.warning("Se marcaron %d trabajos interrumpidos como fallidos.", stale)
        thread = threading.Thread(target=_worker_loop, daemon=True, name="Clipwise-worker")
        thread.start()
        _started = True
        for clip_id in db.queued_clip_ids():
            clip = db.get_clip(clip_id)
            if not clip:
                continue
            job = db.get_job(clip["job_id"])
            if job and job["status"] in ("ready", "failed"):
                _queue.put(("clip", clip_id))
        resumed = 0
        for clip_id in db.stale_clip_ids():
            clip = db.get_clip(clip_id)
            if not clip:
                continue
            job = db.get_job(clip["job_id"])
            if job and job["status"] in ("ready", "failed"):
                db.update_clip(clip_id, status="queued", error=None)
                _queue.put(("clip", clip_id))
                resumed += 1
        if resumed:
            logger.info(
                "Se re-encolaron %d clips interrumpidos por un reinicio.",
                resumed,
            )
        logger.info("Worker de Clipwise iniciado.")


def enqueue_job(job_id: str) -> None:
    start_worker()
    _queue.put(("job", job_id))


def enqueue_clip(clip_id: str) -> None:
    start_worker()
    _queue.put(("clip", clip_id))
