"""Reference for step 1, up to and including task b) rotation.
Run with:  python3 run.py --step 1 --solution 1b
"""

from teleop.commands import VelocityCommand

MAX_SPEED = 0.25    # m/s
MAX_RATE = 0.5      # rad/s


def keys_to_command(keys):
    vx, vy, vz = 0.0, 0.0, 0.0
    wy, wz = 0.0, 0.0

    # a) translation
    if "w" in keys:
        vx = vx + MAX_SPEED
    if "s" in keys:
        vx = vx - MAX_SPEED
    if "a" in keys:
        vy = vy + MAX_SPEED
    if "d" in keys:
        vy = vy - MAX_SPEED
    if "r" in keys:
        vz = vz + MAX_SPEED
    if "f" in keys:
        vz = vz - MAX_SPEED

    # >>> NEW in b): rotation (arrowup = NEGATIVE wy)
    if "q" in keys:
        wz = wz + MAX_RATE
    if "e" in keys:
        wz = wz - MAX_RATE
    if "arrowup" in keys:
        wy = wy - MAX_RATE          # positive wy = nose down
    if "arrowdown" in keys:
        wy = wy + MAX_RATE

    return VelocityCommand(vx=vx, vy=vy, vz=vz, wy=wy, wz=wz)
