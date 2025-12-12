#!/usr/bin/env python3
"""
RSI趋势线策略 (A14)
基于RSI和长期趋势的筛选策略，转换为实时交易策略
"""
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
from strategies.base_strategy import BaseStrategy
from strategies.indicators import calculate_rsi, calculate_moving_average

logger = logging.getLogger(__name__)

class A14RSITrendlineStrategy(BaseStrategy):
    """RSI趋势线策略 - A14"""

    def _default_config(self) -> Dict:
        """默认配置 - 从config.py读取"""
        from config import CONFIG
        strategy_key = 'strategy_a14'
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
                'rsi_oversold_threshold': 33,  # 超卖阈值
                'rsi_lookback_days': 2,  # RSI回溯天数

                # 趋势参数
                'trend_ma_period': 200,  # 长期趋势均线
                'trend_ma_type': 'SMA',  # 均线类型

                # 风险管理
                'stop_loss_pct': 0.03,  # 适中止损
                'take_profit_pct': 0.06,  # 适中止盈
                'max_holding_minutes': 480,  # 8小时

                # 防重复交易
                'signal_cooldown_minutes': 30,

                # 交易参数
                'min_volume': 10000,
                'min_data_points': 220,  # 需要足够数据计算200日均线

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
        if 'Volume' in data.columns:
            avg_volume = data['Volume'].rolling(window=10).mean().iloc[-1]
            if pd.isna(avg_volume) or avg_volume < self.config['min_volume']:
                current_volume = data['Volume'].iloc[-1] if not pd.isna(data['Volume'].iloc[-1]) else 0
                logger.info(f"❌ {symbol} 成交量不足，跳过信号生成 - 当前成交量: {current_volume:.0f}, 平均成交量: {avg_volume:.0f}, 需要: {self.config['min_volume']}")
                return signals

        # 计算指标
        logger.info(f"📊 {symbol} 开始计算RSI和趋势指标")
        close_prices = data['Close']
        rsi = calculate_rsi(close_prices, self.config['rsi_period'])
        trend_ma = calculate_moving_average(close_prices, self.config['trend_ma_period'], self.config['trend_ma_type'])

        if rsi.empty or trend_ma.empty:
            logger.warning(f"⚠️ {symbol} 指标计算失败，返回空序列")
            logger.info(f"❌ {symbol} 指标计算失败，跳过信号生成")
            return signals

        current_price = data['Close'].iloc[-1]
        current_rsi = rsi.iloc[-1]
        current_trend_ma = trend_ma.iloc[-1]

        # 计算最近N日的RSI平均值
        lookback_period = min(self.config['rsi_lookback_days'], len(rsi))
        recent_rsi_avg = rsi.iloc[-lookback_period:].mean()

        logger.info(f"📈 {symbol} 指标计算完成 - RSI({self.config['rsi_period']}): {current_rsi:.2f}, RSI均值({lookback_period}日): {recent_rsi_avg:.2f}, 趋势MA({self.config['trend_ma_period']}): {current_trend_ma:.2f}, 当前价格: {current_price:.2f}")

        atr = indicators.get('ATR', abs(current_price * 0.02))  # 默认2%的ATR

        # 检查现有持仓的退出条件
        if symbol in self.positions and len(data) > 0:
            exit_signal = self.check_exit_conditions(symbol, current_price)
            if exit_signal:
                exit_signal['position_size'] = abs(self.positions[symbol]['size'])
                signals.append(exit_signal)

        # 只在没有持仓时生成买入信号
        if symbol not in self.positions:
            signal = self._detect_rsi_trendline_signal(
                symbol, data, current_price, current_rsi, recent_rsi_avg, current_trend_ma
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

        logger.info(f"📊 {symbol} A14信号生成完成 - 生成信号数量: {len(signals)}")
        return signals

    def _detect_rsi_trendline_signal(self, symbol: str, data: pd.DataFrame,
                                    current_price: float, current_rsi: float,
                                    recent_rsi_avg: float, current_trend_ma: float) -> Optional[Dict]:
        """
        检测RSI趋势线信号
        基于原始筛选逻辑：价格在长期均线上方 + RSI超卖
        """

        # 趋势确认：价格在长期均线上方
        if current_price <= current_trend_ma:
            return None

        # RSI超卖确认：最近N日RSI平均值低于阈值
        rsi_threshold = self.config['rsi_oversold_threshold']
        if recent_rsi_avg >= rsi_threshold:
            return None

        # 计算信号强度
        trend_strength = (current_price - current_trend_ma) / current_trend_ma * 100  # 价格偏离均线的百分比
        rsi_oversold_strength = rsi_threshold - recent_rsi_avg  # RSI超卖程度

        confidence = 0.5
        confidence += min(trend_strength / 10.0, 0.2)  # 趋势强度贡献
        confidence += min(rsi_oversold_strength / 10.0, 0.3)  # RSI超卖贡献

        # 确保价格在均线上方有一定距离
        if trend_strength < 1.0:  # 至少1%的偏离
            confidence -= 0.1

        confidence = min(max(confidence, 0.3), 0.9)

        logger.info(f"📈 {symbol} RSI趋势线买入 - 价格: {current_price:.2f}, 均线: {current_trend_ma:.2f}, RSI均值: {recent_rsi_avg:.1f}, 置信度: {confidence:.2f}")

        return {
            'symbol': symbol,
            'signal_type': 'RSI_TRENDLINE_BUY',
            'action': 'BUY',
            'price': current_price,
            'confidence': confidence,
            'reason': f"RSI趋势线: 价格>{current_trend_ma:.2f}, RSI均值{recent_rsi_avg:.1f}<{rsi_threshold}",
            'indicators': {
                'rsi': float(current_rsi),
                'rsi_avg': float(recent_rsi_avg),
                'trend_ma': float(current_trend_ma),
                'trend_strength': float(trend_strength),
                'rsi_threshold': rsi_threshold,
                'lookback_days': self.config['rsi_lookback_days']
            }
        }

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
            logger.warning(f"⚠️ {symbol} A14触发止损: 亏损{price_change_pct*100:.2f}%")
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
            logger.info(f"✅ {symbol} A14触发止盈: 盈利{price_change_pct*100:.2f}%")
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