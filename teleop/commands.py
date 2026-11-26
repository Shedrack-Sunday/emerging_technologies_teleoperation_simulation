"""Command types sent from the operator to the robot."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class VelocityCommand:
    """Desired velocity of Int-Ball, expressed in its BODY frame.

    vx: forward (camera direction)   [m/s]
    vy: left                         [m/s]
    vz: up                           [m/s]
    wx: roll rate  (about body x)    [rad/s]   (roll is auto-levelled on board)
    wy: pitch rate (about body y)    [rad/s]   positive = nose DOWN (right-hand rule)
    wz: yaw rate   (about body z)    [rad/s]   positive = turn LEFT
    """
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0
    wx: float = 0.0
    wy: float = 0.0
    wz: float = 0.0

    @property
    def linear(self) -> np.ndarray:
        return np.array([self.vx, self.vy, self.vz])

    @property
    def angular(self) -> np.ndarray:
        return np.array([self.wx, self.wy, self.wz])

    def is_zero(self) -> bool:
        return not (np.any(self.linear) or np.any(self.angular))

    def to_json(self) -> dict:
        return {k: round(float(getattr(self, k)), 4) for k in ("vx", "vy", "vz", "wx", "wy", "wz")}

    @classmethod
    def from_json(cls, d: dict) -> "VelocityCommand":
        return cls(**{k: float(d.get(k, 0.0)) for k in ("vx", "vy", "vz", "wx", "wy", "wz")})


# Keys that count as "the operator is commanding motion" (used for the
# move-and-wait analysis). Names follow exercises/step1_command_mapping.py.
MOTION_KEYS = {"w", "a", "s", "d", "r", "f", "q", "e", "arrowup", "arrowdown"}
