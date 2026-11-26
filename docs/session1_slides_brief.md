# Slide brief: Hands-on 1, Teleoperation in Simulation

Input for creating student-facing slides. Everything below is content; the
slide structure at the end is a suggestion.

## Context

- **Course:** Emerging Technologies, TH Augsburg (Master)
- **Session:** 27.11.2026, 90 minutes, hands-on on the students' own laptops

## The robot: JAXA Int-Ball

- **What it is:** Int-Ball ("JEM Internal Ball Camera") is a small free-flying camera robot from the Japan Aerospace Exploration Agency (JAXA). It flies inside *Kibo*, the Japanese Experiment Module (JEM) of the International Space Station.
- **Why it exists:** astronauts spend a significant share of their working time taking photos and videos of experiments. Int-Ball takes over that job and is **teleoperated by flight controllers on the ground** at JAXA's Tsukuba Space Center. Ground teams can look at what they need without taking crew time.
- **Int-Ball (first generation):** arrived on the ISS in 2017. It is a ball of about 15 cm that moves with small electric fans and carries a camera.
- **Int-Ball2:** arrived in 2023. It is a larger ball of about 20 cm and roughly 3 kg, with better navigation and a docking station for automatic recharging. JAXA intends it as a platform that other users can run their own software on. JAXA has published an open-source simulator for it.
- **In our lab:** we fly a simulated **Int-Ball2**, using its 3D model and mass properties from JAXA's simulator, inside a 3D model of the real Kibo module. Like the real robot, it has no gravity to fight; it floats and is pushed by fans.
- **Why it suits teleoperation:**
  - The operator sits far from the robot and sees only what comes down a communication link: camera images and telemetry.
  - Commands go up the same link.
  - Delay, jitter and data loss are real issues for space operations.
- Link to the original [JAXA Int-ball 2 simulator](https://github.com/jaxa/int-ball2_simulator)

## Learning goals/Tasks

1. Explain the structure of a teleoperation system: operator side, communication channel (uplink and downlink), and robot side with an onboard controller and safety functions.
2. Implement direct (rate) control: map operator input to a velocity command.
3. Model a communication channel with delay, jitter and packet loss, and implement a command watchdog.
4. Describe from their own measurements how time delay changes operator performance and strategy (the "move and wait" behaviour).

## Preparation (students)

Ideally done before the session; otherwise in the first 10 minutes.

- **Needed:** a laptop with **Python 3.10 or newer** and **Chrome or Firefox**. Nothing else: no ROS, no game engine, no GPU drivers.
- **Setup commands:**
  ```bash
  git clone <repo-url>
  cd <repo-name>
  python3 -m pip install -r requirements.txt     # numpy, aiohttp, Pillow
  python3 run.py --step 0
  ```
  On Windows: `python` (or `py`) instead of `python3`.
- **Open the station:** go to <http://localhost:8080> in the browser, click once into the page, and fly with the keyboard.
- **Without a local Python:** open the repository on GitHub, then *Code* → *Codespaces* → *Create codespace*. Run the same commands there and open the forwarded port 8080.
- **Working setup:** keep the **terminal next to the browser**. The terminal shows the settings, task results and errors from the students' code.
- **If the camera shows "NO SIGNAL":** reload the page. If that doesn't help, restart the browser.

## How the lab works

Diagram: `docs/architecture.svg` in the repository; please use it on a slide.

- **Browser (operator station):** sends the keys being held and displays what arrives over the downlink.
- **Python side:** everything else runs here.
  - **Operator side:** the keyboard mapping.
  - **Simulated link:** uplink and downlink with delay, jitter and loss.
  - **Robot side:** command watchdog, velocity controller driving the fans, physics with collisions, sensors, and camera with JPEG compression.
- **Message streams (topics, similar to ROS):**
  - **Downlink:** `camera/image` (10 Hz, about 80 kB per frame), `nav/pose` (20 Hz), `imu` (50 Hz), `range` (10 Hz), `status`, `events`.
  - **Uplink:** `cmd/velocity` (20 Hz).
- **Students' code** lives in `exercises/`. It sits exactly between the keyboard and the robot.
- **Settings:** the browser page is the system being worked on. Experiment settings (delay, loss, camera) are command-line options of `run.py`, not buttons in the GUI. To change one, press Ctrl+C and restart; the browser tab reconnects by itself.

### The operator station (what students see)

- **Main camera:** the image *after* the downlink, shown with its **image age** (how old the picture is) and the received frame rate. NO SIGNAL appears when no image has arrived for 1.5 s.
- **Telemetry:** position, speed, attitude, battery, collisions, and command age (how long ago the robot received its last command). Six bars show the distance to the nearest surface around the robot.
- **3D view:** the robot model at the last *received* position inside Kibo.
- **Link monitor:** rate, data rate, latency and loss per topic.
- **Events & faults:** collisions, and exceptions from the students' code.

### Keyboard controls

| Key | Motion | Key | Motion |
|---|---|---|---|
| W / S | forward / back | Q / E | turn left / right |
| A / D | left / right | ↑ / ↓ | look up / down |
| R / F | up / down | Shift (hold) | fine mode (slow) |

## Tasks

### Step 0: Tour (about 10 min, no code)

`python3 run.py --step 0`

- **Do:** fly through Kibo with the reference keyboard mapping over a perfect link. Try fine mode, bump into a cargo bag, and watch the link monitor.
- **Observe:** the camera stream needs about 6–7 Mbit/s, far more than all other data combined.

### Step 1: Direct teleoperation (about 20 min)

- **File:** `exercises/step1_command_mapping.py`, function `keys_to_command(keys)`
- **Run:** `python3 run.py --step 1`. The robot does not move until the function is implemented.
- **Check:** `python3 check.py 1` (12 automatic checks)
- **Tasks:**
  - a) Translation: W/S, A/D, R/F → vx, vy, vz at the maximum speed.
  - b) Rotation: Q/E → yaw rate, arrow keys → pitch rate. Watch the sign: positive pitch rate tilts the nose *down*.
  - c) Fine mode: while Shift is held, scale everything down.
  - d) Diagonals (W + A) must not be faster than the maximum speed, so normalise the vector.
- **Concept:** rate control. Holding a key commands a velocity, and the robot's onboard controller tracks it.

### Step 2: The communication channel (about 30 min)

- **File:** `exercises/step2_channel.py`, class `StudentChannel` with `send(msg, now)` and `receive(now)`, plus the function `watchdog(...)`
- **Run:** for example `python3 run.py --step 2 --delay 1000`
- **Check:** `python3 check.py 2` (9 automatic checks)
- **Tasks:**
  - a) **Constant delay:** a message sent at time t arrives at t + delay. Hint: a priority queue (`heapq`). Success: the link monitor shows about 1000 ms latency.
  - b) **Jitter** (`--jitter 300`): add a random extra delay per message. *Question:* messages can now overtake each other. Is that a problem for camera images, and for commands?
  - c) **Packet loss** (`--loss 5`): a message is split into packets of at most 1200 bytes, and one lost packet loses the whole message. Messages marked *reliable* are re-sent instead, at the cost of an extra round trip. *Question:* why are camera frames hit much harder than telemetry?
  - d) **Watchdog** (on the robot): the robot keeps executing the last command it received. First try `--outage 5:3`, which cuts the link for 3 s, 5 s after the first key press, while holding W. Then implement the watchdog: if the last command is older than 0.5 s, stop.

### Step 3: Feel the delay (about 20 min, experiment)

- **Task (inspection):** fly from the hatch to the **JEM airlock** at the far end of Kibo. Stop 0.5–1 m in front of it, facing it, and hold still for 2 s. This mirrors what Int-Ball does for ground teams.
- **Run once per delay:**
  ```bash
  python3 run.py --step 3 --delay 0    --team <name>
  python3 run.py --step 3 --delay 300  --team <name>
  python3 run.py --step 3 --delay 1000 --team <name>
  python3 run.py --step 3 --delay 3000 --team <name>
  ```
  The clock starts with the first key press. The terminal reports when the robot is in position and then prints the result.
- **Measured per run:** task time, collisions, path length, idle share (time without input) and number of "waits" (pauses longer than 0.5 s).
- **Compare:** all runs side by side at <http://localhost:8080/results>.
- **Fallback:** if a team's channel from step 2 isn't working, `--solution 2` uses the reference channel.
- **Expected observation:** with growing delay, operators switch to *move and wait*: a short input, then waiting for the image to catch up. Task time grows much faster than the delay itself.

### Discussion (about 10 min)

- How did your strategy change with 3 s delay?
- What would help the operator? Possible ideas:
  - showing where the robot *will* be (predictive display)
  - letting the robot keep its distance from walls on its own
  - giving goals instead of velocities (supervisory control)
- Outlook: how much of the camera stream do we really need? This leads to 11.12, designing under bandwidth limits.

## Suggested slide outline

1. Title: Teleoperation hands-on 1
2. Int-Ball: a camera drone inside the ISS (photo, purpose, ground operation)
3. What we build today: learning goals and the 4 steps
4. Setup (commands, Codespaces fallback, terminal next to browser)
5. Architecture of the lab (diagram `docs/architecture.svg`)
6. The operator station: GUI elements and key controls
7. Step 0: Tour
8. Step 1: Keyboard to velocity command (tasks a–d, check command)
9. Step 2: The channel (delay, jitter, loss, watchdog, with the two questions)
10. Step 3: Feel the delay (inspection task, the 4 runs, results page)
11. Discussion and outlook to 04.12 and 11.12

## Notes for the slide author

- Do **not** put solution code on the slides; students write it themselves.
- `<repo-url>` is not yet known; leave it as a placeholder.
- Use JAXA's public Int-Ball and Int-Ball2 images only with their image credit.
- Facts to double-check before showing them: Int-Ball arrival 2017 and Int-Ball2 arrival 2023; Int-Ball2 size and mass (about 20 cm, about 3.3 kg in our model); the statement about crew time spent on photography.
