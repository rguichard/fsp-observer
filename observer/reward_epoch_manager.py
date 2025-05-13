import time

from attrs import define
from eth_typing import ChecksumAddress
from py_flare_common.fsp.messaging.types import (
    FdcSubmit1,
    FdcSubmit2,
    FtsoSubmit1,
    FtsoSubmit2,
    ParsedPayload,
    SubmitSignatures,
)

from configuration.types import Configuration

from .types import (
    ProtocolMessageRelayed,
    RandomAcquisitionStarted,
    SigningPolicyInitialized,
    VotePowerBlockSelected,
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
        self.identity_address = address

    def voter_registered_event(self, e: VoterRegistered):
        if e.voter != self.identity_address:
            return
        self.submit_address = e.submit_address
        self.submit_signatures_address = e.submit_signatures_address
        self.signing_policy_address = e.signing_policy_address

    def voter_registration_info_event(self, e: VoterRegistrationInfo):
        if e.voter != self.identity_address:
            return
        self.delegation_address = e.delegation_address


@define
class SigningPolicy:
    reward_epoch: int
    threshold: int
    start_voting_round_id: int
    fully_set_up: bool

    # keys are identity addresses
    voters: dict[ChecksumAddress, RegisteredVoter]
    weights: dict[ChecksumAddress, int]

    # signing_policy_address -> identity address
    spa_to_ia: dict[ChecksumAddress, ChecksumAddress]

    def __init__(self, reward_epoch_id: int):
        self.reward_epoch = reward_epoch_id
        self.fully_set_up = False
        self.voters = {}
        self.weights = {}
        self.spa_to_ia = {}

    def update_signing_policy_initialized_event(self, e: SigningPolicyInitialized):
        self.threshold = e.threshold
        self.start_voting_round_id = e.start_voting_round_id
        self.fully_set_up = True

        # addresses in e.voters are signing policy addresses
        for i, voter in enumerate(e.voters):
            # as VoterRegisteredEvent and VoterRegistrationInfo always come in
            # the same block, we only need to check if one (VRE) is missing
            if voter not in self.spa_to_ia:
                self.fully_set_up = False
                break

            ia = self.spa_to_ia[voter]
            self.weights[ia] = e.weights[i]

    def update_voter_registered_event(self, e: VoterRegistered):
        ia = e.voter
        spa = e.signing_policy_address

        if ia not in self.voters:
            self.voters[ia] = RegisteredVoter(e.voter)
        self.voters[ia].voter_registered_event(e)

        self.spa_to_ia[spa] = ia

    def update_voter_registration_info_event(self, e: VoterRegistrationInfo):
        ia = e.voter

        if ia not in self.voters:
            self.voters[ia] = RegisteredVoter(e.voter)
        self.voters[ia].voter_registration_info_event(e)

    def update_voter_removed_event(self, e: VoterRemoved):
        ia = e.voter
        self.voters.pop(ia, None)
        self.weights.pop(ia, None)

    def voter_weight(self, identity_address: ChecksumAddress):
        w = self.weights.get(identity_address, 0)
        p = round(w / sum(self.weights.values()), 8)
        return w, p


@define
class VotingEpochInfo:
    id: int

    # ftso
    ftso_mr: tuple[int, str]
    ftso_s1: dict[ChecksumAddress, ParsedPayload[FtsoSubmit1]]
    ftso_s2: dict[ChecksumAddress, ParsedPayload[FtsoSubmit2]]
    ftso_ss: dict[ChecksumAddress, ParsedPayload[SubmitSignatures]]

    # fdc
    fdc_mr: tuple[int, str]
    fdc_s1: dict[ChecksumAddress, ParsedPayload[FdcSubmit1]]
    fdc_s2: dict[ChecksumAddress, ParsedPayload[FdcSubmit2]]
    fdc_ss: dict[ChecksumAddress, ParsedPayload[SubmitSignatures]]

    def __init__(self, id: int):
        self.id = id
        self.ftso_mr = (0, "")
        self.fdc_mr = (0, "")
        self.ftso_s1 = {}
        self.ftso_s2 = {}
        self.ftso_ss = {}
        self.fdc_s1 = {}
        self.fdc_s2 = {}
        self.fdc_ss = {}

    def add_protocol_message_relayed_event(self, e: ProtocolMessageRelayed, ts: int):
        match e.protocol_id:
            case 100:
                self.ftso_mr = ts, e.merkle_root
            case 200:
                self.fdc_mr = ts, e.merkle_root


@define
class RewardEpochInfo:
    id: int

    signing_policy: SigningPolicy | None
    vote_power_block_selected: int | None
    random_acquisition_started: bool

    def __init__(self, id: int):
        self.id = id
        self.random_acquisition_started = False
        self.vote_power_block_selected = None
        self.signing_policy = None

    def add_signing_policy(self, policy: SigningPolicy):
        self.signing_policy = policy

    def add_vote_power_block_selected_event(self, e: VotePowerBlockSelected):
        self.vote_power_block_selected = e.vote_power_block

    def add_random_acquisition_started_event(self, e: RandomAcquisitionStarted):
        self.random_acquisition_started = True

    def status(self, config: Configuration) -> str | None:
        ts_now = int(time.time())
        next_expected_ts = config.epoch.reward_epoch(self.id + 1).start_s

        # current reads
        ras = self.random_acquisition_started
        vpbs = self.vote_power_block_selected
        sp = self.signing_policy

        if not ras:
            return "collecting offers"

        if ras and vpbs is None:
            return "selecting snapshot"

        if vpbs is not None and sp is None:
            return "voter registration"

        if sp is not None:
            svrs = config.epoch.voting_epoch(sp.start_voting_round_id).start_s
            if svrs > ts_now:
                return "ready for start"

            # here svrs < ts_now
            if next_expected_ts > ts_now:
                return "active"

            if next_expected_ts < ts_now:
                return "extended"


@define
class EpochManager:
    reward_epochs: dict[int, RewardEpochInfo]
    voting_epochs: dict[int, VotingEpochInfo]

    def __init__(self):
        self.reward_epochs = {}
        self.voting_epochs = {}
