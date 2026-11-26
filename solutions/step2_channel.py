"""Reference solution for step 2 (see exercises/step2_channel.py)."""
import math
import random

from teleop.channel import ChannelBase
from teleop.commands import VelocityCommand

PACKET_BYTES = 1200


class Link(ChannelBase):
    def __init__(self, config):
        super().__init__(config)
        self.queue = []

    def send(self, msg, now):
        # a) delay + b) jitter
        arrival_time = now + self.delay_s + random.uniform(0, self.jitter_s)

        # c) loss, e) per packet: the message survives only if all packets do
        packets = math.ceil(msg.size / PACKET_BYTES)
        for _ in range(packets):
            if random.random() < self.loss:
                return

        self.queue.append((arrival_time, msg))

    def receive(self, now):
        arrived = []
        waiting = []
        for arrival_time, msg in self.queue:
            if arrival_time <= now:
                arrived.append(msg)
            else:
                waiting.append((arrival_time, msg))
        self.queue = waiting
        return arrived


COMMAND_TIMEOUT_S = 0.5


def watchdog(cmd, age_s):
    if age_s > COMMAND_TIMEOUT_S:
        return VelocityCommand()
    return cmd
