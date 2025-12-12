#!/usr/bin/env python3
"""
Pivot Points策略 (A33)
基于Pivot Points指标的支撑阻力突破信号
"""
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
from strategies.base_strategy import BaseStrategy
from strategies.indicators import calculate_pivot_points

logger = logging.getLogger(__name__)

class A33PivotPointsStrategy(BaseStrategy):
    """Pivot Points策略 - A33"""

    def _default_config(self) -> Dict:
        """默认配置 - 从config.py读取"""
        from config import CONFIG
        strategy_key = 'strategy_a33'
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

                # Pivot Points参数
                'breakout_threshold': 0.001,  # 突破百分比阈值（0.1%）
                'use_r2_s2': False,  # 是否使用R2/S2作为额外信号

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
                'min_data_points': 25,  # 需要足够数据计算Pivot Points

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
        if not self._is_pre_market_hours() and 'Volume' in data.columns:
            avg_volume = data['Volume'].rolling(window=10).mean().iloc[-1]
            if pd.isna(avg_volume) or avg_volume < self.config['min_volume']:
                return signals

        # 计算Pivot Points
        high_prices = data['High']
        low_prices = data['Low']
        close_prices = data['Close']

        pivot, r1, s1, r2, s2 = calculate_pivot_points(high_prices, low_prices, close_prices)

        if pivot.empty or r1.empty or s1.empty:
            return signals

        current_price = data['Close'].iloc[-1]
        current_pivot = pivot.iloc[-1]
        current_r1 = r1.iloc[-1]
        current_s1 = s1.iloc[-1]

        # 获取前一个值用于突破检测
        if len(pivot) >= 2:
            prev_price = data['Close'].iloc[-2]
            prev_r1 = r1.iloc[-2]
            prev_s1 = s1.iloc[-2]
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
            signal = self._detect_pivot_signal(
                symbol, data, current_price, prev_price,
                current_pivot, current_r1, current_s1,
                prev_r1, prev_s1
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
            logger.info(f"📊 {symbol} A33无信号 - 价格: {current_price:.2f}, 支点: {current_pivot:.2f}, R1: {current_r1:.2f}, S1: {current_s1:.2f}")

        return signals

    def _detect_pivot_signal(self, symbol: str, data: pd.DataFrame,
                           current_price: float, prev_price: float,
                           current_pivot: float, current_r1: float, current_s1: float,
                           prev_r1: float, prev_s1: float) -> Optional[Dict]:
        """
        检测Pivot Points突破信号
        """

        # R1阻力突破信号 - 买入
        if prev_price <= prev_r1 and current_price > current_r1:
            # 计算突破强度
            breakout_strength = (current_price - current_r1) / current_r1
            if breakout_strength < self.config['breakout_threshold']:
                return None  # 突破不够强

            confidence = 0.6 + min(breakout_strength * 100, 0.3)  # 突破强度每增加1%增加0.3置信度
            confidence = min(confidence, 0.9)

            logger.info(f"🚀 {symbol} Pivot R1突破 - 价格: {current_price:.2f}, R1: {current_r1:.2f}, 强度: {breakout_strength:.4f}, 置信度: {confidence:.2f}")

            return {
                'symbol': symbol,
                'signal_type': 'PIVOT_R1_BREAKOUT',
                'action': 'BUY',
                'price': current_price,
                'confidence': confidence,
                'reason': f"Pivot R1突破: {current_price:.2f} > {current_r1:.2f}",
                'indicators': {
                    'pivot': current_pivot,
                    'r1': current_r1,
                    's1': current_s1,
                    'breakout_strength': breakout_strength,
                    'breakout_level': 'r1'
                }
            }

        # S1支撑跌破信号 - 卖出
        elif prev_price >= prev_s1 and current_price < current_s1:
            # 计算突破强度
            breakout_strength = (current_s1 - current_price) / current_s1
            if breakout_strength < self.config['breakout_threshold']:
                return None  # 突破不够强

            confidence = 0.6 + min(breakout_strength * 100, 0.3)  # 突破强度每增加1%增加0.3置信度
            confidence = min(confidence, 0.9)

            logger.info(f"🔻 {symbol} Pivot S1跌破 - 价格: {current_price:.2f}, S1: {current_s1:.2f}, 强度: {breakout_strength:.4f}, 置信度: {confidence:.2f}")

            return {
                'symbol': symbol,
                'signal_type': 'PIVOT_S1_BREAKOUT',
                'action': 'SELL',
                'price': current_price,
                'confidence': confidence,
                'reason': f"Pivot S1跌破: {current_price:.2f} < {current_s1:.2f}",
                'indicators': {
                    'pivot': current_pivot,
                    'r1': current_r1,
                    's1': current_s1,
                    'breakout_strength': breakout_strength,
                    'breakout_level': 's1'
                }
            }

        # 可选：R2/S2突破信号
        if self.config.get('use_r2_s2', False) and len(data) >= 2:
            current_r2 = data.get('r2', pd.Series()).iloc[-1] if 'r2' in data.columns else None
            current_s2 = data.get('s2', pd.Series()).iloc[-1] if 's2' in data.columns else None

            if current_r2 is not None and prev_price <= prev_r1 and current_price > current_r2:
                # R2突破 - 更强的买入信号
                breakout_strength = (current_price - current_r2) / current_r2
                if breakout_strength >= self.config['breakout_threshold']:
                    confidence = 0.7 + min(breakout_strength * 100, 0.2)
                    confidence = min(confidence, 0.95)

                    logger.info(f"🚀🚀 {symbol} Pivot R2突破 - 价格: {current_price:.2f}, R2: {current_r2:.2f}, 强度: {breakout_strength:.4f}, 置信度: {confidence:.2f}")

                    return {
                        'symbol': symbol,
                        'signal_type': 'PIVOT_R2_BREAKOUT',
                        'action': 'BUY',
                        'price': current_price,
                        'confidence': confidence,
                        'reason': f"Pivot R2突破: {current_price:.2f} > {current_r2:.2f}",
                        'indicators': {
                            'pivot': current_pivot,
                            'r1': current_r1,
                            's1': current_s1,
                            'r2': current_r2,
                            'breakout_strength': breakout_strength,
                            'breakout_level': 'r2'
                        }
                    }

            elif current_s2 is not None and prev_price >= prev_s1 and current_price < current_s2:
                # S2跌破 - 更强的卖出信号
                breakout_strength = (current_s2 - current_price) / current_s2
                if breakout_strength >= self.config['breakout_threshold']:
                    confidence = 0.7 + min(breakout_strength * 100, 0.2)
                    confidence = min(confidence, 0.95)

                    logger.info(f"🔻🔻 {symbol} Pivot S2跌破 - 价格: {current_price:.2f}, S2: {current_s2:.2f}, 强度: {breakout_strength:.4f}, 置信度: {confidence:.2f}")

                    return {
                        'symbol': symbol,
                        'signal_type': 'PIVOT_S2_BREAKOUT',
                        'action': 'SELL',
                        'price': current_price,
                        'confidence': confidence,
                        'reason': f"Pivot S2跌破: {current_price:.2f} < {current_s2:.2f}",
                        'indicators': {
                            'pivot': current_pivot,
                            'r1': current_r1,
                            's1': current_s1,
                            's2': current_s2,
                            'breakout_strength': breakout_strength,
                            'breakout_level': 's2'
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
            logger.warning(f"⚠️ {symbol} A33触发止损: 亏损{price_change_pct*100:.2f}%")
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
            logger.info(f"✅ {symbol} A33触发止盈: 盈利{price_change_pct*100:.2f}%")
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