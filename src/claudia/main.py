import argparse

from .backends.agent import run as agent_run
from .backends.echo import run as echo_run
from .backends.coder import run as coder_run

from .ui import UI
from . import models


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