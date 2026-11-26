"""Loads the students' implementations (exercises/) or the reference ones (solutions/).

Rule: in step N, every exercise with number <= N comes from exercises/
(unless --solution k is given for it); later exercises are replaced by a
neutral built-in (ideal channel, no watchdog, ...) or by the reference
solution if the feature is needed to fly at all (keyboard mapping in step 0).
"""
from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from teleop.channel import ChannelBase, IdealChannel
from teleop.commands import VelocityCommand

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _identity_watchdog(cmd: VelocityCommand, age_s: float) -> VelocityCommand:
    return cmd


@dataclass
class Implementation:
    step: int
    sources: dict                       # exercise number -> "exercises" | "solutions" | "builtin"
    keys_to_command: Callable
    channel_cls: type[ChannelBase]
    watchdog: Callable


def _module(pkg: str, name: str):
    mod = importlib.import_module(f"{pkg}.{name}")
    return importlib.reload(mod)


# Reference solutions per sub-task (cumulative: "2c" = tasks a, b and c of step 2)
SUBSTEPS = {
    1: {"a": "step1.a_translation", "b": "step1.b_rotation", "c": "step1.c_speed_limit"},
    2: {"a": "step2.a_delay", "b": "step2.b_jitter", "c": "step2.c_loss", "d": "step2.d_watchdog",
        "e": "step2.e_packets"},
}
FULL = {1: "step1_command_mapping", 2: "step2_channel"}


def parse_solutions(text: str) -> dict[int, str]:
    """'1,2c' -> {1: '', 2: 'c'}   (empty string = complete solution)"""
    out = {}
    for tok in text.replace(" ", "").split(","):
        if not tok:
            continue
        n, sub = int(tok[0]), tok[1:].lower()
        if n not in FULL or (sub and sub not in SUBSTEPS[n]):
            raise ValueError(f"unknown solution {tok!r} - use e.g. 1, 2, 1b or 2c")
        out[n] = sub
    return out


def load(step: int, use_solutions: dict[int, str] | None = None, all_solutions: bool = False) -> Implementation:
    use_solutions = use_solutions or {}

    def src(n: int) -> str:
        if all_solutions:
            return "solutions"
        if n in use_solutions:
            return "solutions" + (f" {n}{use_solutions[n]}" if use_solutions[n] else "")
        return "exercises" if step >= n else "builtin"

    def module(n: int):
        s = sources[n]
        if s == "exercises":
            return _module("exercises", FULL[n])
        sub = s.split(" ")[1][1:] if " " in s else ""
        return _module("solutions", SUBSTEPS[n][sub] if sub else FULL[n])

    sources = {1: src(1), 2: src(2)}

    # Step 1: keyboard mapping (needed to fly at all -> reference before step 1)
    if sources[1] == "builtin":
        sources[1] = "solutions"
    keys_to_command = module(1).keys_to_command

    # Step 2: channel + watchdog
    if sources[2] == "builtin":
        channel_cls, watchdog = IdealChannel, _identity_watchdog
    else:
        m2 = module(2)
        channel_cls, watchdog = m2.Link, m2.watchdog

    return Implementation(step, sources, keys_to_command, channel_cls, watchdog)
