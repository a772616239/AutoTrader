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
    A7 趋势跟踪/CTA策略 (Trend Following / CTA) - 增强卖出逻辑版 & 增强买入过滤
    
    核心逻辑：
    - 价格突破20日新高/新低 -> 买入/卖空
    - 趋势过滤：价格位于200日均线之上做多，之下做空
    - 均线过滤：新增MA50/MA200多头/空头排列要求（提升入场质量）
    - 增强过滤：新增10日通道过滤（降低假突破率）
    - 增强出场：价格反向突破10日极值 或 趋势均线被破坏
    """
    
    def get_strategy_name(self) -> str:
        return "A7 CTA Trend Strategy Enhanced Entry/Exit"

    def _default_config(self) -> Dict:
        # 使用现有的字段，并利用一个默认的 MA50 周期
        return {
            'initial_capital': 40000.0,
            'risk_per_trade': 0.02,
            'max_position_size': 0.1,
            'per_trade_notional_cap': 4000.0,
            'max_position_notional': 60000.0,
            
            # 策略参数
            'donchian_entry_period': 20,    # 入场通道周期 (20)
            'donchian_exit_period': 10,     # 出场通道周期 (10)
            'trend_filter_sma_period': 200, # 慢速趋势过滤均线周期 (MA200)
            'stop_loss_atr_multiple': 2.0,  # ATR止损倍数
            
            'trading_start_time': '09:45',
            'trading_end_time': '15:45',
            'avoid_open_hour': True,
            'avoid_close_hour': True,
        }

    def generate_signals(self, symbol: str, data: pd.DataFrame, indicators: Dict) -> List[Dict]:
        # 内部定义快速均线周期，以避免在配置中增加新字段
        FAST_MA_PERIOD = 50 

        if data is None or data.empty or len(data) < self.config['trend_filter_sma_period'] + 10:
            return []

        current_price = data['Close'].iloc[-1]
        
        # 0. 检查通用出场条件 (止损/止盈) - 假设此方法已在 BaseStrategy 中定义
        exit_signal = self.check_exit_conditions(symbol, current_price) 
        if exit_signal:
            return [exit_signal]
            
        # 1. 计算指标
        highs = data['High']
        lows = data['Low']
        closes = data['Close']
        
        # 入场通道 (20) - 仅为保证计算出场所需的指标
        _, _, _ = tech_indicators.calculate_donchian_channels(highs, lows, self.config['donchian_entry_period'])
        # 出场通道 (10)
        upper_exit, _, lower_exit = tech_indicators.calculate_donchian_channels(
            highs, lows, self.config['donchian_exit_period']
        )
        
        # 趋势过滤慢速均线 (200)
        sma_trend = tech_indicators.calculate_moving_average(
            closes, self.config['trend_filter_sma_period'], type='SMA'
        )
        # 快速趋势均线 (50)
        sma_fast = tech_indicators.calculate_moving_average(
            closes, FAST_MA_PERIOD, type='SMA'
        )
        
        # ATR (用于风险计算)
        atr = tech_indicators.calculate_atr(highs, lows, closes, 14) 
        current_atr = atr.iloc[-1]
        
        # 获取上一根K线的值（避免未来函数）
        prev_upper_entry = data['High'].iloc[:-1].rolling(self.config['donchian_entry_period']).max().iloc[-1]
        prev_lower_entry = data['Low'].iloc[:-1].rolling(self.config['donchian_entry_period']).min().iloc[-1]
        
        # 出场通道值 (用于出场和**新的入场过滤**)
        prev_upper_exit = upper_exit.iloc[-2] # 10日高点
        prev_lower_exit = lower_exit.iloc[-2] # 10日低点
        
        current_trend_ma = sma_trend.iloc[-1]
        current_fast_ma = sma_fast.iloc[-1]

        # 2. 获取当前持仓
        current_pos = 0
        if symbol in self.positions:
            current_pos = self.positions[symbol] if isinstance(self.positions[symbol], (int, float)) else self.positions[symbol].get('size', 0)
            
        logger.info(f"🔍 [A7 Debug] {symbol}: Price={current_price:.2f}, Pos={current_pos}, "
                   f"EntryH={prev_upper_entry:.2f}, ExitL={prev_lower_exit:.2f}, "
                   f"MA{FAST_MA_PERIOD}={current_fast_ma:.2f}, MA{self.config['trend_filter_sma_period']}={current_trend_ma:.2f}")

        # 3. 交易逻辑
        
        # ---------------- 🚀 增强出场逻辑 (Exit) ----------------
        if current_pos > 0: # 持多头
            
            # --- 逻辑 A: 10日极值反转 (基础) ---
            if current_price < prev_lower_exit:
                return [{
                    'symbol': symbol,
                    'signal_type': 'CTA_EXIT_LONG_DCH',
                    'action': 'SELL',
                    'price': current_price,
                    'quantity': abs(current_pos),
                    'reason': f"触及10日出场低点 ({prev_lower_exit:.2f})"
                }]
                
            # --- 逻辑 B: 趋势保护离场 (价格跌破关键均线) ---
            if current_price < current_fast_ma or current_price < current_trend_ma:
                return [{
                    'symbol': symbol,
                    'signal_type': 'CTA_EXIT_LONG_TREND_BREAK',
                    'action': 'SELL',
                    'price': current_price,
                    'quantity': abs(current_pos),
                    'reason': f"价格跌破MA{FAST_MA_PERIOD} ({current_fast_ma:.2f}) 或 MA{self.config['trend_filter_sma_period']}"
                }]

            # --- 逻辑 C: 均线交叉离场 (多头排列被破坏) ---
            if current_fast_ma < current_trend_ma:
                return [{
                    'symbol': symbol,
                    'signal_type': 'CTA_EXIT_LONG_MA_CROSS',
                    'action': 'SELL',
                    'price': current_price,
                    'quantity': abs(current_pos),
                    'reason': f"MA交叉离场 (MA{FAST_MA_PERIOD} < MA{self.config['trend_filter_sma_period']})"
                }]

        elif current_pos < 0: # 持空头
            
            # --- 逻辑 A: 10日极值反转 (基础) ---
            if current_price > prev_upper_exit:
                return [{
                    'symbol': symbol,
                    'signal_type': 'CTA_EXIT_SHORT_DCH',
                    'action': 'BUY',
                    'price': current_price,
                    'quantity': abs(current_pos),
                    'reason': f"触及10日出场高点 ({prev_upper_exit:.2f})"
                }]
                
            # --- 逻辑 B: 趋势保护离场 (价格突破关键均线) ---
            if current_price > current_fast_ma or current_price > current_trend_ma:
                return [{
                    'symbol': symbol,
                    'signal_type': 'CTA_EXIT_SHORT_TREND_BREAK',
                    'action': 'BUY',
                    'price': current_price,
                    'quantity': abs(current_pos),
                    'reason': f"价格突破MA{FAST_MA_PERIOD} ({current_fast_ma:.2f}) 或 MA{self.config['trend_filter_sma_period']}"
                }]
            
            # --- 逻辑 C: 均线交叉离场 (空头排列被破坏) ---
            if current_fast_ma > current_trend_ma:
                return [{
                    'symbol': symbol,
                    'signal_type': 'CTA_EXIT_SHORT_MA_CROSS',
                    'action': 'BUY',
                    'price': current_price,
                    'quantity': abs(current_pos),
                    'reason': f"MA交叉离场 (MA{FAST_MA_PERIOD} > MA{self.config['trend_filter_sma_period']})"
                }]

                
        # ---------------- 入场逻辑 (Entry) - 强化过滤 ----------------
        if current_pos == 0:
            
            
            # 多头条件放宽便于测试：
            long_cond_1 = current_price > prev_upper_entry * 0.995      # 接近突破20日高点 (放宽5点)
            long_cond_2 = current_price > current_trend_ma              # 位于MA200之上
            long_cond_3 = current_fast_ma > current_trend_ma * 0.995    # 均线接近多头排列 (放宽)
            # 放宽10日通道过滤
            long_cond_4 = current_price > prev_lower_exit * 0.98               

            if long_cond_1 and long_cond_2 and long_cond_3 and long_cond_4:
                return [{
                    'symbol': symbol,
                    'signal_type': 'CTA_BREAKOUT_LONG',
                    'action': 'BUY',
                    'price': current_price,
                    'confidence': 0.8,
                    'indicators': {
                        'ATR': current_atr,
                        'UpperChannel': prev_upper_entry,
                        'TrendMA': current_trend_ma,
                        'FastMA': current_fast_ma
                    },
                    'reason': f"新高({prev_upper_entry:.2f}) + MA多头排列 + 10日低点过滤"
                }]
            
            # 空头条件放宽便于测试：
            short_cond_1 = current_price < prev_lower_entry * 1.005     # 接近跌破20日低点 (放宽5点)
            short_cond_2 = current_price < current_trend_ma             # 位于MA200之下
            short_cond_3 = current_fast_ma < current_trend_ma * 1.005   # 均线接近空头排列 (放宽)
            # 放宽10日通道过滤
            short_cond_4 = current_price < prev_upper_exit * 1.02              

            if short_cond_1 and short_cond_2 and short_cond_3 and short_cond_4:
                return [{
                    'symbol': symbol,
                    'signal_type': 'CTA_BREAKDOWN_SHORT',
                    'action': 'SELL',
                    'price': current_price,
                    'confidence': 0.8,
                    'indicators': {
                        'ATR': current_atr,
                        'LowerChannel': prev_lower_entry,
                        'TrendMA': current_trend_ma,
                        'FastMA': current_fast_ma
                    },
                    'reason': f"新低({prev_lower_entry:.2f}) + MA空头排列 + 10日高点过滤"
                }]

        return []