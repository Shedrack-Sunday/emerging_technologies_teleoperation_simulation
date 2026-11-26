"""Reference solution for step 2 (see exercises/step2_channel.py)."""
import heapq
import math
import random

from teleop.channel import ChannelBase, ChannelConfig
from teleop.commands import VelocityCommand
from teleop.messages import Message


class StudentChannel(ChannelBase):
    def __init__(self, config: ChannelConfig):
        super().__init__(config)
        self.rng = random.Random(config.seed)
        self.in_flight = []
        self.counter = 0

    def send(self, msg: Message, now: float) -> None:
        cfg = self.config
        delay_s = cfg.delay_ms / 1000.0
        arrival = now + delay_s + self.rng.uniform(0.0, cfg.jitter_ms / 1000.0)

        n_packets = max(1, math.ceil(msg.size / cfg.mtu))
        p_ok = (1.0 - cfg.loss) ** n_packets
        while self.rng.random() > p_ok:
            if not msg.reliable:
                return                       # lost for good
            arrival += 2 * delay_s + 0.05    # retransmission after timeout / NACK

        heapq.heappush(self.in_flight, (arrival, self.counter, msg))
        self.counter += 1

    def receive(self, now: float) -> list[Message]:
        arrived = []
        while self.in_flight and self.in_flight[0][0] <= now:
            arrived.append(heapq.heappop(self.in_flight)[2])
        return arrived


COMMAND_TIMEOUT_S = 0.5


def watchdog(cmd: VelocityCommand, age_s: float) -> VelocityCommand:
    if age_s > COMMAND_TIMEOUT_S:
        return VelocityCommand()
    return cmd
