import subprocess
import llm
import uuid


class DevBoxToolbox(llm.Toolbox):
    """LLM toolbox that hosts a single persistent Docker shell for running commands."""

    def __init__(self, *, ui, volume, base_image):
        self.ui = ui

        # Start the single persistent container immediately on init
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
            stderr=subprocess.STDOUT,  # Combines stderr into stdout
            text=True,
            bufsize=0,
        )

        # Verify the container shell is responsive
        assert self.cmd("true", "Verify shell").endswith("[Exit status: 0]")

    def cmd(self, shell_cmd: str, step_description: str):
        """Execute a shell command inside the persistent container."""
        token = f"END_{uuid.uuid4().hex}"

        # Ship command + token logic to the persistent shell stdin
        full_cmd = f"""{shell_cmd}; echo "[Exit status: $?]{token}"\n"""
        self._shell.stdin.write(full_cmd)
        self._shell.stdin.flush()

        # Read stream character by character until token arrives
        output = ""
        while token not in output:
            if not (char := self._shell.stdout.read(1)):
                break
            output += char

        out, _ = output.split(token)
        return out

    def __del__(self):
        """Clean up and tear down the container when the toolbox is dropped."""
        if hasattr(self, "_shell") and self._shell is not None:
            try:
                self._shell.kill()
            except Exception:
                pass
