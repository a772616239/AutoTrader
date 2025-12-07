#!/usr/bin/env python3
"""
双均线 + 成交量突破策略 (策略A3)
核心思想: 结合快速均线交叉和成交量突破识别趋势
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
    """双均线成交量突破策略"""
    
    def _default_config(self) -> Dict:
        """默认配置"""
        return {
            # 资金管理
            'initial_capital': 40000.0,
            'risk_per_trade': 0.02,
            'max_position_size': 0.1,
            'per_trade_notional_cap': 4000.0,  # 单笔交易美元上限
            'max_position_notional': 60000.0,  # 单股总仓位上限（美元）
            
            # 双均线参数
            'fast_ma_period': 9,  # 快速均线周期
            'slow_ma_period': 21,  # 慢速均线周期
            'ema_or_sma': 'EMA',  # 使用EMA还是SMA
            
            # 成交量参数
            'volume_sma_period': 20,  # 成交量均线周期
            'volume_surge_ratio': 1.5,  # 成交量突破倍数
            'min_volume_threshold': 500000,  # 最小成交量要求
            
            # 入场条件
            'entry_confirmation_bars': 2,  # 入场确认所需的K线数
            'price_above_slow_ma': True,  # 价格需要在慢速均线上方
            'use_atr_stop_loss': True,  # 使用ATR作为止损
            'atr_stop_multiple': 1.5,  # ATR止损倍数
            
            # 出场条件
            'take_profit_pct': 0.03,  # 止盈百分比
            'take_profit_atr_multiple': 2.0,  # 基于ATR的止盈倍数
            'max_holding_minutes': 60,  # 最大持有时间
            'trailing_stop_pct': 0.02,  # 追踪止损百分比
            
            # 时间过滤
            'trading_start_time': '09:45',  # 交易开始时间
            'trading_end_time': '15:30',  # 交易结束时间
            'avoid_open_hour': True,  # 避开开盘第一小时
            'avoid_close_hour': True,  # 避开收盘最后一小时
            
            # 风险管理
            'max_daily_loss_pct': 0.05,  # 日最大亏损百分比
            'max_consecutive_losses': 3,  # 最大连续亏损次数
            'min_profit_pct': 0.01,  # 最小止盈百分比
            
            # 防重复交易
            'signal_cooldown_minutes': 3,
            
            # IB交易参数
            'ib_order_type': 'MKT',
            'ib_limit_offset': 0.01,
        }
    
    def get_strategy_name(self) -> str:
        """获取策略名称"""
        return "A3 Dual MA + Volume Breakout"
    
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
        
        logger.info(
            f"    📊 均线计算完成: 快速MA={fast_ma.iloc[-1]:.2f} 慢速MA={slow_ma.iloc[-1]:.2f}"
        )
        
        return fast_ma, slow_ma
    
    def detect_volume_breakout(self, data: pd.DataFrame) -> Tuple[bool, float]:
        """
        检测成交量突破
        
        返回:
            (是否成交量突破, 成交量倍数)
        """
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
        
        # 判断是否成交量突破
        is_breakout = volume_ratio >= self.config['volume_surge_ratio']
        return is_breakout, volume_ratio
    
    def detect_ma_crossover(self, data: pd.DataFrame, 
                           fast_ma: pd.Series, slow_ma: pd.Series) -> Tuple[str, float]:
        """
        检测均线交叉信号
        
        返回:
            (信号类型: 'BULLISH'/'BEARISH'/'NONE', 置信度)
        """
        if len(data) < 3:
            logger.info(f"    ❌ 数据不足检测均线交叉: {len(data)} < 3")
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
        ma_distance = abs(current_fast - current_slow) / current_slow
        confidence = min(ma_distance * 10, 1.0)  # 归一化到0-1之间
        
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
        
        # 解析交易时间
        start_time = datetime.strptime(self.config['trading_start_time'], '%H:%M').time()
        end_time = datetime.strptime(self.config['trading_end_time'], '%H:%M').time()
        
        # 检查是否在交易时间内
        if not (start_time <= current_dt_time <= end_time):
            return False
        
        # 避开开盘第一小时
        if self.config['avoid_open_hour']:
            market_open = datetime.strptime('09:30', '%H:%M').time()
            open_end = datetime.strptime('10:30', '%H:%M').time()
            if market_open <= current_dt_time <= open_end:
                return False
        
        # 避开收盘最后一小时
        if self.config['avoid_close_hour']:
            close_start = datetime.strptime('14:30', '%H:%M').time()
            market_close = datetime.strptime('16:00', '%H:%M').time()
            if close_start <= current_dt_time <= market_close:
                return False
        
        return True
    
    def detect_buy_signal(self, symbol: str, data: pd.DataFrame, 
                         indicators: Dict) -> Optional[Dict]:
        """检测买入信号"""
        # 数据长度检查
        min_required = max(self.config['fast_ma_period'], self.config['slow_ma_period']) + 5
        if len(data) < min_required:
            return None
        
        # 检查是否已持仓
        if symbol in self.positions:
            return None
        
        # 时间过滤
        # if not self.is_trading_hours():
        #     return None
        
        # 计算均线
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
        current_volume = data['Volume'].iloc[-1]
        if current_volume < self.config['min_volume_threshold']:
            return None
        
        # 计算综合置信度
        volume_confidence = min(volume_ratio / self.config['volume_surge_ratio'], 1.0)
        combined_confidence = (ma_confidence + volume_confidence) / 2
        
        logger.info(
            f"🟢 {symbol} A3买入信号 ✓"
            f" | 均线交叉置信度: {ma_confidence:.1%}"
            f" | 成交量倍数: {volume_ratio:.2f}x"
            f" | 综合置信度: {combined_confidence:.1%}"
            f" | 价格: {current_price:.2f} | 快速MA: {fast_ma.iloc[-1]:.2f} | 慢速MA: {current_slow_ma:.2f}"
        )
        
        signal = {
            'symbol': symbol,
            'signal_type': 'MA_CROSSOVER_BUY',
            'action': 'BUY',
            'price': current_price,
            'reason': f'Dual MA Bullish Crossover (MA Conf: {ma_confidence:.2%}, Vol: {volume_ratio:.2f}x)',
            'confidence': combined_confidence,
            'fast_ma': fast_ma.iloc[-1],
            'slow_ma': current_slow_ma,
            'volume_ratio': volume_ratio,
        }
        
        # 计算仓位大小
        atr = data['High'].iloc[-20:].mean() - data['Low'].iloc[-20:].mean()
        signal['position_size'] = self.calculate_position_size(signal, atr)
        
        if signal['position_size'] <= 0:
            return None
        
        # 生成信号哈希用于防重复
        signal_hash = self._generate_signal_hash(signal)
        signal['signal_hash'] = signal_hash
        
        return signal
    
    def detect_sell_signal(self, symbol: str, data: pd.DataFrame, 
                          indicators: Dict) -> Optional[Dict]:
        """检测卖出信号"""
        logger.info(f"检测 {symbol} 卖出信号:")
        if len(data) < max(self.config['fast_ma_period'], self.config['slow_ma_period']) + 5:
            logger.info(f"  ❌ {symbol} 数据不足，无法检测卖出信号")
            return None
        
        if symbol not in self.positions:
            return None
        
        # 计算均线
        fast_ma, slow_ma = self.calculate_moving_averages(data)
        
        # 检查均线交叉（死叉）
        crossover_signal, ma_confidence = self.detect_ma_crossover(data, fast_ma, slow_ma)
        if crossover_signal == 'BEARISH':
            logger.info(f"🔴 {symbol} A3卖出信号 | 均线死叉 | 置信度: {ma_confidence:.1%}")
            signal = {
                'symbol': symbol,
                'signal_type': 'MA_CROSSOVER_SELL',
                'action': 'SELL',
                'reason': 'Dual MA Bearish Crossover',
                'confidence': ma_confidence,
            }
            return signal
        
        logger.info(f"  ❌ {symbol} 无卖出信号")
        return None
    
    def analyze(self, symbol: str, data: pd.DataFrame) -> List[Dict]:
        """分析股票数据并生成交易信号"""
        signals = []
        
        # 基本检查
        if data.empty or len(data) < self.config['fast_ma_period'] + 5:
            return signals
        
        # 检查是否持有仓位，如果有，检查止损止盈
        if symbol in self.positions:
            current_price = data['Close'].iloc[-1]
            exit_signal = self.check_exit_conditions(symbol, current_price)
            if exit_signal:
                signals.append(exit_signal)

        # 检查买入信号
        buy_signal = self.detect_buy_signal(symbol, data, {})
        if buy_signal:
            signals.append(buy_signal)
        
        # 检查卖出信号
        sell_signal = self.detect_sell_signal(symbol, data, {})
        if sell_signal:
            signals.append(sell_signal)
        
        return signals
    
    def generate_signals(self, symbol: str, data: pd.DataFrame, 
                        indicators: Dict) -> List[Dict]:
        """
        生成交易信号 - 实现基类接口
        
        参数:
            symbol: 股票代码
            data: 历史数据
            indicators: 技术指标字典
        
        返回:
            交易信号列表
        """
        return self.analyze(symbol, data)
