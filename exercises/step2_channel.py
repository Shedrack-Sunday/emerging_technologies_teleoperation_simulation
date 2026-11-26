"""STEP 2 - The communication channel: delay, jitter, packet loss.

Between operator and robot there are two channels (uplink for commands, downlink
for camera and telemetry). Both are instances of the class below. The framework
calls

    send(msg, now)    when a message is transmitted
    receive(now)      every 10 ms; return all messages that have ARRIVED by `now`

`now` is the simulation time in seconds. Each message has
    msg.topic   e.g. "camera/image", "nav/pose", "cmd/velocity"
    msg.size    size on the wire in bytes (a camera frame is ~80 kB!)
    msg.stamp   time the message was created
    msg.reliable  True for topics that must arrive (events, goals)

The current settings are in self.config (set on the command line, e.g.
`python3 run.py --step 2 --delay 1000 --jitter 200 --loss 5`):
    self.config.delay_ms, self.config.jitter_ms, self.config.loss, self.config.mtu

TODO (step 2):
  a) Constant delay: a message sent at `now` arrives at now + delay.
     Hint: store (arrival_time, msg) in a list or a heap (module `heapq`).
  b) Jitter: add a random extra delay per message (e.g. uniform in [0, jitter]).
     Question: can messages now overtake each other? Is that realistic? Is it a
     problem for camera images? For commands?
  c) Packet loss: a message is split into ceil(msg.size / mtu) packets. Each
     packet is lost with probability config.loss. If one packet is lost, the
     whole message is lost - UNLESS msg.reliable is True: then it is
     re-transmitted, which costs one extra round trip (2 * delay) per attempt.
     Question: why are big camera frames hit much harder than small telemetry?

Also in this file:
  d) The onboard command watchdog (see `watchdog` below).

Run with:   python3 run.py --step 2
Check with: python3 check.py 2
"""
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
        self.in_flight = []        # e.g. a heap of (arrival_time, counter, msg)
        self.counter = 0           # tie-breaker for the heap

    def send(self, msg: Message, now: float) -> None:
        delay_s = self.config.delay_ms / 1000.0
        # TODO a) compute the arrival time and store the message
        # TODO b) jitter
        # TODO c) packet loss
        arrival = now  # <- replace
        heapq.heappush(self.in_flight, (arrival, self.counter, msg))
        self.counter += 1

    def receive(self, now: float) -> list[Message]:
        arrived = []
        # TODO a) return only the messages whose arrival time is <= now
        while self.in_flight:
            _, _, msg = heapq.heappop(self.in_flight)
            arrived.append(msg)
        return arrived


# Onboard (robot side) safety feature, called every 10 ms on the robot.
COMMAND_TIMEOUT_S = 0.5


def watchdog(cmd: VelocityCommand, age_s: float) -> VelocityCommand:
    """TODO d) The robot executes the LAST velocity command it received.

    What happens if the link drops while the operator holds "w"? Try it before
    implementing this:  python3 run.py --step 2 --outage 5:3
    (link down for 3 s, starting 5 s after your first key press).

    age_s = time since the last velocity command arrived on the robot.
    Return a safe command (all zero) if the last command is too old.
    """
    return cmd
