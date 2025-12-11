#!/usr/bin/env python3
"""
RSI震荡策略 (A8)
基于相对强弱指数检测超买超卖信号
"""
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
from strategies.base_strategy import BaseStrategy
from strategies.indicators import calculate_rsi

logger = logging.getLogger(__name__)

class A8RSIOscillatorStrategy(BaseStrategy):
    """RSI震荡策略 - A8"""

    def _default_config(self) -> Dict:
        """默认配置 - 从config.py读取"""
        from config import CONFIG
        strategy_key = 'strategy_a8'
        if strategy_key in CONFIG:
            return CONFIG[strategy_key]
        else:
            # 降级到硬编码默认值
            return {
                # 资金管理
                'initial_capital': 40000.0,
                'risk_per_trade': 0.02,
                'max_position_size': 0.1,
                'per_trade_notional_cap': 4000.0,  # 单笔交易美元上限
                'max_position_notional': 60000.0,  # 单股总仓位上限（美元）

                # RSI参数
                'rsi_period': 14,
                'rsi_oversold': 30,
                'rsi_overbought': 70,
                'rsi_signal_threshold': 5,  # RSI距离阈值的距离

                # 风险管理
                'stop_loss_pct': 0.015,  # 降低限制
                'take_profit_pct': 0.025,  # 降低限制
                'max_holding_minutes': 90,  # 延长
                'trailing_stop_activation': 0.02,
                'trailing_stop_distance': 0.015,

                # 防重复交易
                'signal_cooldown_minutes': 10,

                # 交易参数
                'min_volume': 10000,
                'min_data_points': 20,

                # IB交易参数
                'ib_order_type': 'MKT',
                'ib_limit_offset': 0.01,
            }

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
            if pd.isna(avg_volume) or avg_volume < self.config['min_volume']:
                return signals

        # 计算RSI
        close_prices = data['Close']
        rsi_series = calculate_rsi(close_prices, self.config['rsi_period'])
        current_rsi = rsi_series.iloc[-1] if not rsi_series.empty else None

        if current_rsi is None or np.isnan(current_rsi):
            return signals

        current_price = data['Close'].iloc[-1]
        atr = indicators.get('ATR', abs(current_price * 0.02))  # 默认2%的ATR

        # 检查现有持仓的退出条件
        if symbol in self.positions and len(data) > 0:
            exit_signal = self.check_exit_conditions(symbol, current_price)
            if exit_signal:
                exit_signal['position_size'] = abs(self.positions[symbol]['size'])
                signals.append(exit_signal)

        # 只在没有持仓时生成买入信号
        if symbol not in self.positions:
            signal = self._detect_rsi_signal(symbol, data, current_rsi, current_price)
            if signal:
                signal_hash = self._generate_signal_hash(signal)
                if not self._is_signal_cooldown(signal_hash) and signal_hash not in self.executed_signals:
                    signal['position_size'] = self.calculate_position_size(signal, atr)
                    signal['signal_hash'] = signal_hash
                    if signal['position_size'] > 0:
                        signals.append(signal)
                        self.executed_signals.add(signal_hash)

        # 记录信号统计
        if signals:
            self.signals_generated += len(signals)

        return signals

    def _detect_rsi_signal(self, symbol: str, data: pd.DataFrame,
                          current_rsi: float, current_price: float) -> Optional[Dict]:
        """
        检测RSI信号
        """
        rsi_oversold = self.config['rsi_oversold']
        rsi_overbought = self.config['rsi_overbought']

        # 计算RSI距离阈值的程度，用于确定信号强度
        oversold_distance = rsi_oversold - current_rsi
        overbought_distance = current_rsi - rsi_overbought

        # 超卖信号 - 买入
        if current_rsi <= rsi_oversold:
            confidence = min(0.4 + (oversold_distance / rsi_oversold) * 0.4, 0.8)

            # 检查RSI是否还在下降（更强的超卖信号）
            if len(data) >= 3:
                prev_rsi = calculate_rsi(data['Close'], self.config['rsi_period']).iloc[-2]
                if not np.isnan(prev_rsi) and current_rsi < prev_rsi:
                    confidence += 0.1  # RSI仍在下降，增加置信度

            logger.info(f"📈 {symbol} RSI超卖信号 - RSI: {current_rsi:.1f}, 置信度: {confidence:.2f}")

            return {
                'symbol': symbol,
                'signal_type': 'RSI_OVERSOLD',
                'action': 'BUY',
                'price': current_price,
                'confidence': confidence,
                'reason': f"RSI超卖: {current_rsi:.1f} <= {rsi_oversold}",
                'indicators': {
                    'rsi': current_rsi,
                    'rsi_threshold': rsi_oversold,
                    'distance': oversold_distance
                }
            }

        # 超买信号 - 卖出
        elif current_rsi >= rsi_overbought:
            confidence = min(0.4 + (overbought_distance / (100 - rsi_overbought)) * 0.4, 0.8)

            # 检查RSI是否还在上升（更强的超买信号）
            if len(data) >= 3:
                prev_rsi = calculate_rsi(data['Close'], self.config['rsi_period']).iloc[-2]
                if not np.isnan(prev_rsi) and current_rsi > prev_rsi:
                    confidence += 0.1  # RSI仍在上升，增加置信度

            logger.info(f"📉 {symbol} RSI超买信号 - RSI: {current_rsi:.1f}, 置信度: {confidence:.2f}")

            return {
                'symbol': symbol,
                'signal_type': 'RSI_OVERBOUGHT',
                'action': 'SELL',
                'price': current_price,
                'confidence': confidence,
                'reason': f"RSI超买: {current_rsi:.1f} >= {rsi_overbought}",
                'indicators': {
                    'rsi': current_rsi,
                    'rsi_threshold': rsi_overbought,
                    'distance': overbought_distance
                }
            }

        return None

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
        else:
            price_change_pct = (avg_cost - current_price) / avg_cost

        # 止损检查
        stop_loss_pct = -abs(self.config['stop_loss_pct'])
        if price_change_pct <= stop_loss_pct:
            logger.warning(f"⚠️ {symbol} A8触发止损: 亏损{price_change_pct*100:.2f}%")
            return {
                'symbol': symbol,
                'signal_type': 'STOP_LOSS',
                'action': 'SELL' if position_size > 0 else 'BUY',
                'price': current_price,
                'reason': f"触发止损: 亏损{price_change_pct*100:.2f}%",
                'position_size': abs(position_size),
                'profit_pct': price_change_pct * 100,
                'confidence': 1.0
            }

        # 止盈检查
        take_profit_pct = abs(self.config['take_profit_pct'])
        if price_change_pct >= take_profit_pct:
            logger.info(f"✅ {symbol} A8触发止盈: 盈利{price_change_pct*100:.2f}%")
            return {
                'symbol': symbol,
                'signal_type': 'TAKE_PROFIT',
                'action': 'SELL' if position_size > 0 else 'BUY',
                'price': current_price,
                'reason': f"触发止盈: 盈利{price_change_pct*100:.2f}%",
                'position_size': abs(position_size),
                'profit_pct': price_change_pct * 100,
                'confidence': 1.0
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

        # RSI反转退出条件
        if hasattr(self, '_check_rsi_reversal'):
            reversal_signal = self._check_rsi_reversal(symbol, position_size, current_price)
            if reversal_signal:
                return reversal_signal

        return None

    def _check_rsi_reversal(self, symbol: str, position_size: int, current_price: float) -> Optional[Dict]:
        """
        检查RSI反转条件 - 用于在适当的时候退出
        """
        # 这里可以添加RSI中性区域反转逻辑
        # 例如，长仓时RSI>50可以考虑减仓，空仓时RSI<50可以考虑减仓
        # 暂时简化处理
        return None