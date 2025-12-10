# strategies/__init__.py
from .a1_momentum_reversal import A1MomentumReversalStrategy
from .a2_zscore import A2ZScoreStrategy
from .a3_dual_ma_volume import A3DualMAVolumeStrategy
from .a4_pullback import A4PullbackStrategy
from .a5_multifactor_ai import A5MultiFactorAI
from .a6_news_trading import A6NewsTrading
from .a7_cta_trend import A7CTATrendStrategy
from .a8_rsi_oscillator import A8RSIOscillatorStrategy
from .a9_macd_crossover import A9MACDCrossoverStrategy
from .a10_bollinger_bands import A10BollingerBandsStrategy
from .a11_moving_average_crossover import A11MovingAverageCrossoverStrategy
from .base_strategy import BaseStrategy

__all__ = [
    'BaseStrategy',
    'A1MomentumReversalStrategy',
    'A2ZScoreStrategy',
    'A3DualMAVolumeStrategy',
    'A4PullbackStrategy',
    'A5MultiFactorAI',
    'A6NewsTrading',
    'A7CTATrendStrategy',
    'A8RSIOscillatorStrategy',
    'A9MACDCrossoverStrategy',
    'A10BollingerBandsStrategy',
    'A11MovingAverageCrossoverStrategy'
]