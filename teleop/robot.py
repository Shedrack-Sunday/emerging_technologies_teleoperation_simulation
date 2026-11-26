"""Everything that runs ON Int-Ball (robot side of the link).

    uplink msgs ──> command handling ──> watchdog ──> velocity controller ──> fans
                                                                              │
    downlink msgs <── sensor sampling + camera encoding <── simulated world <─┘
"""
from __future__ import annotations

import io
import math
from dataclasses import asdict, dataclass

import numpy as np
from PIL import Image

from teleop.commands import VelocityCommand
from teleop.mathutil import quat_from_euler, quat_to_euler
from teleop.messages import Message, Publisher, TOPICS
from teleop.sim.freeflyer import FreeFlyer
from teleop.sim.world import World

MAX_SPEED = 0.3          # m/s, hard limit of the onboard controller
MAX_RATE = 0.8           # rad/s
CAMERA_HFOV_DEG = 80.0   # Int-Ball2 main camera


@dataclass
class CameraSettings:
    width: int = 800
    height: int = 600
    fps: float = 10.0
    quality: int = 75          # JPEG quality 1..95
    grayscale: bool = False

    def update(self, d: dict):
        for k, v in d.items():
            if hasattr(self, k):
                setattr(self, k, type(getattr(self, k))(v))
        self.width = int(np.clip(self.width, 64, 1280))
        self.height = int(np.clip(self.height, 48, 960))
        self.fps = float(np.clip(self.fps, 0.2, 30))
        self.quality = int(np.clip(self.quality, 1, 95))


class RobotSide:
    def __init__(self, world: World, watchdog, seed: int = 0):
        self.world = world
        self.watchdog = watchdog
        self.ff = FreeFlyer()
        self.pub = Publisher()
        self.rng = np.random.default_rng(seed)
        self.camera = CameraSettings()
        self.rates = {name: spec.rate_hz for name, spec in TOPICS.items() if spec.direction == "down"}
        self.reset(0.0)

    # ------------------------------------------------------------------ state
    def reset(self, now: float):
        w = self.world
        self.ff.reset(w.start_pos.copy(), quat_from_euler(0, 0, w.start_yaw))
        self.cmd = VelocityCommand()
        self.cmd_rx_time = -1e9          # when the last velocity command arrived
        self.mode = "velocity"
        self.goal = None
        self.task_done = False
        self.in_target_since: float | None = None   # inspection: when the robot settled at the target
        self.collisions = 0
        self.last_impact_time = -1e9
        self.battery = 100.0
        self.path_length = 0.0
        self._next_pub = {t: now for t in self.rates}
        self._next_cam = now
        self._events: list[Message] = []
        self._prev_vel = np.zeros(3)
        self._acc = np.zeros(3)


    def truth(self) -> dict:
        return {"p": self.ff.pos.round(4).tolist(), "q": self.ff.quat.round(5).tolist(),
                "v": self.ff.vel.round(4).tolist()}

    # ------------------------------------------------------------------ uplink
    def on_message(self, msg: Message, now: float):
        if msg.topic == "cmd/velocity":
            self.cmd = VelocityCommand.from_json(msg.payload)
            self.cmd_rx_time = now
        elif msg.topic == "cmd/mode":
            self.mode = msg.payload.get("mode", "velocity")
        elif msg.topic == "cmd/goal":
            self.goal = np.array(msg.payload["p"], float)
            self.mode = "goal"

    # ------------------------------------------------------------------ control
    def _velocity_controller(self, cmd: VelocityCommand):
        """Onboard PD-type velocity controller -> body force/torque."""
        ff = self.ff
        R = ff.rot
        v_cmd = cmd.linear
        n = np.linalg.norm(v_cmd)
        if n > MAX_SPEED:
            v_cmd = v_cmd * MAX_SPEED / n
        v_des_world = R @ v_cmd
        f_world = ff.p.mass * 1.5 * (v_des_world - ff.vel)
        f_body = R.T @ f_world

        roll, pitch, _ = quat_to_euler(ff.quat)
        w_des = np.clip(cmd.angular, -MAX_RATE, MAX_RATE)
        w_des[0] += -2.0 * roll                       # keep "up" up (auto-level roll)
        if abs(pitch) > math.radians(75) and np.sign(w_des[1]) == np.sign(pitch):
            w_des[1] = 0.0                            # don't flip over
        I = ff.p.inertia
        t_body = I @ (4.0 * (w_des - ff.omega)) + np.cross(ff.omega, I @ ff.omega)
        return f_body, t_body

    def step(self, now: float, dt: float):
        cmd = self.watchdog(self.cmd, now - self.cmd_rx_time)
        if self.mode != "velocity":
            cmd = VelocityCommand()    # supervisory modes come in a later step
        f, t = self._velocity_controller(cmd)

        p_prev = self.ff.pos.copy()
        self.ff.step(dt, f, t)
        pos, vel, impact = self.world.collide(self.ff.pos, self.ff.vel, self.ff.p.radius)
        self.ff.pos, self.ff.vel = pos, vel
        if impact > 0.0:
            self.ff.omega *= 0.7
            if impact > 0.02 and now - self.last_impact_time > 0.5:
                self.collisions += 1
                self._event(now, {"type": "collision", "speed": round(impact, 3), "count": self.collisions})
            self.last_impact_time = now

        self.path_length += float(np.linalg.norm(self.ff.pos - p_prev))
        tgt = self.world.target
        if tgt is not None and not self.task_done:
            roll, pitch, yaw = quat_to_euler(self.ff.quat)
            if tgt.contains(self.ff.pos, yaw, pitch, float(np.linalg.norm(self.ff.vel))):
                if self.in_target_since is None:
                    self.in_target_since = now
                elif now - self.in_target_since >= tgt.hold_s:
                    self.task_done = True
            else:
                self.in_target_since = None

        self._acc = (self.ff.vel - self._prev_vel) / dt
        self._prev_vel = self.ff.vel.copy()
        self.battery = max(0.0, self.battery - dt * (0.002 + 0.02 * float(np.linalg.norm(self.ff.force_body))))

    def _event(self, now, payload):
        self._events.append(self.pub.make("events", payload, now))

    # ------------------------------------------------------------------ sensors
    def _due(self, topic: str, now: float) -> bool:
        rate = self.rates.get(topic, 0)
        if rate <= 0 or now + 1e-9 < self._next_pub[topic]:
            return False
        self._next_pub[topic] = max(self._next_pub[topic] + 1.0 / rate, now)
        return True

    def sensor_messages(self, now: float) -> list[Message]:
        ff, rng = self.ff, self.rng
        out, self._events = self._events, []
        if self._due("nav/pose", now):
            q = ff.quat + rng.normal(0, 0.0005, 4)
            out.append(self.pub.make("nav/pose", {
                "p": (ff.pos + rng.normal(0, 0.002, 3)).round(4).tolist(),
                "q": (q / np.linalg.norm(q)).round(5).tolist(),
                "v": (ff.vel + rng.normal(0, 0.001, 3)).round(4).tolist(),
                "w": (ff.omega + rng.normal(0, 0.002, 3)).round(4).tolist(),
            }, now))
        if self._due("imu", now):
            out.append(self.pub.make("imu", {
                "w": (ff.omega + rng.normal(0, 0.01, 3)).round(4).tolist(),
                "a": (ff.rot.T @ self._acc + rng.normal(0, 0.01, 3)).round(4).tolist(),
            }, now))
        if self._due("range", now):
            out.append(self.pub.make("range", {"d": self.ranges()}, now))
        if self._due("status", now):
            out.append(self.pub.make("status", {
                "mode": self.mode,
                "battery": round(self.battery, 1),
                "collisions": self.collisions,
                "cmd_age_ms": int(min(99999, 1000 * (now - self.cmd_rx_time))),
            }, now))
        return out

    def ranges(self, max_range: float = 2.5) -> list[float]:
        """Distance from the robot's surface to the nearest obstacle along +x,-x,+y,-y,+z,-z (body)."""
        R = self.ff.rot
        out = []
        for axis in range(3):
            for sign in (1, -1):
                d = R[:, axis] * sign
                r = self.world.raycast(self.ff.pos, d, max_range + self.ff.p.radius) - self.ff.p.radius
                out.append(round(float(max(0.0, r + self.rng.normal(0, 0.005))), 3))
        return out

    # ------------------------------------------------------------------ camera
    def camera_due(self, now: float) -> bool:
        if now + 1e-9 < self._next_cam:
            return False
        self._next_cam = max(self._next_cam + 1.0 / self.camera.fps, now)
        return True

    def camera_request(self) -> dict:
        """What the (browser-based) camera renderer needs to draw one frame."""
        cam = self.camera
        return {"p": self.ff.pos.tolist(), "q": self.ff.quat.tolist(),
                "w": cam.width, "h": cam.height, "hfov": CAMERA_HFOV_DEG}

    def encode_frame(self, rgba: bytes, w: int, h: int, stamp: float) -> Message:
        """Compress a raw RGBA frame into a JPEG message (this is where bandwidth
        is won or lost - session 3 will let you change this)."""
        img = Image.frombuffer("RGBA", (w, h), rgba, "raw", "RGBA", 0, -1)   # WebGL rows are bottom-up
        img = img.convert("L" if self.camera.grayscale else "RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=self.camera.quality)
        return self.pub.make("camera/image", buf.getvalue(), stamp, format="jpeg", w=w, h=h)

    def settings(self) -> dict:
        return {"camera": asdict(self.camera), "rates": self.rates}
