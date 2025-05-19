import enum
import logging
import time
from typing import Self

import requests
from attrs import define
from eth_account._utils.signing import to_standard_v
from eth_keys.datatypes import Signature as EthSignature
from py_flare_common.fsp.epoch.epoch import RewardEpoch
from py_flare_common.fsp.messaging import (
    parse_generic_tx,
    parse_submit1_tx,
    parse_submit2_tx,
    parse_submit_signature_tx,
)
from py_flare_common.fsp.messaging.byte_parser import ByteParser
from py_flare_common.fsp.messaging.types import ParsedPayload
from py_flare_common.fsp.messaging.types import Signature as SSignature
from py_flare_common.ftso.commit import commit_hash
from web3 import AsyncWeb3
from web3._utils.events import get_event_data
from web3.middleware import ExtraDataToPOAMiddleware

from configuration.types import Configuration
from observer.reward_epoch_manager import (
    Entity,
    SigningPolicy,
    VotingRound,
    VotingRoundManager,
    WTxData,
)
from observer.types import (
    ProtocolMessageRelayed,
    RandomAcquisitionStarted,
    SigningPolicyInitialized,
    VotePowerBlockSelected,
    VoterRegistered,
    VoterRegistrationInfo,
    VoterRemoved,
)

LOGGER = logging.getLogger(__name__)
logging.basicConfig(level="INFO")
LOGGER.info("initialized")


class Signature(EthSignature):
    @classmethod
    def from_vrs(cls, s: SSignature) -> Self:
        return cls(
            vrs=(
                to_standard_v(int(s.v, 16)),
                int(s.r, 16),
                int(s.s, 16),
            )
        )


def notify_discord(config: Configuration, message: str) -> None:
    if config.discord_webhook is None:
        return

    requests.post(
        config.discord_webhook,
        headers={"Content-Type": "application/json"},
        json={"content": message},
    )


async def find_voter_registration_blocks(
    w: AsyncWeb3,
    current_block_id: int,
    reward_epoch: RewardEpoch,
) -> tuple[int, int]:
    # there are roughly 3600 blocks in an hour
    avg_block_time = 3600 / 3600
    current_ts = int(time.time())

    # find timestamp that is more than 2h30min (=9000s) before start_of_epoch_ts
    target_start_ts = reward_epoch.start_s - 9000
    start_diff = current_ts - target_start_ts

    start_block_id = current_block_id - int(start_diff / avg_block_time)
    block = await w.eth.get_block(start_block_id)
    assert "timestamp" in block
    d = block["timestamp"] - target_start_ts
    while abs(d) > 600:
        start_block_id -= 100 * (d // abs(d))
        block = await w.eth.get_block(start_block_id)
        assert "timestamp" in block
        d = block["timestamp"] - target_start_ts

    # end timestamp is 1h (=3600s) before start_of_epoch_ts
    target_end_ts = reward_epoch.start_s - 3600
    end_diff = current_ts - target_end_ts
    end_block_id = current_block_id - int(end_diff / avg_block_time)

    block = await w.eth.get_block(end_block_id)
    assert "timestamp" in block
    d = block["timestamp"] - target_end_ts
    while abs(d) > 600:
        end_block_id -= 100 * (d // abs(d))
        block = await w.eth.get_block(end_block_id)
        assert "timestamp" in block
        d = block["timestamp"] - target_end_ts

    return (start_block_id, end_block_id)


async def get_signing_policy_events(
    w: AsyncWeb3,
    config: Configuration,
    reward_epoch: RewardEpoch,
    start_block: int,
    end_block: int,
) -> SigningPolicy:
    # reads logs for given blocks for the informations about the signing policy

    builder = SigningPolicy.builder().for_epoch(reward_epoch)

    contracts = [
        config.contracts.VoterRegistry,
        config.contracts.FlareSystemsCalculator,
        config.contracts.Relay,
        config.contracts.FlareSystemsManager,
    ]

    event_names = {
        # relay
        "SigningPolicyInitialized",
        # flare systems calculator
        "VoterRegistrationInfo",
        # flare systems manager
        "RandomAcquisitionStarted",
        "VotePowerBlockSelected",
        "VoterRegistered",
        "VoterRemoved",
    }
    event_signatures = {
        e.signature: e
        for c in contracts
        for e in c.events.values()
        if e.name in event_names
    }

    block_logs = await w.eth.get_logs(
        {
            "address": [contract.address for contract in contracts],
            "fromBlock": start_block,
            "toBlock": end_block,
        }
    )

    for log in block_logs:
        sig = log["topics"][0]

        if sig.hex() not in event_signatures:
            continue

        event = event_signatures[sig.hex()]
        data = get_event_data(w.eth.codec, event.abi, log)

        match event.name:
            case "VoterRegistered":
                e = VoterRegistered.from_dict(data["args"])
            case "VoterRemoved":
                e = VoterRemoved.from_dict(data["args"])
            case "VoterRegistrationInfo":
                e = VoterRegistrationInfo.from_dict(data["args"])
            case "SigningPolicyInitialized":
                e = SigningPolicyInitialized.from_dict(data["args"])
            case "VotePowerBlockSelected":
                e = VotePowerBlockSelected.from_dict(data["args"])
            case "RandomAcquisitionStarted":
                e = RandomAcquisitionStarted.from_dict(data["args"])
            case x:
                raise ValueError(f"Unexpected event {x}")

        builder.add(e)

        # signing policy initialized is the last event that gets emitted
        if event.name == "SigningPolicyInitialized":
            break

    return builder.build()


class IssueLevel(enum.Enum):
    DEBUG = 10
    INFO = 20


@define
class Issue:
    level: IssueLevel
    message: str


def log_issue(config, issue: Issue):
    LOGGER.log(issue.level.value, issue.message)
    notify_discord(config, issue.level.name + " " + issue.message)


def extract[T](
    payloads: list[tuple[ParsedPayload[T], WTxData]],
    round: int,
    time_range: range,
) -> tuple[ParsedPayload[T], WTxData] | None:
    if not payloads:
        return

    latest: tuple[ParsedPayload[T], WTxData] | None = None

    for pl, wtx in payloads:
        if pl.voting_round_id != round:
            continue
        if not (time_range.start <= wtx.timestamp < time_range.stop):
            continue

        if latest is None or wtx.timestamp > latest[1].timestamp:
            latest = (pl, wtx)

    return latest


def validate_ftso(round: VotingRound, entity: Entity):
    epoch = round.voting_epoch
    ftso = round.ftso
    finalization = ftso.finalization

    _submit1 = ftso.submit_1.by_identity.get(entity.identity_address, [])
    submit_1 = extract(_submit1, epoch.id, range(epoch.start_s, epoch.end_s))

    _submit2 = ftso.submit_2.by_identity.get(entity.identity_address, [])
    submit_2 = extract(
        _submit2, epoch.id, range(epoch.next.start_s, epoch.next.reveal_deadline())
    )

    sig_deadline = max(
        epoch.next.start_s + 55, (finalization and finalization.timestamp) or 0
    )
    _submit_sig = ftso.submit_signatures.by_identity.get(entity.identity_address, [])
    submit_sig = extract(
        _submit_sig,
        epoch.id,
        range(epoch.next.reveal_deadline(), sig_deadline),
    )

    # TODO:(matej) check for transactions that happened too late (or too early)

    issues = []

    s1 = submit_1 is not None
    s2 = submit_2 is not None
    ss = submit_sig is not None

    if not s1:
        issues.append(
            Issue(
                IssueLevel.INFO,
                f"no submit1 transaction for ftso in round {epoch.id}",
            )
        )

    if s1 and not s2:
        issues.append(
            Issue(
                # TODO:(matej) change level to critical
                IssueLevel.INFO,
                (
                    "no submit2 transaction for ftso in round"
                    f"{epoch.id}, causing reveal offence"
                ),
            ),
        )

    if s2:
        indices = [
            str(i) for i, v in enumerate(submit_2[0].payload.values) if v is None
        ]

        if indices:
            issues.append(
                Issue(
                    # TODO:(matej) change level to warning
                    IssueLevel.INFO,
                    (
                        "submit 2 had 'None' value for feeds on indices "
                        f"{', '.join(indices)} in round {epoch.id}"
                    ),
                ),
            )

    if s1 and s2:
        # TODO:(matej) should just build back from parsed message
        bp = ByteParser(parse_generic_tx(submit_2[1].input).ftso.payload)  # type: ignore
        rnd = bp.uint256()
        feed_v = bp.drain()

        hashed = commit_hash(entity.submit_address, epoch.id, rnd, feed_v)

        if submit_1[0].payload.commit_hash.hex() != hashed:
            issues.append(
                Issue(
                    # TODO:(matej) change level to critical
                    IssueLevel.INFO,
                    (
                        "commit hash and reveal didn't match in round "
                        f"{epoch.id}, causing reveal offence"
                    ),
                ),
            )

    if not ss:
        issues.append(
            Issue(
                # TODO:(matej) change level to warning
                IssueLevel.INFO,
                ("no submit signatures transaction for ftso in round " f"{epoch.id}"),
            ),
        )

    if finalization and ss:
        s = Signature.from_vrs(submit_sig[0].payload.signature)
        addr = s.recover_public_key_from_msg_hash(
            finalization.to_message()
        ).to_checksum_address()

        if addr != entity.signing_policy_address:
            issues.append(
                Issue(
                    # TODO:(matej) change level to warning
                    IssueLevel.INFO,
                    (
                        "submit signatures signature doesn't match finalization for "
                        f"ftso in round {epoch.id}"
                    ),
                ),
            )

    return issues


def validate_fdc(round: VotingRound, entity: Entity):
    epoch = round.voting_epoch
    fdc = round.fdc
    finalization = fdc.finalization

    _submit1 = fdc.submit_1.by_identity.get(entity.identity_address, [])
    submit_1 = extract(_submit1, epoch.id, range(epoch.start_s, epoch.end_s))

    _submit2 = fdc.submit_2.by_identity.get(entity.identity_address, [])
    submit_2 = extract(
        _submit2, epoch.id, range(epoch.next.start_s, epoch.next.reveal_deadline())
    )

    sig_deadline = max(
        epoch.next.start_s + 55, (finalization and finalization.timestamp) or 0
    )
    _submit_sig = fdc.submit_signatures.by_identity.get(entity.identity_address, [])
    submit_sig = extract(
        _submit_sig,
        epoch.id,
        range(epoch.next.reveal_deadline(), sig_deadline),
    )

    # TODO:(matej) check for transactions that happened too late (or too early)

    issues = []

    s1 = submit_1 is not None
    s2 = submit_2 is not None
    ss = submit_sig is not None

    if not s1:
        # NOTE:(matej) this is expected behaviour in fdc
        pass

    if not s2:
        issues.append(
            Issue(
                IssueLevel.INFO,
                f"no submit2 transaction for fdc in round {epoch.id}",
            ),
        )

    if s2:
        # TODO:(matej) analize request array and report unprovden errors
        ...

    if s2 and not ss:
        # TODO:(matej) check if submit2 bitvote dominated consensus bitvote
        issues.append(
            Issue(
                # TODO:(matej) change level to critical
                IssueLevel.INFO,
                (
                    "no submit signatures transaction for fdc in round"
                    f"{epoch.id}, causing reveal offence"
                ),
            ),
        )

    if not ss:
        issues.append(
            Issue(
                # TODO:(matej) change level to critical
                IssueLevel.INFO,
                ("no submit signatures transaction for fdc in round " f"{epoch.id}"),
            ),
        )

    if finalization and ss:
        s = Signature.from_vrs(submit_sig[0].payload.signature)
        addr = s.recover_public_key_from_msg_hash(
            finalization.to_message()
        ).to_checksum_address()

        if addr != entity.signing_policy_address:
            issues.append(
                Issue(
                    # TODO:(matej) change level to warning
                    IssueLevel.INFO,
                    (
                        "submit signatures signature doesn't match finalization for "
                        f"fdc in round {epoch.id}"
                    ),
                ),
            )

    return issues


async def observer_loop(config: Configuration) -> None:
    w = AsyncWeb3(
        AsyncWeb3.AsyncHTTPProvider(config.rpc_url),
        middleware=[ExtraDataToPOAMiddleware],
    )

    # reasignments for quick access
    ve = config.epoch.voting_epoch
    # re = config.epoch.reward_epoch
    vef = config.epoch.voting_epoch_factory
    ref = config.epoch.reward_epoch_factory

    # get current voting round and reward epoch
    block = await w.eth.get_block("latest")
    assert "timestamp" in block
    assert "number" in block
    reward_epoch = ref.from_timestamp(block["timestamp"])
    voting_epoch = vef.from_timestamp(block["timestamp"])

    # we first fill signing policy for current reward epoch

    # voter registration period is 2h before the reward epoch and lasts 30min
    # find block that has timestamp approx. 2h30min before the reward epoch
    # and block that has timestamp approx. 1h before the reward epoch
    lower_block_id, end_block_id = await find_voter_registration_blocks(
        w, block["number"], reward_epoch
    )

    # get informations for events that build the current signing policy
    signing_policy = await get_signing_policy_events(
        w,
        config,
        reward_epoch,
        lower_block_id,
        end_block_id,
    )
    spb = SigningPolicy.builder()

    # print("Signing policy created for reward epoch", current_rid)
    # print("Reward Epoch object created", reward_epoch_info)
    # print("Current Reward Epoch status", reward_epoch_info.status(config))

    # set up target address from config
    tia = w.to_checksum_address(config.identity_address)
    # target_voter = signing_policy.entity_mapper.by_identity_address[tia]
    # notify_discord(
    #     config,
    #     f"flare-observer initialized\n\n"
    #     f"chain: {config.chain}\n"
    #     f"submit address: {target_voter.submit_address}\n"
    #     f"submit signatures address: {target_voter.submit_signatures_address}\n",
    #     # f"this address has voting power of: {signing_policy.voter_weight(tia)}\n\n"
    #     # f"starting in voting round: {voting_round.next.id} "
    #     # f"(current: {voting_round.id})\n"
    #     # f"current reward epoch: {current_rid}",
    # )

    # wait until next voting epoch
    block_number = block["number"]
    while True:
        latest_block = await w.eth.block_number
        if block_number == latest_block:
            time.sleep(2)
            continue

        block_number += 1
        block_data = await w.eth.get_block(block_number)

        assert "timestamp" in block_data

        _ve = vef.from_timestamp(block_data["timestamp"])
        if _ve == voting_epoch.next:
            voting_epoch = voting_epoch.next
            break

    vrm = VotingRoundManager(voting_epoch.previous.id)

    # set up contracts and events (from config)
    # TODO: (nejc) set this up with a function on class
    # or contracts = attrs.asdict(config.contracts) <- this doesn't work
    contracts = [
        config.contracts.Relay,
        config.contracts.VoterRegistry,
        config.contracts.FlareSystemsManager,
        config.contracts.FlareSystemsCalculator,
    ]
    event_signatures = {e.signature: e for c in contracts for e in c.events.values()}

    # start listener
    # print("Listener started from block number", block_number)
    # check transactions for submit transactions
    target_function_signatures = {
        config.contracts.Submission.functions[
            "submitSignatures"
        ].signature: "submitSignatures",
        config.contracts.Submission.functions["submit1"].signature: "submit1",
        config.contracts.Submission.functions["submit2"].signature: "submit2",
    }

    while True:
        latest_block = await w.eth.block_number
        if block_number == latest_block:
            time.sleep(2)
            continue

        for block in range(block_number, latest_block):
            LOGGER.debug(f"processing {block}")
            block_data = await w.eth.get_block(block, full_transactions=True)
            assert "transactions" in block_data
            assert "timestamp" in block_data
            block_ts = block_data["timestamp"]

            voting_epoch = vef.from_timestamp(block_ts)

            if (
                spb.signing_policy_initialized is not None
                and spb.signing_policy_initialized.start_voting_round_id == voting_epoch
            ):
                # TODO:(matej) this could fail if the observer is started during
                # last two hours of the reward epoch
                signing_policy = spb.build()
                spb = SigningPolicy.builder().for_epoch(
                    signing_policy.reward_epoch.next
                )

            block_logs = await w.eth.get_logs(
                {
                    "address": [contract.address for contract in contracts],
                    "fromBlock": block,
                    "toBlock": block,
                }
            )

            for log in block_logs:
                sig = log["topics"][0]

                if sig.hex() in event_signatures:
                    event = event_signatures[sig.hex()]
                    data = get_event_data(w.eth.codec, event.abi, log)
                    match event.name:
                        case "ProtocolMessageRelayed":
                            e = ProtocolMessageRelayed.from_dict(
                                data["args"], block_data
                            )
                            voting_round = vrm.get(ve(e.voting_round_id))
                            if e.protocol_id == 100:
                                voting_round.ftso.finalization = e
                            if e.protocol_id == 200:
                                voting_round.fdc.finalization = e

                        case "SigningPolicyInitialized":
                            e = SigningPolicyInitialized.from_dict(data["args"])
                            spb.add(e)
                        case "VoterRegistered":
                            e = VoterRegistered.from_dict(data["args"])
                            spb.add(e)
                        case "VoterRemoved":
                            e = VoterRemoved.from_dict(data["args"])
                            spb.add(e)
                        case "VoterRegistrationInfo":
                            e = VoterRegistrationInfo.from_dict(data["args"])
                            spb.add(e)
                        case "VotePowerBlockSelected":
                            e = VotePowerBlockSelected.from_dict(data["args"])
                            spb.add(e)
                        case "RandomAcquisitionStarted":
                            e = RandomAcquisitionStarted.from_dict(data["args"])
                            spb.add(e)

            for tx in block_data["transactions"]:
                assert not isinstance(tx, bytes)
                wtx = WTxData.from_tx_data(tx, block_data)

                called_function_sig = wtx.input[:4].hex()
                input = wtx.input[4:].hex()
                sender_address = wtx.from_address
                entity = signing_policy.entity_mapper.by_omni.get(sender_address)
                if entity is None:
                    continue

                if called_function_sig in target_function_signatures:
                    mode = target_function_signatures[called_function_sig]
                    match mode:
                        case "submit1":
                            try:
                                parsed = parse_submit1_tx(input)
                                if parsed.ftso is not None:
                                    vrm.get(
                                        ve(parsed.ftso.voting_round_id)
                                    ).ftso.insert_submit_1(entity, parsed.ftso, wtx)
                                if parsed.fdc is not None:
                                    vrm.get(
                                        ve(parsed.fdc.voting_round_id)
                                    ).fdc.insert_submit_1(entity, parsed.fdc, wtx)
                            except Exception:
                                pass

                        case "submit2":
                            try:
                                parsed = parse_submit2_tx(input)
                                if parsed.ftso is not None:
                                    vrm.get(
                                        ve(parsed.ftso.voting_round_id)
                                    ).ftso.insert_submit_2(entity, parsed.ftso, wtx)
                                if parsed.fdc is not None:
                                    vrm.get(
                                        ve(parsed.fdc.voting_round_id)
                                    ).fdc.insert_submit_2(entity, parsed.fdc, wtx)
                            except Exception:
                                pass

                        case "submitSignatures":
                            try:
                                parsed = parse_submit_signature_tx(input)
                                if parsed.ftso is not None:
                                    vrm.get(
                                        ve(parsed.ftso.voting_round_id)
                                    ).ftso.insert_submit_signatures(
                                        entity, parsed.ftso, wtx
                                    )
                                if parsed.fdc is not None:
                                    vrm.get(
                                        ve(parsed.fdc.voting_round_id)
                                    ).fdc.insert_submit_signatures(
                                        entity, parsed.fdc, wtx
                                    )
                            except Exception:
                                pass

            rounds = vrm.finalize(block_data)
            for r in rounds:
                for i in validate_ftso(
                    r, signing_policy.entity_mapper.by_identity_address[tia]
                ):
                    log_issue(config, i)
                for i in validate_fdc(
                    r, signing_policy.entity_mapper.by_identity_address[tia]
                ):
                    log_issue(config, i)

        block_number = latest_block
