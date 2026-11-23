from contextvars import ContextVar
from contextlib import closing, contextmanager
import logging
import sqlite3
from . import db

project = ContextVar("metered_project", default=None)


@contextmanager
def measuring(job_id):
    token = project.set(job_id)
    try:
        yield
    finally:
        project.reset(token)


def record(model, *, job_id=None, calls=0, cached=0, usage=None, seconds=0):
    key = job_id or project.get()
    if not key:
        return
    usage = usage if isinstance(usage, dict) else {}
    try:
        with closing(db._connect()) as conn, conn:
            conn.execute(
                """INSERT INTO studio_usage VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(job_id,model) DO UPDATE SET
                calls=calls+excluded.calls,cached=cached+excluded.cached,prompt=prompt+excluded.prompt,
                completion=completion+excluded.completion,metered=metered+excluded.metered,seconds=seconds+excluded.seconds""",
                (
                    key,
                    model,
                    calls,
                    cached,
                    int(usage.get("prompt_tokens") or 0),
                    int(usage.get("completion_tokens") or 0),
                    int("prompt_tokens" in usage and "completion_tokens" in usage),
                    seconds,
                ),
            )
    except (sqlite3.Error, TypeError, ValueError):
        logging.getLogger(__name__).warning(
            "No se pudo registrar el consumo del proyecto."
        )
