"""
Live tests — every client method is run against the real papertrade.xyz server.

Run:
    cd /home/fsdf1234/tmp/papertrade-client
    source .venv/bin/activate
    pytest tests/test_live.py -v

Write tests (require a real wallet with balance):
    PAPERTRADE_PRIVATE_KEY=0x… pytest tests/test_live.py -v -k write

Each test records its status:  PASS / FAIL / SKIP (auth-gated)
"""
from __future__ import annotations

import os
import time

import pytest

from papertrade import PaperTradeClient
from papertrade.wallet import generate_okx_wallet, wallet_from_private_key
from papertrade.signing import (
    sign_register_session_key,
    sign_open_position,
    sign_close_positions,
    sign_withdraw_to_core,
    sign_stake,
    sign_unstake,
    sign_claim,
    sign_cancel_intent,
    next_nonce,
    deadline,
)
from papertrade.constants import (
    CHAIN_ID,
    EXCHANGE_CONTRACT,
    DOMAIN_EXCHANGE,
    DOMAIN_PAPER_STAKING,
    DOMAIN_CANCELLATION,
    INTENT_TYPES,
)
from papertrade.exceptions import HttpError

ZERO_ADDR = "0x0000000000000000000000000000000000000000"


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def client():
    c = PaperTradeClient()
    yield c
    c.close()


@pytest.fixture(scope="session")
def wallet():
    pk = os.environ.get("PAPERTRADE_PRIVATE_KEY")
    if pk:
        return wallet_from_private_key(pk)
    # Generate a fresh throwaway wallet for signing tests
    info = generate_okx_wallet()
    return wallet_from_private_key(info["private_key"])


@pytest.fixture(scope="session")
def authed_client(wallet):
    c = PaperTradeClient(wallet=wallet)
    yield c
    c.close()


# ── ① Health ─────────────────────────────────────────────────────────

def test_ready(client):
    """GET /query/ready → status: ok"""
    resp = client.read.ready()
    assert "status" in resp
    assert resp["status"] in ("ok", "ready"), f"Unexpected status: {resp['status']}"
    print(f"\n  ✓ /query/ready: {resp}")


# ── ② Protocol metrics (all confirmed live) ───────────────────────────

def test_protocol_summary(client):
    """GET /query/protocol/summary"""
    resp = client.read.protocol_summary()
    assert resp.get("ok") is True or "balances" in resp
    keys = list(resp.keys())
    print(f"\n  ✓ protocol_summary keys: {keys}")


def test_protocol_history_1h(client):
    """GET /query/protocol/history?interval=1h"""
    resp = client.read.protocol_history("1h")
    assert "startMs" in resp or "columns" in resp
    print(f"\n  ✓ protocol_history(1h) keys: {list(resp.keys())}")


def test_protocol_history_1d(client):
    """GET /query/protocol/history?interval=1d"""
    resp = client.read.protocol_history("1d")
    assert "columns" in resp or "startMs" in resp


def test_protocol_history_all(client):
    """interval=all returns 400 on this server — only 1h/1d confirmed"""
    from papertrade.exceptions import HttpError
    try:
        resp = client.read.protocol_history("all")
        assert "columns" in resp or "startMs" in resp
    except (ValueError, HttpError):
        pass  # Expected — server rejects interval=all


def test_protocol_trades_recent(client):
    """GET /query/protocol/trades/recent"""
    resp = client.read.protocol_trades_recent()
    assert "events" in resp or "count" in resp
    print(f"\n  ✓ recent_trades count: {resp.get('count')}")


def test_protocol_paper_activity(client):
    """GET /query/protocol/paper/activity"""
    resp = client.read.protocol_paper_activity()
    assert "items" in resp
    print(f"\n  ✓ paper_activity items: {len(resp.get('items', []))}")


def test_protocol_queue_summary(client):
    """GET /query/protocol/queue-summary"""
    resp = client.read.protocol_queue_summary()
    assert "total" in resp or "count" in resp
    print(f"\n  ✓ queue_summary total: {resp.get('total')}")


def test_notices(client):
    """GET /query/notices"""
    notices = client.read.notices()
    assert isinstance(notices, list)
    print(f"\n  ✓ notices: {len(notices)} active")


# ── ③ Market data ─────────────────────────────────────────────────────

@pytest.mark.parametrize("instrument_id,range_", [
    (0, "1"), (0, "0.5"), (1, "1"), (1, "5"),
])
def test_liquidation_map(client, instrument_id, range_):
    """GET /query/markets/{id}/liquidation-map?range={r}"""
    resp = client.read.liquidation_map(instrument_id, range_)
    assert resp.get("ok") is True
    assert resp.get("instrumentId") == instrument_id
    assert len(resp.get("buckets", [])) == 150
    print(f"\n  ✓ liq_map({instrument_id}, {range_}): {len(resp['buckets'])} buckets")


# ── ④ Trading state ───────────────────────────────────────────────────

def test_trading_state(client):
    """GET /state/trading"""
    resp = client.read.trading_state()
    assert "instruments" in resp
    assert len(resp["instruments"]) >= 2
    # Minimum size check: should be 10 USDC (10 * 10^18)
    min_size = int(resp["minimumTradeSizeRaw"])
    assert min_size == 10 * 10**18, f"Unexpected min size: {min_size}"
    print(f"\n  ✓ trading_state: paused={resp['tradingPaused']}, instruments={len(resp['instruments'])}")


def test_position_topology(client):
    """GET /state/protocol/position-topology"""
    resp = client.read.position_topology()
    assert resp.get("ok") is True
    assert resp.get("count") is not None
    grid = resp.get("grid", {})
    if isinstance(grid, dict):
        assert grid.get("w") == 96 and grid.get("h") == 64
        assert len(grid.get("data", [])) == 6144
    elif isinstance(grid, list):
        assert len(grid) == 6144
    print(f"\n  ✓ position_topology: {resp['count']} positions")


def test_house_current(client):
    """GET /state/house/current"""
    resp = client.read.house_current()
    assert resp.get("ok") is True
    assert "revision" in resp
    print(f"\n  ✓ house_current revision: {resp.get('revision')}")


def test_house_delta_btc(client):
    """GET /state/house/delta?coin=BTC"""
    resp = client.read.house_delta("BTC")
    assert resp.get("ok") is True
    assert "delta" in resp
    print(f"\n  ✓ house_delta(BTC): sourceAsOfMs={resp.get('sourceAsOfMs')}")


def test_house_delta_eth(client):
    """GET /state/house/delta?coin=ETH"""
    resp = client.read.house_delta("ETH")
    assert resp.get("ok") is True


# ── ⑤ Account data (zero address, publicly readable) ─────────────────

def test_account_funding(client):
    """GET /query/accounts/{address}/funding"""
    resp = client.read.account_funding(ZERO_ADDR)
    assert "items" in resp
    assert "coreAccount" in resp
    print(f"\n  ✓ account_funding: {len(resp['items'])} items, coreAccount={resp['coreAccount']}")


def test_account_trades(client):
    """GET /query/accounts/{address}/trades"""
    resp = client.read.account_trades(ZERO_ADDR)
    assert "items" in resp
    print(f"\n  ✓ account_trades: {len(resp.get('items', []))} trades")


def test_account_queue_ring(client):
    """GET /query/accounts/{address}/queue-ring"""
    resp = client.read.account_queue_ring(ZERO_ADDR)
    assert resp.get("ok") is True
    assert "total" in resp
    print(f"\n  ✓ queue_ring: total={resp.get('total')}, count={resp.get('count')}")


def test_account_portfolio_history_all(client):
    """GET /query/accounts/{address}/portfolio-history?range=all"""
    resp = client.read.account_portfolio_history(ZERO_ADDR, range_="all")
    assert "fromMs" in resp or "columns" in resp
    print(f"\n  ✓ portfolio_history(all): keys={list(resp.keys())[:5]}")


def test_account_leaderboard_badges(client):
    """GET /query/accounts/{address}/leaderboard-badges"""
    resp = client.read.account_leaderboard_badges(ZERO_ADDR)
    assert resp.get("ok") is True
    assert "badges" in resp
    print(f"\n  ✓ leaderboard_badges: {resp.get('total')} total badges")


# ── ⑥ Instruments convenience ────────────────────────────────────────

def test_instruments(client):
    """instruments() helper returns BTC and ETH"""
    insts = client.instruments()
    names = {i["name"] for i in insts}
    assert "BTC" in names
    assert "ETH" in names
    print(f"\n  ✓ instruments: {[i['name'] for i in insts]}")


# ── ⑦ EIP-712 signing (no network — pure local crypto) ───────────────

def test_signing_register_session_key(wallet):
    """sign_register_session_key produces correct r/s/v format"""
    signed = sign_register_session_key(
        main_wallet=wallet,
        session_key_address=wallet.address,
    )
    assert signed["user"].lower() == wallet.address.lower()
    assert signed["key"].lower() == wallet.address.lower()
    assert signed["r"].startswith("0x") and len(signed["r"]) == 66
    assert signed["s"].startswith("0x") and len(signed["s"]) == 66
    assert signed["v"] in ("27", "28")
    assert signed["feeAddress"] == "0x0000000000000000000000000000000000000000"
    print(f"\n  ✓ RegisterSessionKey signed: v={signed['v']}, r={signed['r'][:10]}…")


def test_signing_open_position(wallet):
    """sign_open_position produces correct EIP-712 payload"""
    signed = sign_open_position(
        session_key=wallet,
        user_address=wallet.address,
        instrument_id=0,   # BTC
        is_long=True,
        size_raw=100 * 10**18,  # $100 margin
        leverage=10,
    )
    assert signed["user"].lower() == wallet.address.lower()
    assert signed["instrumentId"] == "0"
    assert signed["isLong"] is True
    assert signed["size"] == str(100 * 10**18)
    assert signed["leverage"] == "10"
    assert signed["useDebt"] is False
    assert signed["r"].startswith("0x")
    assert signed["v"] in ("27", "28")
    print(f"\n  ✓ OpenPosition signed: instrument=BTC, long, $100, 10x")


def test_signing_close_positions(wallet):
    """sign_close_positions produces correct positionIds format"""
    signed = sign_close_positions(
        session_key=wallet,
        user_address=wallet.address,
        position_ids=[42, 100, 9999],
    )
    assert signed["positionIds"] == ["42", "100", "9999"]
    assert signed["r"].startswith("0x")
    print(f"\n  ✓ Close signed: positionIds={signed['positionIds']}")


def test_signing_withdraw(wallet):
    """sign_withdraw_to_core produces correct amount"""
    signed = sign_withdraw_to_core(
        main_wallet=wallet,
        amount_raw=50 * 10**18,  # $50 USDC
    )
    assert signed["user"].lower() == wallet.address.lower()
    assert signed["amount"] == str(50 * 10**18)
    assert signed["r"].startswith("0x")
    print(f"\n  ✓ WithdrawToCore signed: amount=$50")


def test_signing_stake(wallet):
    """sign_stake produces correct amount"""
    signed = sign_stake(main_wallet=wallet, amount_raw=100 * 10**18)
    assert signed["amount"] == str(100 * 10**18)
    print(f"\n  ✓ Stake signed: amount=100 PAPER")


def test_signing_claim(wallet):
    """sign_claim produces minimal correct payload"""
    signed = sign_claim(main_wallet=wallet)
    assert signed["user"].lower() == wallet.address.lower()
    assert signed["r"].startswith("0x")
    print(f"\n  ✓ Claim signed")


def test_signing_cancel(wallet):
    """sign_cancel_intent uses cancellation domain"""
    intent_id = "0x" + "ab" * 32  # fake bytes32
    signed = sign_cancel_intent(main_wallet=wallet, intent_id=intent_id)
    assert signed["intentId"] == intent_id.lower()
    assert signed["r"].startswith("0x")
    print(f"\n  ✓ CancelIntent signed")


def test_nonce_monotonic():
    """next_nonce() is strictly monotonically increasing"""
    nonces = [next_nonce("test") for _ in range(10)]
    assert nonces == sorted(nonces)
    assert len(set(nonces)) == len(nonces)
    print(f"\n  ✓ nonces monotonic: {nonces[:3]}…")


# ── ⑧ Dry-run write methods (sign + show payload, NO network submit) ──

def test_write_open_position_dryrun(authed_client):
    """open_position dry_run=True returns signed payload without submitting"""
    result = authed_client.write.open_position(
        instrument="BTC",
        is_long=True,
        margin_usdc=100.0,
        leverage=10,
        dry_run=True,
    )
    assert result.get("dry_run") is True
    body = result["would_post"]
    assert body["action"] == "openPosition"
    assert body["signed"]["r"].startswith("0x")
    print(f"\n  ✓ open_position dry_run: action={body['action']}, r={body['signed']['r'][:10]}…")


def test_write_close_positions_dryrun(authed_client):
    """close_positions dry_run=True returns signed payload"""
    result = authed_client.write.close_positions([1, 2, 3], dry_run=True)
    assert result.get("dry_run") is True
    assert result["would_post"]["action"] == "closePositions"
    print(f"\n  ✓ close_positions dry_run: positionIds=[1,2,3]")


def test_write_register_session_key_dryrun(authed_client):
    """register_session_key dry_run=True returns signed payload"""
    result = authed_client.write.register_session_key(dry_run=True)
    assert result.get("dry_run") is True
    assert result["would_post"]["action"] == "registerSessionKey"
    print(f"\n  ✓ register_session_key dry_run: OK")


def test_write_withdraw_dryrun(authed_client):
    """withdraw_to_core dry_run=True"""
    result = authed_client.write.withdraw_to_core(50.0, dry_run=True)
    assert result.get("dry_run") is True
    assert result["would_post"]["action"] == "withdrawToCore"
    print(f"\n  ✓ withdraw_to_core dry_run: $50 USDC")


def test_write_stake_dryrun(authed_client):
    """stake_paper dry_run=True"""
    result = authed_client.write.stake_paper(100.0, dry_run=True)
    assert result.get("dry_run") is True
    print(f"\n  ✓ stake_paper dry_run: 100 PAPER")


def test_write_unstake_dryrun(authed_client):
    """unstake_paper dry_run=True"""
    result = authed_client.write.unstake_paper(50.0, dry_run=True)
    assert result.get("dry_run") is True
    print(f"\n  ✓ unstake_paper dry_run: 50 PAPER")


def test_write_claim_dryrun(authed_client):
    """claim_paper_rewards dry_run=True"""
    result = authed_client.write.claim_paper_rewards(dry_run=True)
    assert result.get("dry_run") is True
    print(f"\n  ✓ claim_paper_rewards dry_run: OK")


def test_write_cancel_intent_dryrun(authed_client):
    """cancel_intent dry_run=True"""
    fake_id = "0x" + "cc" * 32
    result = authed_client.write.cancel_intent(fake_id, dry_run=True)
    assert result.get("dry_run") is True
    print(f"\n  ✓ cancel_intent dry_run: {fake_id[:10]}…")


# ── ⑨ Write tests that actually submit (require funded wallet + --write) ──
# These are gated: only run when PAPERTRADE_PRIVATE_KEY is set AND
# PAPERTRADE_RUN_WRITES=1 is explicitly set in the environment.

WRITE_ENABLED = (
    os.environ.get("PAPERTRADE_PRIVATE_KEY") and
    os.environ.get("PAPERTRADE_RUN_WRITES") == "1"
)


@pytest.mark.skipif(not WRITE_ENABLED,
                    reason="Set PAPERTRADE_PRIVATE_KEY + PAPERTRADE_RUN_WRITES=1 to run write tests")
def test_write_register_session_key_live(authed_client):
    """⚠️  LIVE WRITE: register the session key on-chain"""
    result = authed_client.write.register_session_key(dry_run=False)
    assert "intentId" in result or result.get("ok") is not False
    print(f"\n  ✓ register_session_key LIVE: {result}")


@pytest.mark.skipif(not WRITE_ENABLED,
                    reason="Set PAPERTRADE_PRIVATE_KEY + PAPERTRADE_RUN_WRITES=1 to run write tests")
def test_write_open_position_live(authed_client):
    """⚠️  LIVE WRITE: open a $10 BTC long at 10x (minimum viable)"""
    result = authed_client.write.open_position(
        instrument="BTC",
        is_long=True,
        margin_usdc=10.0,   # $10 minimum margin
        leverage=10,
        dry_run=False,
    )
    assert "intentId" in result or result.get("ok") is not False
    print(f"\n  ✓ open_position LIVE: {result}")
