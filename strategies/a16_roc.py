#!/usr/bin/env python3
"""
ROC策略 (A16)
基于价格变化率(Rate of Change)的动量策略
"""
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
from strategies.base_strategy import BaseStrategy
from strategies.indicators import calculate_roc

logger = logging.getLogger(__name__)

class A16ROCStrategy(BaseStrategy):
    """ROC动量策略 - A16"""

    def _default_config(self) -> Dict:
        """默认配置 - 从config.py读取"""
        from config import CONFIG
        strategy_key = 'strategy_a16'
        if strategy_key in CONFIG:
            return CONFIG[strategy_key]
        else:
            # 降级到硬编码默认值
            return {
                # 资金管理
                'initial_capital': 50000.0,
                'risk_per_trade': 0.02,
                'max_position_size': 0.1,
                'per_trade_notional_cap': 700.0,  # 单笔交易美元上限
                'max_position_notional': 60000.0,  # 单股总仓位上限（美元）

                # ROC参数（放宽限制）
                'roc_period': 12,
                'bullish_threshold': 5,  # ROC > 5% 为强势上涨
                'bearish_threshold': -5,  # ROC < -5% 为强势下跌

                # 风险管理
                'stop_loss_pct': 0.03,  # 止损百分比
                'take_profit_pct': 0.06,  # 止盈百分比
                'max_holding_minutes': 120,  # 最大持有时间

                # 防重复交易
                'signal_cooldown_minutes': 15,

                # 交易参数（放宽限制）
                'min_volume': 2000,
                'min_data_points': 20,  # 需要足够数据计算ROC

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

        # 检查成交量 - 盘前时段跳过成交量检查
        from config import CONFIG
        skip_volume_check = CONFIG.get('trading', {}).get('skip_volume_check', False)
        if not skip_volume_check and not self._is_pre_market_hours() and 'Volume' in data.columns:
            avg_volume = data['Volume'].rolling(window=10).mean().iloc[-1]
            if pd.isna(avg_volume) or avg_volume < self.config['min_volume']:
                current_volume = data['Volume'].iloc[-1] if not pd.isna(data['Volume'].iloc[-1]) else 0
                logger.info(f"❌ {symbol} 成交量不足，跳过信号生成 - 当前成交量: {current_volume:.0f}, 平均成交量: {avg_volume:.0f}, 需要: {self.config['min_volume']}")
                return signals

        # 计算ROC
        logger.info(f"📊 {symbol} 开始计算ROC指标")
        close_prices = data['Close']
        roc = calculate_roc(close_prices, self.config['roc_period'])

        if roc.empty:
            logger.warning(f"⚠️ {symbol} ROC计算失败，返回空序列")
            logger.info(f"❌ {symbol} 指标计算失败，跳过信号生成")
            return signals

        current_price = data['Close'].iloc[-1]
        current_roc = roc.iloc[-1]

        if np.isnan(current_roc):
            logger.warning(f"⚠️ {symbol} 当前ROC值为NaN，跳过信号生成")
            logger.info(f"❌ {symbol} 指标值无效，跳过信号生成")
            return signals

        # 获取前一个值用于交叉检测
        if len(roc) >= 2:
            prev_roc = roc.iloc[-2]
        else:
            logger.warning(f"⚠️ {symbol} 数据点不足，无法进行交叉检测")
            logger.info(f"❌ {symbol} 数据不足以进行分析，跳过信号生成")
            return signals

        logger.info(f"📈 {symbol} ROC计算完成 - 当前ROC: {current_roc:.2f}%, 前值: {prev_roc:.2f}%, 周期: {self.config['roc_period']}, 当前价格: {current_price:.2f}")

        atr = indicators.get('ATR', abs(current_price * 0.02))  # 默认2%的ATR

        # 检查现有持仓的退出条件
        if symbol in self.positions and len(data) > 0:
            exit_signal = self.check_exit_conditions(symbol, current_price)
            if exit_signal:
                exit_signal['position_size'] = abs(self.positions[symbol]['size'])
                signals.append(exit_signal)

        # 只在没有持仓时生成买入信号
        if symbol not in self.positions:
            signal = self._detect_roc_signal(
                symbol, data, current_price, current_roc, prev_roc
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

        logger.info(f"📊 {symbol} A16信号生成完成 - 生成信号数量: {len(signals)}")
        return signals

    def _detect_roc_signal(self, symbol: str, data: pd.DataFrame,
                          current_price: float, current_roc: float, prev_roc: float) -> Optional[Dict]:
        """
        检测ROC信号
        """

        bullish_threshold = self.config['bullish_threshold']
        bearish_threshold = self.config['bearish_threshold']

        # 强势上涨信号 - ROC从下方突破阈值
        if current_roc > bullish_threshold:
            # 计算突破强度
            roc_strength = current_roc - bullish_threshold
            confidence = 0.5 + min(roc_strength / 20.0, 0.4)  # 最大增加0.4

            # 检查是否从阈值下方突破（更强的信号）
            if prev_roc <= bullish_threshold and current_roc > bullish_threshold:
                confidence += 0.1

            confidence = min(confidence, 0.9)

            logger.info(f"📈 {symbol} ROC强势上涨 - ROC: {current_roc:.2f}%, 阈值: {bullish_threshold}%, 置信度: {confidence:.2f}")

            return {
                'symbol': symbol,
                'signal_type': 'ROC_BULLISH',
                'action': 'BUY',
                'price': current_price,
                'confidence': confidence,
                'reason': f"ROC强势上涨: {current_roc:.2f}% > {bullish_threshold}%",
                'indicators': {
                    'roc': float(current_roc),
                    'roc_period': self.config['roc_period'],
                    'bullish_threshold': bullish_threshold,
                    'bearish_threshold': bearish_threshold
                }
            }

        # 强势下跌信号 - ROC跌破阈值
        elif current_roc < bearish_threshold:
            # 计算突破强度
            roc_strength = bearish_threshold - current_roc
            confidence = 0.5 + min(roc_strength / 20.0, 0.4)  # 最大增加0.4

            # 检查是否从阈值上方跌破（更强的信号）
            if prev_roc >= bearish_threshold and current_roc < bearish_threshold:
                confidence += 0.1

            confidence = min(confidence, 0.9)

            logger.info(f"📉 {symbol} ROC强势下跌 - ROC: {current_roc:.2f}%, 阈值: {bearish_threshold}%, 置信度: {confidence:.2f}")

            return {
                'symbol': symbol,
                'signal_type': 'ROC_BEARISH',
                'action': 'SELL',
                'price': current_price,
                'confidence': confidence,
                'reason': f"ROC强势下跌: {current_roc:.2f}% < {bearish_threshold}%",
                'indicators': {
                    'roc': float(current_roc),
                    'roc_period': self.config['roc_period'],
                    'bullish_threshold': bullish_threshold,
                    'bearish_threshold': bearish_threshold
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
            logger.warning(f"⚠️ {symbol} A16触发止损: 亏损{price_change_pct*100:.2f}%")
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
            logger.info(f"✅ {symbol} A16触发止盈: 盈利{price_change_pct*100:.2f}%")
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