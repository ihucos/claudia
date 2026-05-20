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








