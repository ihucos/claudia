import subprocess
import llm


class DevBox:
    def __init__(self, *, volume, base_image):
        self.volume = volume
        self.base_image = base_image

    @property
    def name(self):
        return f"claudia-{str(self.volume).replace('/', '_')}-{self.base_image}"

    def start_or_create(self):
        if not self.exists():
            self.create()
        else:
            self.start()

    def exists(self):
        existing_containers = subprocess.run(
            ["docker", "ps", "-a", "--format", "{{.Names}}"],
            text=True,
            check=True,
            capture_output=True,
        ).stdout.splitlines()
        return self.name in existing_containers

    def start(self):
        subprocess.run(
            ["docker", "start", self.name],
            check=True,
            capture_output=True,
        )

    def create(self):
        subprocess.run(
            [
                "docker",
                "run",
                "-dti",
                "--volume",
                f"{self.volume}:/app",
                "--name",
                self.name,
                self.base_image,
            ],
            check=True,
            capture_output=True,
        )

    def run(self, cmd):
        return subprocess.run(
            [
                "docker",
                "exec",
                "--workdir",
                "/app",
                self.name,
            ]
            + cmd,
            capture_output=True,
            text=True,
        )


class DevBoxToolbox(llm.Toolbox):
    def __init__(self, *, ui, devbox):
        self.ui = ui
        self.devbox = devbox
        proc = self.cmd("true", "Test cmd")
        assert proc["exit_status"] == 0, proc

    def cmd(self, shell_cmd, step_description):
        proc = self.devbox.run(["/bin/sh", "-c", shell_cmd])
        return {
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "exit_status": proc.returncode,
        }
