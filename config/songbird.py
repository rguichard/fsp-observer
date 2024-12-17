import os

from py_flare_common.fsp.epoch.timing.songbird import (
    reward_epoch,
    reward_epoch_factory,
    voting_epoch,
    voting_epoch_factory,
)

from .types import Configuration, Epoch


def get_config() -> Configuration:
    epoch = Epoch(
        voting_epoch=voting_epoch,
        reward_epoch=reward_epoch,
        voting_epoch_factory=voting_epoch_factory,
        reward_epoch_factory=reward_epoch_factory,
    )

    config = Configuration(
        identity_address=os.environ["IDENTITY_ADDRESS"],
        chain=("songbird", 19),
        rpc_ws_url=os.environ["RPC_WS_URL"],
        epoch=epoch,
        discord_webhook=os.environ["DISCORD_WEBHOOK"]
    )

    return config
