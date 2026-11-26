"""Communication channel interface.

A channel connects the two sides of the teleoperation system. There is one
channel per direction:

    operator --uplink-->   robot      (commands)
    robot    --downlink--> operator   (camera, telemetry)

The framework calls

    channel.send(msg, now)       whenever a side transmits a message
    channel.receive(now)         every simulation tick (100 Hz) to collect the
                                 messages that have arrived by time ``now``

``now`` is the simulation time in seconds. Your implementation (exercise step 2)
lives in ``exercises/step2_channel.py``.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from teleop.messages import Message


@dataclass
class ChannelConfig:
    delay_ms: float = 0.0          # one-way propagation delay
    jitter_ms: float = 0.0         # random extra delay (std dev or max, your choice)
    loss: float = 0.0              # probability that a packet is lost (0..1)
    bandwidth_kbps: float = 0.0    # 0 = unlimited (used from session 3 on)
    mtu: int = 1200                # max bytes per packet; bigger messages are split
    seed: int = 1

    def to_json(self):
        return asdict(self)

    def update(self, d: dict):
        for k, v in d.items():
            if hasattr(self, k):
                setattr(self, k, type(getattr(self, k))(v))


class ChannelBase:
    """Base class. Subclasses implement ``send`` and ``receive``."""

    def __init__(self, config: ChannelConfig | None = None):
        self.config = config or ChannelConfig()

    # Settings in the units the exercise uses
    @property
    def delay_s(self) -> float:
        return self.config.delay_ms / 1000.0

    @property
    def jitter_s(self) -> float:
        return self.config.jitter_ms / 1000.0

    @property
    def loss(self) -> float:
        return self.config.loss

    def configure(self, config: ChannelConfig):
        """Called when delay/jitter/loss change at runtime."""
        self.config = config

    def send(self, msg: Message, now: float) -> None:
        raise NotImplementedError

    def receive(self, now: float) -> list[Message]:
        raise NotImplementedError


class IdealChannel(ChannelBase):
    """No delay, no loss, infinite bandwidth."""

    def __init__(self, config: ChannelConfig | None = None):
        super().__init__(config)
        self._buffer: list[Message] = []

    def send(self, msg: Message, now: float) -> None:
        self._buffer.append(msg)

    def receive(self, now: float) -> list[Message]:
        out, self._buffer = self._buffer, []
        return out
