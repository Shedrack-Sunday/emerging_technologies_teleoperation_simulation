"""The Kibo (JEM pressurized module) interior, simplified.

The aisle between the racks is modelled as an axis-aligned box. Things that stick
out of the racks (cargo bags, experiment hardware, handrails, cables) are smaller
axis-aligned boxes. The robot is a sphere. That is all the geometry we need for
collisions and range sensing; the browser draws the same boxes with textures.

The course task is an inspection: fly to a target position, face the object to
inspect and hold still there (see Target).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

ASSETS = Path(__file__).resolve().parents[2] / "assets"


class DistanceField:
    """Signed distance to the module interior surfaces (m): > 0 in free space,
    < 0 inside racks/walls. Precomputed from the ISS model by tools/build_kibo.py."""

    def __init__(self, path: Path):
        z = np.load(path)
        self.d = z["sdf_cm"].astype(np.float32) / 100.0
        self.origin = z["origin"].astype(float)
        self.h = float(z["h"])
        self.shape = np.array(self.d.shape)

    def __call__(self, p: np.ndarray) -> float:
        """Trilinear interpolation; outside the grid counts as solid."""
        g = (p - self.origin) / self.h
        i = np.floor(g).astype(int)
        if np.any(i < 0) or np.any(i >= self.shape - 1):
            return -1.0
        f = g - i
        c = self.d[i[0]:i[0] + 2, i[1]:i[1] + 2, i[2]:i[2] + 2]
        c = c[0] * (1 - f[0]) + c[1] * f[0]
        c = c[0] * (1 - f[1]) + c[1] * f[1]
        return float(c[0] * (1 - f[2]) + c[1] * f[2])

    def normal(self, p: np.ndarray) -> np.ndarray:
        e = self.h
        g = np.array([self(p + d) - self(p - d) for d in np.eye(3) * e])
        n = np.linalg.norm(g)
        return g / n if n > 1e-9 else np.zeros(3)


@dataclass
class Box:
    name: str
    kind: str
    lo: np.ndarray
    hi: np.ndarray

    def to_json(self):
        return {"name": self.name, "kind": self.kind, "min": self.lo.tolist(), "max": self.hi.tolist()}


@dataclass
class Target:
    """Inspection position: the robot must be inside [lo, hi], face along `yaw`
    (within yaw_tol, nearly level) and hold still for `hold_s` seconds."""
    name: str
    lo: np.ndarray
    hi: np.ndarray
    yaw: float = 0.0
    yaw_tol: float = np.radians(15)
    pitch_tol: float = np.radians(20)
    max_speed: float = 0.03
    hold_s: float = 2.0

    def contains(self, pos, yaw, pitch, speed) -> bool:
        dyaw = (yaw - self.yaw + np.pi) % (2 * np.pi) - np.pi
        return bool(np.all(pos >= self.lo) and np.all(pos <= self.hi) and abs(dyaw) <= self.yaw_tol
                    and abs(pitch) <= self.pitch_tol and speed <= self.max_speed)


def _box(name, kind, lo, hi):
    return Box(name, kind, np.array(lo, float), np.array(hi, float))


@dataclass
class World:
    # Aisle interior (m). Real Kibo PM: ~11 m long, aisle roughly 2 m x 2 m.
    lo: np.ndarray = field(default_factory=lambda: np.array([0.0, -1.05, -1.05]))
    hi: np.ndarray = field(default_factory=lambda: np.array([10.6, 1.05, 1.05]))
    obstacles: list[Box] = field(default_factory=list)
    target: Target | None = None
    start_pos: np.ndarray = field(default_factory=lambda: np.array([0.7, 0.0, 0.0]))
    start_yaw: float = 0.0
    restitution: float = 0.3
    sdf: DistanceField | None = None          # real module geometry (if available)
    mesh_url: str | None = None               # GLB for the browser

    # ------------------------------------------------------------------ geometry
    def collide(self, pos: np.ndarray, vel: np.ndarray, radius: float):
        """Push the sphere out of walls/obstacles and reflect velocity.

        Returns (pos, vel, impact_speed); impact_speed > 0 if something was hit.
        """
        impact = 0.0
        e = self.restitution
        if self.sdf is not None:              # real module: push out along the distance gradient
            for _ in range(3):
                d = self.sdf(pos)
                if d >= radius:
                    break
                n = self.sdf.normal(pos)
                if not n.any():
                    break
                pos += (radius - d) * n
                vn = float(vel @ n)
                if vn < 0:
                    impact = max(impact, -vn)
                    vel -= (1 + e) * vn * n
        # Walls of the aisle: keep the sphere inside [lo + r, hi - r]
        for i in range(3) if self.sdf is None else ():
            if pos[i] - radius < self.lo[i]:
                pos[i] = self.lo[i] + radius
                if vel[i] < 0:
                    impact = max(impact, -vel[i])
                    vel[i] = -e * vel[i]
            elif pos[i] + radius > self.hi[i]:
                pos[i] = self.hi[i] - radius
                if vel[i] > 0:
                    impact = max(impact, vel[i])
                    vel[i] = -e * vel[i]
        # Obstacles: sphere vs. axis-aligned box
        for b in self.obstacles:
            closest = np.clip(pos, b.lo, b.hi)
            d = pos - closest
            dist = float(np.linalg.norm(d))
            if dist >= radius:
                continue
            if dist < 1e-9:  # centre inside the box: push out along the shallowest axis
                pen_lo = pos - b.lo
                pen_hi = b.hi - pos
                axis = int(np.argmin(np.minimum(pen_lo, pen_hi)))
                n = np.zeros(3)
                n[axis] = -1.0 if pen_lo[axis] < pen_hi[axis] else 1.0
                closest = pos.copy()
                closest[axis] = b.lo[axis] if n[axis] < 0 else b.hi[axis]
            else:
                n = d / dist
            pos[:] = closest + n * radius
            vn = float(vel @ n)
            if vn < 0:
                impact = max(impact, -vn)
                vel -= (1 + e) * vn * n
        return pos, vel, impact

    def raycast(self, origin: np.ndarray, direction: np.ndarray, max_range: float) -> float:
        """Distance from origin along unit direction to the first wall/obstacle."""
        t_best = max_range
        if self.sdf is not None:              # sphere tracing through the distance field
            t = 0.0
            while t < max_range:
                d = self.sdf(origin + t * direction)
                if d < 0.005:
                    break
                t += max(d, 0.01)
            t_best = min(t, max_range)
        # Exit through the aisle walls
        for i in range(3) if self.sdf is None else ():
            if direction[i] > 1e-9:
                t_best = min(t_best, (self.hi[i] - origin[i]) / direction[i])
            elif direction[i] < -1e-9:
                t_best = min(t_best, (self.lo[i] - origin[i]) / direction[i])
        # Entry into obstacles (slab method)
        with np.errstate(divide="ignore", invalid="ignore"):
            inv = 1.0 / direction
        for b in self.obstacles:
            t1 = (b.lo - origin) * inv
            t2 = (b.hi - origin) * inv
            t_near = np.nanmax(np.minimum(t1, t2))
            t_far = np.nanmin(np.maximum(t1, t2))
            if t_near <= t_far and t_far > 0 and 0 <= t_near < t_best:
                t_best = t_near
        return max(0.0, float(t_best))

    def to_json(self):
        return {
            "min": self.lo.tolist(),
            "max": self.hi.tolist(),
            "obstacles": [b.to_json() for b in self.obstacles],
            "start": {"pos": self.start_pos.tolist(), "yaw": self.start_yaw},
            "mesh": self.mesh_url,
        }


def make_kibo() -> World:
    """Kibo from the real ISS interior model if the assets exist, else the
    simplified box version."""
    sdf_path = ASSETS / "kibo" / "kibo_sdf.npz"
    if sdf_path.exists() and (ASSETS / "kibo" / "kibo.glb").exists():
        return make_kibo_real(DistanceField(sdf_path))
    return make_kibo_boxes()


def make_kibo_real(sdf: DistanceField) -> World:
    w = World(lo=np.array([0.0, -1.0, -1.0]), hi=np.array([9.6, 1.0, 1.0]), sdf=sdf,
              mesh_url="/assets/kibo/kibo.glb", start_pos=np.array([1.3, 0.0, 0.0]))
    L = 1.05
    w.obstacles = [   # cargo transfer bags strapped to the racks (not part of the ISS model)
        _box("CTB-1", "bag", [3.0, -L, -L], [3.55, -0.5, -0.55]),
        _box("CTB-2", "bag", [5.0, 0.55, 0.5], [5.55, L, L]),
        _box("CTB-3", "bag", [6.6, -L, 0.4], [7.0, -0.6, L]),
    ]
    # JEM airlock hatch in the end cone (its face is at x ~ 8.0 m): inspect from 0.5..1 m
    w.target = Target("JEM airlock", np.array([7.0, -0.3, -0.3]), np.array([7.5, 0.3, 0.3]))
    return w


def make_kibo_boxes() -> World:
    w = World()
    L, H = 1.05, 1.05  # half widths
    obs = [
        # cargo transfer bags strapped to the racks
        _box("CTB-1", "bag", [3.2, -L, -H], [3.75, -0.55, -0.62]),
        _box("CTB-2", "bag", [5.9, 0.62, 0.55], [6.45, L, H]),
        _box("CTB-3", "bag", [8.2, -L, 0.45], [8.6, -0.7, H]),
        # experiment hardware protruding from a rack
        _box("EXP-RACK", "hardware", [5.1, 0.6, -0.45], [5.8, L, 0.45]),
        # laptop on an arm
        _box("SSC-laptop", "laptop", [1.4, -L, 0.05], [1.75, -0.78, 0.35]),
        # cable bundle crossing the lower right corner
        _box("cable", "cable", [7.7, -L, -0.4], [7.8, -0.35, -0.3]),
    ]
    # handrails: thin bars on all four walls every ~2 m
    for i, x in enumerate(np.arange(1.0, 10.0, 2.1)):
        obs.append(_box(f"rail-floor-{i}", "rail", [x, -0.3, -H], [x + 0.6, -0.25, -H + 0.07]))
        obs.append(_box(f"rail-ceil-{i}", "rail", [x + 0.9, 0.25, H - 0.07], [x + 1.5, 0.3, H]))
    w.obstacles = obs
    w.target = Target("end wall", np.array([9.0, -0.3, -0.3]), np.array([9.8, 0.3, 0.3]))
    return w
