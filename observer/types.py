from typing import Any, Self

from attrs import frozen
from eth_typing import ChecksumAddress
from web3.types import BlockData

from observer.utils import prefix_0x


@frozen
class ProtocolMessageRelayed:
    protocol_id: int
    voting_round_id: int
    is_secure_random: bool
    merkle_root: str
    timestamp: int

    @classmethod
    def from_dict(cls, d: dict[str, Any], block_data: BlockData) -> Self:
        assert "timestamp" in block_data

        return cls(
            protocol_id=int(d["protocolId"]),
            voting_round_id=int(d["votingRoundId"]),
            is_secure_random=d["isSecureRandom"],
            merkle_root=prefix_0x(d["merkleRoot"].hex()),
            timestamp=block_data["timestamp"],
        )


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

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        return cls(
            reward_epoch_id=int(d["rewardEpochId"]),
            start_voting_round_id=int(d["startVotingRoundId"]),
            threshold=int(d["threshold"]),
            seed=int(d["seed"]),
            voters=d["voters"],
            weights=[int(w) for w in d["weights"]],
            signing_policy_bytes=d["signingPolicyBytes"],
            timestamp=int(d["timestamp"]),
        )


@frozen
class VoterRegistered:
    reward_epoch_id: int
    voter: ChecksumAddress
    signing_policy_address: ChecksumAddress
    submit_address: ChecksumAddress
    submit_signatures_address: ChecksumAddress
    public_key: str
    registration_weight: int

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        return cls(
            reward_epoch_id=int(d["rewardEpochId"]),
            voter=d["voter"],
            signing_policy_address=d["signingPolicyAddress"],
            submit_address=d["submitAddress"],
            submit_signatures_address=d["submitSignaturesAddress"],
            public_key=d["publicKeyPart1"].hex() + d["publicKeyPart2"].hex(),
            registration_weight=int(d["registrationWeight"]),
        )


@frozen
class VoterRemoved:
    reward_epoch_id: int
    voter: ChecksumAddress

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        return cls(
            reward_epoch_id=int(d["rewardEpochId"]),
            voter=d["voter"],
        )


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

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        return cls(
            reward_epoch_id=int(d["rewardEpochId"]),
            voter=d["voter"],
            delegation_address=d["delegationAddress"],
            delegation_fee_bips=int(d["delegationFeeBIPS"]),
            w_nat_weight=int(d["wNatWeight"]),
            w_nat_capped_weight=int(d["wNatCappedWeight"]),
            node_ids=[n.hex() for n in d["nodeIds"]],
            node_weights=[int(w) for w in d["nodeWeights"]],
        )


@frozen
class VotePowerBlockSelected:
    reward_epoch_id: int
    vote_power_block: int
    timestamp: int

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        return cls(
            reward_epoch_id=int(d["rewardEpochId"]),
            vote_power_block=int(d["votePowerBlock"]),
            timestamp=int(d["timestamp"]),
        )


@frozen
class RandomAcquisitionStarted:
    reward_epoch_id: int
    timestamp: int

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Self:
        return cls(
            reward_epoch_id=int(d["rewardEpochId"]),
            timestamp=int(d["timestamp"]),
        )
