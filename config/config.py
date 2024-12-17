import importlib
import os

import dotenv

from config.types import Configuration


def get_config() -> Configuration:
    dotenv.load_dotenv()

    chain = os.environ.get("NETWORK")
    assert chain in ["songbird", "flare", "coston", "coston2"], (
        f"invalid chain {chain}, should be one of "
        "['coston', 'songbird', 'coston2', 'flare']"
    )

    return importlib.import_module(f".{chain}", "config").get_config()
