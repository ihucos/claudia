from claudia import Claudia
from .utils import TestClaudiaMixin


class Claudia(TestClaudiaMixin, Claudia):
    pass


def test_does_not_fail():
    claudia = Claudia()
    claudia.start()
