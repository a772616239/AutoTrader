#!/usr/bin/env python3
"""
均线交叉策略 (A11)
基于短期和长期移动平均线的交叉信号
"""
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
from strategies.base_strategy import BaseStrategy
from strategies.indicators import calculate_moving_average

logger = logging.getLogger(__name__)

class A11MovingAverageCrossoverStrategy(BaseStrategy):
    """均线交叉策略 - A11"""

    def _default_config(self) -> Dict:
        """默认配置 - 从config.py读取"""
        from config import CONFIG
        strategy_key = 'strategy_a11'
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

                # 均线参数
                'fast_ma_period': 9,
                'slow_ma_period': 21,
                'ma_type': 'SMA',  # 'SMA' 或 'EMA'

                # 风险管理
                'stop_loss_pct': 0.02,  # 降低限制
                'take_profit_pct': 0.04,  # 降低限制
                'max_holding_minutes': 120,  # 延长
                'trailing_stop_activation': 0.035,
                'trailing_stop_distance': 0.02,

                # 防重复交易
                'signal_cooldown_minutes': 30,

                # 交易参数
                'min_volume': 10000,
                'min_data_points': 25,  # 需要足够数据计算慢速均线

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
            logger.debug(f"Generated signals for {symbol}: {signals}")
            return signals

        # 检查成交量
        if 'Volume' in data.columns:
            avg_volume = data['Volume'].rolling(window=10).mean().iloc[-1]
            if pd.isna(avg_volume) or avg_volume < self.config['min_volume']:
                logger.debug(f"Generated signals for {symbol}: {signals}")
                return signals

        # 计算移动平均线
        close_prices = data['Close']
        fast_ma = calculate_moving_average(
            close_prices,
            self.config['fast_ma_period'],
            self.config['ma_type']
        )
        slow_ma = calculate_moving_average(
            close_prices,
            self.config['slow_ma_period'],
            self.config['ma_type']
        )

        if fast_ma.empty or slow_ma.empty:
            logger.debug(f"Generated signals for {symbol}: {signals}")
            return signals

        current_price = data['Close'].iloc[-1]
        current_fast = fast_ma.iloc[-1]
        current_slow = slow_ma.iloc[-1]

        # 获取前一个值用于交叉检测
        if len(fast_ma) >= 2 and len(slow_ma) >= 2:
            prev_fast = fast_ma.iloc[-2]
            prev_slow = slow_ma.iloc[-2]
        else:
            logger.debug(f"Generated signals for {symbol}: {signals}")
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
            signal = self._detect_ma_crossover_signal(
                symbol, data, current_price,
                current_fast, current_slow, prev_fast, prev_slow
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

        logger.debug(f"Generated signals for {symbol}: {signals}")
        return signals

    def _detect_ma_crossover_signal(self, symbol: str, data: pd.DataFrame,
                                   current_price: float,
                                   current_fast: float, current_slow: float,
                                   prev_fast: float, prev_slow: float) -> Optional[Dict]:
        """
        检测均线交叉信号
        """

        # 金叉信号 - 快线上穿慢线
        if prev_fast <= prev_slow and current_fast > current_slow:
            # 计算交叉强度（快线相对慢线的偏离程度）
            crossover_strength = (current_fast - current_slow) / current_slow * 100

            confidence = 0.5

            # 交叉强度确认
            if abs(crossover_strength) > 0.5:  # 至少0.5%的偏离
                confidence += min(abs(crossover_strength) / 2.0, 0.3)

            # 价格位置确认（价格在快线上方更强）
            if current_price > current_fast:
                confidence += 0.1

            confidence = min(confidence, 0.9)

            logger.info(f"📈 {symbol} 均线金叉 - 快线: {current_fast:.2f}, 慢线: {current_slow:.2f}, 强度: {crossover_strength:.2f}%, 置信度: {confidence:.2f}")

            return {
                'symbol': symbol,
                'signal_type': 'MA_GOLDEN_CROSS',
                'action': 'BUY',
                'price': current_price,
                'confidence': confidence,
                'reason': f"均线金叉: {current_fast:.2f} > {current_slow:.2f}",
                'indicators': {
                    'fast_ma': current_fast,
                    'slow_ma': current_slow,
                    'crossover_strength': crossover_strength,
                    'cross_type': 'golden',
                    'fast_period': self.config['fast_ma_period'],
                    'slow_period': self.config['slow_ma_period']
                }
            }

        # 死叉信号 - 快线下穿慢线
        elif prev_fast >= prev_slow and current_fast < current_slow:
            # 计算交叉强度
            crossover_strength = (current_slow - current_fast) / current_fast * 100

            confidence = 0.5

            # 交叉强度确认
            if abs(crossover_strength) > 0.5:  # 至少0.5%的偏离
                confidence += min(abs(crossover_strength) / 2.0, 0.3)

            # 价格位置确认（价格在快线下方更强）
            if current_price < current_fast:
                confidence += 0.1

            confidence = min(confidence, 0.9)

            logger.info(f"📉 {symbol} 均线死叉 - 快线: {current_fast:.2f}, 慢线: {current_slow:.2f}, 强度: {crossover_strength:.2f}%, 置信度: {confidence:.2f}")

            return {
                'symbol': symbol,
                'signal_type': 'MA_DEATH_CROSS',
                'action': 'SELL',
                'price': current_price,
                'confidence': confidence,
                'reason': f"均线死叉: {current_fast:.2f} < {current_slow:.2f}",
                'indicators': {
                    'fast_ma': current_fast,
                    'slow_ma': current_slow,
                    'crossover_strength': crossover_strength,
                    'cross_type': 'death',
                    'fast_period': self.config['fast_ma_period'],
                    'slow_period': self.config['slow_ma_period']
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
            logger.warning(f"⚠️ {symbol} A11触发止损: 亏损{price_change_pct*100:.2f}%")
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
            logger.info(f"✅ {symbol} A11触发止盈: 盈利{price_change_pct*100:.2f}%")
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