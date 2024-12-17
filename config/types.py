from typing import Callable

from attrs import frozen
from py_flare_common.fsp.epoch.epoch import RewardEpoch, VotingEpoch
from py_flare_common.fsp.epoch.factory import RewardEpochFactory, VotingEpochFactory


@frozen
class Epoch:
    voting_epoch: Callable[[int], VotingEpoch]
    reward_epoch: Callable[[int], RewardEpoch]
    voting_epoch_factory: VotingEpochFactory
    reward_epoch_factory: RewardEpochFactory


@frozen
class Configuration:
    identity_address: str
    chain: tuple[str, int]
    rpc_ws_url: str
    epoch: Epoch
    discord_webhook: str
