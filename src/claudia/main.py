import argparse
import os
from pathlib import Path

from .backends.agent import run as agent_run
from .backends.echo import run as echo_run
from .backends.coder import run as coder_run

from .ui import UI
from . import models


def cd_git_root():
    current_dir = Path.cwd().resolve()
    for path in [current_dir] + list(current_dir.parents):
        git_dir = path / ".git"
        if git_dir.is_dir():
            os.chdir(path)


def main():
    parser = argparse.ArgumentParser(description="Claudia - AI assistant")
    parser.add_argument(
        "backend",
        nargs="?",
        choices=["agent", "echo", "coder"],
        default="coder",
        help="Select the backend to run (default: coder)",
    )
    args = parser.parse_args()

    cd_git_root()
    ui = UI.from_env()
    model = models.DeepSeekChat("deepseek-v4-flash")
    model.supports_tools = True

    backends = {
        "agent": agent_run,
        "echo": echo_run,
        "coder": coder_run,
    }

    with ui:
        backends[args.backend](model=model, ui=ui)

