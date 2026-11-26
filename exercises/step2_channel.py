"""STEP 2 - The communication link: delay, jitter, loss.

Between you and Int-Ball there are two links: the UPLINK carries your commands
to the robot, the DOWNLINK carries camera images and telemetry back to you.
Both use the class Link below. The lab calls

    link.send(msg, now)    whenever a message is sent
    link.receive(now)      every 10 ms: return the messages that have ARRIVED

`now` is the time in seconds. The link settings come from the command line:

    self.delay_s    delay in seconds                --delay 1000  (ms)
    self.jitter_s   largest extra random delay (s)  --jitter 300  (ms)
    self.loss       probability that a message is lost (0..1)   --loss 20  (%)

TODO (step 2):
  a) Delay: in send(), store each message with the time it will arrive.
     In receive(), hand out only the messages whose arrival time has come.
     Test: python3 run.py --step 2 --delay 1000
           -> the link monitor shows ~1000 ms latency
  b) Jitter: add a random extra delay between 0 and self.jitter_s
     (random.uniform(a, b)).   Test: --delay 500 --jitter 300
     Question: messages can now overtake each other. Is that a problem for
     camera images? For commands?
  c) Loss: with probability self.loss the message is lost - don't store it
     (random.random() returns a number between 0 and 1).   Test: --loss 20
  d) Watchdog: see the function at the bottom of this file.

Bonus:
  e) Big messages are sent as several packets of 1200 bytes (msg.size is the
     size in bytes). If ONE packet is lost, the whole message is lost.
     Why does the camera image suffer much more than the telemetry?

Run with:   python3 run.py --step 2
Check with: python3 check.py 2
"""
import random

from teleop.channel import ChannelBase
from teleop.commands import VelocityCommand


class Link(ChannelBase):
    def __init__(self, config):
        super().__init__(config)
        self.queue = []                    # messages on their way: (arrival_time, msg)

    def send(self, msg, now):
        # for steps a-c, hint: check base class - self.delay_s, self.jitter_s and self.loss are provided by ChannelBase
        arrival_time = now                 # TODO a) delay    TODO b) jitter
        # TODO c) loss
        self.queue.append((arrival_time, msg))

    def receive(self, now):
        arrived = []                       # messages to hand out now
        waiting = []                       # messages still on their way
        for arrival_time, msg in self.queue:
            # TODO a) only messages whose arrival_time has come have arrived
            arrived.append(msg)
        self.queue = waiting
        return arrived


COMMAND_TIMEOUT_S = 0.5


def watchdog(cmd, age_s):
    """TODO d) Runs on the robot every 10 ms. Int-Ball keeps executing the LAST
    command it received - what if the link breaks while you hold "w"?
    Try it first:  python3 run.py --step 2 --outage 5:3
    (link down for 3 s, starting 5 s after your first key press)

    age_s = how long ago the last command arrived (seconds).
    If it is older than COMMAND_TIMEOUT_S, return VelocityCommand() (= stop).
    """
    return cmd
