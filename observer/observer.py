import time

import requests
from py_flare_common.fsp.messaging import (
    parse_generic_tx,
    parse_submit1_tx,
    parse_submit2_tx,
    parse_submit_signature_tx,
)
from py_flare_common.fsp.messaging.byte_parser import ByteParser
from py_flare_common.ftso.commit import commit_hash
from web3 import AsyncWeb3
from web3._utils.events import get_event_data
from web3.middleware import ExtraDataToPOAMiddleware
from web3.types import TxData

from configuration.types import Configuration
from observer.reward_epoch_manager import (
    EpochManager,
    RewardEpochInfo,
    SigningPolicy,
    VotingEpochInfo,
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
from observer.utils import prefix_0x, un_prefix_0x


def notify_discord(config: Configuration, message: str) -> None:
    requests.post(
        config.discord_webhook,
        headers={"Content-Type": "application/json"},
        json={"content": message},
    )


async def find_voter_registration_blocks(
    config: Configuration, current_block_id: int, start_of_epoch_ts: int
) -> tuple[int, int]:
    w = AsyncWeb3(
        AsyncWeb3.WebSocketProvider(config.rpc_ws_url),
        middleware=[ExtraDataToPOAMiddleware],
    )
    await w.provider.connect()

    # there are roughly 3600 blocks in an hour
    avg_block_time = 3600 / 3600
    current_ts = int(time.time())

    # find timestamp that is more than 2h30min (=9000s) before start_of_epoch_ts
    target_start_ts = start_of_epoch_ts - 9000
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
    target_end_ts = start_of_epoch_ts - 3600
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


def fill_protocol_message_relayed(args):
    event = ProtocolMessageRelayed(
        protocol_id=int(args["protocolId"]),
        voting_round_id=int(args["votingRoundId"]),
        is_secure_random=args["isSecureRandom"],
        merkle_root=prefix_0x(args["merkleRoot"].hex()),
    )
    return event


def fill_signing_policy_initialized(args):
    event = SigningPolicyInitialized(
        reward_epoch_id=int(args["rewardEpochId"]),
        start_voting_round_id=int(args["startVotingRoundId"]),
        threshold=int(args["threshold"]),
        seed=int(args["seed"]),
        voters=args["voters"],
        weights=[int(w) for w in args["weights"]],
        signing_policy_bytes=args["signingPolicyBytes"],
        timestamp=int(args["timestamp"]),
    )
    return event


def fill_voter_registered(args):
    event = VoterRegistered(
        reward_epoch_id=int(args["rewardEpochId"]),
        voter=args["voter"],
        signing_policy_address=args["signingPolicyAddress"],
        submit_address=args["submitAddress"],
        submit_signatures_address=args["submitSignaturesAddress"],
        public_key=un_prefix_0x(args["publicKeyPart1"].hex())
        + un_prefix_0x(args["publicKeyPart2"].hex()),
        registration_weight=int(args["registrationWeight"]),
    )
    return event


def fill_voter_removed(args):
    event = VoterRemoved(
        reward_epoch_id=int(args["rewardEpochId"]),
        voter=args["voter"],
    )
    return event


def fill_voter_registration_info(args):
    event = VoterRegistrationInfo(
        reward_epoch_id=int(args["rewardEpochId"]),
        voter=args["voter"],
        delegation_address=args["delegationAddress"],
        delegation_fee_bips=int(args["delegationFeeBIPS"]),
        w_nat_weight=int(args["wNatWeight"]),
        w_nat_capped_weight=int(args["wNatCappedWeight"]),
        node_ids=[n.hex() for n in args["nodeIds"]],
        node_weights=[int(w) for w in args["nodeWeights"]],
    )
    return event


def fill_vote_power_block_selected(args):
    event = VotePowerBlockSelected(
        reward_epoch_id=int(args["rewardEpochId"]),
        vote_power_block=int(args["votePowerBlock"]),
        timestamp=int(args["timestamp"]),
    )
    return event


def fill_random_acquisition_started(args):
    event = RandomAcquisitionStarted(
        reward_epoch_id=int(args["rewardEpochId"]), timestamp=int(args["timestamp"])
    )
    return event


async def get_signing_policy_events(
    config: Configuration,
    reward_epoch_number: int,
    start_block: int,
    end_block: int,
    signing_policy: SigningPolicy,
    reward_epoch_info_object: RewardEpochInfo,
) -> None:
    # reads logs for given blocks for the informations about the voters
    w = AsyncWeb3(
        AsyncWeb3.WebSocketProvider(config.rpc_ws_url),
        middleware=[ExtraDataToPOAMiddleware],
    )
    await w.provider.connect()
    contracts = [
        config.contracts.VoterRegistry,
        config.contracts.FlareSystemsCalculator,
        config.contracts.Relay,
        config.contracts.FlareSystemsManager,
    ]
    event_signatures = {e.signature: e for c in contracts for e in c.events.values()}
    block_logs = await w.eth.get_logs(
        {
            "address": [contract.address for contract in contracts],
            "fromBlock": start_block,
            "toBlock": end_block,
        }
    )

    # take note if the user (in config) registered as a voter
    user_registered = False
    user_registration_info = False

    for log in block_logs:
        sig = log["topics"][0]

        if sig.hex() in event_signatures:
            event = event_signatures[sig.hex()]
            data = get_event_data(w.eth.codec, event.abi, log)

            # remove not used events (ProtocolMessageRelayed)
            # and check for correct reward_epoch_id
            if (
                event.name == "ProtocolMessageRelayed"
                or data["args"]["rewardEpochId"] != reward_epoch_number
            ):
                continue

            ds = ""
            match event.name:
                case "VoterRegistered":
                    e = fill_voter_registered(data["args"])
                    signing_policy.update_voter_registered_event(e)

                    if e.voter == config.identity_address:
                        ds = (
                            "You registered as voter for reward epoch"
                            f" {reward_epoch_number} with event:\n{e!s}"
                        )
                        user_registered = True

                case "VoterRemoved":
                    e = fill_voter_removed(data["args"])
                    signing_policy.update_voter_removed_event(e)

                    if e.voter == config.identity_address:
                        ds = (
                            "You were removed as a voter for reward epoch"
                            f" {reward_epoch_number} with event:\n{e!s}"
                        )
                        user_registered = False
                        user_registration_info = False

                case "VoterRegistrationInfo":
                    e = fill_voter_registration_info(data["args"])
                    signing_policy.update_voter_registration_info_event(e)

                    if e.voter == config.identity_address:
                        ds = (
                            "Your registration info for reward epoch"
                            f" {reward_epoch_number} with event:\n{e!s}"
                        )
                        user_registration_info = True

                case "SigningPolicyInitialized":
                    e = fill_signing_policy_initialized(data["args"])
                    signing_policy.update_signing_policy_initialized_event(e)

                case "VotePowerBlockSelected":
                    e = fill_vote_power_block_selected(data["args"])
                    reward_epoch_info_object.add_vote_power_block_selected_event(e)

                case "RandomAcquisitionStarted":
                    e = fill_random_acquisition_started(data["args"])
                    reward_epoch_info_object.add_random_acquisition_started_event(e)

            if ds:
                notify_discord(config, ds)

    if not user_registered or not user_registration_info:
        notify_discord(
            config,
            f"Your identity address {config.identity_address}\n"
            f"is NOT REGISTERED for reward epoch {e.reward_epoch_id}.\n"
            f"Did VoterRegisteredEvent happen? {user_registered}\n"
            f"Did VoterRegistrationInfoEvent happen? {user_registration_info}",
        )


async def observer_loop(config: Configuration) -> None:
    w = AsyncWeb3(
        AsyncWeb3.WebSocketProvider(config.rpc_ws_url),
        middleware=[ExtraDataToPOAMiddleware],
    )
    await w.provider.connect()

    # get current voting round and reward epoch
    block = await w.eth.get_block("latest")
    assert "timestamp" in block
    assert "number" in block
    voting_round = config.epoch.voting_epoch_factory.from_timestamp(block["timestamp"])
    reward_epoch = config.epoch.reward_epoch_factory.from_timestamp(block["timestamp"])

    # create objects of EpochManager, RewardEpochInfo and VotingEpochInfo classes
    epoch_manager = EpochManager()

    current_rid = reward_epoch.id
    current_vr = voting_round.id
    reward_epoch_info = RewardEpochInfo(current_rid)
    next_reward_epoch_info = RewardEpochInfo(current_rid + 1)

    epoch_manager.reward_epochs[current_rid] = reward_epoch_info
    epoch_manager.reward_epochs[current_rid + 1] = next_reward_epoch_info
    epoch_manager.voting_epochs[current_vr] = VotingEpochInfo(current_vr)
    # current reward epoch changes, when the reward_epoch_factory in config clicks over
    # at all times, we have at most 3 reward epochs in the manager

    # also create objects of SigningPolicy class
    signing_policy = SigningPolicy(current_rid)
    next_signing_policy = SigningPolicy(current_rid + 1)

    reward_epoch_info.add_signing_policy(signing_policy)
    next_reward_epoch_info.add_signing_policy(next_signing_policy)

    # ---------- all objects created --------------------

    # we first fill signing policy for current reward epoch

    # voter registration period is 2h before the reward epoch and lasts 30min
    # find block that has timestamp approx. 2h30min before the reward epoch
    # and block that has timestamp approx. 1h before the reward epoch
    lower_block_id, end_block_id = await find_voter_registration_blocks(
        config, block["number"], reward_epoch.start_s
    )

    # get informations for events that build the current signing policy
    await get_signing_policy_events(
        config,
        current_rid,
        lower_block_id,
        end_block_id,
        signing_policy,
        reward_epoch_info,
    )
    print("Signing policy created for reward epoch", current_rid)
    print("Reward Epoch object created", reward_epoch_info)
    print("Current Reward Epoch status", reward_epoch_info.status(config))

    # set up target address from config
    tia = w.to_checksum_address(config.identity_address)
    target_voter = signing_policy.voters[tia]
    notify_discord(
        config,
        f"flare-observer initialized\n\n"
        f"chain: {config.chain[0]}\n"
        f"submit address: {target_voter.submit_address}\n"
        f"submit signatures address: {target_voter.submit_signatures_address}\n"
        f"this address has voting power of: {signing_policy.voter_weight(tia)}\n\n"
        f"starting in voting round: {voting_round.next.id} "
        f"(current: {voting_round.id})\n"
        f"current reward epoch: {current_rid}",
    )

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

        vr = config.epoch.voting_epoch_factory.from_timestamp(block_data["timestamp"])
        if vr == voting_round.next:
            break

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
    print("Listener started from block number", block_number)
    while True:
        # check for new voting epoch
        if config.epoch.voting_epoch_factory.now_id() != current_vr:
            # switch current one
            current_vr += 1
            voting_round = voting_round.next
            epoch_manager.voting_epochs[current_vr] = VotingEpochInfo(current_vr)

        # check for new reward epoch
        if config.epoch.reward_epoch_factory.now_id() != current_rid:
            # switch current one
            reward_epoch = reward_epoch.next
            current_rid += 1
            reward_epoch_info = next_reward_epoch_info
            signing_policy = next_signing_policy

            # if signing policy for new current reward epoch is not set up (fully)
            # create a new one and fill it up by checking back
            if (
                not signing_policy.fully_set_up
                or not reward_epoch_info.random_acquisition_started
            ):
                signing_policy = SigningPolicy(current_rid)
                reward_epoch_info.add_signing_policy(signing_policy)

                # fill it up
                lower_block_id, end_block_id = await find_voter_registration_blocks(
                    config, block_number, reward_epoch.start_s
                )
                await get_signing_policy_events(
                    config,
                    current_rid,
                    lower_block_id,
                    end_block_id,
                    signing_policy,
                    reward_epoch_info,
                )

            # create next one
            next_reward_epoch_info = RewardEpochInfo(current_rid + 1)
            epoch_manager.reward_epochs[current_rid + 1] = next_reward_epoch_info
            next_signing_policy = SigningPolicy(current_rid + 1)
            next_reward_epoch_info.add_signing_policy(next_signing_policy)

            # delete reward epoch number current_rid - 2
            epoch_manager.reward_epochs.pop(current_rid - 1, None)

            print(f"Reward epoch number {current_rid} started.")

        latest_block = await w.eth.block_number
        if block_number == latest_block:
            time.sleep(2)
            continue

        print(f"----- Listening up to {latest_block - 1} -----")
        # check logs for events
        block_logs = await w.eth.get_logs(
            {
                "address": [contract.address for contract in contracts],
                "fromBlock": block_number,
                "toBlock": latest_block - 1,
            }
        )
        for log in block_logs:
            sig = log["topics"][0]

            if sig.hex() in event_signatures:
                event = event_signatures[sig.hex()]
                data = get_event_data(w.eth.codec, event.abi, log)
                match event.name:
                    case "ProtocolMessageRelayed":
                        e = fill_protocol_message_relayed(data["args"])
                        vei = epoch_manager.voting_epochs[e.voting_round_id]
                        # timestamp of the event needs to be saved
                        b = await w.eth.get_block(data["blockNumber"])
                        vei.add_protocol_message_relayed_event(e, b["timestamp"])  # type: ignore

                    case "SigningPolicyInitialized":
                        e = fill_signing_policy_initialized(data["args"])
                        next_signing_policy.update_signing_policy_initialized_event(e)

                    case "VoterRegistered":
                        e = fill_voter_registered(data["args"])
                        next_signing_policy.update_voter_registered_event(e)

                    case "VoterRemoved":
                        e = fill_voter_removed(data["args"])
                        next_signing_policy.update_voter_removed_event(e)

                    case "VoterRegistrationInfo":
                        e = fill_voter_registration_info(data["args"])
                        next_signing_policy.update_voter_registration_info_event(e)

                    case "VotePowerBlockSelected":
                        e = fill_vote_power_block_selected(data["args"])
                        next_reward_epoch_info.add_vote_power_block_selected_event(e)

                    case "RandomAcquisitionStarted":
                        e = fill_random_acquisition_started(data["args"])
                        next_reward_epoch_info.add_random_acquisition_started_event(e)

                print(event.name, e)

        # check transactions for submit transactions
        target_function_signatures = {
            config.contracts.Submission.functions[
                "submitSignatures"
            ].signature: "submitSignatures",
            config.contracts.Submission.functions["submit1"].signature: "submit1",
            config.contracts.Submission.functions["submit2"].signature: "submit2",
        }

        for number in range(block_number, latest_block):
            print("checking block number", number)
            block_data = await w.eth.get_block(number, full_transactions=True)
            assert "transactions" in block_data
            assert "timestamp" in block_data
            block_ts = block_data["timestamp"]

            for tx in block_data["transactions"]:
                assert type(tx) is TxData
                assert "input" in tx
                assert "from" in tx
                called_function_sig = tx["input"].hex()[:8]
                input = tx["input"].hex()[8:]
                sender_address = tx["from"]

                ds = ""
                if called_function_sig in target_function_signatures:
                    mode = target_function_signatures[called_function_sig]
                    match mode:
                        case "submit1":
                            parsed = parse_submit1_tx(input)
                            if parsed.ftso is not None:
                                vei = epoch_manager.voting_epochs[
                                    parsed.ftso.voting_round_id
                                ]
                                vei.ftso_s1[sender_address] = parsed.ftso
                            if parsed.fdc is not None:
                                vei = epoch_manager.voting_epochs[
                                    parsed.fdc.voting_round_id
                                ]
                                vei.fdc_s1[sender_address] = parsed.fdc

                            # 1.) check timestamp
                            if block_ts > config.epoch.voting_epoch(vei.id).end_s:
                                ds += "Submit 1 transaction is too late\n"

                        case "submit2":
                            parsed = parse_submit2_tx(input)
                            if parsed.ftso is not None:
                                vei = epoch_manager.voting_epochs[
                                    parsed.ftso.voting_round_id
                                ]
                                vei.ftso_s2[sender_address] = parsed.ftso

                            if parsed.fdc is not None:
                                vei = epoch_manager.voting_epochs[
                                    parsed.fdc.voting_round_id
                                ]
                                vei.fdc_s2[sender_address] = parsed.fdc

                            # 1.) check timestamp
                            if block_ts > config.epoch.voting_epoch(vei.id).end_s + 45:
                                ds += "Submit 2 transaction is too late\n"

                            if parsed.ftso is not None:
                                # 2.) check correct sent value
                                bp = ByteParser(parse_generic_tx(input).ftso.payload)
                                rnd = bp.uint256()
                                feed_v = bp.drain()
                                hashed = commit_hash(
                                    sender_address, vei.id, rnd, feed_v
                                )

                                # the only time this is false is at the start
                                if sender_address in vei.ftso_s1:
                                    s1_val = vei.ftso_s1[
                                        sender_address
                                    ].payload.commit_hash.hex()
                                    if hashed != s1_val:
                                        ds += (
                                            "Submit 1 and Submit 2 values don't match\n"
                                        )

                                # 3.) check if any value is None
                                nv = [
                                    i
                                    for i, v in enumerate(parsed.ftso.payload.values)
                                    if v is None
                                ]
                                if nv:
                                    ds += (
                                        f"Submit 2 values have 'none' on indices {nv}\n"
                                    )

                        case "submitSignatures":
                            parsed = parse_submit_signature_tx(input)
                            if parsed.ftso is not None:
                                vei = epoch_manager.voting_epochs[
                                    parsed.ftso.voting_round_id
                                ]
                                vei.ftso_ss[sender_address] = parsed.ftso
                                # 1.) check timestamp
                                latest_ts = config.epoch.voting_epoch(vei.id).end_s + 55
                                if vei.ftso_mr[1]:
                                    latest_ts = max(latest_ts, vei.ftso_mr[0])
                                if block_ts > latest_ts:
                                    ds += "Submit Signatures ftso tx is too late\n"

                                # 2.) check correct values sent
                                # TODO: (nejc) set this up

                            if parsed.fdc is not None:
                                vei = epoch_manager.voting_epochs[
                                    parsed.fdc.voting_round_id
                                ]
                                vei.fdc_ss[sender_address] = parsed.fdc
                                # 1.) check timestamp
                                latest_ts = config.epoch.voting_epoch(vei.id).end_s + 55
                                if vei.fdc_mr[1]:
                                    latest_ts = max(latest_ts, vei.fdc_mr[0])
                                if block_ts > latest_ts:
                                    ds += "Submit Signatures fdc tx is too late\n"

                                # 2.) check correct values sent
                                # TODO: (nejc) set this up

                if (
                    sender_address
                    in [
                        target_voter.submit_address,
                        target_voter.submit_signatures_address,
                    ]
                    and ds
                ):
                    notify_discord(config, ds)

        block_number = latest_block
