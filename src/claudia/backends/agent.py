import llm
import tempfile

from ..ui import UI
from ..models import DeepSeekChat
from .. import utils

import subprocess



# =========================

SYSOPS_SYSTEM_PROMPT = """
# Task
You are a SysOps agent.

## Notes
- You can delete any data you want as you are sandboxed.
- This is a temporary devbox.
- Install any tools you need.
- The project is at {workdir}.
- When possible, execute complete shell scripts rather than commands
- Read and maintain information usefull for future invocations at /sysops_breadcrumbs.txt to make future invocations of sysops more efficient.

## Project files
{project_files}
""".strip()


def get_tools(*, workdir, devbox, ui, model):
    return [
        CoderToolbox(ui=ui, workdir=workdir, model=model),
        RunnerToolbox(ui=ui, workdir=workdir, devbox=devbox),
    ]
