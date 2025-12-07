#!/usr/bin/env python3
"""
配置文件
"""
import os
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
        'port': 7497,
        'client_id': 1,
        'max_retries': 3,
    },
    'trading': {
        'symbols': [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META',
            'MU', 'INTC', 'AMD', 'NFLX', 'BIDU', 'JD', 'BABA',
            'TCEHY', 'PYPL', 'SHOP', 'CRM', 'ORCL', 'IBM',
            'CSCO', 'QCOM', 'TXN', 'AVGO', 'ADBE', 'INTU',
            'ZM', 'DOCU', 'SNOW', 'UBER', 'LYFT', 'SPOT',
            'TWTR', 'PINS', 'SQ', 'FSLY', 'OKTA', 'DDOG',
            'CRWD', 'ZS', 'NET', 'WORK',
        ],
        'scan_interval_minutes': 1,
        'trading_hours': {
            'start': '09:30',  # 美东时间 06:30（冬令时）或 05:30（夏令时），但 TWS 通常以本地时间计
            'end': '16:00'     # 美东时间下午 4:00
        },
        'max_symbols_per_cycle': 50,
    },
    'logging': {
        'level': 'INFO',
        'file': os.path.join('logs', f'trading_{datetime.now():%Y%m%d_%H%M%S}.log'),
        'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    },
    'strategy_a1': {  # 动量反转策略配置
        'initial_capital': 40000.0,
        'risk_per_trade': 0.02,
        'max_position_size': 0.1,
        'per_trade_notional_cap': 4000.0,  # 单笔交易美元上限
        'max_position_notional': 60000.0,  # 单股总仓位上限（美元）
        'rsi_overbought': 72,
        'rsi_oversold': 28,
        'stop_loss_atr_multiple': 1.5,
        'take_profit_atr_multiple': 3.0,
        'ib_order_type': 'MKT',
        'ib_limit_offset': 0.01,
        'trading_start_time': '09:30',
        'trading_end_time': '16:00',
        'avoid_open_hour': True,
        'avoid_close_hour': True,
    },
    'strategy_a2': {  # Z-Score策略配置
        'initial_capital': 40000.0,
        'risk_per_trade': 0.02,
        'max_position_size': 0.1,
        'per_trade_notional_cap': 4000.0,  # 单笔交易美元上限
        'max_position_notional': 60000.0,  # 单股总仓位上限（美元）
        'zscore_lookback': 20,
        'zscore_entry_threshold': 2.0,
        'zscore_exit_threshold': 0.5,
        'stop_loss_pct': 0.03,
        'take_profit_pct': 0.05,
        'ib_order_type': 'LMT',
        'ib_limit_offset': 0.005,
        'trading_start_time': '09:30',
        'trading_end_time': '16:00',
        'trading_hours_only': True,
    },
    'strategy_a3': {  # 双均线成交量突破策略配置
        'trading': {
            'initial_capital': 40000.0,  # 初始资金
            'risk_per_trade': 0.02,    # 单笔交易风险 (2% equity) (A6 uses 0.015)
            'max_position_size': 0.1,  # 最大仓位 (10% equity)
            'min_cash_buffer': 0.1,    # 最小现金缓冲
            'per_trade_notional_cap': 4000.0, # 单笔名义价值上限 (USD)
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
        'take_profit_pct': 0.03,
        'take_profit_atr_multiple': 2.0,
        'max_holding_minutes': 60,
        'ib_order_type': 'MKT',
        'ib_limit_offset': 0.01,
        'trading_start_time': '09:45',
        'trading_end_time': '15:30',
        'avoid_open_hour': True,
        'avoid_close_hour': True,
    },
    'strategy_a4': {  # 回调交易策略配置（斐波那契回撤）
        'initial_capital': 40000.0,
        'risk_per_trade': 0.02,
        'max_position_size': 0.1,
        'per_trade_notional_cap': 4000.0,  # 单笔交易美元上限
        'max_position_notional': 60000.0,  # 单股总仓位上限（美元）
        'trend_ma_period': 80,              # 长期趋势均线
        'trend_confirmation_bars': 3,      # 趋势确认K线数
        'pullback_lookback': 20,            # 回撤识别窗口
        'fibonacci_levels': [0.236, 0.382, 0.5, 0.618, 0.786],
        'pullback_buy_ratio': [0.15, 0.7],   # 回撤买入位置
        'pullback_sell_ratio': [0.15, 0.7],  # 反弹卖出位置
        'volume_confirmation': True,
        'min_volume_ratio': 1.0,
        'stop_loss_pct': 0.03,
        'take_profit_pct': 0.05,
        'max_holding_days': 5,
        'trading_start_time': '10:00',  # 避开开盘波动
        'trading_end_time': '15:30',
        'avoid_open_hour': True,
        'avoid_close_hour': True,
        'ib_order_type': 'MKT',
        'ib_limit_offset': 0.01,
    },
    'strategy_a5': {  # 多因子AI融合策略配置
        'initial_capital': 40000.0,
        'risk_per_trade': 0.02,
        'max_position_size': 0.06,
        'per_trade_notional_cap': 4000.0,      # 单笔交易美元上限（严格）
        'max_position_notional': 40000.0,      # 单股总仓位上限（美元，严格）
        'min_confidence': 0.65,                # 最小信心度阈值（严格）
        'min_price': 10.0,                     # 最小股价（严格，避免低价股）
        'min_volume': 200000,                 # 最小日成交量（严格，流动性第一）
        'lookback_period': 90,                 # 基本面指标回溯天数
        'recent_period': 20,                   # 最近期间（天数）
        'liquidity_weight': 0.35,              # 流动性因子权重（优先级最高）
        'fundamental_weight': 0.20,            # 基本面因子权重（降低）
        'sentiment_weight': 0.10,              # 情绪因子权重（最小化）
        'momentum_weight': 0.35,               # 动量因子权重（优先级最高）
        'buy_threshold': 0.68,                 # 买入复合得分阈值（严格）
        'sell_threshold': 0.55,                # 卖出复合得分阈值（严格）
        'exit_threshold': 0.25,                # 平仓复合得分阈值（更低，快速止损）
        'ib_order_type': 'MKT',
        'ib_limit_offset': 0.01,
        'trading_start_time': '09:45',
        'trading_end_time': '15:30',
        'avoid_open_hour': True,
        'avoid_close_hour': True,
    },
    'strategy_a6': {  # 新闻交易策略配置
        'initial_capital': 40000.0,
        'risk_per_trade': 0.015,              # 新闻交易风险控制更严格
        'max_position_size': 0.04,             # 小仓位，快速进出
        'per_trade_notional_cap': 4000.0,     # 单笔交易美元上限（更严格）
        'max_position_notional': 20000.0,     # 单股总仓位上限（美元，更严格）
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
        'ib_order_type': 'MKT',
        'ib_limit_offset': 0.005,
        'trading_start_time': '09:45',
        'trading_end_time': '15:30',
        'avoid_open_hour': True,
        'avoid_close_hour': True,
    },
    'strategy_a7': {  # A7 CTA 趋势跟踪策略
        'initial_capital': 40000.0,
        'risk_per_trade': 0.02,
        'max_position_size': 0.1,
        'per_trade_notional_cap': 4000.0,
        'max_position_notional': 60000.0,
        'donchian_entry_period': 20,
        'donchian_exit_period': 10,
        'trend_filter_sma_period': 200,
        'stop_loss_atr_multiple': 2.0,
        'ib_order_type': 'MKT',
        'ib_limit_offset': 0.01,
        'trading_start_time': '09:45',
        'trading_end_time': '16:00',
        'avoid_open_hour': True,
        'avoid_close_hour': True,
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
}

# 每个标的分配策略示例: 将特定股票映射到 a1/a2/a3
# 如果未在此映射中列出，则系统可选择默认策略或轮询分配
# 自动生成 symbol->strategy 映射：默认将 `trading.symbols` 中的每个标的分配到 'a1'
# 如果用户在外部（或在文件上方）已经设置了部分映射，会合并并以用户设置为准。
default_symbols = CONFIG.get('trading', {}).get('symbols', [])
default_symbol_map = {s: 'a7' for s in default_symbols}

# 允许事先存在的自定义映射覆盖默认值
existing_map = CONFIG.get('symbol_strategy_map', {}) or {}

# 预设一些需要使用 a2 策略的标的（可按需修改）。仅在用户未显式设置时应用。
preselect_a2 = {
    # 'AAPL': 'a2',
    # 'MSFT': 'a2',
    # 'GOOGL':'a2',
    # 'AMZN': 'a2',
    # 'TSLA': 'a2',
    # 'NVDA': 'a2',
    # 'META': 'a2',
    # 'INTC': 'a2',
    # 'AMD':  'a2',
}

merged_map = default_symbol_map.copy()
merged_map.update(preselect_a2)
CONFIG['symbol_strategy_map'] = merged_map

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