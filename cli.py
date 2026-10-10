#!/usr/bin/env python3
"""
papertrade-cli — CLI for the unofficial PaperTrade client.

READ commands (no wallet needed):
  ready                   Health-check the exchange
  protocol-summary        TVL, volume, fees
  protocol-history        Time-series metrics
  protocol-trades         Recent trades across all accounts
  protocol-paper          PAPER token activity
  protocol-queue          Deposit queue summary
  notices                 System announcements
  liquidation-map         Open-interest per price bucket
  trading-state           Live trading parameters & instruments
  position-topology       Position heatmap grid
  house-current           Protocol reserve state
  house-delta             Protocol reserve change
  account-funding         Deposit/withdrawal history
  account-trades          Trade history for an address
  account-queue-ring      Position in deposit queue
  account-queue-balances  Paginated queue balances
  account-portfolio       Portfolio P&L history
  account-badges          Leaderboard badges
  leaderboard             Global leaderboard

WALLET commands:
  wallet-new              Generate a new OKX-compatible wallet
  wallet-show             Show address from a wallet file or env var

WRITE commands (⚠️  require --write flag):
  register-session-key    Register the trading session key (run once)
  open-position           Open a long or short position
  close-positions         Close open positions by ID
  withdraw                Withdraw USDC to HyperCore
  stake                   Stake PAPER tokens
  unstake                 Unstake PAPER tokens
  claim                   Claim PAPER rewards
  cancel-intent           Cancel a queued intent

DISCLAIMER: Unofficial, reverse-engineered. ToS risk is the user's to own.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

import click
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from papertrade import (
    PaperTradeClient,
    generate_okx_wallet,
    wallet_from_private_key,
    wallet_from_mnemonic,
    save_wallet,
    load_wallet,
)
from papertrade.exceptions import PaperTradeError, IntentError

console = Console()


# ── Shared options ─────────────────────────────────────────────────────
def _wallet_option(fn):
    fn = click.option(
        "--wallet-file", "-w",
        envvar="PAPERTRADE_WALLET_FILE",
        default=None,
        help="Path to wallet JSON file (or set PAPERTRADE_PRIVATE_KEY env var).",
    )(fn)
    return fn


def _write_flag(fn):
    fn = click.option(
        "--write", "do_write",
        is_flag=True,
        default=False,
        help="⚠️  Actually execute the write. Without this flag, shows the signed payload only.",
    )(fn)
    return fn


def _build_client(wallet_file: Optional[str] = None) -> PaperTradeClient:
    wallet = None
    if wallet_file:
        try:
            wallet = load_wallet(wallet_file)
        except Exception as e:
            console.print(f"[red]Failed to load wallet: {e}[/red]")
            sys.exit(1)
    elif os.environ.get("PAPERTRADE_PRIVATE_KEY"):
        wallet = wallet_from_private_key(os.environ["PAPERTRADE_PRIVATE_KEY"])
    return PaperTradeClient(wallet=wallet)


def _out(data: dict | list) -> None:
    rprint(json.dumps(data, indent=2, default=str))


# ─────────────────────────────────────────────────────────────────────
@click.group()
@click.version_option("0.1.0", prog_name="papertrade")
def cli():
    """Unofficial PaperTrade CLI — papertrade.xyz reverse-engineered client."""


# ══════════════════════ READ COMMANDS ══════════════════════════════════

@cli.command("ready")
def cmd_ready():
    """Health-check: is the exchange operational?"""
    with _build_client() as c:
        data = c.read.ready()
        rprint(f"[green]status: {data.get('status')}[/green]")


@cli.command("protocol-summary")
def cmd_protocol_summary():
    """TVL, volume, fee metrics across the protocol."""
    with _build_client() as c:
        _out(c.read.protocol_summary())


@cli.command("protocol-history")
@click.option("--interval", default="1d",
              type=click.Choice(["1h", "1d", "1w", "all"]),
              show_default=True, help="Time resolution.")
def cmd_protocol_history(interval):
    """Protocol time-series: TVL, volume, PnL, liquidations."""
    with _build_client() as c:
        _out(c.read.protocol_history(interval))


@cli.command("protocol-trades")
def cmd_protocol_trades():
    """Most recent trades across all accounts."""
    with _build_client() as c:
        _out(c.read.protocol_trades_recent())


@cli.command("protocol-paper")
def cmd_protocol_paper():
    """PAPER token staking and distribution activity."""
    with _build_client() as c:
        _out(c.read.protocol_paper_activity())


@cli.command("protocol-queue")
def cmd_protocol_queue():
    """Global deposit queue summary."""
    with _build_client() as c:
        _out(c.read.protocol_queue_summary())


@cli.command("notices")
def cmd_notices():
    """Active system notices and announcements."""
    with _build_client() as c:
        notices = c.read.notices()
        if not notices:
            rprint("[dim]No active notices.[/dim]")
        else:
            _out(notices)


@cli.command("liquidation-map")
@click.option("--instrument", default="BTC",
              type=click.Choice(["BTC", "ETH"]), show_default=True)
@click.option("--range", "price_range", default="1",
              type=click.Choice(["0.1","0.25","0.5","1","2","5","10","25"]),
              show_default=True, help="Price range ±% around current price.")
def cmd_liquidation_map(instrument, price_range):
    """Open-interest per price bucket (liquidation map)."""
    from papertrade.constants import INSTRUMENT_BY_NAME
    iid = INSTRUMENT_BY_NAME[instrument]
    with _build_client() as c:
        _out(c.read.liquidation_map(iid, price_range))


@cli.command("trading-state")
def cmd_trading_state():
    """Live global trading parameters, instruments, and intake status."""
    with _build_client() as c:
        state = c.read.trading_state()
        # Pretty-print instruments table
        t = Table(title="Instruments", show_header=True)
        t.add_column("ID"); t.add_column("Name"); t.add_column("Active")
        for row in state.get("instruments", []):
            t.add_row(str(row[0]), str(row[1]), "✓" if row[4] else "✗")
        console.print(t)
        rprint(f"[bold]Paused:[/bold] {state.get('tradingPaused')}")
        rprint(f"[bold]Min margin (USDC):[/bold] "
               f"{int(state.get('minimumTradeSizeRaw','0')) / 1e18:.2f}")
        rprint(f"[bold]Min notional (USDC):[/bold] "
               f"{int(state.get('minimumOpenNotionalRaw','0')) / 1e18:.2f}")


@cli.command("position-topology")
def cmd_position_topology():
    """Protocol-wide open position heatmap grid (96x64)."""
    with _build_client() as c:
        data = c.read.position_topology()
        rprint(f"[bold]Open positions:[/bold] {data.get('count')}")
        rprint(f"[bold]nExt/pExt:[/bold] {data.get('nExt')} / {data.get('pExt')}")


@cli.command("house-current")
def cmd_house_current():
    """Protocol reserve (house) current state."""
    with _build_client() as c:
        _out(c.read.house_current())


@cli.command("house-delta")
@click.option("--coin", default="BTC",
              type=click.Choice(["BTC", "ETH"]), show_default=True)
def cmd_house_delta(coin):
    """Protocol reserve delta for a specific coin."""
    with _build_client() as c:
        _out(c.read.house_delta(coin))


@cli.command("account-funding")
@click.argument("address")
def cmd_account_funding(address):
    """Deposit/withdrawal history for an address."""
    with _build_client() as c:
        _out(c.read.account_funding(address))


@cli.command("account-trades")
@click.argument("address")
@click.option("--cursor", default=None, help="Pagination cursor.")
def cmd_account_trades(address, cursor):
    """Paginated trade history for an address."""
    with _build_client() as c:
        _out(c.read.account_trades(address, cursor=cursor))


@cli.command("account-queue-ring")
@click.argument("address")
def cmd_account_queue_ring(address):
    """Account's position in the deposit queue."""
    with _build_client() as c:
        _out(c.read.account_queue_ring(address))


@cli.command("account-queue-balances")
@click.argument("address")
@click.option("--cursor", default=None)
@click.option("--limit", default=75, show_default=True)
def cmd_account_queue_balances(address, cursor, limit):
    """Paginated queue balance entries for an address."""
    with _build_client() as c:
        _out(c.read.account_queue_balances(address, cursor=cursor, limit=limit))


@cli.command("account-portfolio")
@click.argument("address")
@click.option("--range", "range_", default="all",
              type=click.Choice(["24h","7d","30d","all"]), show_default=True)
def cmd_account_portfolio(address, range_):
    """Portfolio P&L history for an address."""
    with _build_client() as c:
        _out(c.read.account_portfolio_history(address, range_=range_))


@cli.command("account-badges")
@click.argument("address")
def cmd_account_badges(address):
    """Leaderboard badges for an address."""
    with _build_client() as c:
        _out(c.read.account_leaderboard_badges(address))


@cli.command("leaderboard")
@click.argument("address", default="0x0000000000000000000000000000000000000000")
@click.option("--window", default="24h",
              type=click.Choice(["24h","7d","30d","all"]), show_default=True)
@click.option("--page", default=0, show_default=True)
@click.option("--sort-key", default="totalWindowedPnl", show_default=True)
@click.option("--sort-dir", default="desc",
              type=click.Choice(["asc","desc"]), show_default=True)
@click.option("--query", default="", help="Search filter.")
def cmd_leaderboard(address, window, page, sort_key, sort_dir, query):
    """Global leaderboard. Pass address for own rank (selfRow)."""
    with _build_client() as c:
        _out(c.read.leaderboard(address, window, page, sort_key, sort_dir, query))


# ══════════════════════ WALLET COMMANDS ═══════════════════════════════

@cli.command("wallet-new")
@click.option("--output", "-o", default="wallet.json", show_default=True,
              help="Path to save the wallet JSON file.")
@click.option("--words", default=12, type=click.Choice(["12","24"]), show_default=True)
def cmd_wallet_new(output, words):
    """Generate a new OKX-compatible BIP-39 wallet and save it."""
    info = generate_okx_wallet(words=int(words))
    p = save_wallet(info, output)
    console.print(f"\n[green]✓ Wallet generated:[/green] {p}")
    console.print(f"[bold]Address:[/bold]     {info['address']}")
    console.print(f"[bold]Derivation:[/bold]  {info['path']}")
    console.print(
        "\n[red bold]⚠️  NEVER share your mnemonic or private key.[/red bold]\n"
        f"[dim]Mnemonic stored in {p} (permissions 0600). "
        "Back it up securely.[/dim]"
    )


@cli.command("wallet-show")
@click.option("--wallet-file", "-w", default=None)
def cmd_wallet_show(wallet_file):
    """Show the address of a loaded wallet."""
    acct = None
    if wallet_file:
        acct = load_wallet(wallet_file)
    elif os.environ.get("PAPERTRADE_PRIVATE_KEY"):
        acct = wallet_from_private_key(os.environ["PAPERTRADE_PRIVATE_KEY"])
    if acct is None:
        console.print("[red]No wallet found. Use --wallet-file or PAPERTRADE_PRIVATE_KEY.[/red]")
        sys.exit(1)
    rprint(f"[bold]Address:[/bold] {acct.address}")


# ══════════════════════ WRITE COMMANDS ════════════════════════════════

@cli.command("register-session-key")
@_wallet_option
@_write_flag
def cmd_register_session_key(wallet_file, do_write):
    """
    ⚠️  WRITE: Register the session key (run once before trading).

    Signs a RegisterSessionKey EIP-712 intent with your main wallet.
    Without --write, prints the signed payload only.
    """
    with _build_client(wallet_file) as c:
        if c.write is None:
            console.print("[red]No wallet loaded. Use --wallet-file or PAPERTRADE_PRIVATE_KEY.[/red]")
            sys.exit(1)
        result = c.write.register_session_key(dry_run=not do_write)
        if not do_write:
            console.print("[yellow]DRY RUN — pass --write to submit:[/yellow]")
        _out(result)


@cli.command("open-position")
@_wallet_option
@_write_flag
@click.option("--instrument", default="BTC",
              type=click.Choice(["BTC","ETH"]), show_default=True)
@click.option("--long/--short", default=True, show_default=True)
@click.option("--margin", required=True, type=float,
              help="Margin in USDC (e.g. 100.0 = $100).")
@click.option("--leverage", required=True, type=int,
              help="Leverage multiplier (1–1000).")
@click.option("--debt/--no-debt", default=False, show_default=True,
              help="Open with borrowed collateral.")
def cmd_open_position(wallet_file, do_write, instrument, long, margin, leverage, debt):
    """
    ⚠️  WRITE: Open a leveraged long or short position.

    Without --write, prints the signed EIP-712 payload without sending.
    """
    with _build_client(wallet_file) as c:
        if c.write is None:
            console.print("[red]No wallet loaded.[/red]"); sys.exit(1)
        try:
            result = c.write.open_position(
                instrument=instrument,
                is_long=long,
                margin_usdc=margin,
                leverage=leverage,
                use_debt=debt,
                dry_run=not do_write,
            )
        except (PaperTradeError, ValueError) as e:
            console.print(f"[red]Error: {e}[/red]"); sys.exit(1)
        if not do_write:
            console.print("[yellow]DRY RUN — pass --write to submit:[/yellow]")
        _out(result)


@cli.command("close-positions")
@_wallet_option
@_write_flag
@click.argument("position_ids", nargs=-1, type=int, required=True)
def cmd_close_positions(wallet_file, do_write, position_ids):
    """
    ⚠️  WRITE: Close positions by their integer IDs.

    Example: papertrade close-positions 123 456 --write
    """
    with _build_client(wallet_file) as c:
        if c.write is None:
            console.print("[red]No wallet loaded.[/red]"); sys.exit(1)
        try:
            result = c.write.close_positions(list(position_ids), dry_run=not do_write)
        except (PaperTradeError, ValueError) as e:
            console.print(f"[red]Error: {e}[/red]"); sys.exit(1)
        if not do_write:
            console.print("[yellow]DRY RUN — pass --write to submit:[/yellow]")
        _out(result)


@cli.command("withdraw")
@_wallet_option
@_write_flag
@click.option("--amount", required=True, type=float, help="USDC amount to withdraw.")
def cmd_withdraw(wallet_file, do_write, amount):
    """⚠️  WRITE: Withdraw USDC collateral to HyperCore."""
    with _build_client(wallet_file) as c:
        if c.write is None:
            console.print("[red]No wallet loaded.[/red]"); sys.exit(1)
        result = c.write.withdraw_to_core(amount, dry_run=not do_write)
        if not do_write:
            console.print("[yellow]DRY RUN — pass --write to submit:[/yellow]")
        _out(result)


@cli.command("stake")
@_wallet_option
@_write_flag
@click.option("--amount", required=True, type=float, help="PAPER tokens to stake.")
def cmd_stake(wallet_file, do_write, amount):
    """⚠️  WRITE: Stake PAPER governance tokens."""
    with _build_client(wallet_file) as c:
        if c.write is None:
            console.print("[red]No wallet loaded.[/red]"); sys.exit(1)
        result = c.write.stake_paper(amount, dry_run=not do_write)
        if not do_write:
            console.print("[yellow]DRY RUN — pass --write to submit:[/yellow]")
        _out(result)


@cli.command("unstake")
@_wallet_option
@_write_flag
@click.option("--amount", required=True, type=float, help="PAPER tokens to unstake.")
def cmd_unstake(wallet_file, do_write, amount):
    """⚠️  WRITE: Unstake PAPER governance tokens."""
    with _build_client(wallet_file) as c:
        if c.write is None:
            console.print("[red]No wallet loaded.[/red]"); sys.exit(1)
        result = c.write.unstake_paper(amount, dry_run=not do_write)
        if not do_write:
            console.print("[yellow]DRY RUN — pass --write to submit:[/yellow]")
        _out(result)


@cli.command("claim")
@_wallet_option
@_write_flag
def cmd_claim(wallet_file, do_write):
    """⚠️  WRITE: Claim available PAPER token rewards."""
    with _build_client(wallet_file) as c:
        if c.write is None:
            console.print("[red]No wallet loaded.[/red]"); sys.exit(1)
        result = c.write.claim_paper_rewards(dry_run=not do_write)
        if not do_write:
            console.print("[yellow]DRY RUN — pass --write to submit:[/yellow]")
        _out(result)


@cli.command("cancel-intent")
@_wallet_option
@_write_flag
@click.argument("intent_id")
def cmd_cancel_intent(wallet_file, do_write, intent_id):
    """⚠️  WRITE: Cancel a queued intent by its bytes32 ID."""
    with _build_client(wallet_file) as c:
        if c.write is None:
            console.print("[red]No wallet loaded.[/red]"); sys.exit(1)
        result = c.write.cancel_intent(intent_id, dry_run=not do_write)
        if not do_write:
            console.print("[yellow]DRY RUN — pass --write to submit:[/yellow]")
        _out(result)


if __name__ == "__main__":
    cli()
