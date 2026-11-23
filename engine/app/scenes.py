from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Scene detection decodes the whole file. Past this length the transcript
# already gives us enough information to pick clips, so we skip the cost.
_MAX_SCENE_SCAN_SECONDS = 45 * 60


def detect_scenes(path: Path, *, duration: float, threshold: float = 27.0) -> list[dict[str, float]]:
    if duration > _MAX_SCENE_SCAN_SECONDS:
        logger.info("Video de %.0f s: se omite la deteccion de escenas.", duration)
        return []
    try:
        from scenedetect import ContentDetector, SceneManager, open_video
    except ImportError:
        logger.warning("scenedetect no esta instalado; se omite el analisis visual.")
        return []

    try:
        video = open_video(str(path))
        fps = float(video.frame_rate or 30.0)
        manager = SceneManager()
        manager.add_detector(
            ContentDetector(
                threshold=threshold,
                min_scene_len=max(1, int(round(fps * 0.7))),
            )
        )
        # Scene edges only guide clip boundaries. Sampling every third frame
        # cuts the expensive full-resolution scan without changing the
        # transcript-driven moment scoring or subtitle timing.
        manager.detect_scenes(video, frame_skip=2, show_progress=False)
        scene_list = manager.get_scene_list()
    except Exception as exc:  # keep the pipeline alive if visual analysis fails
        logger.warning("Deteccion de escenas fallida: %s", exc)
        return []

    scenes = [
        {"start": round(start.get_seconds(), 3), "end": round(end.get_seconds(), 3)}
        for start, end in scene_list
    ]
    logger.info("Detectadas %d escenas.", len(scenes))
    return scenes
