"""STEP 1 - Direct teleoperation: from keys to a velocity command.

The lab calls keys_to_command() 20 times per second with the set of keys you
are holding, e.g. {"w", "q"}. The command you return is sent to Int-Ball, and
its onboard controller makes it move at that velocity. Holding a key = moving.

    "w" / "s"                forward / backward
    "a" / "d"                left / right
    "r" / "f"                up / down
    "q" / "e"                turn left / turn right
    "arrowup" / "arrowdown"  look up / look down

Directions as seen by Int-Ball (x = where the camera looks):
    vx > 0  forward          wz > 0  turn left
    vy > 0  left             wy > 0  look DOWN  (careful!)
    vz > 0  up

TODO (step 1):
  a) Translation: w/s, a/d, r/f  ->  vx, vy, vz   (use MAX_SPEED)
  b) Rotation:    q/e -> wz,  arrowup/arrowdown -> wy   (use MAX_RATE)
  c) Holding w and a together must not be faster than MAX_SPEED.

Run with:   python3 run.py --step 1
Check with: python3 check.py 1
"""
import math

from teleop.commands import VelocityCommand

MAX_SPEED = 0.25    # m/s
MAX_RATE = 0.5      # rad/s


def keys_to_command(keys):
    vx, vy, vz = 0.0, 0.0, 0.0      # m/s
    wy, wz = 0.0, 0.0               # rad/s

    # TODO a) translation - the first one is done for you:
    if "w" in keys:
        vx = vx + MAX_SPEED

    # TODO b) rotation

    # TODO c) speed = math.sqrt(vx**2 + vy**2 + vz**2)
    #         if it is larger than MAX_SPEED, scale vx, vy, vz down

    return VelocityCommand(vx=vx, vy=vy, vz=vz, wy=wy, wz=wz)
