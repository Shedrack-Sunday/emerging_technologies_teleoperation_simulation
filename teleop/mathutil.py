"""Small quaternion / rotation helpers.

Conventions (same as ROS):
  * quaternions are numpy arrays [w, x, y, z]
  * world frame: x along the Kibo module axis, y to the left, z "up" (ceiling)
  * body frame of Int-Ball: x = main camera direction, y = left, z = up
"""
from __future__ import annotations

import math

import numpy as np


def quat_mul(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return np.array([
        aw * bw - ax * bx - ay * by - az * bz,
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
    ])


def quat_normalize(q: np.ndarray) -> np.ndarray:
    return q / np.linalg.norm(q)


def quat_from_axis_angle(axis, angle: float) -> np.ndarray:
    axis = np.asarray(axis, dtype=float)
    n = np.linalg.norm(axis)
    if n < 1e-12 or abs(angle) < 1e-12:
        return np.array([1.0, 0.0, 0.0, 0.0])
    axis = axis / n
    s = math.sin(angle / 2.0)
    return np.array([math.cos(angle / 2.0), *(axis * s)])


def quat_from_euler(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """ZYX convention (yaw about z, then pitch about y, then roll about x)."""
    qz = quat_from_axis_angle([0, 0, 1], yaw)
    qy = quat_from_axis_angle([0, 1, 0], pitch)
    qx = quat_from_axis_angle([1, 0, 0], roll)
    return quat_mul(quat_mul(qz, qy), qx)


def quat_to_euler(q: np.ndarray) -> tuple[float, float, float]:
    """Returns (roll, pitch, yaw), ZYX convention."""
    w, x, y, z = q
    roll = math.atan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    sp = max(-1.0, min(1.0, 2 * (w * y - z * x)))
    pitch = math.asin(sp)
    yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return roll, pitch, yaw


def quat_to_rot(q: np.ndarray) -> np.ndarray:
    """Rotation matrix R so that v_world = R @ v_body."""
    w, x, y, z = q
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
        [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
        [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)],
    ])


def quat_integrate(q: np.ndarray, omega_body: np.ndarray, dt: float) -> np.ndarray:
    """Integrate an orientation with a body-frame angular velocity over dt."""
    angle = float(np.linalg.norm(omega_body)) * dt
    dq = quat_from_axis_angle(omega_body, angle)
    return quat_normalize(quat_mul(q, dq))


def wrap_angle(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi
