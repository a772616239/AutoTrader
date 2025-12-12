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
from .a12_stochastic_rsi import A12StochasticRSIStrategy
from .a13_ema_crossover import A13EMACrossoverStrategy
from .a14_rsi_trendline import A14RSITrendlineStrategy
from .a15_pairs_trading import A15PairsTradingStrategy
from .a16_roc import A16ROCStrategy
from .a17_cci import A17CCIStrategy
from .a18_isolation_forest import A18IsolationForestStrategy
from .a22_super_trend import A22SuperTrendStrategy
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
    'A11MovingAverageCrossoverStrategy',
    'A12StochasticRSIStrategy',
    'A13EMACrossoverStrategy',
    'A14RSITrendlineStrategy',
    'A15PairsTradingStrategy',
    'A16ROCStrategy',
    'A17CCIStrategy',
    'A18IsolationForestStrategy',
    'A22SuperTrendStrategy'
]