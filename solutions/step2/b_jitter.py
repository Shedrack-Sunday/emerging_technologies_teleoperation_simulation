"""Reference for step 2, up to and including task b) jitter.
Run with:  python3 run.py --step 2 --solution 2b
"""
import random

from teleop.channel import ChannelBase
from teleop.commands import VelocityCommand


class Link(ChannelBase):
    def __init__(self, config):
        super().__init__(config)
        self.queue = []

    def send(self, msg, now):
        # a) delay
        # >>> NEW in b): + a random extra delay between 0 and jitter_s
        arrival_time = now + self.delay_s + random.uniform(0, self.jitter_s)

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
    return cmd          # d) not implemented yet
