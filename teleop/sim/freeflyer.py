"""Rigid-body dynamics of a free-flying robot in microgravity.

There is no gravity and no friction: once the robot moves, it keeps moving
until its own fans brake it. That is what makes teleoperation with delay hard.

The model is deliberately small enough to read in a few minutes:

    m * dv/dt = f                      (translation, world frame)
    I * dw/dt = tau - w x (I w)        (rotation, body frame; Euler's equation)

Fans cannot change their thrust instantly; we model this with a first-order lag
(time constant ``actuator_tau``) and per-axis limits in the body frame.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from teleop.mathutil import quat_integrate, quat_to_rot


@dataclass
class FreeFlyerParams:
    # Values for Int-Ball2 from JAXA's URDF (ib2.urdf)
    mass: float = 3.324                       # kg
    inertia: np.ndarray = field(default_factory=lambda: np.diag([0.01400, 0.01434, 0.01324]))  # kg m^2
    radius: float = 0.09                      # m, collision sphere
    # Actuator limits (fan thrust), body frame, per axis.
    # Real Int-Ball2 is even weaker; these are scaled up a bit to keep the lab snappy.
    max_force: float = 0.40                   # N   -> ~0.12 m/s^2
    max_torque: float = 0.010                 # N m -> ~0.7 rad/s^2
    actuator_tau: float = 0.15                # s, fan spin-up time constant


class FreeFlyer:
    def __init__(self, params: FreeFlyerParams | None = None):
        self.p = params or FreeFlyerParams()
        self.inertia_inv = np.linalg.inv(self.p.inertia)
        self.reset(np.zeros(3), np.array([1.0, 0, 0, 0]))

    def reset(self, position, orientation):
        self.pos = np.array(position, dtype=float)          # world frame, m
        self.vel = np.zeros(3)                               # world frame, m/s
        self.quat = np.array(orientation, dtype=float)       # body -> world, [w x y z]
        self.omega = np.zeros(3)                             # body frame, rad/s
        self.force_body = np.zeros(3)                        # current (lagged) fan force, body frame
        self.torque_body = np.zeros(3)

    @property
    def rot(self) -> np.ndarray:
        return quat_to_rot(self.quat)

    def step(self, dt: float, force_body_cmd: np.ndarray, torque_body_cmd: np.ndarray):
        """Advance the state by dt with the commanded body-frame force/torque."""
        f_cmd = np.clip(force_body_cmd, -self.p.max_force, self.p.max_force)
        t_cmd = np.clip(torque_body_cmd, -self.p.max_torque, self.p.max_torque)
        alpha = min(1.0, dt / self.p.actuator_tau)
        self.force_body += alpha * (f_cmd - self.force_body)
        self.torque_body += alpha * (t_cmd - self.torque_body)

        # Translation (semi-implicit Euler)
        acc = self.rot @ self.force_body / self.p.mass
        self.vel += acc * dt
        self.pos += self.vel * dt

        # Rotation
        I = self.p.inertia
        w = self.omega
        w_dot = self.inertia_inv @ (self.torque_body - np.cross(w, I @ w))
        self.omega = w + w_dot * dt
        self.quat = quat_integrate(self.quat, self.omega, dt)
