# Space Robotics Teleop Simulation

Hands-on exercises on teleoperation for the THA course *Emerging Technologies*.
You fly JAXA's free-flying camera robot **Int-Ball2** through the Japanese
module *Kibo* of the ISS - first directly, then over a link with delay, jitter
and packet loss.

![How the browser and the Python code work together](docs/architecture.svg)

The browser is only the operator station: it sends the keys you hold and shows
what arrives over the downlink. Everything else runs in Python - your code
(orange) sits between the keyboard and the robot. The camera image is drawn by
the browser's GPU from the robot's true pose, then goes back to Python and through
the downlink like any other sensor message.

## Setup

You need **Python 3.10 or newer** and **Chrome or Firefox**.

```bash
git clone <repo-url> teleop-lab
cd teleop-lab
python3 -m pip install -r requirements.txt      # numpy, aiohttp, Pillow
python3 run.py --step 0
```

> **Windows:** type `python` (or `py`) instead of `python3` in all commands.

Open <http://localhost:8080>. Click once into the page, then fly with the keyboard.
Keep the terminal next to the browser: experiment settings, and
errors from your code show up there.

## Steps

| Step | Run | You implement | Check |
|---|---|---|---|
| 0 Tour | `python3 run.py --step 0` | nothing - fly through Kibo to the gap above the airlock at the far end | |
| 1 Direct teleop | `python3 run.py --step 1` | `exercises/step1_command_mapping.py` | `python3 check.py 1` |
| 2 The channel | `python3 run.py --step 2 --delay 1000` | `exercises/step2_channel.py` | `python3 check.py 2` |
| 3 Feel the delay | `python3 run.py --step 3 --delay 0` (then 300, 1000, 3000) | experiment: do the inspection task at each delay | <http://localhost:8080/results> |

Stuck on a step? `python3 run.py --step 3 --solution 2` uses the reference
channel so you can continue.

### Step 2 sub-task by sub-task

After each sub-task, restart with the command from the table and check what
you see in the operator station. (Step 1 not finished? Add `--solution 1` so
you can fly.)

| Sub-task | Run | What you should see |
|---|---|---|
| a) Delay | `python3 run.py --step 2 --delay 1000` | link monitor: ~1000 ms latency; *image age* ~1 s; a key press shows in the image after ~2 s |
| b) Jitter | `python3 run.py --step 2 --delay 500 --jitter 300` | latency varies between 500 and 800 ms; the image arrives unevenly |
| c) Loss | `python3 run.py --step 2 --loss 20` | ~20 % loss on all topics in the link monitor; flying still works |
| d) Watchdog | `python3 run.py --step 2 --outage 5:3` | hold W: the link drops 5 s after your first key press. Before d), Int-Ball keeps flying; after d), it stops 0.5 s after the link drops (see below) |
| e) Bonus: packets | `python3 run.py --step 2 --loss 5` | telemetry loses ~5 %, the camera almost everything; compare with `--loss 5 --camera 320x240 --quality 50` |

Check all sub-tasks at once with `python3 check.py 2`.

**What `--outage 5:3` means (sub-task d):** `START:DURATION` in seconds. 5 s
after your first key press (not the program start, so you have time to get
ready), the link goes down for 3 s - in both directions: no commands reach the
robot, no images or telemetry reach you. Messages sent in that time are lost,
not delayed. After 8 s the link works normally again.

1. Hold W from the start. At 5 s the link drops; release W at about 6 s.
2. Without the watchdog: your release ("stop") never arrives - Int-Ball keeps
   executing its last "forward" until the link is back at 8 s. You only notice
   afterwards, when the images catch up (or after a collision).
3. With the watchdog: Int-Ball notices that no command has arrived for 0.5 s
   and stops by itself, at about 5.5 s.

During the outage, *image age* climbs and NO SIGNAL appears; *cmd age* freezes,
because the telemetry carrying it is cut off too, and briefly shows a high value
when the link is back. The option can be repeated, e.g.
`--outage 5:3 --outage 15:1`.

**What `--loss 5` means (sub-task e):** a 5 % loss chance - but *per what*
depends on your code. With c) alone, each **message** is lost with 5 %, small
or large. With e), each **1200-byte packet** is lost with 5 %, and a message
only arrives if all its packets do (probability 0.95ⁿ for n packets):

| Message | Packets | Arrives |
|---|---|---|
| telemetry, commands (~150 B) | 1 | 95 % |
| camera 320×240, quality 50 (~10 kB) | ~9 | ~63 % |
| camera 800×600, quality 75 (~82 kB, default) | ~69 | ~3 % |

The same link that barely touches the telemetry almost kills the camera -
smaller images survive much better.

## The operator station

The browser page is the system you work on: it shows only what an operator of
the real Int-Ball would see - everything that came down the (simulated) link.

| Element | What it shows |
|---|---|
| **Main camera** | JPEG frames from Int-Ball's front camera after the downlink. Top right: resolution, size per frame, frame rate as received. *image age*: how old the picture is (now − time it was taken). *NO SIGNAL*: no frame for 1.5 s. |
| **Telemetry** (below the camera) | From `nav/pose`, `status` and `range`: position, speed, attitude, battery, collisions, *cmd age* (how long ago the robot received its last command). The numbers are averaged and refreshed 4× per second. Bars: distance to the nearest surface in six directions - red below 0.15 m. |
| **3D view** | A model of Int-Ball placed at the last *received* pose inside Kibo, with its trail. *follow* keeps the view behind the robot. |
| **Link monitor** | Per topic, measured over the last 2 s: messages per second, data rate, latency (receive time − send time) and loss. ↓ downlink (robot → you), ↑ uplink (you → robot). |
| **Events & faults** | Collisions reported by the robot, and exceptions raised by your code (file and line). |
| **Status bar** | Connection to Python, the velocity command your `keys_to_command` produced, and the keys currently held. |

## Command line

Everything about the experiment is set when you start the code. To change a
setting, press Ctrl+C and start again - the open browser tab reconnects by
itself. `python3 run.py --help` lists all options.

| Option | Meaning |
|---|---|
| `--step N` | exercise step 0..3 |
| `--solution 1,2` | use the reference solution for these exercises; with a letter only up to that sub-task, e.g. `--solution 2b` = delay + jitter (files in `solutions/step1/`, `solutions/step2/`) |
| `--delay MS`, `--jitter MS`, `--loss PCT` | link properties (from step 2 on - before that the link is ideal) |
| `--outage START:DUR` | link down for DUR seconds, START seconds after your first key press; can be repeated |
| `--camera WxH`, `--fps F`, `--quality Q`, `--gray` | camera stream (default 800x600, 10 fps, JPEG quality 75) |
| `--course` | timed inspection task (always on in step 3, see below) |
| `--truth` | show the simulator's ground truth in the 3D view (not available in reality) |

## The inspection task (step 3)

Int-Ball's job on the ISS is to film for the ground team. Your task: fly from
the hatch to the far end of Kibo and into the narrow **gap above the JEM
airlock**, between the airlock and the ceiling. Face the end wall and hold still
there for 2 s. The clock starts with your first key press; the terminal tells
you when you are in position and prints the result (time, collisions, path
length, idle time, number of waits), which is also saved to `results/runs.csv`.

## Controls

| Key | Motion | Key | Motion |
|---|---|---|---|
| W / S | forward / back | Q / E | yaw left / right |
| A / D | left / right | ↑ / ↓ | look up / down |
| R / F | up / down | | |

## Repository layout

```
run.py            start the lab
check.py          automatic checks for your exercises
exercises/        <- your code goes here
teleop/           framework: simulation, robot side, operator side, server
web/              operator UI (three.js)
assets/intball2/  Int-Ball2 3D model (JAXA)
results/          your course runs (CSV)
```

## Credits

Int-Ball2 model and inertia parameters: JAXA, from the
[Int-Ball2 simulator](https://github.com/jaxa/int-ball2_simulator).
Kibo interior: cut out of an ISS interior model with `tools/build_kibo.py`
3D rendering: [three.js](https://threejs.org) (MIT).
