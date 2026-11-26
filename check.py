#!/usr/bin/env python3
"""Self-check for the exercises.   python3 check.py 1   |   python3 check.py 2

Add --solution to check the reference solution instead, or e.g. --solution=2b
for the reference up to sub-task b.
"""
import importlib
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from teleop.channel import ChannelConfig          # noqa: E402
from teleop.commands import VelocityCommand       # noqa: E402
from teleop.messages import Message               # noqa: E402

PKG = "solutions" if any(a.startswith("--solution") for a in sys.argv) else "exercises"
SUB = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--solution=")), "")
results = []


def check(name, cond, hint="", bonus=False):
    if not bonus:
        results.append(bool(cond))
    mark = "✔" if cond else ("·" if bonus else "✘")
    print(f"  {mark} {'(bonus) ' if bonus else ''}{name}" + ("" if cond else f"\n      → {hint}"))


def module_name(n):
    if SUB and SUB[0] == str(n) and len(SUB) > 1:
        from teleop.student import SUBSTEPS
        return f"solutions.{SUBSTEPS[n][SUB[1:]]}"
    return f"{PKG}.{ {1: 'step1_command_mapping', 2: 'step2_channel'}[n] }"


def close(a, b, tol=1e-6):
    return abs(a - b) <= tol


# ---------------------------------------------------------------- step 1
def step1():
    m = importlib.import_module(module_name(1))
    f, V, R = m.keys_to_command, m.MAX_SPEED, m.MAX_RATE
    print("Step 1: keyboard -> velocity command")
    c = f(set())
    check("no key -> zero command", isinstance(c, VelocityCommand) and c.is_zero(), "return VelocityCommand() with all zeros")
    check("w -> forward", close(f({"w"}).vx, V), "vx should be +MAX_SPEED")
    check("s -> backward", close(f({"s"}).vx, -V), "vx should be -MAX_SPEED")
    check("a -> left (+y)", close(f({"a"}).vy, V), "body y points LEFT")
    check("d -> right (-y)", close(f({"d"}).vy, -V), "right is NEGATIVE vy")
    check("r / f -> up / down", close(f({"r"}).vz, V) and close(f({"f"}).vz, -V), "r: vz = +MAX_SPEED, f: vz = -MAX_SPEED")
    check("q -> yaw left (+wz)", close(f({"q"}).wz, R), "positive wz = counter-clockwise seen from above = left")
    check("e -> yaw right (-wz)", close(f({"e"}).wz, -R), "e: wz = -MAX_RATE")
    check("arrowup -> look up (-wy)", close(f({"arrowup"}).wy, -R),
          "right-hand rule about body y (pointing left): positive wy tilts the nose DOWN")
    check("w + s cancel", close(f({"w", "s"}).vx, 0), "add/subtract instead of overwriting: vx = vx + ..., vx = vx - ...")
    c = f({"w", "a", "r"})
    check("diagonal limited to MAX_SPEED", close(math.sqrt(c.vx**2 + c.vy**2 + c.vz**2), V, 1e-3),
          "normalise (vx, vy, vz) if its length exceeds MAX_SPEED")


# ---------------------------------------------------------------- step 2
def run_channel(cls, cfg, n=200, size=100, topic="nav/pose", dt=0.01, extra=3.0):
    ch = cls(cfg)
    sent, got = {}, []
    t = 0.0
    for i in range(n):
        msg = Message(topic, {"i": i}, t, seq=i + 1, size=size)
        ch.send(msg, t)
        sent[i + 1] = t
        got += [(t, m) for m in ch.receive(t)]
        t += dt
    while t < n * dt + extra:
        got += [(t, m) for m in ch.receive(t)]
        t += dt
    return sent, got


def step2():
    m = importlib.import_module(module_name(2))
    cls = m.Link
    print("Step 2: channel")

    sent, got = run_channel(cls, ChannelConfig())
    check("no delay: everything arrives", len(got) == len(sent), "every message you store must come out of receive()")

    sent, got = run_channel(cls, ChannelConfig(delay_ms=300))
    lat = [t - m.stamp for t, m in got]
    check("delay 300 ms: everything arrives", len(got) == len(sent), "keep the messages that have not arrived yet in self.queue")
    check("delay 300 ms: latency is 0.30 s", lat and all(0.295 <= x <= 0.315 for x in lat),
          f"measured latency {min(lat, default=0):.3f}..{max(lat, default=0):.3f} s - receive() must hold messages back")

    sent, got = run_channel(cls, ChannelConfig(delay_ms=300, jitter_ms=100), n=500)
    lat = [t - m.stamp for t, m in got]
    check("jitter: latency varies between 0.3 and 0.4 s",
          lat and min(lat) >= 0.295 and max(lat) <= 0.415 and max(lat) - min(lat) > 0.05,
          "arrival_time = now + delay + random.uniform(0, self.jitter_s)")

    sent, got = run_channel(cls, ChannelConfig(loss=0.2), n=2000, size=100)
    frac = len(got) / len(sent)
    check("loss 20 %, small messages: ~80 % arrive", 0.75 < frac < 0.85, f"{100 * frac:.0f} % arrived - drop a message if random.random() < self.loss")

    sent, got = run_channel(cls, ChannelConfig(loss=0.2), n=1000, size=6000)
    frac = len(got) / len(sent)
    check("loss 20 %, big messages (5 packets): ~33 % arrive", 0.25 < frac < 0.41,
          f"{100 * frac:.0f} % arrived - 6000 bytes = 5 packets, all must survive: 0.8^5 = 0.33", bonus=True)

    wd = m.watchdog
    cmd = VelocityCommand(vx=0.2)
    check("watchdog: fresh command passes", close(wd(cmd, 0.05).vx, 0.2))
    check("watchdog: old command -> stop", wd(cmd, 2.0).is_zero(), "return VelocityCommand() if age_s is too large")


if __name__ == "__main__":
    steps = [a for a in sys.argv[1:] if a.isdigit()]
    if not steps:
        sys.exit(__doc__)
    for s in steps:
        {"1": step1, "2": step2}.get(s, lambda: print(f"no automatic checks for step {s}"))()
    ok = sum(results)
    print(f"\n{ok}/{len(results)} checks passed")
    sys.exit(0 if ok == len(results) else 1)
