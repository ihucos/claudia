import llm
from pathlib import Path
import os
import sys
from contextlib import contextmanager
import sys
import shutil
import traceback


@contextmanager
def die():
    try:
        yield
    except Exception:
        # Handle the exception exactly like your decorator did
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


class DisallowedFilenameError(Exception):
    pass


class CoderToolbox(llm.Toolbox):
    def __init__(self, *, ui, workdir, model):
        self.ui = ui
        self.workdir = workdir
        self.model = model

    def _check_filename(self, filename):
        filename = (Path(self.workdir) / Path(self.workdir)).resolve()
        if not filename.is_relative_to(self.workdir):
            raise DisallowedFilenameError(f"Bad filename: {filename}")

    def _read_file(self, filename: str):
        with die():
            self._check_filename(filename)
            # with self.ui.loading(f"Reading {filename}"):
            try:
                with open(os.path.join(self.workdir, filename), "r") as f:
                    return f.read()
            except FileNotFoundError:
                return {"error": "File not found"}
            except DisallowedFilenameError:
                return {"error": "Disallowed filename"}
            except OSError:
                return {"error": f"OSError: {filename}"}

    def read_files(self, filenames: list[str], step_description) -> dict[str, str]:
        with die(), self.ui.loading(step_description):
            files = {}
            for filename in filenames:
                files[filename] = self._read_file(filename)
            return files

    def write_file(self, filename: str, content: str, step_description: str):
        with die(), self.ui.loading(step_description):
            try:
                self._check_filename(filename)
            except DisallowedFilenameError:
                return {"error": "Disallowed filename"}
            with self.ui.loading(step_description):
                full_filename = os.path.join(self.workdir, filename)
                os.makedirs(os.path.dirname(full_filename), exist_ok=True)
                with open(full_filename, "w") as f:
                    f.write(content)

    def copy(self, path: str, dest: str, step_description: str):
        with die(), self.ui.loading(step_description):
            try:
                self._check_filename(path)
            except DisallowedFilenameError:
                return {"error": "Disallowed filename"}
            shutil.copy(path, dest)

    def move(self, path: str, dest: str, step_description: str):
        with die(), self.ui.loading(step_description):
            try:
                self._check_filename(path)
            except DisallowedFilenameError:
                return {"error": "Disallowed filename"}
            shutil.move(path, dest)

    def delete(self, path: str, step_description: str):
        with die(), self.ui.loading(step_description):
            try:
                self._check_filename(path)
            except DisallowedFilenameError:
                return {"error": "Disallowed filename"}
            try:
                shutil.rmtree(path)
            except OSError as exc:
                return {"error": str(exc)}

    # def coder(self, prompt: str, step_description: str):
    #     """
    #     This tool is used to do any code changes. It is optimized for implementation.
    #     It works best when given high level instructions.
    #     Use it to delegate bigger chunks of programming work. Coder cannot move, rename or delete files.
    #     You can use this tool first, then other editing capabilites for polishing the result.
    #     """
    #     with die():
    #         with self.ui.loading(step_description):
    #             from . import coder
    #
    #             files = coder.implement(
    #                 task=prompt,
    #                 context_files=coder.get_context_files(self.model, prompt),
    #                 model=self.model,
    #                 progress_cb=self.ui.loading,
    #             )
    #
    #             errors = {}
    #             for file, content in files.items():
    #                 os.makedirs(
    #                     os.path.dirname(os.path.join(self.workdir, file)), exist_ok=True
    #                 )
    #                 try:
    #                     with open(os.path.join(self.workdir, file), "w") as f:
    #                         f.write(content)
    #                 except OSError as exc:
    #                     errors[file] = str(exc)
    #             ret = f"Files changed: {', '.join(files.keys())}."
    #             if errors:
    #                 ret += f" Errors: {', '.join(errors.keys())}"
    #             return ret


class RunnerToolbox(llm.Toolbox):
    def __init__(self, *, ui, workdir, devbox):
        self.ui = ui
        self.workdir = workdir
        self.devbox = devbox
        # Sanity check
        proc = self.cmd("true", "Test cmd")
        assert proc["exit_status"] == 0, proc

    def cmd(self, shell_cmd, step_description):
        with die():
            with self.ui.loading(step_description):
                proc = self.devbox.run(["/bin/sh", "-c", shell_cmd])
                return {
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                    "exit_status": proc.returncode,
                }
