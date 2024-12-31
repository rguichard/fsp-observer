from attrs import define
from eth_typing import ChecksumAddress

from observer.types import (
    SigningPolicyInitialized,
    VoterRegistered,
    VoterRegistrationInfo,
    VoterRemoved,
)


@define
class RegisteredVoter:
    identity_address: ChecksumAddress
    signing_policy_address: ChecksumAddress
    submit_address: ChecksumAddress
    submit_signatures_address: ChecksumAddress
    delegation_address: ChecksumAddress

    def __init__(self, address: ChecksumAddress):
        self.signing_policy_address = address

    def voter_registered_event(self, e: VoterRegistered):
        if e.signing_policy_address != self.signing_policy_address:
            return
        self.identity_address = e.voter
        self.submit_address = e.submit_address
        self.submit_signatures_address = e.submit_signatures_address

    def voter_registration_info_event(self, e: VoterRegistrationInfo):
        if e.voter != self.identity_address:
            return
        self.delegation_address = e.delegation_address


@define
class SigningPolicy:
    reward_epoch: int
    threshold: int

    signing_policy_addresses: dict[ChecksumAddress, ChecksumAddress]
    voters: dict[ChecksumAddress, RegisteredVoter]
    weights: dict[ChecksumAddress, int]

    def __init__(self, e: SigningPolicyInitialized):
        self.reward_epoch = e.reward_epoch_id
        self.threshold = e.threshold
        self.voters = {}
        self.weights = {}
        self.signing_policy_addresses = {}

        for i, voter in enumerate(e.voters):
            self.voters[voter] = RegisteredVoter(voter)
            self.weights[voter] = e.weights[i]

    def update_voter_registered_event(self, e: VoterRegistered):
        ia = e.voter
        spa = e.signing_policy_address
        self.voters[spa].voter_registered_event(e)
        self.signing_policy_addresses[ia] = spa

    def update_voter_registration_info_event(self, e: VoterRegistrationInfo):
        ia = e.voter
        spa = self.signing_policy_addresses[ia]
        self.voters[spa].voter_registration_info_event(e)

    def update_voter_removed_event(self, e: VoterRemoved):
        ia = e.voter
        spa = self.signing_policy_addresses[ia]
        self.voters.pop(spa, None)
        self.weights.pop(spa, None)


@define
class RewardEpochInfo:
    id: int
    signing_policy: SigningPolicy


@define
class RewardEpochManager:
    id: int
