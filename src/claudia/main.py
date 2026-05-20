from .backends.agent import run as agent_run
from .backends.echo import run as echo_run
from .backends.coder import run as coder_run

from .ui import UI
from . import models


def main():
    ui = UI.from_env()
    model = models.DeepSeekChat("deepseek-v4-flash")
    model.supports_tools = True
    with ui:
        # agent_run(model=model, ui=ui)
        # echo_run(model=model, ui=ui)
        # echo_run(model=model, ui=ui)
        coder_run(model=model, ui=ui)
