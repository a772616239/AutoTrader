#!/usr/bin/env python3
"""
Keltner Channels策略 (A32)
基于Keltner Channels指标的价格突破和趋势跟踪信号
"""
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
from strategies.base_strategy import BaseStrategy
from strategies.indicators import calculate_keltner_channels

logger = logging.getLogger(__name__)

class A32KeltnerChannelsStrategy(BaseStrategy):
    """Keltner Channels策略 - A32"""

    def _default_config(self) -> Dict:
        """默认配置 - 从config.py读取"""
        from config import CONFIG
        strategy_key = 'strategy_a32'
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

                # Keltner Channels参数
                'atr_period': 14,
                'multiplier': 2.0,
                'breakout_threshold': 0.1,  # 突破百分比阈值

                # 风险管理
                'stop_loss_pct': 0.02,  # 降低限制
                'take_profit_pct': 0.04,  # 降低限制
                'max_holding_minutes': 120,  # 延长
                'trailing_stop_activation': 0.04,
                'trailing_stop_distance': 0.025,

                # 防重复交易
                'signal_cooldown_minutes': 20,

                # 交易参数
                'min_volume': 10000,
                'min_data_points': 25,  # 需要足够数据计算Keltner Channels

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

        # 检查成交量 - 盘前时段跳过成交量检查
        from config import CONFIG
        skip_volume_check = CONFIG.get('trading', {}).get('skip_volume_check', False)
        if not skip_volume_check and not self._is_pre_market_hours() and 'Volume' in data.columns:
            avg_volume = data['Volume'].rolling(window=10).mean().iloc[-1]
            if pd.isna(avg_volume) or avg_volume < self.config['min_volume']:
                return signals

        # 计算Keltner Channels
        high_prices = data['High']
        low_prices = data['Low']
        close_prices = data['Close']

        upper_channel, middle_channel, lower_channel = calculate_keltner_channels(
            high_prices, low_prices, close_prices,
            self.config['atr_period'], self.config['multiplier']
        )

        if upper_channel.empty or middle_channel.empty or lower_channel.empty:
            return signals

        current_price = data['Close'].iloc[-1]
        current_upper = upper_channel.iloc[-1]
        current_middle = middle_channel.iloc[-1]
        current_lower = lower_channel.iloc[-1]

        # 获取前一个值用于突破检测
        if len(upper_channel) >= 2:
            prev_price = data['Close'].iloc[-2]
            prev_upper = upper_channel.iloc[-2]
            prev_lower = lower_channel.iloc[-2]
        else:
            return signals

        atr = indicators.get('ATR', abs(current_price * 0.02))  # 默认2%的ATR

        # 检查现有持仓的退出条件
        if symbol in self.positions and len(data) > 0:
            exit_signal = self.check_exit_conditions(symbol, current_price)
            if exit_signal:
                exit_signal['position_size'] = abs(self.positions[symbol]['size'])
                signals.append(exit_signal)

        # 只在没有持仓时生成买入信号
        if symbol not in self.positions:
            signal = self._detect_keltner_signal(
                symbol, data, current_price, prev_price,
                current_upper, current_lower, prev_upper, prev_lower,
                current_middle
            )
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
        else:
            logger.info(f"📊 {symbol} A32无信号 - 价格: {current_price:.2f}, 上轨: {current_upper:.2f}, 中轨: {current_middle:.2f}, 下轨: {current_lower:.2f}")

        return signals

    def _detect_keltner_signal(self, symbol: str, data: pd.DataFrame,
                              current_price: float, prev_price: float,
                              current_upper: float, current_lower: float,
                              prev_upper: float, prev_lower: float,
                              current_middle: float) -> Optional[Dict]:
        """
        检测Keltner Channels突破信号
        """

        # 上轨突破信号 - 买入
        if prev_price <= prev_upper and current_price > current_upper:
            # 计算突破强度，降低阈值便于测试
            breakout_strength = (current_price - current_middle) / (current_upper - current_middle)
            if breakout_strength < self.config['breakout_threshold']:
                return None  # 突破不够强

            confidence = 0.5 + min(breakout_strength * 0.3, 0.4)
            confidence = min(confidence, 0.9)

            logger.info(f"🚀 {symbol} Keltner上轨突破 - 价格: {current_price:.2f}, 上轨: {current_upper:.2f}, 强度: {breakout_strength:.2f}, 置信度: {confidence:.2f}")

            return {
                'symbol': symbol,
                'signal_type': 'KC_UPPER_BREAKOUT',
                'action': 'BUY',
                'price': current_price,
                'confidence': confidence,
                'reason': f"Keltner上轨突破: {current_price:.2f} > {current_upper:.2f}",
                'indicators': {
                    'upper_channel': current_upper,
                    'middle_channel': current_middle,
                    'lower_channel': current_lower,
                    'breakout_strength': breakout_strength,
                    'breakout_type': 'upper'
                }
            }

        # 下轨跌破信号 - 卖出
        elif prev_price >= prev_lower and current_price < current_lower:
            # 计算突破强度，降低阈值便于测试
            breakout_strength = (current_middle - current_price) / (current_middle - current_lower)
            if breakout_strength < self.config['breakout_threshold']:
                return None  # 突破不够强

            confidence = 0.5 + min(breakout_strength * 0.3, 0.4)
            confidence = min(confidence, 0.9)

            logger.info(f"🔻 {symbol} Keltner下轨跌破 - 价格: {current_price:.2f}, 下轨: {current_lower:.2f}, 强度: {breakout_strength:.2f}, 置信度: {confidence:.2f}")

            return {
                'symbol': symbol,
                'signal_type': 'KC_LOWER_BREAKOUT',
                'action': 'SELL',
                'price': current_price,
                'confidence': confidence,
                'reason': f"Keltner下轨跌破: {current_price:.2f} < {current_lower:.2f}",
                'indicators': {
                    'upper_channel': current_upper,
                    'middle_channel': current_middle,
                    'lower_channel': current_lower,
                    'breakout_strength': breakout_strength,
                    'breakout_type': 'lower'
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
            logger.warning(f"⚠️ {symbol} A32触发止损: 亏损{price_change_pct*100:.2f}%")
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
            logger.info(f"✅ {symbol} A32触发止盈: 盈利{price_change_pct*100:.2f}%")
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

        return None