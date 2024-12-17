import asyncio

from config.config import get_config
from config.types import Configuration
from observer.observer import observer_loop


def main(config: Configuration):
    asyncio.run(observer_loop(config))


if __name__ == "__main__":
    config = get_config()
    main(config)
