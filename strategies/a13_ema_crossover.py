#!/usr/bin/env python3
"""
EMA交叉策略 (A13)
基于指数移动平均线交叉的多资产组合策略
"""
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
from strategies.base_strategy import BaseStrategy
from strategies.indicators import calculate_moving_average

logger = logging.getLogger(__name__)

class A13EMACrossoverStrategy(BaseStrategy):
    """EMA交叉策略 - A13"""

    def _default_config(self) -> Dict:
        """默认配置 - 从config.py读取"""
        from config import CONFIG
        strategy_key = 'strategy_a13'
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

                # EMA参数
                'short_ema_period': 20,
                'long_ema_period': 100,
                'position_size_fraction': 0.33,  # 每资产仓位比例

                # 风险管理
                'stop_loss_pct': 0.05,  # 较宽松的止损
                'take_profit_pct': 0.10,  # 较宽松的止盈
                'max_holding_minutes': 1440,  # 24小时

                # 防重复交易
                'signal_cooldown_minutes': 60,

                # 交易参数
                'min_volume': 10000,
                'min_data_points': 110,  # 需要足够数据计算长周期EMA

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
            logger.info(f"❌ {symbol} 数据不足，跳过信号生成 - 数据点: {len(data)}, 需要: {self.config['min_data_points']}")
            return signals

        # 检查成交量
        from config import CONFIG
        skip_volume_check = CONFIG.get('trading', {}).get('skip_volume_check', False)
        if not skip_volume_check and 'Volume' in data.columns:
            avg_volume = data['Volume'].rolling(window=10).mean().iloc[-1]
            if pd.isna(avg_volume) or avg_volume < self.config['min_volume']:
                current_volume = data['Volume'].iloc[-1] if not pd.isna(data['Volume'].iloc[-1]) else 0
                logger.info(f"❌ {symbol} 成交量不足，跳过信号生成 - 当前成交量: {current_volume:.0f}, 平均成交量: {avg_volume:.0f}, 需要: {self.config['min_volume']}")
                return signals

        # 计算EMA
        close_prices = data['Close']
        short_ema = calculate_moving_average(close_prices, self.config['short_ema_period'], 'EMA')
        long_ema = calculate_moving_average(close_prices, self.config['long_ema_period'], 'EMA')

        if short_ema.empty or long_ema.empty:
            logger.warning(f"⚠️ {symbol} EMA计算失败，返回空序列")
            logger.info(f"❌ {symbol} 指标计算失败，跳过信号生成")
            return signals

        current_price = data['Close'].iloc[-1]
        current_short_ema = short_ema.iloc[-1]
        current_long_ema = long_ema.iloc[-1]

        # 获取前一个值用于交叉检测
        if len(short_ema) >= 2 and len(long_ema) >= 2:
            prev_short_ema = short_ema.iloc[-2]
            prev_long_ema = long_ema.iloc[-2]
        else:
            logger.info(f"❌ {symbol} 数据不足以进行分析，跳过信号生成")
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
            signal = self._detect_ema_crossover_signal(
                symbol, data, current_price,
                current_short_ema, current_long_ema, prev_short_ema, prev_long_ema
            )
            if signal:
                signal_hash = self._generate_signal_hash(signal)
                if not self._is_signal_cooldown(signal_hash) and signal_hash not in self.executed_signals:
                    # 对于组合策略，使用固定比例而不是基于ATR的仓位计算
                    signal['position_size'] = int((self.equity * self.config['position_size_fraction']) / current_price)
                    signal['position_size'] = max(1, min(signal['position_size'], 1000))  # 限制在合理范围内
                    signal['signal_hash'] = signal_hash
                    if signal['position_size'] > 0:
                        signals.append(signal)
                        self.executed_signals.add(signal_hash)

        # 记录信号统计
        if signals:
            self.signals_generated += len(signals)

        logger.info(f"📊 {symbol} A13信号生成完成 - 生成信号数量: {len(signals)}")
        return signals

    def _detect_ema_crossover_signal(self, symbol: str, data: pd.DataFrame,
                                    current_price: float,
                                    current_short_ema: float, current_long_ema: float,
                                    prev_short_ema: float, prev_long_ema: float) -> Optional[Dict]:
        """
        检测EMA交叉信号
        """

        # 金叉信号 - 短期EMA上穿长期EMA
        if prev_short_ema <= prev_long_ema and current_short_ema > current_long_ema:
            logger.info(f"🔬 {symbol} 检测到EMA金叉条件 - 前值: {prev_short_ema:.2f} <= {prev_long_ema:.2f}, 当前: {current_short_ema:.2f} > {current_long_ema:.2f}")
            confidence = 0.6

            # 确认信号强度：交叉幅度越大越强
            crossover_strength = (current_short_ema - current_long_ema) / current_long_ema * 100
            logger.info(f"💪 {symbol} 交叉强度计算: {crossover_strength:.2f}%")
            if abs(crossover_strength) > 1.0:  # 至少1%的偏离
                strength_bonus = min(abs(crossover_strength) / 5.0, 0.3)
                confidence += strength_bonus
                logger.info(f"🚀 {symbol} 强度奖励: +{strength_bonus:.3f}")

            # 价格位置确认：价格在短期EMA上方更强
            position_bonus = 0.0
            if current_price > current_short_ema:
                position_bonus = 0.1
                confidence += position_bonus
                logger.info(f"📈 {symbol} 价格位置奖励: +{position_bonus} (价格在EMA上方)")

            confidence = min(confidence, 0.9)
            logger.info(f"🎯 {symbol} 最终买入置信度: {confidence:.3f}")

            logger.info(f"📈 {symbol} EMA金叉 - 短期EMA: {current_short_ema:.2f}, 长期EMA: {current_long_ema:.2f}, 强度: {crossover_strength:.2f}%, 置信度: {confidence:.2f}")

            return {
                'symbol': symbol,
                'signal_type': 'EMA_GOLDEN_CROSS',
                'action': 'BUY',
                'price': current_price,
                'confidence': confidence,
                'reason': f"EMA金叉: {current_short_ema:.2f} > {current_long_ema:.2f}",
                'indicators': {
                    'short_ema': current_short_ema,
                    'long_ema': current_long_ema,
                    'crossover_strength': crossover_strength,
                    'cross_type': 'golden',
                    'short_period': self.config['short_ema_period'],
                    'long_period': self.config['long_ema_period']
                }
            }

        # 死叉信号 - 短期EMA下穿长期EMA
        elif prev_short_ema >= prev_long_ema and current_short_ema < current_long_ema:
            confidence = 0.6

            # 确认信号强度
            crossover_strength = (current_long_ema - current_short_ema) / current_short_ema * 100
            if abs(crossover_strength) > 1.0:  # 至少1%的偏离
                confidence += min(abs(crossover_strength) / 5.0, 0.3)

            # 价格位置确认：价格在短期EMA下方更强
            if current_price < current_short_ema:
                confidence += 0.1

            confidence = min(confidence, 0.9)

            logger.info(f"📉 {symbol} EMA死叉 - 短期EMA: {current_short_ema:.2f}, 长期EMA: {current_long_ema:.2f}, 强度: {crossover_strength:.2f}%, 置信度: {confidence:.2f}")

            return {
                'symbol': symbol,
                'signal_type': 'EMA_DEATH_CROSS',
                'action': 'SELL',
                'price': current_price,
                'confidence': confidence,
                'reason': f"EMA死叉: {current_short_ema:.2f} < {current_long_ema:.2f}",
                'indicators': {
                    'short_ema': current_short_ema,
                    'long_ema': current_long_ema,
                    'crossover_strength': crossover_strength,
                    'cross_type': 'death',
                    'short_period': self.config['short_ema_period'],
                    'long_period': self.config['long_ema_period']
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
            logger.warning(f"⚠️ {symbol} A13触发止损: 亏损{price_change_pct*100:.2f}%")
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
            logger.info(f"✅ {symbol} A13触发止盈: 盈利{price_change_pct*100:.2f}%")
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