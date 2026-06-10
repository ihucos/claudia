import llm
from pathlib import Path
import shutil
from functools import wraps


class DisallowedFilenameError(Exception):
    pass


def _as_error(exc: Exception) -> dict:
    """Map a caught exception to a standard error dict for LLM consumption.

    This is the single source of truth for how exceptions are reported
    to the LLM. Both the ``handle_errors`` decorator and the per-item
    error handling in ``read_files`` delegate to this function to stay
    consistent and avoid duplication.
    """
    if isinstance(exc, DisallowedFilenameError):
        return {"error": "Disallowed filename"}
    if isinstance(exc, FileNotFoundError):
        return {"error": "File not found"}
    if isinstance(exc, OSError):
        return {"error": f"{type(exc).__name__}: {exc}"}
    # Unexpected exception - return error to LLM instead of crashing
    return {"error": f"Unexpected {type(exc).__name__}: {exc}"}


def handle_errors(func):
    """Decorator to catch and standardise exceptions via ``_as_error``.

    Methods that need per-item granularity (like ``read_files``) should
    call ``_as_error`` directly instead of using this decorator.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            return _as_error(exc)

    return wrapper


class CoderToolbox(llm.Toolbox):
    """Toolbox for file system operations.

    Provides tools for reading, writing, copying, moving and deleting files
    within a sandboxed working directory.
    """

    tool_prefix = "coder"

    def __init__(self, *, ui, workdir):
        self.ui = ui
        self.workdir = Path(workdir).resolve()

    def _resolve_and_verify(self, filename: str | Path) -> Path:
        """Resolves a filename relative to workdir and ensures it stays inside it."""
        target_path = (self.workdir / filename).resolve()
        if not target_path.is_relative_to(self.workdir):
            raise DisallowedFilenameError(f"Bad filename: {filename}")
        return target_path

    def read_files(self, filenames: list[str], step_description: str) -> dict[str, any]:
        """Read multiple files, returning per-file results or errors.

        Each file is handled independently so a single missing file does
        not prevent reading the rest.
        """
        if not isinstance(filenames, list):
            return {"error": "filenames must be a list"}

        results = {}
        for name in filenames:
            try:
                target = self._resolve_and_verify(name)
                results[name] = target.read_text(encoding="utf-8")
            except Exception as exc:
                results[name] = _as_error(exc)
        return results

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
