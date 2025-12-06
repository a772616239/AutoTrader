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
            'ZM', 'DOCU', 'SNOW', 'UBER', 'LYFT'
        ],
        'scan_interval_minutes': 1,
        'trading_hours': {
            'start': '09:30',
            'end': '16:00'
        },
        'max_symbols_per_cycle': 50,
    },
    'logging': {
        'level': 'INFO',
        'file': os.path.join('logs', f'trading_{datetime.now():%Y%m%d_%H%M%S}.log'),
        'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    },
    'strategy_a1': {  # 动量反转策略配置
        'initial_capital': 100000.0,
        'risk_per_trade': 0.02,
        'max_position_size': 0.1,
        'rsi_overbought': 72,
        'rsi_oversold': 28,
        'stop_loss_atr_multiple': 1.5,
        'take_profit_atr_multiple': 3.0,
        'ib_order_type': 'MKT',
        'ib_limit_offset': 0.01,
    },
    'strategy_a2': {  # Z-Score策略配置
        'initial_capital': 100000.0,
        'risk_per_trade': 0.02,
        'max_position_size': 0.1,
        'zscore_lookback': 20,
        'zscore_entry_threshold': 2.0,
        'zscore_exit_threshold': 0.5,
        'stop_loss_pct': 0.03,
        'take_profit_pct': 0.05,
        'ib_order_type': 'LMT',
        'ib_limit_offset': 0.005,
    }
}

# 策略映射
STRATEGY_CONFIG_MAP = {
    'a1': 'strategy_a1',
    'a2': 'strategy_a2',
}