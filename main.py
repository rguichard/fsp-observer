import asyncio

import dotenv

from configuration.config import get_config
from configuration.types import Configuration
from observer.observer import observer_loop


def main(config: Configuration):
    asyncio.run(observer_loop(config))


if __name__ == "__main__":
    dotenv.load_dotenv()
    config = get_config()
    main(config)
