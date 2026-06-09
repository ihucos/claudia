import llm
from pathlib import Path
import os
import sys
from contextlib import contextmanager
import sys
import shutil
import traceback
from functools import wraps


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


def handle_errors(func):
    """Decorator to unify and standardize file operation exception handling."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except DisallowedFilenameError:
            return {"error": "Disallowed filename"}
        except FileNotFoundError:
            return {"error": "File not found"}
        except OSError as exc:
            return {"error": f"{type(exc).__name__}: {exc}"}
        except Exception:
            # Unexpected exception
            traceback.print_exc(file=sys.stderr)
            sys.exit(1)

    return wrapper


class CoderToolbox(llm.Toolbox):
    def __init__(self, *, ui, workdir, model):
        self.ui = ui
        self.workdir = Path(workdir).resolve()
        self.model = model

    def _resolve_and_verify(self, filename: str | Path) -> Path:
        """Resolves a filename relative to workdir and ensures it stays inside it."""
        target_path = (self.workdir / filename).resolve()
        if not target_path.is_relative_to(self.workdir):
            raise DisallowedFilenameError(f"Bad filename: {filename}")
        return target_path

    @handle_errors
    def _read_file(self, filename: str) -> str:
        target = self._resolve_and_verify(filename)
        return target.read_text(encoding="utf-8")

    @handle_errors
    def read_files(self, filenames: list[str], step_description: str) -> dict[str, any]:
        if not isinstance(filenames, list):
            return {"error": "filenames must be a list"}

        return {name: self._read_file(name) for name in filenames}

    @handle_errors
    def write_file(self, filename: str, content: str, step_description: str):
        target = self._resolve_and_verify(filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    @handle_errors
    def copy(self, path: str, dest: str, step_description: str):
        src_target = self._resolve_and_verify(path)
        dest_target = self._resolve_and_verify(dest)
        if src_target.is_dir():
            shutil.copytree(src_target, dest_target, dirs_exist_ok=True)
        else:
            shutil.copy(src_target, dest_target)

    @handle_errors
    def move(self, path: str, dest: str, step_description: str):
        src_target = self._resolve_and_verify(path)
        dest_target = self._resolve_and_verify(dest)
        shutil.move(src_target, dest_target)

    @handle_errors
    def delete(self, path: str, step_description: str):
        target = self._resolve_and_verify(path)
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()

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

