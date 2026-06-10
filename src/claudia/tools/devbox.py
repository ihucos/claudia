import subprocess
import llm
import uuid


def _process_error(shell, message_prefix=""):
    """Build a descriptive error string when the container process dies.

    Inspects the (possibly dead) Popen object to extract the return
    code and includes it in the error message so the LLM has more
    context to act upon.
    """
    if shell is None:
        ret = "N/A (never started)"
    else:
        code = shell.poll()
        ret = str(code) if code is not None else "N/A (still running)"
    prefix = f"{message_prefix}: " if message_prefix else ""
    return f"[Process terminated] {prefix}return code: {ret}"


class DevBoxToolbox(llm.Toolbox):
    """LLM toolbox that hosts a single persistent Docker shell for running commands.

    Can be used as a context manager for deterministic cleanup::

        with DevBoxToolbox(volume=..., base_image=..., ui=...) as devbox:
            devbox.cmd("echo hello", "greeting")

    Also supports falling back to ``__del__`` for garbage collection scenarios.
    """

    tool_prefix = "shell"

    def __init__(self, *, ui, volume, base_image):
        self.ui = ui
        self._shell = None

        # Start the single persistent container immediately on init
        try:
            self._shell = subprocess.Popen(
                [
                    "docker",
                    "run",
                    "-i",
                    "--rm",
                    "--volume",
                    f"{volume}:/app",
                    "--workdir",
                    "/app",
                    base_image,
                    "sh",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=0,
            )

            # Verify the container shell is responsive
            if not self.cmd("true", "Verify shell").endswith("[Exit status: 0]"):
                raise RuntimeError("DevBox container shell did not start correctly")
        except BaseException:
            # Ensure the process is cleaned up if anything goes wrong
            self.close()
            raise

    def close(self):
        """Explicitly tear down the container process."""
        if self._shell is not None:
            try:
                self._shell.kill()
            except Exception:
                pass
            self._shell = None

    def cmd(self, shell_cmd: str, step_description: str):
        """Execute a shell command inside the persistent container.

        Returns the command output. The exit status line is included
        at the end (e.g. '[Exit status: 0]').

        If the process has terminated unexpectedly, returns a descriptive
        error message with the exit code so the LLM can act on it.
        """
        if self._shell is None:
            return _process_error(self._shell, "shell was never started")

        if self._shell.poll() is not None:
            return _process_error(self._shell, "shell died before command")

        token = f"END_{uuid.uuid4().hex}"

        # Ship command + token logic to the persistent shell stdin
        full_cmd = f"{shell_cmd}; echo \"[Exit status: $?]{token}\"\n"
        self._shell.stdin.write(full_cmd)
        self._shell.stdin.flush()

        # Read output line by line until the token line arrives
        output_lines = []
        while True:
            line = self._shell.stdout.readline()
            if not line:
                # Process died or pipe closed - token never arrived
                partial = "".join(output_lines)
                return partial + "\n" + _process_error(self._shell, "pipe closed during command")
            output_lines.append(line)
            if token in line:
                break

        output = "".join(output_lines)
        # Token appears only on the final status line. Split at that
        # position: everything before is the command output.
        idx = output.index(token)
        return output[:idx]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False  # Do not suppress exceptions

    def __del__(self):
        self.close()
