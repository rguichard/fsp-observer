import importlib
import os

import dotenv

from configuration.types import Configuration


def get_config() -> Configuration:
    dotenv.load_dotenv()

    network = os.environ.get("NETWORK")
    assert network in ["songbird", "flare", "coston", "coston2"], (
        f"invalid network {network}, should be one of "
        "['coston', 'songbird', 'coston2', 'flare']"
    )

    return importlib.import_module(f".{network}", "configuration.configs").get_config()
