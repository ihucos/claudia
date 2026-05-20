from rich.console import Console
import functools
import os
import sys
import subprocess
from io import StringIO

from .constants import DUMMY_DIR, CODEBLOCK, ESCAPED_CODEBLOCK

console = Console()


#
# TO BE DELETED
#


def debug(text):
    if os.environ.get("CLAUDIA_DEBUG") in ["1", "true"]:
        console.print(text, style="dim")




def trim_code_blocks_magic(fname, content):
    """Remove surrounding code block markers from content if present."""
    content = content.rstrip("\n`")
    content = content.lstrip("\n")

    content_lines = content.splitlines()
    if content_lines and content_lines[0].startswith("```"):
        content = "\n".join(content_lines[1:])

    if not content.endswith("\n"):
        content += "\n"

    return content




