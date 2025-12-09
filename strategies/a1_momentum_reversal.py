#!/usr/bin/env python3
"""
动量反转策略 (原策略A1)
"""
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
from strategies.base_strategy import BaseStrategy

logger = logging.getLogger(__name__)

class A1MomentumReversalStrategy(BaseStrategy):
    """动量反转策略 - 原策略A1"""
    
    def _default_config(self) -> Dict:
        """默认配置"""
        return {
            # 资金管理
            'initial_capital': 40000.0,
            'risk_per_trade': 0.02,
            'max_position_size': 0.1,
            'per_trade_notional_cap': 4000.0,  # 单笔交易美元上限
            'max_position_notional': 60000.0,  # 单股总仓位上限（美元）
            
            # 时间分区
            'morning_session': ('09:30', '10:30'),
            'midday_session': ('10:30', '14:30'),
            'afternoon_session': ('14:30', '15:00'),
            
            # 信号参数
            'rsi_overbought': 72,
            'rsi_oversold': 28,
            'price_deviation_threshold': 2.5,
            'volume_surge_multiplier': 1.5,
            
            # 风险管理
            'stop_loss_atr_multiple': 1.5,
            'take_profit_atr_multiple': 3.0,
            'trailing_stop_activation': 0.02,
            'trailing_stop_distance': 0.015,
            
            # 卖出条件
            'min_profit_pct': 0.01,
            'max_holding_minutes': 120,
            'quick_loss_cutoff': -0.03,
            
            # 防重复交易
            'signal_cooldown_minutes': 5,
            'same_symbol_cooldown': 15,
            
            # 交易参数
            'min_volume': 10000,
            'min_data_points': 30,
            'commission_rate': 0.0005,
            
            # IB交易参数
            'ib_order_type': 'MKT',
            'ib_limit_offset': 0.01,
        }
    
    def analyze_market_regime(self, data: pd.DataFrame) -> str:
        """分析市场状态"""
        if len(data) < 20:
            return "INSUFFICIENT_DATA"
        
        returns = data['Close'].pct_change().dropna()
        volatility = returns.std() * np.sqrt(252)
        price_change = (data['Close'].iloc[-1] / data['Close'].iloc[0] - 1) * 100
        
        if volatility > 0.25:
            return "HIGH_VOLATILITY"
        elif abs(price_change) > 3:
            return "TRENDING"
        else:
            return "RANGING"
    
    def detect_morning_momentum(self, symbol: str, data: pd.DataFrame, 
                               indicators: Dict) -> Optional[Dict]:
        """
        检测早盘动量信号
        """
        if len(data) < 10:
            return None
        
        if symbol in self.positions:
            return None
        
        latest = data.iloc[-1]
        
        # RSI条件
        rsi = indicators.get('RSI', 50)
        if not (50 <= rsi <= 67):
            return None
        
        # 价格偏离均线
        ma_key = 'MA_20'
        if ma_key not in indicators or indicators[ma_key] is None:
            return None
        
        price_deviation = (latest['Close'] - indicators[ma_key]) / indicators[ma_key] * 100
        if abs(price_deviation) < 0.3:
            return None
        
        # 成交量确认
        if 'Volume' in data.columns and len(data) >= 5:
            recent_volume = data['Volume'].iloc[-5:].mean()
            if latest['Volume'] < recent_volume * 1.05:
                return None
        
        # 计算信号强度
        confidence = 0.5
        if price_deviation > 0:
            confidence += min(price_deviation / 5.0, 0.3)
        if rsi > 55:
            confidence += 0.1
        
        logger.info(f"✅ {symbol} 早盘动量信号，置信度: {confidence:.2f}")
        
        signal = {
            'symbol': symbol,
            'signal_type': 'MORNING_MOMENTUM',
            'action': 'BUY' if price_deviation > 0 else 'SELL',
            'price': latest['Close'],
            'confidence': min(confidence, 0.9),
            'reason': f"早盘动量: 价格偏离MA20 {price_deviation:.1f}%, RSI {rsi:.1f}",
            'indicators': {
                'rsi': rsi,
                'price_deviation': price_deviation,
                'ma20': indicators[ma_key]
            }
        }
        
        return signal
    
    def detect_afternoon_reversal(self, symbol: str, data: pd.DataFrame,
                                 indicators: Dict) -> Optional[Dict]:
        """
        检测午盘/尾盘反转信号
        """
        if symbol in self.positions:
            return None
        
        latest = data.iloc[-1]
        
        # RSI极端条件
        rsi = indicators.get('RSI', 50)
        is_overbought = rsi > self.config['rsi_overbought']
        is_oversold = rsi < self.config['rsi_oversold']
        
        if not (is_overbought or is_oversold):
            return None
        
        # 价格位置
        lookback = min(20, len(data))
        recent_high = data['High'].iloc[-lookback:].max()
        recent_low = data['Low'].iloc[-lookback:].min()
        
        current_price = latest['Close']
        near_high = current_price > recent_high * 0.98
        near_low = current_price < recent_low * 1.02
        
        if not ((is_overbought and near_high) or (is_oversold and near_low)):
            return None
        
        # 成交量确认
        volume_ok = True
        if 'Volume' in data.columns and len(data) >= 10:
            avg_volume = data['Volume'].iloc[-10:].mean()
            volume_ratio = latest['Volume'] / avg_volume
            volume_ok = 0.5 < volume_ratio < 2.5
        
        if not volume_ok:
            return None
        
        # 确定交易方向
        if is_overbought and near_high:
            action = 'SELL'
            reason = f"午盘反转: RSI超买 {rsi:.1f}, 接近近期高点"
            confidence = min(0.4 + (rsi - 70) / 30, 0.8)
        else:
            action = 'BUY'
            reason = f"午盘反转: RSI超卖 {rsi:.1f}, 接近近期低点"
            confidence = min(0.4 + (30 - rsi) / 30, 0.8)
        
        logger.info(f"✅ {symbol} 午盘反转信号，置信度: {confidence:.2f}")
        
        signal = {
            'symbol': symbol,
            'signal_type': 'AFTERNOON_REVERSAL',
            'action': action,
            'price': current_price,
            'confidence': confidence,
            'reason': reason,
            'indicators': {
                'rsi': rsi,
                'recent_high': recent_high,
                'recent_low': recent_low,
                'price_position': 'high' if near_high else 'low'
            }
        }
        
        return signal
    
    def generate_signals(self, symbol: str, data: pd.DataFrame, 
                        indicators: Dict) -> List[Dict]:
        """生成交易信号"""
        signals = []
        
        # 基本数据检查
        if data.empty or len(data) < self.config['min_data_points']:
            return signals
        
        # 检查成交量
        if 'Volume' in data.columns:
            avg_volume = data['Volume'].rolling(window=10).mean().iloc[-1]
            if avg_volume < self.config['min_volume']:
                return signals
        
        # 获取ATR
        atr = indicators.get('ATR', data['Close'].std() * 0.01)
        
        # 检查是否有持仓需要卖出
        if symbol in self.positions and len(data) > 0:
            current_price = data['Close'].iloc[-1]
            exit_signal = self.check_exit_conditions(symbol, current_price)
            if exit_signal:
                exit_signal['position_size'] = abs(self.positions[symbol]['size'])
                signals.append(exit_signal)
        
        # 只在没有持仓时生成买入信号
        if symbol not in self.positions:
            # 早盘动量信号
            morning_signal = self.detect_morning_momentum(symbol, data, indicators)
            if morning_signal:
                signal_hash = self._generate_signal_hash(morning_signal)
                if not self._is_signal_cooldown(signal_hash) and signal_hash not in self.executed_signals:
                    morning_signal['position_size'] = self.calculate_position_size(morning_signal, atr)
                    morning_signal['signal_hash'] = signal_hash
                    if morning_signal['position_size'] > 0:
                        signals.append(morning_signal)
                        self.executed_signals.add(signal_hash)
            
            # 午盘/尾盘反转信号
            reversal_signal = self.detect_afternoon_reversal(symbol, data, indicators)
            if reversal_signal:
                signal_hash = self._generate_signal_hash(reversal_signal)
                if not self._is_signal_cooldown(signal_hash) and signal_hash not in self.executed_signals:
                    reversal_signal['position_size'] = self.calculate_position_size(reversal_signal, atr)
                    reversal_signal['signal_hash'] = signal_hash
                    if reversal_signal['position_size'] > 0:
                        signals.append(reversal_signal)
                        self.executed_signals.add(signal_hash)
        
        # 记录信号统计
        if signals:
            self.signals_generated += len(signals)
        
        return signals
    
    def check_exit_conditions(self, symbol: str, current_price: float, 
                             current_time: datetime = None) -> Optional[Dict]:
        """
        检查卖出条件 - 重写基类方法
        """
        if symbol not in self.positions:
            return None
        
        if current_time is None:
            current_time = datetime.now()
        
        position = self.positions[symbol]
        avg_cost = position['avg_cost']
        position_size = position['size']
        
        entry_time = position.get('entry_time', current_time - timedelta(minutes=60))
        
        # 计算盈亏
        if position_size > 0:
            price_change_pct = (current_price - avg_cost) / avg_cost
            unrealized_pnl = position_size * (current_price - avg_cost)
        else:
            price_change_pct = (avg_cost - current_price) / avg_cost
            unrealized_pnl = abs(position_size) * (avg_cost - current_price)
        
        # 检查止损条件（优先使用百分比止损，如果没有则使用ATR倍数估算）
        stop_loss_pct = -abs(self.config.get('stop_loss_pct', self.config.get('stop_loss_atr_multiple', 1.5) * 0.02))
        if price_change_pct <= stop_loss_pct:
            logger.warning(f"⚠️ {symbol} A1触发止损: 亏损{price_change_pct*100:.2f}% (成本: ${avg_cost:.2f}, 当前: ${current_price:.2f})")
            return {
                'symbol': symbol,
                'signal_type': 'STOP_LOSS',
                'action': 'SELL' if position_size > 0 else 'BUY',
                'price': current_price,
                'reason': f"触发止损: 亏损{price_change_pct*100:.2f}% (阈值: {abs(stop_loss_pct)*100:.1f}%)",
                'position_size': abs(position_size),
                'profit_pct': price_change_pct * 100,
                'confidence': 1.0
            }
        
        # 检查止盈条件（优先使用百分比止盈，如果没有则使用ATR倍数估算）
        # 注意：基于ATR的止盈需要实际ATR值，这里使用百分比作为后备
        take_profit_pct = abs(self.config.get('take_profit_pct', None))
        if take_profit_pct is None:
            # 如果没有配置百分比止盈，使用ATR倍数估算（约4-6%）
            take_profit_pct = self.config.get('take_profit_atr_multiple', 3.0) * 0.02
        if price_change_pct >= take_profit_pct:
            logger.info(f"✅ {symbol} A1触发止盈: 盈利{price_change_pct*100:.2f}% (成本: ${avg_cost:.2f}, 当前: ${current_price:.2f})")
            return {
                'symbol': symbol,
                'signal_type': 'TAKE_PROFIT',
                'action': 'SELL' if position_size > 0 else 'BUY',
                'price': current_price,
                'reason': f"触发止盈: 盈利{price_change_pct*100:.2f}% (阈值: {take_profit_pct*100:.1f}%)",
                'position_size': abs(position_size),
                'profit_pct': price_change_pct * 100,
                'confidence': 1.0
            }
        
        # 快速止损
        if price_change_pct <= self.config['quick_loss_cutoff']:
            return {
                'symbol': symbol,
                'signal_type': 'QUICK_LOSS',
                'action': 'SELL' if position_size > 0 else 'BUY',
                'price': current_price,
                'reason': f"快速止损: 亏损{price_change_pct*100:.1f}%",
                'position_size': abs(position_size),
                'profit_pct': price_change_pct * 100
            }
        
        # 最大持仓时间
        holding_minutes = (current_time - entry_time).total_seconds() / 60
        if holding_minutes > self.config['max_holding_minutes']:
            return {
                'symbol': symbol,
                'signal_type': 'MAX_HOLDING',
                'action': 'SELL' if position_size > 0 else 'BUY',
                'price': current_price,
                'reason': f"超时平仓: 持仓{holding_minutes:.0f}分钟",
                'position_size': abs(position_size),
                'profit_pct': price_change_pct * 100
            }
        
        # 尾盘强制平仓（使用配置的时间，如果没有则使用默认15:45）
        force_close_time_str = self.config.get('force_close_time', '15:45')
        try:
            force_close_time = datetime.strptime(force_close_time_str, "%H:%M").time()
        except:
            force_close_time = datetime.strptime("15:45", "%H:%M").time()
        
        current_time_of_day = current_time.time()
        if current_time_of_day >= force_close_time and abs(position_size) > 0:
            logger.info(f"🕐 {symbol} A1尾盘强制平仓: 当前时间 {current_time_of_day.strftime('%H:%M')} >= {force_close_time_str}")
            return {
                'symbol': symbol,
                'signal_type': 'MARKET_CLOSE',
                'action': 'SELL' if position_size > 0 else 'BUY',
                'price': current_price,
                'reason': f"尾盘强制平仓: {current_time_of_day.strftime('%H:%M')} >= {force_close_time_str}",
                'position_size': abs(position_size),
                'profit_pct': price_change_pct * 100,
                'confidence': 1.0
            }
        
        return None