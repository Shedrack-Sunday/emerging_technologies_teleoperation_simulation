"""Reference for step 2, up to and including task a) delay.
Run with:  python3 run.py --step 2 --solution 2a
"""
import random

from teleop.channel import ChannelBase
from teleop.commands import VelocityCommand


class Link(ChannelBase):
    def __init__(self, config):
        super().__init__(config)
        self.queue = []

    def send(self, msg, now):
        # >>> NEW in a): the message arrives delay_s later
        arrival_time = now + self.delay_s

        self.queue.append((arrival_time, msg))

    def receive(self, now):
        arrived = []
        waiting = []
        for arrival_time, msg in self.queue:
            # >>> NEW in a): hand out only what has arrived, keep the rest
            if arrival_time <= now:
                arrived.append(msg)
            else:
                waiting.append((arrival_time, msg))
        self.queue = waiting
        return arrived


COMMAND_TIMEOUT_S = 0.5


def watchdog(cmd, age_s):
    return cmd          # d) not implemented yet
