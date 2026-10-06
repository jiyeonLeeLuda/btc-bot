from dataclasses import dataclass


@dataclass(frozen=True)
class MeanReversion:
    """싸게 줍기(평균회귀) 전략 파라미터.

    - 산다: 가격이 ref_window일 평균보다 buy_dip_pct 아래로 내려오면
    - 손절: 산값보다 stop_loss_pct 아래로 떨어지면
    - 익절: +arm_profit_pct 찍은 뒤, 고점 대비 trail_pct 빠지면 (트레일링)
    - 장세 필터: trend_filter_window > 0이면, 가격이 그 기간 평균(장기선)
      아래일 땐 사지 않고, 보유 중이면 빠져나온다 ("긴 하락장엔 쉰다")
    """

    ref_window: int = 30            # "싸다"를 재는 평균 기간 (일)
    buy_dip_pct: float = 0.05       # 평균보다 5% 아래면 매수
    stop_loss_pct: float = 0.04     # 산값 -4%면 손절
    arm_profit_pct: float = 0.06    # +6% 찍어야 트레일링 익절 발동
    trail_pct: float = 0.04         # 고점 대비 -4%면 익절 매도
    trend_filter_window: int = 0    # 0=off. >0이면 장기선(일) 필터 적용

    @property
    def name(self) -> str:
        base = (
            f"mean_rev(ref={self.ref_window}d, dip={self.buy_dip_pct:.0%}, "
            f"stop={self.stop_loss_pct:.0%}, arm={self.arm_profit_pct:.0%}, "
            f"trail={self.trail_pct:.0%}"
        )
        if self.trend_filter_window > 0:
            base += f", trend={self.trend_filter_window}d"
        return base + ")"
