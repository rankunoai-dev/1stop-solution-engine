import re

import src


def test_package_exposes_a_semantic_version() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", src.__version__)
