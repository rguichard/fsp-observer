from attrs import frozen
from eth_typing import ChecksumAddress


@frozen
class ProtocolMessageRelayed:
    protocol_id: int
    voting_round_id: int
    is_secure_random: bool
    merkle_root: str


@frozen
class SigningPolicyInitialized:
    reward_epoch_id: int
    start_voting_round_id: int
    threshold: int
    seed: int
    voters: list[ChecksumAddress]
    weights: list[int]
    signing_policy_bytes: str
    timestamp: int


@frozen
class VoterRegistered:
    reward_epoch_id: int
    voter: ChecksumAddress
    signing_policy_address: ChecksumAddress
    submit_address: ChecksumAddress
    submit_signatures_address: ChecksumAddress
    public_key: str
    registration_weight: int


@frozen
class VoterRemoved:
    reward_epoch_id: int
    voter: ChecksumAddress


@frozen
class VoterRegistrationInfo:
    reward_epoch_id: int
    voter: ChecksumAddress
    delegation_address: ChecksumAddress
    delegation_fee_bips: int
    w_nat_weight: int
    w_nat_capped_weight: int
    node_ids: list[str]
    node_weights: list[int]


@frozen
class VotePowerBlockSelected:
    reward_epoch_id: int
    vote_power_block: int
    timestamp: int


@frozen
class RandomAcquisitionStarted:
    reward_epoch_id: int
    timestamp: int
