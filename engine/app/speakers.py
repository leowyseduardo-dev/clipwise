"""Anonymous visual speaker selection during timed speech, using local lip motion."""

import math
import cv2
import numpy as np


class SpeakerFocus:
    def __init__(self):
        self.previous = []
        self.streak = 0
        self.center = None

    def choose(self, frame, faces, speaking):
        current = []
        height, width = frame.shape[:2]
        for x, y, w, h, confidence in faces:
            left, right = max(0, int(x - w * 0.30)), min(width, int(x + w * 0.30))
            top, bottom = max(0, int(y - h * 0.24)), min(height, int(y + h * 0.41))
            if right - left < 5 or bottom - top < 5:
                continue
            gray = cv2.cvtColor(frame[top:bottom, left:right], cv2.COLOR_BGR2GRAY)
            patch = cv2.resize(gray, (24, 24), interpolation=cv2.INTER_AREA).astype(
                np.float32
            )
            patch -= patch.mean()
            prior = min(
                self.previous,
                key=lambda q: math.hypot(x - q[0], y - q[1]),
                default=None,
            )
            motion = 0
            if prior and math.hypot(x - prior[0], y - prior[1]) < max(w, h) * 0.4:
                delta = np.abs(patch - prior[2])
                motion = max(0, float(delta[15:23].mean() - 0.85 * delta[:9].mean()))
            current.append((x, y, patch, motion))
        self.previous = current
        ranked = sorted(current, key=lambda q: q[3], reverse=True)
        if (
            not speaking
            or len(ranked) < 2
            or ranked[0][3] < 4
            or ranked[0][3] < 1.5 * ranked[1][3]
        ):
            self.streak = 0
            return None
        x, y = ranked[0][:2]
        self.streak = (
            self.streak + 1
            if self.center and math.dist((x, y), self.center) < width * 0.09
            else 1
        )
        self.center = (x, y)
        return self.center if self.streak >= 2 else None
