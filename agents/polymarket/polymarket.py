# core polymarket api
# https://github.com/Polymarket/py-clob-client/tree/main/examples

import os
import pdb
import time
import ast
import requests
from typing import Optional

from dotenv import load_dotenv

from web3 import Web3
from web3.constants import MAX_INT
from web3.middleware import geth_poa_middleware

import httpx
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds
from py_clob_client.constants import AMOY, POLYGON
from py_order_utils.builders import OrderBuilder
from py_order_utils.model import OrderData
from py_order_utils.signer import Signer
from py_clob_client.clob_types import (
    OrderArgs,
    MarketOrderArgs,
    OrderType,
    OrderBookSummary,
    BalanceAllowanceParams,
    AssetType,
)
from py_clob_client.order_builder.constants import BUY

from agents.utils.objects import SimpleMarket, SimpleEvent

load_dotenv()


class Polymarket:
    def __init__(self, initialize_clob_client: bool = True) -> None:
        self.gamma_url = "https://gamma-api.polymarket.com"
        self.gamma_markets_endpoint = self.gamma_url + "/markets"
        self.gamma_events_endpoint = self.gamma_url + "/events"

        self.clob_url = "https://clob.polymarket.com"
        self.clob_auth_endpoint = self.clob_url + "/auth/api-key"

        self.chain_id = 137  # POLYGON
        self.private_key = os.getenv("POLYGON_WALLET_PRIVATE_KEY")
        self.signature_type = int(str(os.getenv("POLYMARKET_SIGNATURE_TYPE", "0")).strip() or "0")
        self.funder_address = str(os.getenv("POLYMARKET_FUNDER_ADDRESS", "") or "").strip() or None
        self.allow_restricted_events = (
            str(os.getenv("ALLOW_RESTRICTED_EVENTS", "false")).strip().lower()
            in ("1", "true", "yes", "on")
        )
        self.polygon_rpc = os.getenv("POLYGON_RPC_URL", "https://polygon-rpc.com")
        self.w3 = Web3(Web3.HTTPProvider(self.polygon_rpc))

        self.exchange_address = "0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e"
        self.neg_risk_exchange_address = "0xC5d563A36AE78145C45a50134d48A1215220f80a"

        self.erc20_approve = """[{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"owner","type":"address"},{"indexed":true,"internalType":"address","name":"spender","type":"address"},{"indexed":false,"internalType":"uint256","name":"value","type":"uint256"}],"name":"Approval","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"authorizer","type":"address"},{"indexed":true,"internalType":"bytes32","name":"nonce","type":"bytes32"}],"name":"AuthorizationCanceled","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"authorizer","type":"address"},{"indexed":true,"internalType":"bytes32","name":"nonce","type":"bytes32"}],"name":"AuthorizationUsed","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"account","type":"address"}],"name":"Blacklisted","type":"event"},{"anonymous":false,"inputs":[{"indexed":false,"internalType":"address","name":"userAddress","type":"address"},{"indexed":false,"internalType":"address payable","name":"relayerAddress","type":"address"},{"indexed":false,"internalType":"bytes","name":"functionSignature","type":"bytes"}],"name":"MetaTransactionExecuted","type":"event"},{"anonymous":false,"inputs":[],"name":"Pause","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"newRescuer","type":"address"}],"name":"RescuerChanged","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"bytes32","name":"role","type":"bytes32"},{"indexed":true,"internalType":"bytes32","name":"previousAdminRole","type":"bytes32"},{"indexed":true,"internalType":"bytes32","name":"newAdminRole","type":"bytes32"}],"name":"RoleAdminChanged","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"bytes32","name":"role","type":"bytes32"},{"indexed":true,"internalType":"address","name":"account","type":"address"},{"indexed":true,"internalType":"address","name":"sender","type":"address"}],"name":"RoleGranted","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"bytes32","name":"role","type":"bytes32"},{"indexed":true,"internalType":"address","name":"account","type":"address"},{"indexed":true,"internalType":"address","name":"sender","type":"address"}],"name":"RoleRevoked","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"from","type":"address"},{"indexed":true,"internalType":"address","name":"to","type":"address"},{"indexed":false,"internalType":"uint256","name":"value","type":"uint256"}],"name":"Transfer","type":"event"},{"anonymous":false,"inputs":[{"indexed":true,"internalType":"address","name":"account","type":"address"}],"name":"UnBlacklisted","type":"event"},{"anonymous":false,"inputs":[],"name":"Unpause","type":"event"},{"inputs":[],"name":"APPROVE_WITH_AUTHORIZATION_TYPEHASH","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"BLACKLISTER_ROLE","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"CANCEL_AUTHORIZATION_TYPEHASH","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"DECREASE_ALLOWANCE_WITH_AUTHORIZATION_TYPEHASH","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"DEFAULT_ADMIN_ROLE","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"DEPOSITOR_ROLE","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"DOMAIN_SEPARATOR","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"EIP712_VERSION","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"INCREASE_ALLOWANCE_WITH_AUTHORIZATION_TYPEHASH","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"META_TRANSACTION_TYPEHASH","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"PAUSER_ROLE","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"PERMIT_TYPEHASH","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"RESCUER_ROLE","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"TRANSFER_WITH_AUTHORIZATION_TYPEHASH","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"WITHDRAW_WITH_AUTHORIZATION_TYPEHASH","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"owner","type":"address"},{"internalType":"address","name":"spender","type":"address"}],"name":"allowance","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"spender","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"}],"name":"approve","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"owner","type":"address"},{"internalType":"address","name":"spender","type":"address"},{"internalType":"uint256","name":"value","type":"uint256"},{"internalType":"uint256","name":"validAfter","type":"uint256"},{"internalType":"uint256","name":"validBefore","type":"uint256"},{"internalType":"bytes32","name":"nonce","type":"bytes32"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"approveWithAuthorization","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"authorizer","type":"address"},{"internalType":"bytes32","name":"nonce","type":"bytes32"}],"name":"authorizationState","outputs":[{"internalType":"enum GasAbstraction.AuthorizationState","name":"","type":"uint8"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"account","type":"address"}],"name":"balanceOf","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"account","type":"address"}],"name":"blacklist","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"blacklisters","outputs":[{"internalType":"address[]","name":"","type":"address[]"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"authorizer","type":"address"},{"internalType":"bytes32","name":"nonce","type":"bytes32"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"cancelAuthorization","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"decimals","outputs":[{"internalType":"uint8","name":"","type":"uint8"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"spender","type":"address"},{"internalType":"uint256","name":"subtractedValue","type":"uint256"}],"name":"decreaseAllowance","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"owner","type":"address"},{"internalType":"address","name":"spender","type":"address"},{"internalType":"uint256","name":"decrement","type":"uint256"},{"internalType":"uint256","name":"validAfter","type":"uint256"},{"internalType":"uint256","name":"validBefore","type":"uint256"},{"internalType":"bytes32","name":"nonce","type":"bytes32"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"decreaseAllowanceWithAuthorization","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"user","type":"address"},{"internalType":"bytes","name":"depositData","type":"bytes"}],"name":"deposit","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"userAddress","type":"address"},{"internalType":"bytes","name":"functionSignature","type":"bytes"},{"internalType":"bytes32","name":"sigR","type":"bytes32"},{"internalType":"bytes32","name":"sigS","type":"bytes32"},{"internalType":"uint8","name":"sigV","type":"uint8"}],"name":"executeMetaTransaction","outputs":[{"internalType":"bytes","name":"","type":"bytes"}],"stateMutability":"payable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"role","type":"bytes32"}],"name":"getRoleAdmin","outputs":[{"internalType":"bytes32","name":"","type":"bytes32"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"role","type":"bytes32"},{"internalType":"uint256","name":"index","type":"uint256"}],"name":"getRoleMember","outputs":[{"internalType":"address","name":"","type":"address"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"role","type":"bytes32"}],"name":"getRoleMemberCount","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"role","type":"bytes32"},{"internalType":"address","name":"account","type":"address"}],"name":"grantRole","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"role","type":"bytes32"},{"internalType":"address","name":"account","type":"address"}],"name":"hasRole","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"spender","type":"address"},{"internalType":"uint256","name":"addedValue","type":"uint256"}],"name":"increaseAllowance","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"owner","type":"address"},{"internalType":"address","name":"spender","type":"address"},{"internalType":"uint256","name":"increment","type":"uint256"},{"internalType":"uint256","name":"validAfter","type":"uint256"},{"internalType":"uint256","name":"validBefore","type":"uint256"},{"internalType":"bytes32","name":"nonce","type":"bytes32"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"increaseAllowanceWithAuthorization","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"string","name":"newName","type":"string"},{"internalType":"string","name":"newSymbol","type":"string"},{"internalType":"uint8","name":"newDecimals","type":"uint8"},{"internalType":"address","name":"childChainManager","type":"address"}],"name":"initialize","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"initialized","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"account","type":"address"}],"name":"isBlacklisted","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"name","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"owner","type":"address"}],"name":"nonces","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"pause","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"paused","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"pausers","outputs":[{"internalType":"address[]","name":"","type":"address[]"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"owner","type":"address"},{"internalType":"address","name":"spender","type":"address"},{"internalType":"uint256","name":"value","type":"uint256"},{"internalType":"uint256","name":"deadline","type":"uint256"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"permit","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"bytes32","name":"role","type":"bytes32"},{"internalType":"address","name":"account","type":"address"}],"name":"renounceRole","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"contract IERC20","name":"tokenContract","type":"address"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"}],"name":"rescueERC20","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"rescuers","outputs":[{"internalType":"address[]","name":"","type":"address[]"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"bytes32","name":"role","type":"bytes32"},{"internalType":"address","name":"account","type":"address"}],"name":"revokeRole","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"symbol","outputs":[{"internalType":"string","name":"","type":"string"}],"stateMutability":"view","type":"function"},{"inputs":[],"name":"totalSupply","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},{"inputs":[{"internalType":"address","name":"recipient","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"}],"name":"transfer","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"sender","type":"address"},{"internalType":"address","name":"recipient","type":"address"},{"internalType":"uint256","name":"amount","type":"uint256"}],"name":"transferFrom","outputs":[{"internalType":"bool","name":"","type":"bool"}],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"from","type":"address"},{"internalType":"address","name":"to","type":"address"},{"internalType":"uint256","name":"value","type":"uint256"},{"internalType":"uint256","name":"validAfter","type":"uint256"},{"internalType":"uint256","name":"validBefore","type":"uint256"},{"internalType":"bytes32","name":"nonce","type":"bytes32"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"transferWithAuthorization","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"account","type":"address"}],"name":"unBlacklist","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[],"name":"unpause","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"string","name":"newName","type":"string"},{"internalType":"string","name":"newSymbol","type":"string"}],"name":"updateMetadata","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"uint256","name":"amount","type":"uint256"}],"name":"withdraw","outputs":[],"stateMutability":"nonpayable","type":"function"},{"inputs":[{"internalType":"address","name":"owner","type":"address"},{"internalType":"uint256","name":"value","type":"uint256"},{"internalType":"uint256","name":"validAfter","type":"uint256"},{"internalType":"uint256","name":"validBefore","type":"uint256"},{"internalType":"bytes32","name":"nonce","type":"bytes32"},{"internalType":"uint8","name":"v","type":"uint8"},{"internalType":"bytes32","name":"r","type":"bytes32"},{"internalType":"bytes32","name":"s","type":"bytes32"}],"name":"withdrawWithAuthorization","outputs":[],"stateMutability":"nonpayable","type":"function"}]"""
        self.erc1155_set_approval = """[{"inputs": [{ "internalType": "address", "name": "operator", "type": "address" },{ "internalType": "bool", "name": "approved", "type": "bool" }],"name": "setApprovalForAll","outputs": [],"stateMutability": "nonpayable","type": "function"}]"""

        self.usdc_address = (
            str(
                os.getenv(
                    "POLYGON_COLLATERAL_USDC_ADDRESS",
                    "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
                )
                or ""
            ).strip()
            or "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
        )
        self.native_usdc_address = (
            str(
                os.getenv(
                    "POLYGON_NATIVE_USDC_ADDRESS",
                    "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359",
                )
                or ""
            ).strip()
            or "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359"
        )
        self.usdc_balance_token_addresses = os.getenv(
            "USDC_BALANCE_TOKEN_ADDRESSES",
            "",
        )
        self.ctf_address = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"

        self.web3 = Web3(Web3.HTTPProvider(self.polygon_rpc))
        self.web3.middleware_onion.inject(geth_poa_middleware, layer=0)

        self.usdc = self._erc20_contract(self.usdc_address)
        self.ctf = self.web3.eth.contract(
            address=self._as_checksum_address(self.ctf_address), abi=self.erc1155_set_approval
        )
        self.client = None
        self.credentials = None
        if initialize_clob_client:
            self._init_api_keys()
            self._init_approvals(False)

    def _init_api_keys(self) -> None:
        self.client = ClobClient(
            self.clob_url,
            key=self.private_key,
            chain_id=self.chain_id,
            signature_type=self.signature_type,
            funder=self.funder_address,
        )
        self.credentials = self.client.create_or_derive_api_creds()
        self.client.set_api_creds(self.credentials)
        # print(self.credentials)

    def _init_approvals(self, run: bool = False) -> None:
        if not run:
            return

        priv_key = self.private_key
        pub_key = self.get_address_for_private_key()
        chain_id = self.chain_id
        web3 = self.web3
        nonce = web3.eth.get_transaction_count(pub_key)
        usdc = self.usdc
        ctf = self.ctf

        # CTF Exchange
        raw_usdc_approve_txn = usdc.functions.approve(
            "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E", int(MAX_INT, 0)
        ).build_transaction({"chainId": chain_id, "from": pub_key, "nonce": nonce})
        signed_usdc_approve_tx = web3.eth.account.sign_transaction(
            raw_usdc_approve_txn, private_key=priv_key
        )
        send_usdc_approve_tx = web3.eth.send_raw_transaction(
            signed_usdc_approve_tx.raw_transaction
        )
        usdc_approve_tx_receipt = web3.eth.wait_for_transaction_receipt(
            send_usdc_approve_tx, 600
        )
        print(usdc_approve_tx_receipt)

        nonce = web3.eth.get_transaction_count(pub_key)

        raw_ctf_approval_txn = ctf.functions.setApprovalForAll(
            "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E", True
        ).build_transaction({"chainId": chain_id, "from": pub_key, "nonce": nonce})
        signed_ctf_approval_tx = web3.eth.account.sign_transaction(
            raw_ctf_approval_txn, private_key=priv_key
        )
        send_ctf_approval_tx = web3.eth.send_raw_transaction(
            signed_ctf_approval_tx.raw_transaction
        )
        ctf_approval_tx_receipt = web3.eth.wait_for_transaction_receipt(
            send_ctf_approval_tx, 600
        )
        print(ctf_approval_tx_receipt)

        nonce = web3.eth.get_transaction_count(pub_key)

        # Neg Risk CTF Exchange
        raw_usdc_approve_txn = usdc.functions.approve(
            "0xC5d563A36AE78145C45a50134d48A1215220f80a", int(MAX_INT, 0)
        ).build_transaction({"chainId": chain_id, "from": pub_key, "nonce": nonce})
        signed_usdc_approve_tx = web3.eth.account.sign_transaction(
            raw_usdc_approve_txn, private_key=priv_key
        )
        send_usdc_approve_tx = web3.eth.send_raw_transaction(
            signed_usdc_approve_tx.raw_transaction
        )
        usdc_approve_tx_receipt = web3.eth.wait_for_transaction_receipt(
            send_usdc_approve_tx, 600
        )
        print(usdc_approve_tx_receipt)

        nonce = web3.eth.get_transaction_count(pub_key)

        raw_ctf_approval_txn = ctf.functions.setApprovalForAll(
            "0xC5d563A36AE78145C45a50134d48A1215220f80a", True
        ).build_transaction({"chainId": chain_id, "from": pub_key, "nonce": nonce})
        signed_ctf_approval_tx = web3.eth.account.sign_transaction(
            raw_ctf_approval_txn, private_key=priv_key
        )
        send_ctf_approval_tx = web3.eth.send_raw_transaction(
            signed_ctf_approval_tx.raw_transaction
        )
        ctf_approval_tx_receipt = web3.eth.wait_for_transaction_receipt(
            send_ctf_approval_tx, 600
        )
        print(ctf_approval_tx_receipt)

        nonce = web3.eth.get_transaction_count(pub_key)

        # Neg Risk Adapter
        raw_usdc_approve_txn = usdc.functions.approve(
            "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296", int(MAX_INT, 0)
        ).build_transaction({"chainId": chain_id, "from": pub_key, "nonce": nonce})
        signed_usdc_approve_tx = web3.eth.account.sign_transaction(
            raw_usdc_approve_txn, private_key=priv_key
        )
        send_usdc_approve_tx = web3.eth.send_raw_transaction(
            signed_usdc_approve_tx.raw_transaction
        )
        usdc_approve_tx_receipt = web3.eth.wait_for_transaction_receipt(
            send_usdc_approve_tx, 600
        )
        print(usdc_approve_tx_receipt)

        nonce = web3.eth.get_transaction_count(pub_key)

        raw_ctf_approval_txn = ctf.functions.setApprovalForAll(
            "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296", True
        ).build_transaction({"chainId": chain_id, "from": pub_key, "nonce": nonce})
        signed_ctf_approval_tx = web3.eth.account.sign_transaction(
            raw_ctf_approval_txn, private_key=priv_key
        )
        send_ctf_approval_tx = web3.eth.send_raw_transaction(
            signed_ctf_approval_tx.raw_transaction
        )
        ctf_approval_tx_receipt = web3.eth.wait_for_transaction_receipt(
            send_ctf_approval_tx, 600
        )
        print(ctf_approval_tx_receipt)

    def get_all_markets(self) -> "list[SimpleMarket]":
        markets = []
        res = httpx.get(self.gamma_markets_endpoint)
        if res.status_code == 200:
            for market in res.json():
                try:
                    market_data = self.map_api_to_market(market)
                    markets.append(SimpleMarket(**market_data))
                except Exception as e:
                    print(e)
                    pass
        return markets

    def filter_markets_for_trading(self, markets: "list[SimpleMarket]"):
        tradeable_markets = []
        for market in markets:
            if market.active:
                tradeable_markets.append(market)
        return tradeable_markets

    def get_market(self, token_id: str) -> SimpleMarket:
        params = {"clob_token_ids": token_id}
        res = httpx.get(self.gamma_markets_endpoint, params=params)
        if res.status_code == 200:
            data = res.json()
            if not data:
                print(f"[markets] no_market_found_for_token token_id={token_id}")
                return None
            market = data[0]
            return self.map_api_to_market(market, token_id)
        print(
            f"[markets] request_failed status={res.status_code} token_id={token_id} params={params}"
        )
        return None

    def map_api_to_market(self, market, token_id: str = "") -> SimpleMarket:
        def _float_or_zero(value):
            try:
                return float(value) if value is not None else 0.0
            except (TypeError, ValueError):
                return 0.0

        def _list_or_empty(value):
            if isinstance(value, list):
                return value
            if isinstance(value, str):
                try:
                    parsed = ast.literal_eval(value)
                    return parsed if isinstance(parsed, list) else []
                except Exception:
                    return []
            return []

        def _extract_tags(raw_market: dict) -> list[str]:
            tags = []
            events = raw_market.get("events") or []
            for event in events:
                for tag in event.get("tags") or []:
                    label = tag.get("label") or tag.get("slug")
                    if label:
                        tags.append(str(label))
            for tag in raw_market.get("tags") or []:
                label = tag.get("label") or tag.get("slug")
                if label:
                    tags.append(str(label))
            # Keep insertion order while removing duplicates.
            return list(dict.fromkeys(tags))

        market_id = int(market.get("id", 0))
        outcomes = _list_or_empty(market.get("outcomes", []))
        outcome_prices = _list_or_empty(
            market.get("outcomePrices", market.get("outcome_prices", []))
        )
        clob_token_ids = _list_or_empty(
            market.get("clobTokenIds", market.get("clob_token_ids", []))
        )
        events = market.get("events") or []
        first_event = events[0] if events else {}
        category = str(market.get("category") or "").strip()
        tags = _extract_tags(market)

        if outcome_prices == []:
            print(f"[markets] missing_outcome_prices market_id={market_id}")

        mapped_market = {
            "id": market_id,
            "question": market.get("question", ""),
            "end": market.get("endDate", ""),
            "description": market.get("description", ""),
            "active": bool(market.get("active")),
            # "deployed": market["deployed"],
            "funded": bool(market.get("funded")),
            "rewardsMinSize": _float_or_zero(market.get("rewardsMinSize")),
            "rewardsMaxSpread": _float_or_zero(market.get("rewardsMaxSpread")),
            "volume": _float_or_zero(market.get("volume", market.get("volumeNum"))),
            "volume24hr": _float_or_zero(market.get("volume24hr")),
            "volume_clob": _float_or_zero(market.get("volumeClob")),
            "volume24hr_clob": _float_or_zero(market.get("volume24hrClob")),
            "liquidity": _float_or_zero(market.get("liquidity", market.get("liquidityNum"))),
            "liquidity_clob": _float_or_zero(market.get("liquidityClob")),
            "spread": _float_or_zero(market.get("spread")),
            "outcomes": str(outcomes),
            "outcome_prices": str(outcome_prices),
            "clob_token_ids": str(clob_token_ids),
            "category": category,
            "tags": ",".join(tags),
            "event_id": str(first_event.get("id") or ""),
            "event_title": str(first_event.get("title") or ""),
            "event_slug": str(first_event.get("slug") or ""),
        }
        if token_id:
            mapped_market["clob_token_ids"] = str([token_id])
        return mapped_market

    def get_all_events(self) -> "list[SimpleEvent]":
        events = []
        raw_events = []
        limit = 200
        offset = 0
        page = 0

        while True:
            page += 1
            params = {
                "active": True,
                "closed": False,
                "archived": False,
                "limit": limit,
                "offset": offset,
            }
            res = httpx.get(self.gamma_events_endpoint, params=params)
            if res.status_code != 200:
                print(
                    f"[events] request_failed status={res.status_code} url={self.gamma_events_endpoint} params={params}"
                )
                break

            batch = res.json()
            raw_events.extend(batch)
            print(
                f"[events] page={page} fetched_batch={len(batch)} offset={offset} params={params}"
            )

            if len(batch) < limit:
                break
            offset += limit

        if raw_events:
            print(
                f"[events] fetched_total={len(raw_events)} from={self.gamma_events_endpoint}"
            )

            active_count = 0
            closed_count = 0
            archived_count = 0
            restricted_count = 0
            status_combo_counts = {}
            for event in raw_events:
                active = bool(event.get("active"))
                closed = bool(event.get("closed"))
                archived = bool(event.get("archived"))
                restricted = bool(event.get("restricted"))
                if active:
                    active_count += 1
                if closed:
                    closed_count += 1
                if archived:
                    archived_count += 1
                if restricted:
                    restricted_count += 1

                key = (active, closed, archived, restricted)
                status_combo_counts[key] = status_combo_counts.get(key, 0) + 1

            print(
                "[events] raw_flags "
                f"active={active_count} "
                f"closed={closed_count} "
                f"archived={archived_count} "
                f"restricted={restricted_count}"
            )
            sorted_combos = sorted(
                status_combo_counts.items(),
                key=lambda item: item[1],
                reverse=True,
            )
            for combo, count in sorted_combos[:5]:
                active, closed, archived, restricted = combo
                print(
                    "[events] raw_combo "
                    f"count={count} "
                    f"active={active} closed={closed} archived={archived} restricted={restricted}"
                )

            parse_errors = 0
            for event in raw_events:
                try:
                    event_data = self.map_api_to_event(event)
                    events.append(SimpleEvent(**event_data))
                except Exception as e:
                    parse_errors += 1
                    event_id = event.get("id", "unknown")
                    title = event.get("title", "")
                    print(
                        f"[events] parse_error id={event_id} title={title!r}: {e}"
                    )

            print(f"[events] parsed={len(events)} parse_errors={parse_errors}")
        else:
            print("[events] no_raw_events_returned")
        return events

    def map_api_to_event(self, event) -> SimpleEvent:
        description = event["description"] if "description" in event.keys() else ""
        end = event.get("endDate") or ""
        markets = event.get("markets") or []
        return {
            "id": int(event["id"]),
            "ticker": event.get("ticker") or "",
            "slug": event.get("slug") or "",
            "title": event.get("title") or "",
            "description": description,
            "active": bool(event.get("active")),
            "closed": bool(event.get("closed")),
            "archived": bool(event.get("archived")),
            "new": bool(event.get("new")),
            "featured": bool(event.get("featured")),
            "restricted": bool(event.get("restricted")),
            "end": end,
            "markets": ",".join([str(x.get("id", "")) for x in markets if x.get("id")]),
        }

    def filter_events_for_trading(
        self, events: "list[SimpleEvent]"
    ) -> "list[SimpleEvent]":
        tradeable_events = []
        excluded_inactive = 0
        excluded_restricted = 0
        excluded_archived = 0
        excluded_closed = 0
        excluded_samples = []

        for event in events:
            excluded_reasons = []
            if not event.active:
                excluded_inactive += 1
                excluded_reasons.append("inactive")
            if event.restricted:
                excluded_restricted += 1
                excluded_reasons.append("restricted")
            if event.archived:
                excluded_archived += 1
                excluded_reasons.append("archived")
            if event.closed:
                excluded_closed += 1
                excluded_reasons.append("closed")

            if (
                event.active
                and (self.allow_restricted_events or not event.restricted)
                and not event.archived
                and not event.closed
            ):
                tradeable_events.append(event)
            elif len(excluded_samples) < 5:
                excluded_samples.append(
                    {
                        "id": event.id,
                        "title": event.title,
                        "reasons": ",".join(excluded_reasons),
                    }
                )

        print(
            "[events] filter_summary "
            f"input={len(events)} "
            f"tradeable={len(tradeable_events)} "
            f"allow_restricted={self.allow_restricted_events} "
            f"excluded_inactive={excluded_inactive} "
            f"excluded_restricted={excluded_restricted} "
            f"excluded_archived={excluded_archived} "
            f"excluded_closed={excluded_closed}"
        )
        for sample in excluded_samples:
            print(
                "[events] excluded_sample "
                f"id={sample['id']} title={sample['title']!r} reasons={sample['reasons']}"
            )
        return tradeable_events

    def get_all_tradeable_events(self) -> "list[SimpleEvent]":
        all_events = self.get_all_events()
        tradeable_events = self.filter_events_for_trading(all_events)
        print(
            f"[events] tradeable_total={len(tradeable_events)} from_parsed={len(all_events)}"
        )
        return tradeable_events

    def get_sampling_simplified_markets(self) -> "list[SimpleEvent]":
        if self.client is None:
            raise RuntimeError("CLOB client not initialized")
        markets = []
        raw_sampling_simplified_markets = self.client.get_sampling_simplified_markets()
        for raw_market in raw_sampling_simplified_markets["data"]:
            token_one_id = raw_market["tokens"][0]["token_id"]
            market = self.get_market(token_one_id)
            markets.append(market)
        return markets

    def get_orderbook(self, token_id: str) -> OrderBookSummary:
        if self.client is None:
            raise RuntimeError("CLOB client not initialized")
        return self.client.get_order_book(token_id)

    def get_orderbook_price(self, token_id: str) -> float:
        if self.client is None:
            raise RuntimeError("CLOB client not initialized")
        return float(self.client.get_price(token_id))

    def get_address_for_private_key(self):
        account = self.w3.eth.account.from_key(str(self.private_key))
        return account.address

    def get_funder_address(self) -> Optional[str]:
        if not self.funder_address:
            return None
        return self._as_checksum_address(self.funder_address)

    def get_balance_owner_address(self) -> str:
        funder = self.get_funder_address()
        if funder:
            return funder
        return self.get_address_for_private_key()

    @staticmethod
    def _is_plain_integer(value: str) -> bool:
        text = str(value or "").strip()
        return bool(text) and text.isdigit()

    def _as_checksum_address(self, address: str) -> str:
        return Web3.to_checksum_address(str(address).strip())

    def _erc20_contract(self, token_address: str):
        return self.web3.eth.contract(
            address=self._as_checksum_address(token_address),
            abi=self.erc20_approve,
        )

    def _token_addresses_for_balance_check(self) -> list[str]:
        raw_custom_addresses = [
            item.strip()
            for item in str(self.usdc_balance_token_addresses or "").split(",")
            if str(item).strip()
        ]
        ordered_addresses = [
            self.usdc_address,  # Polymarket collateral token (primary source for execution budget)
            self.native_usdc_address,  # Helpful diagnostic when users fund the wrong USDC token
            *raw_custom_addresses,
        ]
        deduped_addresses = []
        seen = set()
        for address in ordered_addresses:
            try:
                checksum = self._as_checksum_address(address)
            except Exception:
                continue
            lowered = checksum.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            deduped_addresses.append(checksum)
        return deduped_addresses

    def _read_erc20_balance(self, token_address: str, wallet_address: str) -> dict:
        contract = self._erc20_contract(token_address)
        raw_balance = int(contract.functions.balanceOf(wallet_address).call())
        try:
            decimals = int(contract.functions.decimals().call())
        except Exception:
            decimals = 6
        divisor = 10 ** max(decimals, 0)
        normalized_balance = float(raw_balance) / float(divisor)
        return {
            "address": self._as_checksum_address(token_address),
            "raw_balance": raw_balance,
            "decimals": decimals,
            "balance_usdc": normalized_balance,
        }

    def _parse_clob_balance_usdc(self, payload: dict) -> Optional[float]:
        if not isinstance(payload, dict):
            return None
        raw_balance = payload.get("balance")
        if raw_balance is None:
            return None
        raw_text = str(raw_balance).strip()
        try:
            if self._is_plain_integer(raw_text):
                # CLOB balance endpoint typically returns collateral units as 6-decimal fixed integers.
                return float(int(raw_text)) / 1_000_000.0
            return float(raw_text)
        except (TypeError, ValueError):
            return None

    def get_usdc_balance_report(self) -> dict:
        report = {
            "wallet_address": "",
            "signer_address": "",
            "funder_address": "",
            "balance_owner_address": "",
            "signature_type": self.signature_type,
            "chain_id": self.chain_id,
            "rpc_url": self.polygon_rpc,
            "collateral_address": self._as_checksum_address(self.usdc_address),
            "balances_by_token": {},
            "collateral_balance_usdc": 0.0,
            "clob_balance_usdc": None,
            "clob_balance_raw": None,
            "available_usdc_balance": 0.0,
            "balance_source": "onchain_collateral",
            "warnings": [],
            "errors": [],
        }

        try:
            signer_address = self.get_address_for_private_key()
            report["signer_address"] = signer_address
            funder_address = self.get_funder_address()
            report["funder_address"] = funder_address or ""
            wallet_address = funder_address or signer_address
            report["wallet_address"] = wallet_address
            report["balance_owner_address"] = wallet_address
        except Exception as err:
            report["errors"].append(f"wallet_derivation_failed error={err}")
            return report

        if self.signature_type in (1, 2) and not report["funder_address"]:
            report["warnings"].append(
                "missing_funder_address_for_proxy_signature "
                "set POLYMARKET_FUNDER_ADDRESS to your Polymarket profile wallet"
            )

        token_addresses = self._token_addresses_for_balance_check()
        for token_address in token_addresses:
            try:
                token_balance = self._read_erc20_balance(token_address, wallet_address)
                report["balances_by_token"][token_balance["address"]] = token_balance
            except Exception as err:
                report["errors"].append(
                    f"onchain_balance_failed token={token_address} error={err}"
                )

        collateral_address = report["collateral_address"]
        collateral_entry = report["balances_by_token"].get(collateral_address)
        if collateral_entry is not None:
            report["collateral_balance_usdc"] = float(collateral_entry["balance_usdc"])

        native_usdc_address = self._as_checksum_address(self.native_usdc_address)
        native_usdc_entry = report["balances_by_token"].get(native_usdc_address)
        if (
            native_usdc_entry is not None
            and float(native_usdc_entry.get("balance_usdc", 0.0)) > 0
            and report["collateral_balance_usdc"] <= 0
        ):
            report["warnings"].append(
                "native_usdc_detected_without_collateral_balance "
                f"native_token={native_usdc_address} collateral_token={collateral_address}"
            )

        if self.client is not None and self.credentials is not None:
            try:
                clob_payload = self.client.get_balance_allowance(
                    params=BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
                )
                report["clob_balance_raw"] = clob_payload
                report["clob_balance_usdc"] = self._parse_clob_balance_usdc(clob_payload)
            except Exception as err:
                report["errors"].append(f"clob_balance_failed error={err}")

        available_balance = float(report["collateral_balance_usdc"])
        if available_balance <= 0 and report["clob_balance_usdc"] is not None:
            available_balance = max(0.0, float(report["clob_balance_usdc"]))
            report["balance_source"] = "clob_balance_allowance"

        report["available_usdc_balance"] = float(available_balance)

        if (
            report["clob_balance_usdc"] is not None
            and report["collateral_balance_usdc"] > 0
            and abs(float(report["clob_balance_usdc"]) - report["collateral_balance_usdc"]) > 1.0
        ):
            report["warnings"].append(
                "clob_and_onchain_balance_mismatch "
                f"onchain={report['collateral_balance_usdc']:.6f} "
                f"clob={float(report['clob_balance_usdc']):.6f}"
            )

        return report

    def build_order(
        self,
        market_token: str,
        amount: float,
        nonce: str = str(round(time.time())),  # for cancellations
        side: str = "BUY",
        expiration: str = "0",  # timestamp after which order expires
    ):
        signer = Signer(self.private_key)
        builder = OrderBuilder(self.exchange_address, self.chain_id, signer)

        buy = side == "BUY"
        side = 0 if buy else 1
        maker_amount = amount if buy else 0
        taker_amount = amount if not buy else 0
        order_data = OrderData(
            maker=self.get_address_for_private_key(),
            tokenId=market_token,
            makerAmount=maker_amount,
            takerAmount=taker_amount,
            feeRateBps="1",
            nonce=nonce,
            side=side,
            expiration=expiration,
        )
        order = builder.build_signed_order(order_data)
        return order

    def execute_order(self, price, size, side, token_id) -> str:
        if self.client is None:
            raise RuntimeError("CLOB client not initialized")
        return self.client.create_and_post_order(
            OrderArgs(price=price, size=size, side=side, token_id=token_id)
        )

    def resolve_token_for_outcome(
        self, outcomes: list, token_ids: list, selected_outcome: str, side: str
    ) -> dict:
        if not outcomes or not token_ids:
            raise ValueError("Cannot resolve token without outcomes and token ids")
        if len(outcomes) != len(token_ids):
            raise ValueError(
                f"Outcome/token length mismatch outcomes={len(outcomes)} token_ids={len(token_ids)}"
            )

        normalized_outcome_map = {}
        for idx, outcome in enumerate(outcomes):
            normalized_outcome_map[str(outcome).strip().lower()] = idx

        selected_index = normalized_outcome_map.get(str(selected_outcome).strip().lower())
        if selected_index is None:
            raise ValueError(
                f"Selected outcome not found in market outcomes selected={selected_outcome!r} outcomes={outcomes}"
            )

        requested_side = str(side or "BUY").strip().upper()
        if requested_side not in ("BUY", "SELL"):
            raise ValueError(f"Unsupported side: {side}")

        execution_side = "BUY"
        execution_outcome = outcomes[selected_index]
        token_index = selected_index
        transform = "NONE"

        # Polymarket market orders buy a token. SELL signals are mapped to opposite BUY for binary markets.
        if requested_side == "SELL":
            if len(outcomes) != 2:
                raise ValueError(
                    "SELL mapping is only supported for binary markets; got non-binary market"
                )
            token_index = 1 - selected_index
            execution_outcome = outcomes[token_index]
            transform = "SELL_TO_OPPOSITE_BUY"

        return {
            "token_id": str(token_ids[token_index]),
            "execution_side": execution_side,
            "requested_side": requested_side,
            "requested_outcome": selected_outcome,
            "execution_outcome": execution_outcome,
            "transform": transform,
        }

    def execute_market_order_for_token(self, token_id: str, amount: float) -> str:
        if self.client is None:
            raise RuntimeError("CLOB client not initialized")
        if amount <= 0:
            raise ValueError(f"amount must be > 0; got {amount}")
        order_args = MarketOrderArgs(token_id=str(token_id), amount=float(amount))
        signed_order = self.client.create_market_order(order_args)
        print("Execute market order... signed_order ", signed_order)
        resp = self.client.post_order(signed_order, orderType=OrderType.FOK)
        print(resp)
        print("Done!")
        return resp

    def execute_market_order(self, market, amount) -> str:
        token_ids = ast.literal_eval(market[0].dict()["metadata"]["clob_token_ids"])
        if not token_ids:
            raise ValueError("No token ids available for market order")
        token_id = token_ids[1] if len(token_ids) > 1 else token_ids[0]
        return self.execute_market_order_for_token(token_id=token_id, amount=amount)

    def get_usdc_balance(self) -> float:
        report = self.get_usdc_balance_report()
        return float(report.get("available_usdc_balance", 0.0))


def test():
    host = "https://clob.polymarket.com"
    key = os.getenv("POLYGON_WALLET_PRIVATE_KEY")
    print(key)
    chain_id = POLYGON

    # Create CLOB client and get/set API credentials
    client = ClobClient(host, key=key, chain_id=chain_id)
    client.set_api_creds(client.create_or_derive_api_creds())

    creds = ApiCreds(
        api_key=os.getenv("CLOB_API_KEY"),
        api_secret=os.getenv("CLOB_SECRET"),
        api_passphrase=os.getenv("CLOB_PASS_PHRASE"),
    )
    chain_id = AMOY
    client = ClobClient(host, key=key, chain_id=chain_id, creds=creds)

    print(client.get_markets())
    print(client.get_simplified_markets())
    print(client.get_sampling_markets())
    print(client.get_sampling_simplified_markets())
    print(client.get_market("condition_id"))

    print("Done!")


def gamma():
    url = "https://gamma-com"
    markets_url = url + "/markets"
    res = httpx.get(markets_url)
    code = res.status_code
    if code == 200:
        markets: list[SimpleMarket] = []
        data = res.json()
        for market in data:
            try:
                market_data = {
                    "id": int(market["id"]),
                    "question": market["question"],
                    # "start": market['startDate'],
                    "end": market["endDate"],
                    "description": market["description"],
                    "active": market["active"],
                    "deployed": market["deployed"],
                    "funded": market["funded"],
                    # "orderMinSize": float(market['orderMinSize']) if market['orderMinSize'] else 0,
                    # "orderPriceMinTickSize": float(market['orderPriceMinTickSize']),
                    "rewardsMinSize": float(market["rewardsMinSize"]),
                    "rewardsMaxSpread": float(market["rewardsMaxSpread"]),
                    "volume": float(market["volume"]),
                    "spread": float(market["spread"]),
                    "outcome_a": str(market["outcomes"][0]),
                    "outcome_b": str(market["outcomes"][1]),
                    "outcome_a_price": str(market["outcomePrices"][0]),
                    "outcome_b_price": str(market["outcomePrices"][1]),
                }
                markets.append(SimpleMarket(**market_data))
            except Exception as err:
                print(f"error {err} for market {id}")
        pdb.set_trace()
    else:
        raise Exception()


def main():
    # auth()
    # test()
    # gamma()
    print(Polymarket().get_all_events())


if __name__ == "__main__":
    load_dotenv()

    p = Polymarket()

    # k = p.get_api_key()
    # m = p.get_sampling_simplified_markets()

    # print(m)
    # m = p.get_market('11015470973684177829729219287262166995141465048508201953575582100565462316088')

    # t = m[0]['token_id']
    # o = p.get_orderbook(t)
    # pdb.set_trace()

    """
    
    (Pdb) pprint(o)
            OrderBookSummary(
                market='0x26ee82bee2493a302d21283cb578f7e2fff2dd15743854f53034d12420863b55', 
                asset_id='11015470973684177829729219287262166995141465048508201953575582100565462316088', 
                bids=[OrderSummary(price='0.01', size='600005'), OrderSummary(price='0.02', size='200000'), ...
                asks=[OrderSummary(price='0.99', size='100000'), OrderSummary(price='0.98', size='200000'), ...
            )
    
    """

    # https://polygon-rpc.com

    test_market_token_id = (
        "101669189743438912873361127612589311253202068943959811456820079057046819967115"
    )
    test_market_data = p.get_market(test_market_token_id)

    # test_size = 0.0001
    test_size = 1
    test_side = BUY
    test_price = float(ast.literal_eval(test_market_data["outcome_prices"])[0])

    # order = p.execute_order(
    #    test_price,
    #    test_size,
    #    test_side,
    #    test_market_token_id,
    # )

    # order = p.execute_market_order(test_price, test_market_token_id)

    balance = p.get_usdc_balance()
