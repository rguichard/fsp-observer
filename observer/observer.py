import time

import requests
from web3 import AsyncWeb3
from web3._utils.events import get_event_data
from web3.middleware import ExtraDataToPOAMiddleware

from configuration.types import Configuration
from observer.reward_epoch_manager import RewardEpochInfo, SigningPolicy
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


async def get_signing_policy_events(
    config: Configuration, start_block: int, end_block: int
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
    ]
    event_signatures = {e.signature: e for c in contracts for e in c.events.values()}

    block_logs = await w.eth.get_logs(
        {
            "address": [contract.address for contract in contracts],
            "fromBlock": start_block,
            "toBlock": end_block,
        }
    )

    for log in block_logs:
        sig = log["topics"][0]

        if sig.hex() in event_signatures:
            event = event_signatures[sig.hex()]
            data = get_event_data(w.eth.codec, event.abi, log)
            match event.name:
                case "VoterRegistered":
                    e = fill_voter_registered(data["args"])
                    found_events["VoterRegistry"].append(e)

                case "VoterRegistrationInfo":
                    e = fill_voter_registration_info(data["args"])
                    found_events["FlareSystemsCalculator"].append(e)

                case "SigningPolicyInitialized":
                    e = fill_signing_policy_initialized(data["args"])
                    found_events["Relay"].append(e)


def build_signing_policy() -> SigningPolicy:
    # for now this assumes the following events are in found_events
    # - 1 SigningPolicyInitialized event
    # - n VoterRegistered events
    # - n VoterRegistrationInfo events

    # create signing policy
    signing_policy = SigningPolicy(found_events["Relay"][0])

    # update voters info
    for e in found_events["VoterRegistry"]:
        signing_policy.update_voter_registered_event(e)
    for e in found_events["FlareSystemsCalculator"]:
        signing_policy.update_voter_registration_info_event(e)

    return signing_policy


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

    # TODO: (nejc) do this properly
    # voter registration period is 2h (= 80 voting rounds) before the reward epoch
    # avg time = 1s
    avg_time = 1
    starting_timestamp = reward_epoch.start_s
    lower_block_id = block["number"] - int(
        (time.time() - (starting_timestamp - 2 * 3600)) / avg_time
    )
    end_block_id = block["number"] - int((time.time() - starting_timestamp) / avg_time)

    # get informations for events that build the current signing policy
    await get_signing_policy_events(config, lower_block_id, end_block_id)
    signing_policy = build_signing_policy()

    reward_epoch_info = RewardEpochInfo(reward_epoch.id, signing_policy)

    print("Signing policy created for reward epoch", reward_epoch.id)
    print("Reward Epoch object created", reward_epoch_info)

    # set up target address from config
    tia = w.to_checksum_address(config.identity_address)
    tspa = signing_policy.signing_policy_addresses[tia]
    target_voter = signing_policy.voters[tspa]
    notify_discord(
        config,
        f"flare-observer initialized\n\n"
        f"chain: {config.chain[0]}\n"
        f"submit address: {target_voter.submit_address}\n"
        f"submit signatures address: {target_voter.submit_signatures_address}\n\n"
        f"starting in voting round: {voting_round.next.id} "
        f"(current: {voting_round.id})",
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
        latest_block = await w.eth.block_number
        if block_number == latest_block:
            time.sleep(2)
            continue

        print(f"----- Listening up to {latest_block} -----")
        block_logs = await w.eth.get_logs(
            {
                "address": [contract.address for contract in contracts],
                "fromBlock": block_number,
                "toBlock": latest_block,
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
                print(event.name, e)

        block_number = latest_block
