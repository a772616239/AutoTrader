import logging
import hashlib
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, time as dt_time
from typing import Dict, Optional
# 导入所需的类型提示，但在运行时不需要直接依赖 IBTrader，只需要其接口

logger = logging.getLogger(__name__)

class MomentumReversalEngine:
    """策略 A1: 动量反转日内交易系统 (原逻辑)"""

    def __init__(self, ib_trader, data_provider, config: Dict = None):
        self.ib_trader = ib_trader
        self.data_provider = data_provider
        self.config = self._default_config()
        if config:
            self.config.update(config)
            
        self.positions = {}
        self.signal_cache = {}
        self.name = "Strategy_A1_MomentumReversal"
        logger.info(f"策略引擎 {self.name} 已加载")

    def _default_config(self) -> Dict:
        return {
            'morning_session': ('09:30', '10:30'),
            'midday_session': ('10:30', '14:30'),
            'afternoon_session': ('14:30', '15:00'),
            'rsi_overbought': 72,
            'rsi_oversold': 28,
            'stop_loss_atr_multiple': 1.5,
            'max_holding_minutes': 120,
            'risk_per_trade': 0.02
        }

    def run_analysis(self, symbol: str):
        """主分析入口，被 main.py 调用"""
        # 1. 获取数据
        df = self.data_provider.get_intraday_data(symbol)
        indicators = self.data_provider.get_technical_indicators(symbol)
        
        if df.empty: return None

        # 2. 获取当前时间段
        now = datetime.now().time()
        morning_end = datetime.strptime(self.config['morning_session'][1], '%H:%M').time()
        afternoon_start = datetime.strptime(self.config['afternoon_session'][0], '%H:%M').time()

        signal = None
        
        # 3. 根据时间段选择原有逻辑
        if now < morning_end:
            signal = self.detect_morning_momentum(symbol, df, indicators)
        elif now > afternoon_start:
            signal = self.detect_afternoon_reversal(symbol, df, indicators)
            
        # 4. 检查退出条件 (通用)
        exit_signal = self.check_exit_conditions(symbol, df['Close'].iloc[-1])
        if exit_signal:
            return exit_signal # 止损/止盈优先
            
        return signal

    def detect_morning_momentum(self, symbol, data, indicators):
        # ... (保留原有的早盘动量逻辑代码) ...
        # 简写演示：
        rsi = indicators.get('RSI', 50)
        if 50 <= rsi <= 67: # 示例逻辑
             # 这里应填入你原有代码的完整逻辑
             return {'symbol': symbol, 'action': 'BUY', 'signal_type': 'MORNING_MOMENTUM', 'price': data['Close'].iloc[-1]}
        return None

    def detect_afternoon_reversal(self, symbol, data, indicators):
        # ... (保留原有的午盘反转逻辑代码) ...
        rsi = indicators.get('RSI', 50)
        if rsi > self.config['rsi_overbought']:
            return {'symbol': symbol, 'action': 'SELL', 'signal_type': 'AFTERNOON_REVERSAL', 'price': data['Close'].iloc[-1]}
        return None

    def check_exit_conditions(self, symbol, current_price):
        # 这里的逻辑需要依赖 self.positions
        # 在 main loop 中我们需要确保 self.positions 是同步的
        if symbol not in self.positions:
            return None
        
        pos = self.positions[symbol]
        avg_cost = pos['avg_cost']
        pct_change = (current_price - avg_cost) / avg_cost
        
        # 简单示例原有的止损逻辑
        if pct_change < -0.02: 
            return {'symbol': symbol, 'action': 'SELL', 'signal_type': 'STOP_LOSS', 'price': current_price}
        return None

    def sync_positions(self):
        """从IB同步持仓"""
        holdings = self.ib_trader.get_holdings()
        self.positions = {}
        for h in holdings:
            self.positions[h.contract.symbol] = {
                'size': h.position,
                'avg_cost': h.avgCost
            }