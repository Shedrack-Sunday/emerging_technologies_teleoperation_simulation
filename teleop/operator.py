"""Everything that runs at the OPERATOR station (ground side of the link)."""
from __future__ import annotations

from teleop.commands import MOTION_KEYS, VelocityCommand
from teleop.messages import Message, Publisher

COMMAND_RATE_HZ = 20


class OperatorSide:
    def __init__(self, keys_to_command):
        self.keys_to_command = keys_to_command
        self.pub = Publisher()
        self.keys: set[str] = set()
        self.last_cmd = VelocityCommand()
        self.cmd_error: str | None = None
        self.latest: dict[str, Message] = {}     # newest received message per topic
        self._next_cmd = 0.0

    def reset(self, now: float):
        self.latest.clear()
        self._next_cmd = now

    @property
    def commanding_motion(self) -> bool:
        return bool(self.keys & MOTION_KEYS)

    def on_message(self, msg: Message, now: float) -> bool:
        """Store a received message. Returns False for stale messages (older than
        what we already have) - e.g. a camera frame overtaken by a newer one."""
        prev = self.latest.get(msg.topic)
        if prev is not None and msg.topic != "events" and msg.seq < prev.seq:
            return False
        self.latest[msg.topic] = msg
        return True

    def commands(self, now: float) -> list[Message]:
        """Periodically turn the keyboard state into a velocity command."""
        if now + 1e-9 < self._next_cmd:
            return []
        self._next_cmd = max(self._next_cmd + 1.0 / COMMAND_RATE_HZ, now)
        try:
            cmd = self.keys_to_command(set(self.keys))
            if not isinstance(cmd, VelocityCommand):
                raise TypeError(f"keys_to_command must return a VelocityCommand, got {type(cmd).__name__}")
            self.cmd_error = None
        except Exception as e:  # show student errors in the UI instead of crashing
            cmd = VelocityCommand()
            self.cmd_error = f"{type(e).__name__}: {e}"
        self.last_cmd = cmd
        return [self.pub.make("cmd/velocity", cmd.to_json(), now)]
