from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from btc_bot.backtest.engine import run_backtest
from btc_bot.backtest.event_engine import run_event_backtest
from btc_bot.backtest.walk_forward import run_oos
from btc_bot.config import DEFAULT_CONFIG
from btc_bot.data.fetcher import fetch_ohlcv, load_ohlcv, save_ohlcv
from btc_bot.monitor.regime import detect_regime, run_regime_watch
from btc_bot.notify import make_notifier
from btc_bot.paper.engine import run_paper_loop
from btc_bot.strategies.mean_reversion import MeanReversion
from btc_bot.strategies.sma_cross import SmaCross

load_dotenv()

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


@app.command("backtest-mr")
def backtest_mr(
    ref_window: int = 30,
    buy_dip: float = 0.05,
    stop_loss: float = 0.04,
    arm_profit: float = 0.06,
    trail: float = 0.04,
    timeframe: str = "1d",
) -> None:
    """저장된 캔들로 평균회귀(싸게 줍기) 전략 백테스트."""
    candles = load_ohlcv(_candles_path(timeframe))
    strategy = MeanReversion(
        ref_window=ref_window,
        buy_dip_pct=buy_dip,
        stop_loss_pct=stop_loss,
        arm_profit_pct=arm_profit,
        trail_pct=trail,
    )
    result = run_event_backtest(
        candles, strategy,
        fee_rate=DEFAULT_CONFIG.fee_rate,
        initial_cash=DEFAULT_CONFIG.initial_cash,
    )

    table = Table(title=f"평균회귀 백테스트 ({timeframe}, ref={ref_window}일)")
    table.add_column("지표")
    table.add_column("값", justify="right")
    table.add_row("전략 수익률", f"{result.total_return_pct}%")
    table.add_row("단순 보유(benchmark)", f"{result.buy_and_hold_pct}%")
    table.add_row("최대 낙폭(MDD)", f"{result.max_drawdown_pct}%")
    table.add_row("매매 횟수", str(result.num_trades))
    table.add_row("승률", f"{result.win_rate_pct}%")
    table.add_row("평균 보유일", f"{result.avg_hold_days}일")
    console.print(table)


@app.command()
def oos(min_w: int = 3, max_w: int = 15, timeframe: str = "1d", trend_filter: int = 0) -> None:
    """아웃오브샘플: 앞 절반에서 고른 기준이 뒷 절반에서도 통하나 검증.

    trend_filter > 0이면 장기선(일) 필터를 적용 ("긴 하락장엔 쉰다").
    """
    candles = load_ohlcv(_candles_path(timeframe))
    report = run_oos(
        candles, range(min_w, max_w + 1),
        fee_rate=DEFAULT_CONFIG.fee_rate,
        initial_cash=DEFAULT_CONFIG.initial_cash,
        trend_filter_window=trend_filter,
    )

    console.print(
        f"[bold]train[/] {report.train_period[0].date()}~{report.train_period[1].date()} "
        f"(벤치마크 {report.train_bench_pct}%)   "
        f"[bold]test[/] {report.test_period[0].date()}~{report.test_period[1].date()} "
        f"(벤치마크 {report.test_bench_pct}%)"
    )

    table = Table(title="기준별 train vs test 수익률")
    table.add_column("ref(일)", justify="right")
    table.add_column("train 수익률", justify="right")
    table.add_column("test 수익률", justify="right")
    for row in report.rows:
        marker = "  ← train 최고" if row.ref_window == report.best_train_window else ""
        table.add_row(str(row.ref_window), f"{row.train_return_pct}%", f"{row.test_return_pct}%{marker}")
    console.print(table)

    console.print(
        f"\n[bold]판정[/]: train 최고는 ref={report.best_train_window}일 "
        f"({report.best_train_return_pct}%) → 같은 기준으로 test에선 "
        f"[bold]{report.best_window_test_return_pct}%[/] "
        f"(test 벤치마크 {report.test_bench_pct}%)"
    )


@app.command()
def regime(window: int = 200, timeframe: str = "1d") -> None:
    """지금 비트코인이 장기선 위(상승장)인지 아래(하락장)인지 즉시 확인."""
    candles = fetch_ohlcv(DEFAULT_CONFIG.symbol, timeframe, limit=window + 50)
    status = detect_regime(candles, window)
    label = "📉 하락장 (장기선 아래)" if status.regime == "down" else "📈 상승장 (장기선 위)"
    table = Table(title=f"현재 장세 ({window}일선 기준)")
    table.add_column("지표")
    table.add_column("값", justify="right")
    table.add_row("판정", label)
    table.add_row("현재가", f"${status.price:,.0f}")
    table.add_row(f"{window}일 평균선", f"${status.long_ma:,.0f}")
    table.add_row("장기선 대비", f"{status.gap_pct:+.2f}%")
    console.print(table)
    if status.regime == "down":
        console.print("[yellow]평균회귀 전략은 이런 장에서 손실이 나요 — 매수 쉬는 걸 권장.[/]")


@app.command("watch-regime")
def watch_regime(window: int = 200, poll_seconds: int = 3600) -> None:
    """장세를 계속 감시하다 상승↔하락이 바뀌면 디스코드로 알림 (Ctrl+C로 종료)."""
    run_regime_watch(
        DEFAULT_CONFIG.symbol, window,
        state_path=DATA_DIR / "regime-state.json",
        notifier=make_notifier(),
        poll_seconds=poll_seconds,
    )


@app.command()
def paper(fast: int = 20, slow: int = 60, poll_seconds: int = 60) -> None:
    """실시간 시세로 페이퍼 트레이딩 시작 (Ctrl+C로 종료)."""
    strategy = SmaCross(fast=fast, slow=slow)
    log_path = DATA_DIR / "paper-trades.jsonl"
    run_paper_loop(strategy, DEFAULT_CONFIG, log_path, poll_seconds=poll_seconds)


if __name__ == "__main__":
    app()
