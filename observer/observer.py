import time
from collections import defaultdict
from typing import Generic, TypeAlias, TypeVar

import requests
from py_flare_common.fsp.messaging import types as mt
from py_flare_common.fsp.messaging.byte_parser import ParseError
from py_flare_common.fsp.messaging.parse import (
    parse_submit1_tx,
    parse_submit2_tx,
    parse_submit_signature_tx,
)
from web3 import AsyncWeb3
from web3.middleware import ExtraDataToPOAMiddleware
from web3.types import TxData

from config.types import Configuration


def notify_discord(config: Configuration, message: str) -> None:
    requests.post(
        config.discord_webhook,
        headers={"Content-Type": "application/json"},
        json={"content": message},
    )


T = TypeVar("T")
U = TypeVar("U")

Submit1Tx: TypeAlias = dict[int, dict[str, tuple[mt.ParsedPayload[T], TxData]]]
Submit2Tx: TypeAlias = dict[int, dict[str, tuple[mt.ParsedPayload[U], TxData]]]
SubmitSignaturesTx: TypeAlias = dict[
    int, dict[str, tuple[mt.ParsedPayload[mt.SubmitSignatures], TxData]]
]


class MessageStore(Generic[T, U]):
    def __init__(self) -> None:
        self.submit1: Submit1Tx = defaultdict(dict)
        self.submit2: Submit2Tx = defaultdict(dict)
        self.submit_signatures: SubmitSignaturesTx = defaultdict(dict)

    def store_submit1(
        self,
        tx: TxData,
        message: mt.ParsedPayload[T],
    ) -> None:
        assert "from" in tx
        self.submit1[message.voting_round_id][tx["from"]] = (message, tx)

    def store_submit2(
        self,
        tx: TxData,
        message: mt.ParsedPayload[U],
    ) -> None:
        assert "from" in tx
        self.submit2[message.voting_round_id][tx["from"]] = (message, tx)

    def store_submit_signatures(
        self,
        tx: TxData,
        message: mt.ParsedPayload[mt.SubmitSignatures],
    ) -> None:
        assert "from" in tx
        self.submit_signatures[message.voting_round_id][tx["from"]] = (message, tx)

    def clear(self, voting_round_id: int) -> None:
        self.submit1.pop(voting_round_id, None)
        self.submit2.pop(voting_round_id, None)
        self.submit_signatures.pop(voting_round_id, None)


SUBMIT1 = "6c532fae"
SUBMIT2 = "9d00c9fd"
SUBMIT_SIG = "57eed580"

SUBMIT_ADDRESS = "addr"
SUBMIT_SIG_ADDRESS = "addr"


async def observer_loop(config: Configuration) -> None:
    ftso_ms = MessageStore[mt.FtsoSubmit1, mt.FtsoSubmit2]()
    fdc_ms = MessageStore[mt.FdcSubmit1, mt.FdcSubmit2]()

    w = AsyncWeb3(
        AsyncWeb3.WebSocketProvider(config.rpc_ws_url),
        middleware=[ExtraDataToPOAMiddleware],
    )

    await w.provider.connect()

    block = await w.eth.block_number
    # TODO:(matej) calculate voting round from block timestamp
    # w.eth.get_block will need to be called
    voting_round = config.epoch.voting_epoch_factory.now().next

    notify_discord(
        config,
        f"flare-observer initialized\n\n"
        f"chain: {config.chain[0]}\n"
        f"submit address: {SUBMIT_ADDRESS}\n"
        f"submit signatures address: {SUBMIT_SIG_ADDRESS}\n\n"
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

        block_data = await w.eth.get_block(block, full_transactions=True)
        block += 1

        assert "timestamp" in block_data

        # at 155s submit1, submit2 and submitSignature transactions should
        # already happen if normal behaviour
        if voting_round.end_s + 65 < block_data["timestamp"]:
            # NOTE: a very basic check if fdc round had any requests and
            # specified addresses was part of consensus
            submit_signatures = fdc_ms.submit_signatures[voting_round.id]
            ss_message = submit_signatures.get(SUBMIT_SIG_ADDRESS)

            if submit_signatures and ss_message is None:
                notify_discord(
                    config,
                    "Didn't send fdc submit signatures before relay grace period (155s)"
                    f" for voting round {voting_round.id}.",
                )

            ftso_ms.clear(voting_round.id)
            fdc_ms.clear(voting_round.id)
            voting_round = voting_round.next

        assert "transactions" in block_data
        for tx in block_data["transactions"]:
            assert not isinstance(tx, bytes)

            assert "input" in tx

            tx_in = tx["input"].hex()

            if tx_in[:8] == SUBMIT1:
                try:
                    message = parse_submit1_tx(tx_in[8:])
                    if message.fdc is not None:
                        fdc_ms.store_submit1(tx, message.fdc)
                    if message.ftso is not None:
                        ftso_ms.store_submit1(tx, message.ftso)
                except ParseError:
                    pass

            if tx_in[:8] == SUBMIT2:
                try:
                    message = parse_submit2_tx(tx_in[8:])
                    if message.fdc is not None:
                        fdc_ms.store_submit2(tx, message.fdc)
                    if message.ftso is not None:
                        ftso_ms.store_submit2(tx, message.ftso)
                except ParseError:
                    pass

            if tx_in[:8] == SUBMIT_SIG:
                try:
                    message = parse_submit_signature_tx(tx_in[8:])
                    if message.fdc is not None:
                        fdc_ms.store_submit_signatures(tx, message.fdc)
                    if message.ftso is not None:
                        ftso_ms.store_submit_signatures(tx, message.ftso)
                except ParseError:
                    pass
