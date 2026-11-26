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


def load(step: int, use_solutions: set[int] | None = None, all_solutions: bool = False) -> Implementation:
    use_solutions = use_solutions or set()

    def src(n: int) -> str:
        if all_solutions or n in use_solutions:
            return "solutions"
        return "exercises" if step >= n else "builtin"

    sources = {1: src(1), 2: src(2)}

    # Step 1: keyboard mapping (needed to fly at all -> reference before step 1)
    pkg1 = "solutions" if sources[1] == "builtin" else sources[1]
    if sources[1] == "builtin":
        sources[1] = "solutions"
    keys_to_command = _module(pkg1, "step1_command_mapping").keys_to_command

    # Step 2: channel + watchdog
    if sources[2] == "builtin":
        channel_cls, watchdog = IdealChannel, _identity_watchdog
    else:
        m2 = _module(sources[2], "step2_channel")
        channel_cls, watchdog = m2.StudentChannel, m2.watchdog

    return Implementation(step, sources, keys_to_command, channel_cls, watchdog)
