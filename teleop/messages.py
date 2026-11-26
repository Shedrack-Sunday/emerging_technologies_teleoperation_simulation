"""Messages that travel over the (simulated) communication link.

Every sensor stream and every command is a ``Message`` on a *topic*, similar to
ROS topics. Each message knows how many bytes it would occupy on the wire, so the
channel can model bandwidth and the UI can show kbit/s per topic.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

# Rough per-message protocol overhead (IP + UDP + our own header).
HEADER_BYTES = 40


@dataclass
class TopicSpec:
    name: str
    rate_hz: float          # default publish rate (0 = event-driven)
    reliable: bool          # True: must arrive (retransmit); False: best effort
    direction: str          # "down" (robot -> operator) or "up" (operator -> robot)
    description: str


TOPICS: dict[str, TopicSpec] = {t.name: t for t in [
    TopicSpec("camera/image", 10, False, "down", "JPEG image from the main (front) camera"),
    TopicSpec("nav/pose", 20, False, "down", "estimated position, orientation and velocity"),
    TopicSpec("imu", 50, False, "down", "angular rate and linear acceleration"),
    TopicSpec("range", 10, False, "down", "distance to walls along 6 body axes"),
    TopicSpec("status", 1, False, "down", "mode, battery, collisions, command age"),
    TopicSpec("events", 0, True, "down", "collisions"),
    TopicSpec("cmd/velocity", 20, False, "up", "body-frame velocity command from the operator"),
    TopicSpec("cmd/goal", 0, True, "up", "goal position for supervisory control"),
    TopicSpec("cmd/mode", 0, True, "up", "switch control mode"),
]}


@dataclass
class Message:
    topic: str
    payload: Any                # dict (JSON-able) or bytes (e.g. JPEG)
    stamp: float                # sim time at which the message was created (s)
    seq: int = 0                # per-topic sequence number, set by the sender
    size: int = 0               # bytes on the wire, computed automatically if 0
    meta: dict = field(default_factory=dict)   # extra info that is NOT transmitted (e.g. image format)

    def __post_init__(self):
        if self.size == 0:
            if isinstance(self.payload, (bytes, bytearray)):
                body = len(self.payload)
            else:
                body = len(json.dumps(self.payload, separators=(",", ":")))
            self.size = body + HEADER_BYTES

    @property
    def reliable(self) -> bool:
        spec = TOPICS.get(self.topic)
        return bool(spec and spec.reliable)


class Publisher:
    """Hands out sequence numbers per topic."""

    def __init__(self):
        self._seq: dict[str, int] = {}

    def make(self, topic: str, payload, stamp: float, **meta) -> Message:
        seq = self._seq.get(topic, 0) + 1
        self._seq[topic] = seq
        return Message(topic, payload, stamp, seq, meta=meta)
