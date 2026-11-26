"""STEP 1 - Direct teleoperation: map keyboard input to a velocity command.

This function runs on the OPERATOR side, 20 times per second. Its result is sent
over the uplink to Int-Ball, whose onboard controller then tries to reach the
commanded velocity (rate control: holding a key = moving).

Keys arrive as a set of lowercase names of all keys that are currently pressed:

    "w" / "s"              forward / backward      (body x)
    "a" / "d"              left / right            (body y)
    "r" / "f"              up / down               (body z)
    "q" / "e"              yaw left / yaw right    (about body z)
    "arrowup" / "arrowdown"  pitch: look up / look down (about body y)
    "shift"                fine mode (slow, precise motion)

Body frame of Int-Ball: x = camera direction, y = left, z = up.
Right-hand rule: positive wz turns LEFT, positive wy pitches the nose DOWN.

TODO (step 1):
  a) Translation: w/s, a/d, r/f -> vx, vy, vz with MAX_SPEED
  b) Rotation: q/e -> wz, arrowup/arrowdown -> wy with MAX_RATE
     (careful with the sign of the pitch!)
  c) Fine mode: while "shift" is held, scale everything by FINE_SCALE
  d) Pressing w and a together should not make Int-Ball faster than MAX_SPEED.
     Normalise the linear velocity if needed.

Run with:   python3 run.py --step 1
Check with: python3 check.py 1
"""
from teleop.commands import VelocityCommand

MAX_SPEED = 0.25    # m/s
MAX_RATE = 0.5      # rad/s
FINE_SCALE = 0.3


def keys_to_command(keys: set[str]) -> VelocityCommand:
    cmd = VelocityCommand()

    # TODO a) translation, e.g.
    # if "w" in keys:
    #     cmd.vx += MAX_SPEED

    # TODO b) rotation

    # TODO c) fine mode

    # TODO d) limit the norm of (vx, vy, vz) to MAX_SPEED (hint: math.sqrt or numpy)

    return cmd
