# btc-bot

바이낸스 기준 학습용 비트코인 페이퍼 트레이딩 봇. 실제 주문은 하지 않는다.

## 구조

- `bot/` — Python: 데이터 수집(ccxt) · 백테스트 · 페이퍼 트레이딩
- `dashboard/` — (예정) Next.js 대시보드

## 사용법

```bash
cd bot
uv sync

# 1. 바이낸스에서 캔들 받기 (공개 API, 키 불필요)
uv run btc-bot fetch --timeframe 1h --limit 1000

# 2. SMA 크로스 전략 백테스트
uv run btc-bot backtest --fast 20 --slow 60

# 3. 실시간 페이퍼 트레이딩 (Ctrl+C로 종료)
uv run btc-bot paper
```

## 다음 단계 아이디어

- [ ] 전략 추가 (RSI, 변동성 돌파)
- [ ] 백테스트 개선: 다음 봉 시가 체결, 슬리피지 반영
- [ ] 파라미터 스윕 (fast/slow 조합 탐색)
- [ ] Next.js 대시보드 (equity curve, 거래 로그 시각화)
