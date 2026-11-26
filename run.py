#!/usr/bin/env python3
"""Start the Int-Ball teleoperation lab.

    python3 run.py --step 0          tour: fly Int-Ball with the keyboard
    python3 run.py --step 1          use YOUR keyboard mapping (exercises/step1_*.py)
    python3 run.py --step 2          + YOUR channel (exercises/step2_*.py)
    python3 run.py --step 3          feel-the-delay experiment (timed inspection task)

The browser page is the operator station. Everything about the experiment
(link, camera, timed task) is set here on the command line. To change a
setting, stop with Ctrl+C and start again - the open browser tab reconnects.

Examples:
    python3 run.py --step 2 --delay 1000 --jitter 200 --loss 5
    python3 run.py --step 2 --outage 5:3            link down 5..8 s after the first key press
    python3 run.py --step 3 --delay 3000
    python3 run.py --step 3 --solution 2 --delay 300
    python3 run.py --step 2 --solution 1,2b       reference up to task 2b (delay + jitter)
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def outage(s: str) -> tuple[float, float]:
    try:
        start, dur = (float(x) for x in s.split(":"))
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected START:DURATION in seconds, e.g. 5:3 (got {s!r})")
    return start, dur


def resolution(s: str) -> tuple[int, int]:
    try:
        w, h = (int(x) for x in s.lower().split("x"))
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected WIDTHxHEIGHT, e.g. 640x480 (got {s!r})")
    return w, h


def main():
    if sys.version_info < (3, 10):
        sys.exit("Python 3.10 or newer is required (you have %d.%d)." % sys.version_info[:2])
    try:
        import aiohttp  # noqa: F401
        import numpy  # noqa: F401
        import PIL  # noqa: F401
    except ImportError as e:
        sys.exit(f"Missing package: {e.name}.  Run:  python3 -m pip install -r requirements.txt")

    from teleop import student
    from teleop.lab import Lab
    from teleop.server import serve

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--step", type=int, default=0, help="exercise step 0..3 (default 0)")
    ap.add_argument("--solution", default="", metavar="N[,N]",
                    help="use the reference solution instead of your code: 1, 2 or both (1,2); "
                         "a letter stops after that sub-task, e.g. 2b = delay + jitter")
    ap.add_argument("--all-solutions", action="store_true", help=argparse.SUPPRESS)

    g = ap.add_argument_group("link (needs your channel from step 2 on)")
    g.add_argument("--delay", type=float, default=0.0, metavar="MS", help="one-way delay in ms")
    g.add_argument("--jitter", type=float, default=0.0, metavar="MS", help="random extra delay in ms")
    g.add_argument("--loss", type=float, default=0.0, metavar="PCT", help="packet loss in percent")
    g.add_argument("--outage", type=outage, action="append", default=[], metavar="START:DUR",
                   help="link down for DUR s, START s after the first key press (repeatable)")

    g = ap.add_argument_group("camera on Int-Ball")
    g.add_argument("--camera", type=resolution, default=None, metavar="WxH", help="resolution (default 800x600)")
    g.add_argument("--fps", type=float, default=None, help="frame rate (default 10)")
    g.add_argument("--quality", type=int, default=None, metavar="Q", help="JPEG quality 1..95 (default 75)")
    g.add_argument("--gray", action="store_true", help="grayscale images")

    g = ap.add_argument_group("timed task")
    g.add_argument("--course", action="store_true",
                   help="timed inspection task: fly to the airlock at the end of Kibo and hold still "
                        "in front of it; the clock starts with the first key press (always on in step 3)")
    g.add_argument("--truth", action="store_true",
                   help="show the simulator's ground truth in the 3D view (not available in reality)")

    g = ap.add_argument_group("server")
    g.add_argument("--port", type=int, default=8080)
    g.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()

    try:
        sol = student.parse_solutions(a.solution)
    except ValueError as e:
        ap.error(str(e))
    impl = student.load(a.step, sol, a.all_solutions)
    lab = Lab(impl, results_dir=ROOT / "results", course=a.course or a.step >= 3,
              outages=a.outage, show_truth=a.truth, log=lambda *x: print(*x, flush=True))
    lab.set_channel({"delay_ms": a.delay, "jitter_ms": a.jitter, "loss": a.loss / 100.0})
    cam = {}
    if a.camera:
        cam["width"], cam["height"] = a.camera
    if a.fps is not None:
        cam["fps"] = a.fps
    if a.quality is not None:
        cam["quality"] = a.quality
    if a.gray:
        cam["grayscale"] = True
    lab.robot.camera.update(cam)
    serve(lab, a.host, a.port)


if __name__ == "__main__":
    main()
