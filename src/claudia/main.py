from .backends.agent import run as agent_run

from .ui import UI
from . import models


def main():
    ui = UI.from_env()
    model = models.DeepSeekChat("deepseek-v4-flash")
    agent_run(model=model, ui=ui)
