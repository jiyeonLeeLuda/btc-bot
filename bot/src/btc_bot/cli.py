from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from btc_bot.backtest.engine import run_backtest
from btc_bot.config import DEFAULT_CONFIG
from btc_bot.data.fetcher import fetch_ohlcv, load_ohlcv, save_ohlcv
from btc_bot.paper.engine import run_paper_loop
from btc_bot.strategies.sma_cross import SmaCross

app = typer.Typer(help="BTC 학습용 페이퍼 트레이딩 봇")
console = Console()

DATA_DIR = Path(__file__).resolve().parents[3] / "data"


def _candles_path(timeframe: str) -> Path:
    symbol_slug = DEFAULT_CONFIG.symbol.replace("/", "-")
    return DATA_DIR / f"{symbol_slug}-{timeframe}.csv"


@app.command()
def fetch(timeframe: str = DEFAULT_CONFIG.timeframe, limit: int = 1000) -> None:
    """바이낸스에서 캔들 데이터를 받아 data/에 저장."""
    df = fetch_ohlcv(DEFAULT_CONFIG.symbol, timeframe, limit=limit)
    path = _candles_path(timeframe)
    save_ohlcv(df, path)
    console.print(f"[green]{len(df)}개 캔들 저장[/] → {path}")
    console.print(f"기간: {df.index[0]} ~ {df.index[-1]}")


@app.command()
def backtest(
    fast: int = 20,
    slow: int = 60,
    timeframe: str = DEFAULT_CONFIG.timeframe,
) -> None:
    """저장된 캔들로 SMA 크로스 전략 백테스트."""
    candles = load_ohlcv(_candles_path(timeframe))
    strategy = SmaCross(fast=fast, slow=slow)
    result = run_backtest(
        candles, strategy,
        fee_rate=DEFAULT_CONFIG.fee_rate,
        initial_cash=DEFAULT_CONFIG.initial_cash,
    )

    table = Table(title=f"백테스트: {result.strategy_name} ({timeframe})")
    table.add_column("지표")
    table.add_column("값", justify="right")
    table.add_row("전략 수익률", f"{result.total_return_pct}%")
    table.add_row("단순 보유(benchmark)", f"{result.buy_and_hold_pct}%")
    table.add_row("최대 낙폭(MDD)", f"{result.max_drawdown_pct}%")
    table.add_row("매매 횟수", str(result.num_trades))
    console.print(table)


@app.command()
def paper(fast: int = 20, slow: int = 60, poll_seconds: int = 60) -> None:
    """실시간 시세로 페이퍼 트레이딩 시작 (Ctrl+C로 종료)."""
    strategy = SmaCross(fast=fast, slow=slow)
    log_path = DATA_DIR / "paper-trades.jsonl"
    run_paper_loop(strategy, DEFAULT_CONFIG, log_path, poll_seconds=poll_seconds)


if __name__ == "__main__":
    app()
