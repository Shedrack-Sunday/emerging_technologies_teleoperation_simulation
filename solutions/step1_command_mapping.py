"""Reference solution for step 1 (see exercises/step1_command_mapping.py)."""
import math

from teleop.commands import VelocityCommand

MAX_SPEED = 0.25    # m/s
MAX_RATE = 0.5      # rad/s
FINE_SCALE = 0.3


def keys_to_command(keys: set[str]) -> VelocityCommand:
    def axis(pos: str, neg: str) -> float:
        return float(pos in keys) - float(neg in keys)

    cmd = VelocityCommand(
        vx=MAX_SPEED * axis("w", "s"),
        vy=MAX_SPEED * axis("a", "d"),
        vz=MAX_SPEED * axis("r", "f"),
        wz=MAX_RATE * axis("q", "e"),
        wy=MAX_RATE * axis("arrowdown", "arrowup"),   # +wy = nose down
    )

    scale = FINE_SCALE if "shift" in keys else 1.0
    speed = math.sqrt(cmd.vx ** 2 + cmd.vy ** 2 + cmd.vz ** 2)
    if speed > MAX_SPEED:
        scale *= MAX_SPEED / speed

    cmd.vx *= scale
    cmd.vy *= scale
    cmd.vz *= scale
    cmd.wy *= FINE_SCALE if "shift" in keys else 1.0
    cmd.wz *= FINE_SCALE if "shift" in keys else 1.0
    return cmd
