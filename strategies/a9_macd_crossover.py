#!/usr/bin/env python3
"""
MACD交叉策略 (A9)
基于MACD指标的线条交叉和直方图信号
"""
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
from strategies.base_strategy import BaseStrategy
from strategies.indicators import calculate_macd

logger = logging.getLogger(__name__)

class A9MACDCrossoverStrategy(BaseStrategy):
    """MACD交叉策略 - A9"""

    def _default_config(self) -> Dict:
        """默认配置 - 从config.py读取"""
        from config import CONFIG
        strategy_key = 'strategy_a9'
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

                # MACD参数
                'macd_fast': 12,
                'macd_slow': 26,
                'macd_signal': 9,
                'histogram_threshold': 0.1,  # 直方图阈值

                # 风险管理
                'stop_loss_pct': 0.02,  # 降低限制
                'take_profit_pct': 0.04,  # 降低限制
                'max_holding_minutes': 180,  # 延长
                'trailing_stop_activation': 0.03,
                'trailing_stop_distance': 0.02,

                # 防重复交易
                'signal_cooldown_minutes': 15,

                # 交易参数
                'min_volume': 10000,
                'min_data_points': 35,  # 需要足够数据计算MACD

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
        from config import CONFIG
        skip_volume_check = CONFIG.get('trading', {}).get('skip_volume_check', False)
        if not skip_volume_check and 'Volume' in data.columns:
            avg_volume = data['Volume'].rolling(window=10).mean().iloc[-1]
            if pd.isna(avg_volume) or avg_volume < self.config['min_volume']:
                return signals

        # 计算MACD
        close_prices = data['Close']
        macd_line, signal_line, histogram = calculate_macd(
            close_prices,
            self.config['macd_fast'],
            self.config['macd_slow'],
            self.config['macd_signal']
        )

        if macd_line.empty or signal_line.empty or histogram.empty:
            return signals

        current_price = data['Close'].iloc[-1]
        current_macd = macd_line.iloc[-1]
        current_signal = signal_line.iloc[-1]
        current_histogram = histogram.iloc[-1]

        # 获取前一个值用于交叉检测
        if len(macd_line) >= 2 and len(signal_line) >= 2:
            prev_macd = macd_line.iloc[-2]
            prev_signal = signal_line.iloc[-2]
            prev_histogram = histogram.iloc[-2]
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
            signal = self._detect_macd_signal(
                symbol, data, current_macd, current_signal, current_histogram,
                prev_macd, prev_signal, prev_histogram, current_price
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

        return signals

    def _detect_macd_signal(self, symbol: str, data: pd.DataFrame,
                           current_macd: float, current_signal: float, current_histogram: float,
                           prev_macd: float, prev_signal: float, prev_histogram: float,
                           current_price: float) -> Optional[Dict]:
        """
        检测MACD交叉信号
        """

        # 金叉信号 - MACD线上穿信号线
        if prev_macd <= prev_signal and current_macd > current_signal:
            confidence = 0.5

            # 直方图确认：直方图应该从负转正或增加
            if current_histogram > self.config['histogram_threshold']:
                confidence += 0.2
            if prev_histogram < 0 and current_histogram > 0:
                confidence += 0.1  # 从负转正更强

            # MACD值大小确认
            macd_diff = current_macd - current_signal
            if macd_diff > abs(prev_macd - prev_signal) * 1.2:
                confidence += 0.1

            confidence = min(confidence, 0.9)

            logger.info(f"📈 {symbol} MACD金叉信号 - MACD: {current_macd:.3f}, Signal: {current_signal:.3f}, 置信度: {confidence:.2f}")

            return {
                'symbol': symbol,
                'signal_type': 'MACD_GOLDEN_CROSS',
                'action': 'BUY',
                'price': current_price,
                'confidence': confidence,
                'reason': f"MACD金叉: {current_macd:.3f} > {current_signal:.3f}",
                'indicators': {
                    'macd': current_macd,
                    'signal': current_signal,
                    'histogram': current_histogram,
                    'cross_type': 'golden'
                }
            }

        # 死叉信号 - MACD线下穿信号线
        elif prev_macd >= prev_signal and current_macd < current_signal:
            confidence = 0.5

            # 直方图确认：直方图应该从正转负或减少
            if current_histogram < -self.config['histogram_threshold']:
                confidence += 0.2
            if prev_histogram > 0 and current_histogram < 0:
                confidence += 0.1  # 从正转负更强

            # MACD值大小确认
            macd_diff = current_macd - current_signal
            if abs(macd_diff) > abs(prev_macd - prev_signal) * 1.2:
                confidence += 0.1

            confidence = min(confidence, 0.9)

            logger.info(f"📉 {symbol} MACD死叉信号 - MACD: {current_macd:.3f}, Signal: {current_signal:.3f}, 置信度: {confidence:.2f}")

            return {
                'symbol': symbol,
                'signal_type': 'MACD_DEATH_CROSS',
                'action': 'SELL',
                'price': current_price,
                'confidence': confidence,
                'reason': f"MACD死叉: {current_macd:.3f} < {current_signal:.3f}",
                'indicators': {
                    'macd': current_macd,
                    'signal': current_signal,
                    'histogram': current_histogram,
                    'cross_type': 'death'
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
            logger.warning(f"⚠️ {symbol} A9触发止损: 亏损{price_change_pct*100:.2f}%")
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
            logger.info(f"✅ {symbol} A9触发止盈: 盈利{price_change_pct*100:.2f}%")
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