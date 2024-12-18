import time

import requests
from web3 import AsyncWeb3
from web3._utils.events import get_event_data
from web3.middleware import ExtraDataToPOAMiddleware

from configuration.types import Configuration
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


found_events: dict[str, list] = {}
found_events["Relay"] = []
found_events["FlareSystemsManager"] = []
found_events["FlareSystemsCalculator"] = []
found_events["VoterRegistry"] = []


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


async def observer_loop(config: Configuration) -> None:
    w = AsyncWeb3(
        AsyncWeb3.WebSocketProvider(config.rpc_ws_url),
        middleware=[ExtraDataToPOAMiddleware],
    )
    await w.provider.connect()

    block = await w.eth.block_number
    # TODO:(matej) calculate voting round from block timestamp
    # w.eth.get_block will need to be called
    voting_round = config.epoch.voting_epoch_factory.now().next

    # TODO: (nejc) addresses are wrong
    notify_discord(
        config,
        f"flare-observer initialized\n\n"
        f"chain: {config.chain[0]}\n"
        f"submit address: {config.identity_address}\n"
        f"submit signatures address: {config.identity_address}\n\n"
        f"starting in voting round: {voting_round.id} "
        f"(current: {voting_round.previous.id})",
    )

    while True:
        latest_block = await w.eth.block_number
        if block == latest_block:
            time.sleep(2)
            continue

        block += 1
        block_data = await w.eth.get_block(block)

        assert "timestamp" in block_data

        vr = config.epoch.voting_epoch_factory.from_timestamp(block_data["timestamp"])
        if vr == voting_round:
            break

    while True:
        latest_block = await w.eth.block_number
        if block == latest_block:
            time.sleep(2)
            continue

        contracts = [
            config.contracts.Relay,
            config.contracts.VoterRegistry,
            config.contracts.FlareSystemsManager,
            config.contracts.FlareSystemsCalculator,
        ]
        for contract in contracts:
            event_signatures = {e.signature: e for e in contract.events.values()}

            block_logs = await w.eth.get_logs(
                {
                    "address": contract.address,
                    "fromBlock": block,
                    "toBlock": latest_block,
                }
            )
            # VoterRegistered: 78662702 - 10000, 78662702
            # SigningPolicyInitialized, VotePowerBlockSelected
            # and RandomAcquisitionStarted:
            # 78660002, 78670002
            # VoterRegistrationInfo: 78662702 - 1000, 78662702

            for log in block_logs:
                sig = log["topics"][0]

                if sig.hex() in event_signatures:
                    event = event_signatures[sig.hex()]
                    data = get_event_data(w.eth.codec, event.abi, log)
                    match event.name:
                        case "ProtocolMessageRelayed":
                            e = fill_protocol_message_relayed(data["args"])
                            found_events["Relay"].append(e)
                        case "SigningPolicyInitialized":
                            e = fill_signing_policy_initialized(data["args"])
                            found_events["Relay"].append(e)
                        case "VoterRegistered":
                            e = fill_voter_registered(data["args"])
                            found_events["VoterRegistry"].append(e)
                        case "VoterRemoved":
                            e = fill_voter_removed(data["args"])
                            found_events["VoterRegistry"].append(e)
                        case "VoterRegistrationInfo":
                            e = fill_voter_registration_info(data["args"])
                            found_events["FlareSystemsCalculator"].append(e)
                        case "VotePowerBlockSelected":
                            e = fill_vote_power_block_selected(data["args"])
                            found_events["FlareSystemsManager"].append(e)
                        case "RandomAcquisitionStarted":
                            e = fill_random_acquisition_started(data["args"])
                            found_events["FlareSystemsManager"].append(e)

        block = latest_block
        print(f"------ {block}-----------")
        print(found_events)
