"""The lab: wires operator side, channels and robot side together and runs the
simulation clock. Independent of the web server, so it can also run headless
(see check.py).

One tick (10 ms of simulation time):

    uplink.receive  -> robot.on_message
    robot.step      (watchdog, controller, dynamics, collisions, course)
    robot sensors   -> downlink.send          (camera frames: via the renderer)
    downlink.receive-> operator.on_message -> UI
    operator.commands -> uplink.send
"""
from __future__ import annotations

import csv
import copy
import os
import datetime as dt_mod
import re
import time
import traceback
from pathlib import Path

import numpy as np

from teleop.channel import ChannelConfig
from teleop.linkstats import LinkMonitor
from teleop.messages import Message
from teleop.operator import OperatorSide
from teleop.robot import RobotSide
from teleop.sim.world import make_kibo
from teleop.student import Implementation

RESULT_FIELDS = ["finished_at", "team", "step", "delay_ms", "jitter_ms", "loss", "task_time_s",
                 "collisions", "path_m", "idle_frac", "waits", "task"]


class RunRecorder:
    """Course runs and the metrics for the 'feel the delay' experiment."""

    def __init__(self):
        self.state = "idle"
        self.reset()

    def reset(self):
        self.t0 = None
        self.t_end = None
        self.idle_time = 0.0
        self.waits = 0
        self._idle_run = 0.0
        self.samples = []
        self.result = None
        self.settled = False

    def summary(self, now):
        el = None
        if self.t0 is not None:
            el = (self.t_end or now) - self.t0
        return {"state": self.state, "elapsed": el, "result": self.result}


class Lab:
    """Experiment settings (link, camera, course, outages) come from the command
    line (run.py); the browser is only the operator station."""

    def __init__(self, impl: Implementation, results_dir: Path | None = None, seed: int = 0,
                 course: bool = False, team: str = "", outages: list[tuple[float, float]] | None = None,
                 show_truth: bool = False, log=None):
        self.impl = impl
        self.results_dir = results_dir
        self.world = make_kibo()
        self.robot = RobotSide(self.world, self._safe_watchdog, seed=seed)
        self.op = OperatorSide(impl.keys_to_command)
        self.config = ChannelConfig()
        self.now = 0.0
        self.team = re.sub(r"[^\w\- ]", "", team)[:30]
        self.course = course
        self.show_truth = show_truth
        self.log = log or (lambda *a: None)       # terminal output (run.py passes print)
        self.results_url = ""                      # set by the server
        self.session = f"{time.time():.3f}"        # lets the browser notice a restarted server
        self.outages = sorted(outages or [])      # (start s after first key press, duration s)
        self.t_first_input: float | None = None
        self.outage_until = -1.0
        self.errors: dict[str, str] = {}
        self.ui_out: list = []                 # ("json", dict) | ("bin", header, bytes) | ("render", dict)
        self.run = RunRecorder()
        self.render_pending: dict | None = None
        self.pending_renders: dict[int, dict] = {}
        self.render_fn = None                   # headless renderer: f(request) -> (rgba, w, h)
        self._render_id = 0
        self._next_ui = {"truth": 0.0, "stats": 0.0, "op": 0.0}
        self._new_channels()
        if course:
            self.run.state = "armed"

    # ------------------------------------------------------------------ setup
    def _new_channels(self):
        self.uplink = self.impl.channel_cls(copy.deepcopy(self.config))
        self.downlink = self.impl.channel_cls(copy.deepcopy(self.config))
        self.up_mon, self.down_mon = LinkMonitor(), LinkMonitor()

    def set_channel(self, d: dict):
        self.config.update(d)
        for ch in (self.uplink, self.downlink):
            try:
                ch.configure(copy.deepcopy(self.config))
            except Exception as e:
                self._error("channel.configure", e)

    def reset(self, keep_channel_config=True):
        self.robot.reset(self.now)
        self.op.reset(self.now)
        self.render_pending = None
        self.pending_renders = {}
        self._new_channels()

    # ------------------------------------------------------------------ errors
    def _error(self, where: str, e: Exception):
        tb = traceback.extract_tb(e.__traceback__)
        loc = next((f"{Path(f.filename).name}:{f.lineno}" for f in reversed(tb)
                    if "exercises" in f.filename or "solutions" in f.filename), "")
        text = f"{type(e).__name__}: {e} {('(' + loc + ')') if loc else ''}".strip()
        if self.errors.get(where) != text:
            self.log(f"  ERROR in {where}: {text}")
        self.errors[where] = text

    def _safe_watchdog(self, cmd, age):
        try:
            out = self.impl.watchdog(cmd, age)
            self.errors.pop("watchdog", None)
            return out if out is not None else cmd
        except Exception as e:
            self._error("watchdog", e)
            return cmd

    def _send(self, channel, monitor, msg: Message, where: str):
        if self.now < self.outage_until:
            return
        monitor.on_send(msg, self.now)
        try:
            channel.send(msg, self.now)
            self.errors.pop(where, None)
        except Exception as e:
            self._error(where, e)

    def _receive(self, channel, monitor, where: str) -> list[Message]:
        try:
            msgs = channel.receive(self.now) or []
            self.errors.pop(where, None)
        except Exception as e:
            self._error(where, e)
            return []
        out = [m for m in msgs if isinstance(m, Message)]
        for m in out:
            monitor.on_receive(m, self.now)
        return out

    # ------------------------------------------------------------------ main loop
    def tick(self, dt: float = 0.01):
        self.now += dt
        now = self.now

        for m in self._receive(self.uplink, self.up_mon, "uplink.receive"):
            self.robot.on_message(m, now)

        self.robot.step(now, dt)

        for m in self.robot.sensor_messages(now):
            self._send(self.downlink, self.down_mon, m, "downlink.send")

        if self.robot.camera_due(now):
            self._request_frame()

        for m in self._receive(self.downlink, self.down_mon, "downlink.receive"):
            if self.op.on_message(m, now):
                self._to_ui(m)

        for m in self.op.commands(now):
            self._send(self.uplink, self.up_mon, m, "uplink.send")

        self._update_outage()
        self._update_run(dt)
        self._periodic_ui()

    def _update_outage(self):
        if self.t_first_input is None:
            if not self.op.commanding_motion:
                return
            self.t_first_input = self.now
        t = self.now - self.t_first_input
        while self.outages and t >= self.outages[0][0]:
            _, dur = self.outages.pop(0)
            self.outage_until = self.now + dur
            self.log(f"  link outage for {dur:g} s")

    # ------------------------------------------------------------------ camera
    def _request_frame(self):
        # One frame in flight at a time. A slow renderer then simply gives a lower
        # frame rate; queueing requests would make every frame arrive "too late".
        self.pending_renders = {i: r for i, r in self.pending_renders.items() if self.now - r["stamp"] < 5.0}
        if self.render_pending and self.now - self.render_pending["stamp"] < 2.0:
            return  # renderer still busy -> skip this frame
        self._render_id += 1
        req = {"id": self._render_id, "stamp": self.now, **self.robot.camera_request()}
        self.render_pending = req
        self.pending_renders[req["id"]] = req
        if self.render_fn is not None:
            rgba, w, h = self.render_fn(req)
            self.on_frame(req["id"], w, h, rgba)
        else:
            self.ui_out.append(("render", req))

    def on_frame(self, req_id: int, w: int, h: int, rgba: bytes):
        req = self.pending_renders.pop(req_id, None)
        if req is None:
            return
        if self.render_pending and self.render_pending["id"] == req_id:
            self.render_pending = None
        self.errors.pop("camera", None)
        msg = self.robot.encode_frame(rgba, w, h, req["stamp"])
        if os.environ.get("TELEOP_DUMP_DIR"):           # debugging: keep the last encoded frame
            Path(os.environ["TELEOP_DUMP_DIR"], "last_frame.jpg").write_bytes(msg.payload)
        self._send(self.downlink, self.down_mon, msg, "downlink.send")

    # ------------------------------------------------------------------ UI
    def _to_ui(self, m: Message):
        if isinstance(m.payload, (bytes, bytearray)):
            hdr = {"type": "msg", "topic": m.topic, "stamp": m.stamp, "recv": self.now, "seq": m.seq,
                   "size": m.size, **m.meta}
            self.ui_out.append(("bin", hdr, bytes(m.payload)))
        else:
            self.ui_out.append(("json", {"type": "msg", "topic": m.topic, "stamp": m.stamp, "recv": self.now,
                                         "seq": m.seq, "size": m.size, "data": m.payload}))

    def _periodic_ui(self):
        now = self.now
        if now >= self._next_ui["truth"]:
            self._next_ui["truth"] = now + 0.05
            self.ui_out.append(("json", {"type": "truth", "t": now, **self.robot.truth()}))
        if now >= self._next_ui["op"]:
            self._next_ui["op"] = now + 0.1
            self.ui_out.append(("json", {"type": "op", "t": now, "cmd": self.op.last_cmd.to_json(),
                                         "keys": sorted(self.op.keys)}))
        if now >= self._next_ui["stats"]:
            self._next_ui["stats"] = now + 0.5
            self.ui_out.append(("json", {
                "type": "stats", "t": now,
                "down": self.down_mon.summary(now), "up": self.up_mon.summary(now),
                "errors": {**self.errors, **({"keys_to_command": self.op.cmd_error} if self.op.cmd_error else {})},
                "outage": max(0.0, self.outage_until - now),
            }))

    def info(self) -> dict:
        return {"type": "init", "session": self.session, "world": self.world.to_json(),
                "show_truth": self.show_truth}

    def handle_ui(self, d: dict):
        """Input from the operator station: only the keyboard."""
        if d.get("type") == "keys":
            self.op.keys = {str(k).lower() for k in d.get("keys", [])}
        elif d.get("type") == "render_error":           # camera renderer in the browser failed
            text = f"camera renderer: {str(d.get('error', '?'))[:200]}"
            if self.errors.get("camera") != text:
                self.log(f"  ERROR in the browser - {text}  (try reloading the page)")
            self.errors["camera"] = text
            self.render_pending = None

    # ------------------------------------------------------------------ runs
    def _update_run(self, dt):
        r = self.run
        moving = self.op.commanding_motion
        if r.state == "armed" and moving:
            r.state, r.t0 = "running", self.now
            self.log("  clock started")
        if r.state != "running":
            return
        settled = self.robot.in_target_since is not None
        if settled != r.settled:
            r.settled = settled
            self.log(f"  {self.now - r.t0:6.1f} s  " + (f"at the {self.world.target.name} - hold still..." if settled
                                                       else "left the inspection position"))
        if moving:
            if r._idle_run > 0.5:
                r.waits += 1
            r._idle_run = 0.0
        else:
            r.idle_time += dt
            r._idle_run += dt
        if len(r.samples) == 0 or self.now - r.samples[-1][0] >= 0.1:
            p = self.robot.ff.pos
            r.samples.append((round(self.now - r.t0, 2), *p.round(3), int(moving)))
        if self.robot.task_done:
            r.state, r.t_end = "done", self.now
            self._finish_run()

    def _finish_run(self):
        r, cfg = self.run, self.config
        T = r.t_end - r.t0
        r.result = {
            "finished_at": dt_mod.datetime.now().isoformat(timespec="seconds"),
            "team": self.team or "anonymous", "step": self.impl.step,
            "delay_ms": cfg.delay_ms, "jitter_ms": cfg.jitter_ms, "loss": cfg.loss,
            "task_time_s": round(T, 2), "collisions": self.robot.collisions,
            "path_m": round(self.robot.path_length, 2),
            "idle_frac": round(r.idle_time / T, 3) if T > 0 else 0.0,
            "waits": r.waits, "task": self.world.target.name,
        }
        res = r.result
        self.log(f"\n  TASK COMPLETE: {res['task_time_s']:.1f} s at {res['delay_ms']:g} ms delay, "
                 f"{res['collisions']} collisions, idle {100 * res['idle_frac']:.0f} %, "
                 f"{res['waits']} waits, path {res['path_m']} m")
        if self.results_dir is None:
            return
        self.results_dir.mkdir(parents=True, exist_ok=True)
        f = self.results_dir / "runs.csv"
        if f.exists() and f.read_text().split("\n", 1)[0] != ",".join(RESULT_FIELDS):
            f.rename(f.with_name("runs_old.csv"))          # older format
        new = not f.exists()
        with f.open("a", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=RESULT_FIELDS)
            if new:
                w.writeheader()
            w.writerow(r.result)
        tdir = self.results_dir / "trajectories"
        tdir.mkdir(exist_ok=True)
        name = f"{r.result['finished_at'].replace(':', '')}_{r.result['team'].replace(' ', '_')}_{int(cfg.delay_ms)}ms.csv"
        with (tdir / name).open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["t", "x", "y", "z", "commanding"])
            w.writerows(r.samples)
        try:
            shown = f.relative_to(Path.cwd())
        except ValueError:
            shown = f
        self.log(f"  saved to {shown}" + (f"   compare runs: {self.results_url}" if self.results_url else ""))
        self.log("  next run: Ctrl+C, then start again (e.g. with another --delay)\n")


def read_results(results_dir: Path) -> list[dict]:
    f = results_dir / "runs.csv"
    if not f.exists():
        return []
    with f.open() as fh:
        return list(csv.DictReader(fh))
