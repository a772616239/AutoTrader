from datetime import datetime, time
import pandas as pd
import numpy as np
import logging
from typing import Dict, List, Optional, Tuple
from .base_strategy import BaseStrategy
from . import indicators as tech_indicators

logger = logging.getLogger(__name__)

class A7CTATrendStrategy(BaseStrategy):
    """
    A7 趋势跟踪/CTA策略 (Trend Following / CTA)
    
    核心逻辑：
    - 价格突破20日新高 -> 买入
    - 价格跌破20日新低 -> 卖空
    - 趋势过滤：只在价格位于200日均线之上做多，之下做空
    - 出场：价格反向突破10日极值
    """
    
    def get_strategy_name(self) -> str:
        return "A7 CTA Trend Strategy"

    def _default_config(self) -> Dict:
        return {
            'initial_capital': 40000.0,
            'risk_per_trade': 0.02,
            'max_position_size': 0.1,
            'per_trade_notional_cap': 4000.0,
            'max_position_notional': 60000.0,
            
            # 策略参数
            'donchian_entry_period': 20,    # 入场通道周期
            'donchian_exit_period': 10,     # 出场通道周期
            'trend_filter_sma_period': 200, # 趋势过滤均线周期
            'stop_loss_atr_multiple': 2.0,  # ATR止损倍数
            
            'trading_start_time': '09:45',
            'trading_end_time': '15:45',
            'avoid_open_hour': True,
            'avoid_close_hour': True,
        }

    def generate_signals(self, symbol: str, data: pd.DataFrame, indicators: Dict) -> List[Dict]:
        if data is None or data.empty or len(data) < self.config['trend_filter_sma_period'] + 10:
            return []

        current_price = data['Close'].iloc[-1]
        
        # 0. 检查通用出场条件 (止损/止盈)
        exit_signal = self.check_exit_conditions(symbol, current_price)
        if exit_signal:
            return [exit_signal]
            
        # 1. 计算指标
        highs = data['High']
        lows = data['Low']
        closes = data['Close']
        
        # 入场通道 (20)
        upper_entry, _, lower_entry = tech_indicators.calculate_donchian_channels(
            highs, lows, self.config['donchian_entry_period']
        )
        # 出场通道 (10)
        upper_exit, _, lower_exit = tech_indicators.calculate_donchian_channels(
            highs, lows, self.config['donchian_exit_period']
        )
        
        # 趋势过滤均线 (200)
        sma_trend = tech_indicators.calculate_moving_average(
            closes, self.config['trend_filter_sma_period'], type='SMA'
        )
        
        # ATR (用于风险计算)
        atr = tech_indicators.calculate_atr(highs, lows, closes, 14)
        current_atr = atr.iloc[-1]
        
        # 获取上一根K线的值（避免未来函数）
        prev_close = closes.iloc[-2]
        prev_upper_entry = upper_entry.iloc[-2]
        prev_lower_entry = lower_entry.iloc[-2]
        
        # 出场通道值
        prev_upper_exit = upper_exit.iloc[-2]
        prev_lower_exit = lower_exit.iloc[-2]
        
        current_trend_ma = sma_trend.iloc[-1]

        # 2. 获取当前持仓
        current_pos = 0
        if symbol in self.positions:
            current_pos = self.positions[symbol]['size']
            
        # 🟢 调试日志：打印关键数据
        logger.info(f"🔍 [A7 Debug] {symbol}: Price={current_price:.2f}, Pos={current_pos}, "
                   f"Entry20H={prev_upper_entry:.2f}, Entry20L={prev_lower_entry:.2f}, "
                   f"TrendMA200={current_trend_ma:.2f}, ATR={current_atr:.2f}")

        # 3. 交易逻辑
        
        # ---------------- 出场逻辑 ----------------
        if current_pos > 0: # 持多头
            # 价格跌破短期(10日)低点 -> 平多
            if current_price < prev_lower_exit:
                return [{
                    'symbol': symbol,
                    'signal_type': 'CTA_EXIT_LONG',
                    'action': 'SELL',
                    'price': current_price,
                    'position_size': abs(current_pos),
                    'reason': f"触及10日低点退出 ({prev_lower_exit:.2f})"
                }]
            else:
                logger.debug(f"  🛑 {symbol} 多头持有: 当前价 {current_price:.2f} >= 出场线 {prev_lower_exit:.2f}")

        elif current_pos < 0: # 持空头
            # 价格突破短期(10日)高点 -> 平空
            if current_price > prev_upper_exit:
                return [{
                    'symbol': symbol,
                    'signal_type': 'CTA_EXIT_SHORT',
                    'action': 'BUY',
                    'price': current_price,
                    'position_size': abs(current_pos),
                    'reason': f"触及10日高点退出 ({prev_upper_exit:.2f})"
                }]
            else:
                logger.debug(f"  🛑 {symbol} 空头持有: 当前价 {current_price:.2f} <= 出场线 {prev_upper_exit:.2f}")
                
        # ---------------- 入场逻辑 ----------------
        # 只有在没有反向持仓时才开仓（或者已平仓）
        if current_pos == 0:
            # 突破20日新高 且 价格 > 200日均线 (多头)
            long_cond_1 = current_price > prev_upper_entry
            long_cond_2 = current_price > current_trend_ma
            
            if long_cond_1 and long_cond_2:
                return [{
                    'symbol': symbol,
                    'signal_type': 'CTA_BREAKOUT_LONG',
                    'action': 'BUY',
                    'price': current_price,
                    'confidence': 0.7, # 趋势策略通常信心度固定
                    'indicators': {
                        'ATR': current_atr,
                        'UpperChannel': prev_upper_entry,
                        'TrendMA': current_trend_ma
                    },
                    'reason': f"突破20日新高 ({prev_upper_entry:.2f}) 且 > MA200"
                }]
            else:
                 logger.debug(f"  ⏸️ {symbol} 多头过滤: 突破20日高点?{long_cond_1} ({current_price:.2f}>{prev_upper_entry:.2f}), >MA200?{long_cond_2}")
            
            # 跌破20日新低 且 价格 < 200日均线 (空头)
            short_cond_1 = current_price < prev_lower_entry
            short_cond_2 = current_price < current_trend_ma
            
            if short_cond_1 and short_cond_2:
                return [{
                    'symbol': symbol,
                    'signal_type': 'CTA_BREAKDOWN_SHORT',
                    'action': 'SELL',
                    'price': current_price,
                    'confidence': 0.7,
                    'indicators': {
                        'ATR': current_atr,
                        'LowerChannel': prev_lower_entry,
                        'TrendMA': current_trend_ma
                    },
                    'reason': f"跌破20日新低 ({prev_lower_entry:.2f}) 且 < MA200"
                }]
            else:
                logger.debug(f"  ⏸️ {symbol} 空头过滤: 跌破20日低点?{short_cond_1} ({current_price:.2f}<{prev_lower_entry:.2f}), <MA200?{short_cond_2}")

        return []
