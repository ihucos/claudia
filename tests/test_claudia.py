from claudia import Claudia
from .utils import TestClaudiaMixin
from claudia import tools
import tempfile
from pathlib import Path

from functools import wraps


def patch(instance):
    def decorator(func):
        setattr(instance, func.__name__, func)

        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        return wrapper

    return decorator


class Claudia(TestClaudiaMixin, Claudia):
    pass


def test_does_not_fail():
    with tempfile.TemporaryDirectory() as app_dir:
        claudia = Claudia(app_dir=app_dir)

        @patch(claudia)
        def get_response(*, conversation, prompt):
            for t in claudia.tools:
                if isinstance(t, tools.CoderToolbox):
                    assert Path(t.workdir).resolve() == Path(claudia.app_dir).resolve()
                    t.write_file("test.txt", prompt, "test")
            return "file written"

        # claudia.get_response = fake_get_response

        claudia.start()
