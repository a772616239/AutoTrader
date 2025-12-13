#!/usr/bin/env python3
"""
双均线 + 成交量突破策略 (策略A3)
核心思想: 结合快速均线交叉和成交量突破识别趋势
增强版: 包含多层级卖出逻辑（趋势破坏、动量衰竭、放量反转）
"""
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
from strategies.base_strategy import BaseStrategy
from strategies import indicators

logger = logging.getLogger(__name__)

class A3DualMAVolumeStrategy(BaseStrategy):
    """双均线成交量突破策略 (增强版)"""
    
    def _default_config(self) -> Dict:
        """默认配置"""
        return {
            # 资金管理
            'initial_capital': 40000.0,
            'risk_per_trade': 0.02,
            'max_position_size': 0.1,
            'per_trade_notional_cap': 4000.0,
            'max_position_notional': 60000.0,
            
            # 双均线参数
            'fast_ma_period': 9,
            'slow_ma_period': 21,
            'ema_or_sma': 'EMA',
            
            # 成交量参数（放宽限制）
            'volume_sma_period': 20,
            'volume_surge_ratio': 1.1,
            'min_volume_threshold': 5000,
            
            # 入场条件（放宽限制）
            'entry_confirmation_bars': 1,
            'price_above_slow_ma': False,
            'use_atr_stop_loss': True,
            'atr_stop_multiple': 1.5,
            
            # 出场条件
            'take_profit_pct': 0.03,
            'take_profit_atr_multiple': 2.0,
            'max_holding_minutes': 60,
            'trailing_stop_pct': 0.02,
            
            # 时间过滤（放宽限制）
            'trading_start_time': '09:30',
            'trading_end_time': '15:00',
            'avoid_open_hour': False,
            'avoid_close_hour': False,
            
            # 风险管理
            'max_daily_loss_pct': 0.05,
            'max_consecutive_losses': 3,
            'min_profit_pct': 0.01,
            
            # 防重复交易
            'signal_cooldown_minutes': 3,
            
            # IB交易参数
            'ib_order_type': 'MKT',
            'ib_limit_offset': 0.01,
        }
    
    def get_strategy_name(self) -> str:
        """获取策略名称"""
        return "A3 Dual MA + Volume Breakout Enhanced"
    
    def calculate_moving_averages(self, data: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        """计算快速和慢速均线"""
        fast_ma = indicators.calculate_moving_average(
            data['Close'], 
            self.config['fast_ma_period'], 
            self.config['ema_or_sma']
        )
        slow_ma = indicators.calculate_moving_average(
            data['Close'], 
            self.config['slow_ma_period'], 
            self.config['ema_or_sma']
        )
        return fast_ma, slow_ma
    
    def detect_volume_breakout(self, data: pd.DataFrame) -> Tuple[bool, float]:
        """检测成交量突破"""
        if len(data) < self.config['volume_sma_period'] + 1:
            return False, 0.0
        
        # 计算成交量均线
        volume_sma = data['Volume'].rolling(window=self.config['volume_sma_period']).mean()
        
        # 获取最新和前一根K线的成交量
        current_volume = data['Volume'].iloc[-1]
        avg_volume = volume_sma.iloc[-2]
        
        if avg_volume <= 0:
            return False, 0.0
        
        volume_ratio = current_volume / avg_volume
        is_breakout = volume_ratio >= self.config['volume_surge_ratio']
        
        return is_breakout, volume_ratio
    
    def detect_ma_crossover(self, data: pd.DataFrame, 
                           fast_ma: pd.Series, slow_ma: pd.Series) -> Tuple[str, float]:
        """检测均线交叉信号"""
        if len(data) < 3:
            return 'NONE', 0.0
        
        # 获取最新两根K线的均线关系
        current_fast = fast_ma.iloc[-1]
        current_slow = slow_ma.iloc[-1]
        prev_fast = fast_ma.iloc[-2]
        prev_slow = slow_ma.iloc[-2]
        
        # 检查金叉（快线从下穿过慢线）
        bullish_cross = (prev_fast <= prev_slow) and (current_fast > current_slow)
        # 检查死叉（快线从上穿过慢线）
        bearish_cross = (prev_fast >= prev_slow) and (current_fast < current_slow)
        
        # 计算均线距离作为置信度
        ma_distance = abs(current_fast - current_slow) / (current_slow + 0.01)
        confidence = min(ma_distance * 20, 1.0)  # 稍微放大系数
        
        if bullish_cross:
            return 'BULLISH', confidence
        elif bearish_cross:
            return 'BEARISH', confidence
        else:
            return 'NONE', 0.0
    
    def is_trading_hours(self, current_time: Optional[datetime] = None) -> bool:
        """检查是否在交易时段"""
        if current_time is None:
            current_time = datetime.now()
        current_dt_time = current_time.time()
        
        start_time = datetime.strptime(self.config['trading_start_time'], '%H:%M').time()
        end_time = datetime.strptime(self.config['trading_end_time'], '%H:%M').time()
        
        if not (start_time <= current_dt_time <= end_time):
            return False
            
        if self.config['avoid_open_hour']:
            market_open = datetime.strptime('09:30', '%H:%M').time()
            open_end = datetime.strptime('10:30', '%H:%M').time()
            if market_open <= current_dt_time <= open_end:
                return False
                
        if self.config['avoid_close_hour']:
            close_start = datetime.strptime('14:30', '%H:%M').time()
            market_close = datetime.strptime('16:00', '%H:%M').time()
            if close_start <= current_dt_time <= market_close:
                return False
                
        return True
    
    def detect_buy_signal(self, symbol: str, data: pd.DataFrame, 
                         indicators_dict: Dict) -> Optional[Dict]:
        """检测买入信号"""
        min_required = max(self.config['fast_ma_period'], self.config['slow_ma_period']) + 2
        if len(data) < min_required:
            return None
        
        if symbol in self.positions:
            return None
        
        fast_ma, slow_ma = self.calculate_moving_averages(data)
        
        # 检查均线交叉
        crossover_signal, ma_confidence = self.detect_ma_crossover(data, fast_ma, slow_ma)
        if crossover_signal != 'BULLISH':
            return None
        
        # 检查价格在慢速均线上方
        current_price = data['Close'].iloc[-1]
        current_slow_ma = slow_ma.iloc[-1]
        if self.config['price_above_slow_ma'] and current_price < current_slow_ma:
            return None
        
        # 检查成交量突破
        volume_breakout, volume_ratio = self.detect_volume_breakout(data)
        if not volume_breakout:
            return None
        
        # 最小成交量检查
        from config import CONFIG
        skip_volume_check = CONFIG.get('trading', {}).get('skip_volume_check', False)
        if not skip_volume_check:
            current_volume = data['Volume'].iloc[-1]
            if current_volume < self.config['min_volume_threshold']:
                return None
        
        # 综合置信度
        volume_confidence = min(volume_ratio / self.config['volume_surge_ratio'], 1.0)
        combined_confidence = (ma_confidence + volume_confidence) / 2
        
        logger.info(
            f"🟢 {symbol} A3买入信号 ✓ "
            f"Price={current_price:.2f}, VolRatio={volume_ratio:.2f}x"
        )
        
        signal = {
            'symbol': symbol,
            'signal_type': 'MA_CROSSOVER_BUY',
            'action': 'BUY',
            'price': current_price,
            'reason': f'A3 Bullish: MA Cross + Vol {volume_ratio:.1f}x',
            'confidence': combined_confidence,
            'fast_ma': fast_ma.iloc[-1],
            'slow_ma': current_slow_ma,
            'volume_ratio': volume_ratio,
            'timestamp': datetime.now()
        }
        
        # 计算仓位 (依赖ATR)
        atr_val = indicators.calculate_atr(data['High'], data['Low'], data['Close'], 14).iloc[-1] if len(data) > 15 else (data['High'] - data['Low']).mean()
        signal['position_size'] = self.calculate_position_size(signal, atr_val)
        
        if signal['position_size'] <= 0:
            return None
        
        signal_hash = self._generate_signal_hash(signal)
        signal['signal_hash'] = signal_hash
        
        return signal
    
    def detect_sell_signal(self, symbol: str, data: pd.DataFrame, 
                          indicators_dict: Dict) -> Optional[Dict]:
        """
        检测卖出信号 (增强版逻辑)
        
        逻辑层次:
        1. 均线死叉 (基础)
        2. 趋势破坏: 价格跌破慢速均线 (快速止损)
        3. 放量反转: 成交量巨幅放大但价格下跌 (主力出货)
        4. 动量衰竭: 价格跌破快速均线 + RSI 高位回落 (获利保护)
        """
        min_required = max(self.config['fast_ma_period'], self.config['slow_ma_period']) + 5
        if len(data) < min_required or symbol not in self.positions:
            return None
        
        current_price = data['Close'].iloc[-1]
        prev_price = data['Close'].iloc[-2]
        price_change = (current_price - prev_price) / prev_price
        
        # 1. 计算基础指标
        fast_ma, slow_ma = self.calculate_moving_averages(data)
        curr_fast = fast_ma.iloc[-1]
        curr_slow = slow_ma.iloc[-1]
        
        # 计算 RSI (14周期)
        rsi_series = indicators.calculate_rsi(data['Close'], 14)
        current_rsi = rsi_series.iloc[-1] if not rsi_series.empty else 50.0
        
        # 计算成交量情况
        volume_breakout, volume_ratio = self.detect_volume_breakout(data)
        
        sell_reason = ""
        sell_confidence = 0.0
        should_sell = False
        
        # --- 卖出逻辑判断 ---
        
        # 逻辑 1: 均线死叉 (最强烈的反转信号)
        crossover_signal, ma_confidence = self.detect_ma_crossover(data, fast_ma, slow_ma)
        if crossover_signal == 'BEARISH':
            should_sell = True
            sell_reason = f"均线死叉 (Fast {curr_fast:.2f} < Slow {curr_slow:.2f})"
            sell_confidence = 0.9
            
        # 逻辑 2: 趋势破坏 (价格直接跌破慢速均线)
        # 即使均线还没死叉，如果价格实体已经完全在慢线下方，说明趋势坏了
        elif current_price < curr_slow:
            should_sell = True
            sell_reason = f"跌破慢速均线 (Price {current_price:.2f} < {curr_slow:.2f})"
            sell_confidence = 0.8
            
        # 逻辑 3: 放量出货 (Climax)
        # 成交量是突破标准的1.5倍以上，且价格明显下跌
        elif (volume_ratio > self.config['volume_surge_ratio'] * 1.5) and (price_change < -0.005):
            should_sell = True
            sell_reason = f"放量下跌 (Vol {volume_ratio:.1f}x, Change {price_change:.1%})"
            sell_confidence = 0.75
            
        # 逻辑 4: 动量衰竭与获利保护
        # 价格跌破快速均线，并且 RSI 已经从高位 (>75) 回落 或者 RSI 极高 (>85)
        elif current_price < curr_fast:
            if current_rsi > 85:
                should_sell = True
                sell_reason = f"RSI极端超买保护 (RSI {current_rsi:.1f})"
                sell_confidence = 0.7
            elif current_rsi < 50 and price_change < -0.01:
                # RSI 变弱且出现阴线
                should_sell = True
                sell_reason = f"短期动量衰竭 (Price < FastMA & RSI < 50)"
                sell_confidence = 0.6

        if should_sell:
            signal = {
                'symbol': symbol,
                'signal_type': 'MA_CROSSOVER_SELL', # 保持兼容性类型
                'action': 'SELL',
                'price': current_price,
                'quantity': self.positions[symbol], # 卖出全部
                'reason': f'A3 Sell: {sell_reason}',
                'confidence': sell_confidence,
                'timestamp': datetime.now()
            }
            
            logger.info(f"🔴 {symbol} A3生成卖出信号: {sell_reason} | 信度: {sell_confidence:.2f}")
            return signal
        
        return None
    
    def analyze(self, symbol: str, data: pd.DataFrame) -> List[Dict]:
        """分析流程"""
        signals = []
        
        if data.empty or len(data) < 20:
            return signals
        
        # 1. 优先检查持仓的风控 (止损/止盈)
        if symbol in self.positions:
            current_price = data['Close'].iloc[-1]
            current_time = datetime.now()

            # 优先检查强制止损止盈
            forced_exit = self.check_forced_exit_conditions(symbol, current_price, current_time, data)
            if forced_exit:
                forced_exit['position_size'] = abs(self.positions[symbol]['size'])
                signals.append(forced_exit)
                return signals # 强制退出直接返回

            exit_signal = self.check_exit_conditions(symbol, current_price)
            if exit_signal:
                exit_signal['position_size'] = abs(self.positions[symbol]['size'])
                signals.append(exit_signal)
                return signals # 触发风控直接返回
            
            # 2. 如果没触发硬性风控，检查策略卖出信号
            sell_signal = self.detect_sell_signal(symbol, data, {})
            if sell_signal:
                signals.append(sell_signal)
        
        # 3. 没持仓才检查买入
        else:
            buy_signal = self.detect_buy_signal(symbol, data, {})
            if buy_signal:
                signals.append(buy_signal)
        
        return signals
    
    def generate_signals(self, symbol: str, data: pd.DataFrame, 
                        indicators_dict: Dict) -> List[Dict]:
        """实现基类接口"""
        return self.analyze(symbol, data)