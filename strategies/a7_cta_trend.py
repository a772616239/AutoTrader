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
    A7 趋势跟踪/CTA策略 (Trend Following / CTA) - 增强卖出逻辑版
    
    核心逻辑：
    - 价格突破20日新高 -> 买入
    - 价格跌破20日新低 -> 卖空
    - 趋势过滤：只在价格位于200日均线之上做多，之下做空
    - 增强出场：价格反向突破10日极值 或 趋势均线被破坏
    """
    
    def get_strategy_name(self) -> str:
        return "A7 CTA Trend Strategy Enhanced Exit"

    def _default_config(self) -> Dict:
        # 使用现有的字段，并利用一个默认的 MA50 周期
        return {
            'initial_capital': 40000.0,
            'risk_per_trade': 0.02,
            'max_position_size': 0.1,
            'per_trade_notional_cap': 4000.0,
            'max_position_notional': 60000.0,
            
            # 策略参数
            'donchian_entry_period': 20,    # 入场通道周期
            'donchian_exit_period': 10,     # 出场通道周期
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
        
        # 0. 检查通用出场条件 (止损/止盈)
        exit_signal = self.check_exit_conditions(symbol, current_price)
        if exit_signal:
            return [exit_signal]
            
        # 1. 计算指标
        highs = data['High']
        lows = data['Low']
        closes = data['Close']
        
        # 入场通道 (20)
        # 简化调用，只计算出场所需的
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
        
        # ATR (用于风险计算) - 🚩 修复 ATR 调用错误
        # 传入 High, Low, Close series
        atr = tech_indicators.calculate_atr(highs, lows, closes, 14) 
        current_atr = atr.iloc[-1]
        
        # 获取上一根K线的值（避免未来函数）
        prev_upper_entry = data['High'].iloc[:-1].rolling(self.config['donchian_entry_period']).max().iloc[-1]
        prev_lower_entry = data['Low'].iloc[:-1].rolling(self.config['donchian_entry_period']).min().iloc[-1]
        
        # 出场通道值
        prev_upper_exit = upper_exit.iloc[-2]
        prev_lower_exit = lower_exit.iloc[-2]
        
        current_trend_ma = sma_trend.iloc[-1]
        current_fast_ma = sma_fast.iloc[-1]

        # 2. 获取当前持仓
        current_pos = 0
        if symbol in self.positions:
            # 假设 self.positions[symbol] 存储的是持仓数量
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
            # 跌破 MA50 或 MA200 视为趋势破坏
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
            # 避免大幅回撤，当 MA50 跌破 MA200 时，立即离场
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
            # 突破 MA50 或 MA200 视为趋势反转
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
            # 避免大幅回撤，当 MA50 站上 MA200 时，立即离场
            if current_fast_ma > current_trend_ma:
                return [{
                    'symbol': symbol,
                    'signal_type': 'CTA_EXIT_SHORT_MA_CROSS',
                    'action': 'BUY',
                    'price': current_price,
                    'quantity': abs(current_pos),
                    'reason': f"MA交叉离场 (MA{FAST_MA_PERIOD} > MA{self.config['trend_filter_sma_period']})"
                }]

                
        # ---------------- 入场逻辑 (Entry) ----------------
        if current_pos == 0:
            
            # 多头严格条件：
            long_cond_1 = current_price > prev_upper_entry
            long_cond_2 = current_price > current_trend_ma
            long_cond_3 = current_fast_ma > current_trend_ma # 均线多头排列
            
            if long_cond_1 and long_cond_2 and long_cond_3:
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
                    'reason': f"新高({prev_upper_entry:.2f}) + MA多头排列(MA{FAST_MA_PERIOD}>MA{self.config['trend_filter_sma_period']})"
                }]
            
            # 空头严格条件：
            short_cond_1 = current_price < prev_lower_entry
            short_cond_2 = current_price < current_trend_ma
            short_cond_3 = current_fast_ma < current_trend_ma # 均线空头排列
            
            if short_cond_1 and short_cond_2 and short_cond_3:
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
                    'reason': f"新低({prev_lower_entry:.2f}) + MA空头排列(MA{FAST_MA_PERIOD}<MA{self.config['trend_filter_sma_period']})"
                }]

        return []