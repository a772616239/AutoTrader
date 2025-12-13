#!/usr/bin/env python3
"""
配置文件
"""
import os
import json
from datetime import datetime

# 基本配置
CONFIG = {
    'data_server': {
        'base_url': 'http://localhost:8001',
        'retry_attempts': 3,
        'cache_duration': 300,  # 缓存时间（秒）
    },
    'ib_server': {
        'host': '127.0.0.1',
        'port': 7496,
        'client_id': 1,
        'max_retries': 3,
    },
    'trading': {

'symbols': [
    # A1 动量反转（更新）
    'AMD',
    'META',
    'INTC',
    'RIVN',
    'COIN',
    # 'SQ',
    # 'ZM',
    'UBER',
    'UPST',
    'DUOL',
    'AUDC',
    'TMDX',
    # A2 Z-Score 均值回归（更新）
    'XOM',
    'CVX',
    'JPM',
    'PFE',
    'JNJ',
    'BAC',
    # 'GS',
    'PEP',
    'CSCO',
    # 'TXN',
    'COMM',
    'UNH',
    'DINO',
    # A3 双均线量能（更新）
    'TEAM',
    'GOOGL',
    'WDC',
    'CRM',
    # 'ORCL',
    'AVGO',
    'IBM',
    'NOW',
    'AAPL',
    'ADP',
    'DV',
    # A4 回调买入（更新）
    'AMZN',
    'BKNG',
    'TSLA',
    'NFLX',
    'DIS',
    'NKE',
    'SBUX',
    'BABA',
    'BIDU',
    # 'LAC',
    # A5 多因子 AI（更新）
    'NVDA',
    'MSFT',
    'ETN',
    'SNOW',
    # 'AI',
    'PLTR',
    'DDOG',
    'CRWD',
    'INCY',
    'PRIM',
    'MSTR',
    # A7 CTA 趋势（更新）
    # 'OKLO',
    # 'SMCI',
    'LEU',
    'TSM',
    'BA',
    'ASML',
    'LLY',
    'RTX',
    'AMAT',
    # 'AZN',
    'STX',
]

,
        'scan_interval_minutes': 1,
        'trading_hours': {
            'start': '09:30',
            'end': '16:00'
        },
        'enable_trading': False,  # 是否启用交易（False时仅测算，不提交订单）
        'allow_short_selling': False,  # 是否允许无持仓卖出（空头交易）
        'same_day_sell_only': False,  # 是否限制当日不能买入
        'sell_only_mode': True,  # 是否只能提交卖出单，禁止买入
        
        'allow_orders_outside_trading_hours': True,  # 是否允许在非交易时间提交委托单
        'auto_cancel_orders': False, # 每个周期开始时是否自动取消未完成订单
        'max_symbols_per_cycle': 50,
        'close_all_positions_before_market_close': False,  # 是否在收盘前清仓所有持仓（已启用）
        'close_positions_time': '15:45',  # 清仓时间（美东时间，默认收盘前15分钟）
        'sell_exempt_from_cap': True   ,  # 卖出是否不受per_trade_notional_cap单笔限额限制
    },
    'logging': {
        'debug_mode': True,  # 调试模式：每次运行生成新日志文件，启用DEBUG级别日志
        'level': 'DEBUG',
        'file': os.path.join('logs', f'trading_{datetime.now():%Y%m%d_%H%M%S}.log'),
        'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    },
    'strategy_a1': {  # 动量反转策略配置（日内交易）
        'initial_capital': 50000,
        'risk_per_trade': 0.02,
        'max_position_size': 0.1,
        'per_trade_notional_cap': 700.0,  # 单笔交易美元上限
        'max_position_notional': 60000.0,  # 单股总仓位上限（美元）
        'rsi_overbought': 72,
        'rsi_oversold': 28,
        'stop_loss_atr_multiple': 1.5,      # ATR止损倍数（用于仓位计算）
        'stop_loss_pct': 0.02,              # 止损百分比（2%，降低限制）
        'take_profit_atr_multiple': 3.0,    # ATR止盈倍数（用于仓位计算）
        'take_profit_pct': 0.03,            # 止盈百分比（3%，降低限制）
 'take_profit_pnl_threshold': 100.0, # IB未实现盈利止盈阈值（美元，降低限制）
        'max_holding_minutes': 180,         # 最大持有时间（180分钟，延长）
        'quick_loss_cutoff': -0.03,         # 快速止损阈值（-3%）
        'force_close_time': '15:45',        # 收盘前强制平仓时间
        'ib_order_type': 'LMT',
        'ib_limit_offset': 0.01,
        'trading_start_time': '09:30',
        'trading_end_time': '16:00',
        'avoid_open_hour': True,
        'avoid_close_hour': True,
    },
    'strategy_a2': {  # Z-Score策略配置
        'initial_capital': 50000,
        'risk_per_trade': 0.02,
        'max_position_size': 0.1,
        'per_trade_notional_cap': 700.0,  # 单笔交易美元上限
        'max_position_notional': 60000.0,  # 单股总仓位上限（美元）
        'zscore_lookback': 20,
        'zscore_entry_threshold': 2.0,
        'zscore_exit_threshold': 0.5,
        'stop_loss_pct': 0.025,             # 止损百分比（2.5%，降低限制）
        'take_profit_pct': 0.04,             # 止盈百分比（4%，降低限制）
        'max_holding_days': 7,               # 最大持有天数（延长）
        'ib_order_type': 'LMT',
        'ib_limit_offset': 0.005,
        'trading_start_time': '09:30',
        'trading_end_time': '16:00',
        'trading_hours_only': True,
    },
    'strategy_a3': {  # 双均线成交量突破策略配置（日内交易）
        'trading': {
            'initial_capital': 50000,  # 初始资金
            'risk_per_trade': 0.02,    # 单笔交易风险 (2% equity) (A6 uses 0.015)
            'max_position_size': 0.1,  # 最大仓位 (10% equity)
            'min_cash_buffer': 0.1,    # 最小现金缓冲
            'per_trade_notional_cap': 700.0, # 单笔名义价值上限 (USD)
            'max_position_notional': 60000.0, # 单个标的持仓名义价值上限 (USD)
            
            # 交易时间
            'trading_start_time': '09:45', # 避开开盘前15分钟波动
            'trading_end_time': '15:45',   # 收盘前15分钟停止开新仓
        },
        'fast_ma_period': 9,
        'slow_ma_period': 21,
        'ema_or_sma': 'EMA',
        'volume_sma_period': 20,
        'volume_surge_ratio': 1.5,
        'min_volume_threshold': 500000,
        'stop_loss_pct': 0.02,             # 止损百分比（2%，降低限制）
        'take_profit_pct': 0.025,          # 止盈百分比（2.5%，降低限制）
        'take_profit_atr_multiple': 2.0,   # 基于ATR的止盈倍数
        'max_holding_minutes': 90,         # 最大持有时间（90分钟，延长）
        'force_close_time': '15:30',       # 收盘前强制平仓时间
        'ib_order_type': 'LMT',
        'ib_limit_offset': 0.01,
        'trading_start_time': '09:45',
        'trading_end_time': '15:30',
        'avoid_open_hour': True,
        'avoid_close_hour': True,
    },
    'strategy_a4': {  # 回调交易策略配置（斐波那契回撤，多日持仓）
        'initial_capital': 50000,
        'risk_per_trade': 0.02,
        'max_position_size': 0.1,
        'per_trade_notional_cap': 700.0,  # 单笔交易美元上限
        'max_position_notional': 60000.0,  # 单股总仓位上限（美元）
        'trend_ma_period': 80,              # 长期趋势均线
        'trend_confirmation_bars': 3,      # 趋势确认K线数
        'pullback_lookback': 20,            # 回撤识别窗口
        'fibonacci_levels': [0.236, 0.382, 0.5, 0.618, 0.786],
        'pullback_buy_ratio': [0.08, 0.7],   # 回撤买入位置
        'pullback_sell_ratio': [0.08, 0.7],  # 反弹卖出位置
        'volume_confirmation': True,
        'min_volume_ratio': 0.6,          # 最小成交量相对历史平均值的比例（0.5=50%，基于历史对比）
        'stop_loss_pct': 0.025,  # 降低限制
        'take_profit_pct': 0.04,   # 降低限制
        'max_holding_days': 7,     # 延长
        'trading_start_time': '10:00',  # 避开开盘波动
        'trading_end_time': '15:30',
        'avoid_open_hour': True,
        'avoid_close_hour': True,
        'ib_order_type': 'LMT',
        'ib_limit_offset': 0.01,
    },
    'strategy_a5': {  # 多因子AI融合策略配置（多日持仓）
        'initial_capital': 50000,
        'risk_per_trade': 0.02,
        'max_position_size': 0.06,
        'per_trade_notional_cap': 700.0,      # 单笔交易美元上限（严格）
        'max_position_notional': 50000,      # 单股总仓位上限（美元，严格）
        'min_confidence': 0.65,                # 最小信心度阈值（严格）
        'min_price': 10.0,                     # 最小股价（严格，避免低价股）
        'min_volume_ratio': 0.1,               # 最小成交量相对历史平均值的比例（0.5=50%，基于历史对比）
        'volume_lookback_period': 30,          # 计算历史平均成交量的回溯天数
        'lookback_period': 90,                 # 基本面指标回溯天数
        'recent_period': 20,                   # 最近期间（天数）
        'liquidity_weight': 0.35,              # 流动性因子权重（优先级最高）
        'fundamental_weight': 0.20,            # 基本面因子权重（降低）
        'sentiment_weight': 0.10,              # 情绪因子权重（最小化）
        'momentum_weight': 0.35,               # 动量因子权重（优先级最高）
        'buy_threshold': 0.68,                 # 买入复合得分阈值（严格）
        'sell_threshold': 0.55,                # 卖出复合得分阈值（严格）
        'exit_threshold': 0.25,                # 平仓复合得分阈值（更低，快速止损）
        'stop_loss_pct': 0.015,               # 止损百分比（1.5%，降低限制）
        'take_profit_pct': 0.03,               # 止盈百分比（3%，降低限制）
        'max_holding_days': 7,                 # 最大持有天数（延长）
        'ib_order_type': 'LMT',
        'ib_limit_offset': 0.01,
        'trading_start_time': '09:45',
        'trading_end_time': '15:30',
        'avoid_open_hour': True,
        'avoid_close_hour': True,
    },
    'strategy_a6': {  # 新闻交易策略配置（日内交易）
        'initial_capital': 50000,
        'risk_per_trade': 0.015,              # 新闻交易风险控制更严格
        'max_position_size': 0.04,             # 小仓位，快速进出
        'per_trade_notional_cap': 700.0,     # 单笔交易美元上限（更严格）
        'max_position_notional': 400000.0,     # 单股总仓位上限（美元，更严格）
        'polygon_api_key': '0SgE61bAeLNqkcDks0y0FDtP2t7l_8an',  # 🔴 需要替换为您的Polygon API密钥
        # 获取API密钥: https://polygon.io/
        'news_lookback_hours': 48,             # 新闻回顾小时数
        'sentiment_threshold_positive': 0.6,   # 正面新闻情感阈值
        'sentiment_threshold_negative': -0.6,  # 负面新闻情感阈值
        'volatility_threshold': 0.02,          # 价格波动阈值（2%）
        'news_reaction_window': 30,            # 新闻发布后反应窗口（分钟）
        'min_news_relevance': 0.7,             # 最小新闻相关性评分
        'max_news_age_hours': 4,               # 最大新闻年龄（小时）
        'cooldown_after_news_trade': 60,       # 新闻交易后冷却期（分钟）
        'stop_loss_pct': 0.015,               # 止损百分比（1.5%，降低限制）
        'take_profit_pct': 0.02,               # 止盈百分比（2%，降低限制）
        'max_holding_minutes': 90,            # 最大持有时间（90分钟，延长）
        'force_close_time': '15:30',          # 收盘前强制平仓时间
        'ib_order_type': 'LMT',
        'ib_limit_offset': 0.005,
        'trading_start_time': '09:45',
        'trading_end_time': '15:30',
        'avoid_open_hour': True,
        'avoid_close_hour': True,
    },
    'strategy_a7': {  # A7 CTA 趋势跟踪策略（中短期持仓）
        'initial_capital': 50000,
        'risk_per_trade': 0.02,
        'max_position_size': 0.1,
        'per_trade_notional_cap': 700.0,
        'max_position_notional': 60000.0,
        'donchian_entry_period': 60,    # 入场通道周期 (调大到60)
        'donchian_exit_period': 20,     # 出场通道周期
        'trend_filter_sma_period': 200, # 慢速趋势线 (MA200)
        'trend_filter_fast_sma_period': 50, # 快速趋势线 (MA50) - 新增：要求 MA50 > MA200
        'stop_loss_atr_multiple': 2.0,  # ATR止损倍数
        'stop_loss_pct': 0.025,         # 止损百分比（2.5%，降低限制）
        'take_profit_pct': 0.035,        # 止盈百分比（3.5%，降低限制）
        'take_profit_atr_multiple': 2.5, # 或使用ATR止盈（2.5倍ATR）
        'max_holding_days': 14,          # 最大持有天数（延长）
        'ib_order_type': 'LMT', # 使用限价单 (无行情权限需用LMT)
        'ib_limit_offset': -0.003, # 激进单 (Marketable Limit)
        'trading_start_time': '09:45',
        'trading_end_time': '16:00',
        'avoid_open_hour': True,
        'avoid_close_hour': True,
    },
    'strategy_a8': {  # A8 RSI震荡策略配置
        'initial_capital': 50000,
        'risk_per_trade': 0.02,
        'max_position_size': 0.1,
        'per_trade_notional_cap': 700.0,
        'max_position_notional': 60000.0,
        'rsi_period': 14,
        'rsi_oversold': 30,
        'rsi_overbought': 70,
        'rsi_signal_threshold': 5,
        'stop_loss_pct': 0.015,         # 止损百分比（1.5%，降低限制）
        'take_profit_pct': 0.025,        # 止盈百分比（2.5%，降低限制）
        'max_holding_minutes': 90,       # 最大持有时间（90分钟，延长）
        'trailing_stop_activation': 0.02,
        'trailing_stop_distance': 0.015,
        'signal_cooldown_minutes': 10,
        'min_volume': 5000,
        'min_data_points': 20,
        'ib_order_type': 'MKT',
        'ib_limit_offset': 0.01,
    },
    'strategy_a9': {  # A9 MACD交叉策略配置
        'initial_capital': 50000,
        'risk_per_trade': 0.02,
        'max_position_size': 0.1,
        'per_trade_notional_cap': 700.0,
        'max_position_notional': 60000.0,
        'macd_fast': 12,
        'macd_slow': 26,
        'macd_signal': 9,
        'histogram_threshold': 0.1,
        'stop_loss_pct': 0.02,          # 止损百分比（2%，降低限制）
        'take_profit_pct': 0.04,         # 止盈百分比（4%，降低限制）
        'max_holding_minutes': 180,      # 最大持有时间（180分钟，延长）
        'trailing_stop_activation': 0.03,
        'trailing_stop_distance': 0.02,
        'signal_cooldown_minutes': 15,
        'min_volume': 5000,
        'min_data_points': 35,
        'ib_order_type': 'MKT',
        'ib_limit_offset': 0.01,
    },
    'strategy_a10': {  # A10 布林带策略配置
        'initial_capital': 50000,
        'risk_per_trade': 0.02,
        'max_position_size': 0.1,
        'per_trade_notional_cap': 700.0,
        'max_position_notional': 60000.0,
        'bollinger_period': 20,
        'bollinger_std': 2.0,
        'breakout_threshold': 0.1,    # 突破强度阈值（降低便于测试）
        'stop_loss_pct': 0.02,          # 止损百分比（2%，降低限制）
        'take_profit_pct': 0.04,         # 止盈百分比（4%，降低限制）
        'max_holding_minutes': 120,      # 最大持有时间（120分钟，延长）
        'signal_cooldown_minutes': 10,
        'min_volume': 5000,
        'min_data_points': 25,
        'ib_order_type': 'MKT',
        'ib_limit_offset': 0.01,
    },
    'strategy_a11': {  # A11 移动平均交叉策略配置
        'initial_capital': 50000,
        'risk_per_trade': 0.02,
        'max_position_size': 0.1,
        'per_trade_notional_cap': 700.0,
        'max_position_notional': 60000.0,
        'fast_ma_period': 9,
        'slow_ma_period': 21,
        'ma_type': 'SMA',
        'stop_loss_pct': 0.02,          # 止损百分比（2%，降低限制）
        'take_profit_pct': 0.04,         # 止盈百分比（4%，降低限制）
        'max_holding_minutes': 120,      # 最大持有时间（120分钟，延长）
        'signal_cooldown_minutes': 15,
        'min_volume': 5000,
        'min_data_points': 25,
        'ib_order_type': 'MKT',
        'ib_limit_offset': 0.01,
    },
    'strategy_a12': {  # A12 Stochastic RSI策略配置
        'initial_capital': 50000,
        'risk_per_trade': 0.02,
        'max_position_size': 0.1,
        'per_trade_notional_cap': 700.0,
        'max_position_notional': 60000.0,
        'rsi_period': 14,
        'stoch_period': 14,
        'oversold_level': 0.2,
        'overbought_level': 0.8,
        'stop_loss_pct': 0.02,          # 止损百分比（2%，降低限制）
        'take_profit_pct': 0.04,         # 止盈百分比（4%，降低限制）
        'max_holding_minutes': 120,      # 最大持有时间（120分钟，延长）
        'signal_cooldown_minutes': 15,
        'min_volume': 5000,
        'min_data_points': 30,
        'ib_order_type': 'MKT',
        'ib_limit_offset': 0.01,
    },
    'strategy_a13': {  # A13 EMA交叉策略配置
        'initial_capital': 50000,
        'risk_per_trade': 0.02,
        'max_position_size': 0.1,
        'per_trade_notional_cap': 700.0,
        'max_position_notional': 60000.0,
        'short_ema_period': 20,
        'long_ema_period': 100,
        'position_size_fraction': 0.33,
        'stop_loss_pct': 0.05,          # 较宽松的止损
        'take_profit_pct': 0.10,         # 较宽松的止盈
        'max_holding_minutes': 1440,     # 24小时
        'signal_cooldown_minutes': 60,
        'min_volume': 5000,
        'min_data_points': 110,
        'ib_order_type': 'MKT',
        'ib_limit_offset': 0.01,
    },
    'strategy_a14': {  # A14 RSI趋势线策略配置
        'initial_capital': 50000,
        'risk_per_trade': 0.02,
        'max_position_size': 0.1,
        'per_trade_notional_cap': 700.0,
        'max_position_notional': 60000.0,
        'rsi_period': 14,
        'rsi_oversold_threshold': 33,
        'rsi_lookback_days': 2,
        'trend_ma_period': 200,
        'trend_ma_type': 'SMA',
        'stop_loss_pct': 0.03,          # 适中止损
        'take_profit_pct': 0.06,         # 适中止盈
        'max_holding_minutes': 480,      # 8小时
        'signal_cooldown_minutes': 30,
        'min_volume': 5000,
        'min_data_points': 220,
        'ib_order_type': 'MKT',
        'ib_limit_offset': 0.01,
    },
    'strategy_a15': {  # A15 配对交易策略配置
        'initial_capital': 50000,
        'risk_per_trade': 0.02,
        'max_position_size': 0.05,
        'per_trade_notional_cap': 500.0,
        'max_position_notional': 30000.0,
        'pair_symbol': 'SPY',
        'lookback_period': 60,
        'entry_threshold': 2.0,
        'exit_threshold': 0.5,
        'stop_loss_pct': 0.05,
        'take_profit_pct': 0.08,
        'max_holding_minutes': 240,
        'signal_cooldown_minutes': 30,
        'min_volume': 5000,
        'min_data_points': 70,
        'ib_order_type': 'MKT',
        'ib_limit_offset': 0.01,
    },
    'strategy_a16': {  # A16 ROC策略配置
        'initial_capital': 50000,
        'risk_per_trade': 0.02,
        'max_position_size': 0.1,
        'per_trade_notional_cap': 700.0,
        'max_position_notional': 60000.0,
        'roc_period': 12,
        'bullish_threshold': 10,
        'bearish_threshold': -10,
        'stop_loss_pct': 0.03,
        'take_profit_pct': 0.06,
        'max_holding_minutes': 120,
        'signal_cooldown_minutes': 15,
        'min_volume': 5000,
        'min_data_points': 25,
        'ib_order_type': 'MKT',
        'ib_limit_offset': 0.01,
    },
    'strategy_a17': {  # A17 CCI策略配置
        'initial_capital': 50000,
        'risk_per_trade': 0.02,
        'max_position_size': 0.1,
        'per_trade_notional_cap': 700.0,
        'max_position_notional': 60000.0,
        'cci_period': 20,
        'overbought_level': 100,
        'oversold_level': -100,
        'stop_loss_pct': 0.03,
        'take_profit_pct': 0.06,
        'max_holding_minutes': 120,
        'signal_cooldown_minutes': 15,
        'min_volume': 5000,
        'min_data_points': 25,
        'ib_order_type': 'MKT',
        'ib_limit_offset': 0.01,
    },
    'strategy_a18': {  # A18 IsolationForest异常检测策略配置
        'initial_capital': 50000,
        'risk_per_trade': 0.02,
        'max_position_size': 0.1,
        'per_trade_notional_cap': 700.0,
        'max_position_notional': 60000.0,
        'contamination': 0.001,        # 异常值比例
        'cooldown_days': 7,            # 交易冷却期（天）
        'min_data_points': 50,          # 最小数据点数量
        'model_retrain_days': 30,       # 模型重训练间隔（天）
        'stop_loss_pct': 0.02,          # 止损百分比
        'take_profit_pct': 0.05,        # 止盈百分比
        'max_holding_days': 3,          # 最大持有天数
        'signal_cooldown_minutes': 60,  # 信号冷却时间
        'min_volume': 5000,
        'ib_order_type': 'MKT',
        'ib_limit_offset': 0.01,
    },
    'strategy_a22': {  # A22 超级趋势策略配置
        'initial_capital': 50000.0,
        'risk_per_trade': 0.015,        # 1.5% 单笔风险
        'max_position_size': 0.08,       # 8% 最大仓位
        'per_trade_notional_cap': 5000.0,
        'max_position_notional': 40000.0,

        # 超级趋势参数
        'atr_period': 14,                # ATR周期
        'factor': 3.0,                   # 乘数因子
        'trend_confirmation': 2,         # 趋势确认周期
        'min_trend_strength': 0.001,     # 最小趋势强度

        # 风险管理
        'stop_loss_pct': 0.03,           # 3% 止损
        'take_profit_pct': 0.06,         # 6% 止盈
        'max_holding_days': 7,           # 最大持有7天
        'trailing_stop_pct': 0.02,       # 2% 追踪止损

        # 交易过滤
        'trading_hours_only': True,
        'avoid_earnings': True,
        'min_volume_threshold': 100000,  # 最小成交量
        'min_price': 5.0,
        'max_price': None,

        # 防重复交易
        'signal_cooldown_minutes': 15,   # 15分钟冷却

        # IB交易参数
        'ib_order_type': 'MKT',
        'ib_limit_offset': 0.01,
    },
    'strategy_a23': {  # A23 Aroon震荡策略配置
        'initial_capital': 50000.0,
        'risk_per_trade': 0.02,
        'max_position_size': 0.1,
        'per_trade_notional_cap': 700.0,
        'max_position_notional': 60000.0,

        # Aroon参数
        'aroon_period': 14,
        'overbought_level': 70,
        'oversold_level': 30,

        # 风险管理
        'stop_loss_pct': 0.02,
        'take_profit_pct': 0.04,
        'max_holding_minutes': 120,

        # 防重复交易
        'signal_cooldown_minutes': 15,

        # 交易参数
        'min_volume': 5000,
        'min_data_points': 25,

        # IB交易参数
        'ib_order_type': 'MKT',
        'ib_limit_offset': 0.01,
    },
    'strategy_a24': {  # A24 终极震荡策略配置
        'initial_capital': 50000.0,
        'risk_per_trade': 0.02,
        'max_position_size': 0.1,
        'per_trade_notional_cap': 700.0,
        'max_position_notional': 60000.0,

        # 终极震荡参数
        'fast_period': 7,
        'slow_period': 14,
        'signal_period': 9,
        'overbought_level': 70,
        'oversold_level': 30,

        # 风险管理
        'stop_loss_pct': 0.02,
        'take_profit_pct': 0.04,
        'max_holding_minutes': 120,

        # 防重复交易
        'signal_cooldown_minutes': 15,

        # 交易参数
        'min_volume': 5000,
        'min_data_points': 25,

        # IB交易参数
        'ib_order_type': 'MKT',
        'ib_limit_offset': 0.01,
    },
    'strategy_a25': {  # A25 配对交易策略配置（增强版）
        'initial_capital': 50000,
        'risk_per_trade': 0.02,
        'max_position_size': 0.05,
        'per_trade_notional_cap': 500.0,
        'max_position_notional': 30000.0,
        'pair_symbol': 'SPY',
        'lookback_period': 60,
        'entry_threshold': 2.0,
        'exit_threshold': 0.5,
        'stop_loss_pct': 0.05,
        'take_profit_pct': 0.08,
        'max_holding_minutes': 240,
        'signal_cooldown_minutes': 30,
        'min_volume': 5000,
        'min_data_points': 70,
        'ib_order_type': 'MKT',
        'ib_limit_offset': 0.01,
    },
    'strategy_a26': {  # A26 Williams %R策略配置
        'initial_capital': 50000.0,
        'risk_per_trade': 0.02,
        'max_position_size': 0.1,
        'per_trade_notional_cap': 700.0,
        'max_position_notional': 60000.0,

        # Williams %R参数
        'williams_period': 14,
        'overbought_level': -20,
        'oversold_level': -80,

        # 风险管理
        'stop_loss_pct': 0.02,
        'take_profit_pct': 0.04,
        'max_holding_minutes': 120,

        # 防重复交易
        'signal_cooldown_minutes': 15,

        # 交易参数
        'min_volume': 5000,
        'min_data_points': 25,

        # IB交易参数
        'ib_order_type': 'MKT',
        'ib_limit_offset': 0.01,
    },
    'strategy_a27': {  # A27 Minervini趋势策略配置
        'initial_capital': 50000.0,
        'risk_per_trade': 0.02,
        'max_position_size': 0.1,
        'per_trade_notional_cap': 700.0,
        'max_position_notional': 60000.0,

        # Minervini参数
        'sma_50_period': 50,
        'sma_150_period': 150,
        'sma_200_period': 200,
        'rs_lookback': 252,
        'rs_percentile': 70,
        'min_price_increase': 1.3,
        'max_price_decline': 0.75,

        # 风险管理
        'stop_loss_pct': 0.08,
        'take_profit_pct': 0.15,
        'max_holding_days': 60,
        'trailing_stop_pct': 0.05,

        # 交易过滤
        'trading_hours_only': True,
        'avoid_earnings': True,
        'min_volume_threshold': 5000,
        'min_price': 10.0,
        'max_price': None,

        # 防重复交易
        'signal_cooldown_minutes': 1440,

        # IB交易参数
        'ib_order_type': 'MKT',
        'ib_limit_offset': 0.01,
    },
    'strategy_a28': {  # A28 True Strength Index策略配置
        'initial_capital': 50000.0,
        'risk_per_trade': 0.015,        # 1.5% 单笔风险
        'max_position_size': 0.08,       # 8% 最大仓位
        'per_trade_notional_cap': 5000.0,
        'max_position_notional': 40000.0,

        # True Strength Index参数
        'tsi_r_period': 25,              # 第一次平滑周期
        'tsi_s_period': 13,              # 第二次平滑周期
        'overbought_level': 25,          # 超买水平
        'oversold_level': -25,           # 超卖水平

        # 风险管理
        'stop_loss_pct': 0.03,           # 3% 止损
        'take_profit_pct': 0.06,         # 6% 止盈
        'max_holding_days': 10,          # 最大持有10天
        'trailing_stop_pct': 0.02,       # 2% 追踪止损

        # 交易过滤
        'trading_hours_only': True,
        'avoid_earnings': True,
        'min_volume_threshold': 5000,    # 最小成交量（放宽限制）
        'min_price': 5.0,
        'max_price': None,

        # 防重复交易
        'signal_cooldown_minutes': 15,   # 15分钟冷却

        # IB交易参数
        'ib_order_type': 'MKT',
        'ib_limit_offset': 0.01,
    },
    'strategy_a29': {  # A29 随机震荡策略配置
        'initial_capital': 50000.0,
        'risk_per_trade': 0.02,
        'max_position_size': 0.1,
        'per_trade_notional_cap': 700.0,
        'max_position_notional': 60000.0,

        # Stochastic参数
        'k_period': 14,
        'd_period': 3,
        'overbought_level': 80,
        'oversold_level': 20,

        # 风险管理
        'stop_loss_pct': 0.02,
        'take_profit_pct': 0.04,
        'max_holding_minutes': 120,

        # 防重复交易
        'signal_cooldown_minutes': 15,

        # 交易参数
        'min_volume': 5000,
        'min_data_points': 25,

        # IB交易参数
        'ib_order_type': 'MKT',
        'ib_limit_offset': 0.01,
    },
    'strategy_a30': {  # A30 IBD RS评级策略配置
        'initial_capital': 50000.0,
        'risk_per_trade': 0.02,
        'max_position_size': 0.1,
        'per_trade_notional_cap': 700.0,
        'max_position_notional': 60000.0,

        # IBD RS参数
        'rs_lookback_period': 252,
        'rs_rating_threshold': 70,
        'momentum_weight': 0.6,
        'trend_weight': 0.4,

        # 风险管理
        'stop_loss_pct': 0.05,
        'take_profit_pct': 0.10,
        'max_holding_days': 30,
        'trailing_stop_pct': 0.03,

        # 交易过滤
        'trading_hours_only': True,
        'avoid_earnings': True,
        'min_volume_threshold': 5000,
        'min_price': 10.0,
        'max_price': None,

        # 防重复交易
        'signal_cooldown_minutes': 1440,

        # IB交易参数
        'ib_order_type': 'MKT',
        'ib_limit_offset': 0.01,
    },
    'strategy_a31': {  # A31 资金流量指数策略配置
        'initial_capital': 50000.0,
        'risk_per_trade': 0.02,
        'max_position_size': 0.1,
        'per_trade_notional_cap': 700.0,
        'max_position_notional': 60000.0,

        # MFI参数
        'mfi_period': 14,
        'overbought_level': 80,
        'oversold_level': 20,

        # 风险管理
        'stop_loss_pct': 0.02,
        'take_profit_pct': 0.04,
        'max_holding_minutes': 120,

        # 防重复交易
        'signal_cooldown_minutes': 15,

        # 交易参数
        'min_volume': 5000,
        'min_data_points': 25,

        # IB交易参数
        'ib_order_type': 'MKT',
        'ib_limit_offset': 0.01,
    },
    'strategy_a32': {  # A32 Keltner Channels策略配置
        'initial_capital': 50000.0,
        'risk_per_trade': 0.02,
        'max_position_size': 0.1,
        'per_trade_notional_cap': 700.0,
        'max_position_notional': 60000.0,

        # Keltner Channels参数
        'atr_period': 14,
        'multiplier': 2.0,
        'breakout_threshold': 0.1,

        # 风险管理
        'stop_loss_pct': 0.02,
        'take_profit_pct': 0.04,
        'max_holding_minutes': 120,

        # 防重复交易
        'signal_cooldown_minutes': 20,

        # 交易参数
        'min_volume': 5000,
        'min_data_points': 25,

        # IB交易参数
        'ib_order_type': 'MKT',
        'ib_limit_offset': 0.01,
    },
    'strategy_a33': {  # A33 Pivot Points策略配置
        'initial_capital': 50000.0,
        'risk_per_trade': 0.02,
        'max_position_size': 0.1,
        'per_trade_notional_cap': 700.0,
        'max_position_notional': 60000.0,

        # Pivot Points参数
        'breakout_threshold': 0.001,
        'use_r2_s2': False,

        # 风险管理
        'stop_loss_pct': 0.02,
        'take_profit_pct': 0.04,
        'max_holding_minutes': 120,

        # 防重复交易
        'signal_cooldown_minutes': 20,

        # 交易参数
        'min_volume': 5000,
        'min_data_points': 25,

        # IB交易参数
        'ib_order_type': 'MKT',
        'ib_limit_offset': 0.01,
    },
    'strategy_a34': {  # A34 线性回归策略配置
        'initial_capital': 50000.0,
        'risk_per_trade': 0.02,
        'max_position_size': 0.1,
        'per_trade_notional_cap': 700.0,
        'max_position_notional': 60000.0,

        # 线性回归参数
        'lookback_period': 30,
        'prediction_horizon': 1,
        'retrain_frequency': 5,
        'prediction_threshold': 0.02,

        # 风险管理
        'stop_loss_pct': 0.03,
        'take_profit_pct': 0.05,
        'max_holding_minutes': 240,

        # 防重复交易
        'signal_cooldown_minutes': 30,

        # 交易参数
        'min_volume': 5000,
        'min_data_points': 50,

        # IB交易参数
        'ib_order_type': 'MKT',
        'ib_limit_offset': 0.01,
    },
    'strategy_a35': {  # A35 MLP神经网络策略配置
        'initial_capital': 50000.0,
        'risk_per_trade': 0.02,
        'max_position_size': 0.1,
        'per_trade_notional_cap': 700.0,
        'max_position_notional': 60000.0,

        # MLP神经网络参数
        'lookback_period': 30,
        'prediction_horizon': 1,
        'retrain_frequency': 10,
        'prediction_threshold': 0.025,

        # 神经网络架构
        'hidden_layers': (100, 50, 25),
        'activation': 'relu',
        'solver': 'adam',
        'max_iter': 1000,
        'learning_rate': 'adaptive',
        'alpha': 0.0001,
        'early_stopping': True,
        'validation_fraction': 0.2,

        # 风险管理
        'stop_loss_pct': 0.03,
        'take_profit_pct': 0.06,
        'max_holding_minutes': 300,

        # 防重复交易
        'signal_cooldown_minutes': 45,

        # 交易参数
        'min_volume': 5000,
        'min_data_points': 60,

        # IB交易参数
        'ib_order_type': 'MKT',
        'ib_limit_offset': 0.01,
    }
}

# 策略映射
STRATEGY_CONFIG_MAP = {
    'a1': 'strategy_a1',
    'a2': 'strategy_a2',
    'a3': 'strategy_a3',
    'a4': 'strategy_a4',
    'a5': 'strategy_a5',
    'a6': 'strategy_a6',
    'a7': 'strategy_a7',
    'a8': 'strategy_a8',
    'a9': 'strategy_a9',
    'a10': 'strategy_a10',
    'a11': 'strategy_a11',
    'a12': 'strategy_a12',
    'a13': 'strategy_a13',
    'a14': 'strategy_a14',
    'a15': 'strategy_a15',
    'a16': 'strategy_a16',
    'a17': 'strategy_a17',
    'a18': 'strategy_a18',
    'a22': 'strategy_a22',
    'a23': 'strategy_a23',
    'a24': 'strategy_a24',
    'a25': 'strategy_a25',
    'a26': 'strategy_a26',
    'a27': 'strategy_a27',
    'a28': 'strategy_a28',
    'a29': 'strategy_a29',
    'a30': 'strategy_a30',
    'a31': 'strategy_a31',
    'a32': 'strategy_a32',
    'a33': 'strategy_a33',
    'a34': 'strategy_a34',
    'a35': 'strategy_a35',
}

# 每个标的分配策略示例: 将特定股票映射到 a8/a9/a10
# 如果未在此映射中列出，则系统可选择默认策略或轮询分配
# 自动生成 symbol->strategy 映射：默认将 `trading.symbols` 中的每个标的分配到 'a8'
# 如果用户在外部（或在文件上方）已经设置了部分映射，会合并并以用户设置为准。
default_symbols = CONFIG.get('trading', {}).get('symbols', [])
default_symbol_map = {s: 'a11' for s in default_symbols}

# 允许事先存在的自定义映射覆盖默认值
existing_map = CONFIG.get('symbol_strategy_map', {}) or {}

# 预设一些需要使用不同策略的标的（可按需修改）。仅在用户未显式设置时应用。
preselect_a2 = {

        # A1 动量反转策略 - 基于早盘动量/午盘反转信号
    'AMD':  'a8',
    # 'META': 'a9',
    'RIVN': 'a10',
    'COIN': 'a11',
    # 'ZM':   'a12',
    'UBER': 'a13',
    'UPST': 'a14',  # 高波动金融科技，适合动量反转
    'DUOL': 'a15',  # 高波动成长股
    'AUDC': 'a16',  # 小盘科技股，情绪驱动
    'TMDX': 'a17',  # 医疗设备股，高波动


    # A3 双均线成交量突破策略 - 基于趋势突破
    'TEAM': 'a18',
    'GOOGL':'a4',
    'CRM':  'a4',
    'AVGO': 'a4',
    'IBM':  'a22',
    'NOW':  'a23',
    'AAPL': 'a24',  # 趋势清晰，成交量稳定
    'ADP':  'a25',  # 企业服务，稳定趋势
    'DV':   'a26',  # 数字验证，成长趋势明确
    
    # A2 Z-Score均值回归策略 - 基于统计套利
    'XOM':  'a27',
    'CVX':  'a28',
    'JPM':  'a29',
    'PFE':  'a30',
    'JNJ':  'a31',
    'BAC':  'a32',
    'PEP':  'a33',  # 稳定消费品，均值回归强
    'CSCO': 'a34',  # 成熟科技股，稳定波动
    'COMM': 'a35',  # 通信设备，周期性
    'UNH':  'a2',  # 医疗巨头，稳定大盘股
    'DINO': 'a2',  # 炼油股，周期性均值回归
    # 'TXN':  'a2',  # 半导体周期股，均值回归明显

    # A4 回调交易策略 - 基于斐波那契回撤
    'AMZN': 'a4',
    'TSLA': 'a4',
    'NFLX': 'a4',
    'DIS':  'a4',
    'NKE':  'a4',
    'SBUX': 'a4',
    'BABA': 'a4',  # 中概股，经常深度回调
    'BIDU': 'a4',  # 类似BABA，回调幅度大
    'AFRM': 'a4',  # 高波动电商股，回调明显
    'KSS': 'a4',  # 高波动电商股，回调明显
    'MRVL': 'a4',  # 高波动电商股，回调明显
    'TWLO': 'a4',  # 高波动电商股，回调明显
    'TOST': 'a4',  # 高波动电商股，回调明显
    'LMND': 'a4',  # 高波动电商股，回调明显
    'STRL': 'a4',  # 高波动电商股，回调明显
    'MRNA': 'a4',  # 高波动电商股，回调明显
    'ALAB': 'a4',  # 高波动电商股，回调明显
    'MQ': 'a4',  # 高波动电商股，回调明显
    
    

    # A5 多因子AI融合策略 - 整合流动性、基本面、情绪、动量
    'NVDA': 'a5',
    'MSFT': 'a5',
    'ETN':  'a5',
    'SNOW': 'a5',
    'PLTR': 'a5',
    'DDOG': 'a5',
    'CRWD': 'a5',
    'INCY': 'a5',  # 生物科技，多因子特征
    'PRIM': 'a5',  # 制造业，多重因素影响
    'MSTR': 'a5',  # 比特币概念，多维度驱动

    # A6 新闻交易策略 - 基于实时新闻情绪分析
    'ALHC': 'a6',  # 医疗保健，政策敏感
    'CLSK': 'a6',  # 比特币挖矿，加密货币新闻驱动
    'TSSI': 'a6',  # 小盘科技，事件驱动
    'SMR':  'a6',  # 核能概念，政策新闻敏感
    'SLDP': 'a6',  # 固态电池，新闻事件驱动

    # A7 CTA趋势跟踪策略 - 基于唐奇安通道突破
    'TSM':  'a7',
    'BA':   'a7',
    'ASML': 'a7',
    'LLY':  'a7',
    'RTX':  'a7',
    'AMAT': 'a7',
    # 'AZN':  'a7',  # 大型药企，趋势稳定
    'STX':  'a7',  # 存储周期股，趋势明显
    'WDC':  'a7',  # 同存储行业，趋势性强
}


merged_map = default_symbol_map.copy()
merged_map.update(preselect_a2)
CONFIG['symbol_strategy_map'] = merged_map

# 持久化映射到文件
os.makedirs('config', exist_ok=True)
with open('config/symbol_strategy_map.json', 'w') as f:
    json.dump(merged_map, f, indent=4)

# 打印最终的策略映射
a1_symbols = [s for s, strat in merged_map.items() if strat == 'a1']
a2_symbols = [s for s, strat in merged_map.items() if strat == 'a2']
a3_symbols = [s for s, strat in merged_map.items() if strat == 'a3']
a4_symbols = [s for s, strat in merged_map.items() if strat == 'a4']
a5_symbols = [s for s, strat in merged_map.items() if strat == 'a5']
print(f"✅ 策略映射加载完成，共 {len(merged_map)} 个标的")
if a1_symbols:
    print(f"   A1 策略 ({len(a1_symbols)} 个): {', '.join(sorted(a1_symbols[:5]))} {'...' if len(a1_symbols) > 5 else ''}")
if a2_symbols:
    print(f"   A2 策略 ({len(a2_symbols)} 个): {', '.join(sorted(a2_symbols[:5]))} {'...' if len(a2_symbols) > 5 else ''}")
if a3_symbols:
    print(f"   A3 策略 ({len(a3_symbols)} 个): {', '.join(sorted(a3_symbols[:5]))} {'...' if len(a3_symbols) > 5 else ''}")
if a4_symbols:
    print(f"   A4 策略 ({len(a4_symbols)} 个): {', '.join(sorted(a4_symbols[:5]))} {'...' if len(a4_symbols) > 5 else ''}")
if a5_symbols:
    print(f"   A5 策略 ({len(a5_symbols)} 个): {', '.join(sorted(a5_symbols[:5]))} {'...' if len(a5_symbols) > 5 else ''}")
a7_symbols = [s for s, strat in merged_map.items() if strat == 'a7']
if a7_symbols:
    print(f"   A7 策略 ({len(a7_symbols)} 个): {', '.join(sorted(a7_symbols[:5]))} {'...' if len(a7_symbols) > 5 else ''}")