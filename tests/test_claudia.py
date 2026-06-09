from claudia import Claudia
from .utils import TestClaudiaMixin
import tempfile


class Claudia(TestClaudiaMixin, Claudia):
    pass


def test_does_not_fail():
    with tempfile.TemporaryDirectory() as app_dir:
        claudia = Claudia(app_dir=app_dir)
        claudia.start()
