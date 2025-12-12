#!/usr/bin/env python3
"""
配对交易策略 (A15)
基于协整关系的统计套利策略（简化版）
注意：这是一个概念性实现，实际配对交易需要更复杂的风险管理和对冲逻辑
"""
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
from strategies.base_strategy import BaseStrategy

logger = logging.getLogger(__name__)

class A15PairsTradingStrategy(BaseStrategy):
    """配对交易策略 - A15（简化版）"""

    def _default_config(self) -> Dict:
        """默认配置 - 从config.py读取"""
        from config import CONFIG
        strategy_key = 'strategy_a15'
        if strategy_key in CONFIG:
            return CONFIG[strategy_key]
        else:
            # 降级到硬编码默认值
            return {
                # 资金管理
                'initial_capital': 50000.0,
                'risk_per_trade': 0.02,
                'max_position_size': 0.05,  # 配对交易使用较小仓位
                'per_trade_notional_cap': 500.0,  # 单笔交易美元上限（更严格）
                'max_position_notional': 30000.0,  # 单股总仓位上限（美元，更严格）

                # 配对参数（简化版 - 使用固定配对）
                'pair_symbol': 'SPY',  # 配对基准（实际应动态选择协整配对）
                'lookback_period': 60,  # 价差计算回溯期
                'entry_threshold': 2.0,  # 价差标准差阈值
                'exit_threshold': 0.5,   # 平仓阈值

                # 风险管理
                'stop_loss_pct': 0.05,  # 较宽松的止损
                'take_profit_pct': 0.08,  # 较宽松的止盈
                'max_holding_minutes': 240,  # 较长持有时间

                # 防重复交易
                'signal_cooldown_minutes': 30,

                # 交易参数
                'min_volume': 10000,
                'min_data_points': 70,  # 需要足够数据计算价差

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

        current_price = data['Close'].iloc[-1]

        # 简化版：使用SPY作为基准进行相对价值判断
        # 实际配对交易需要找到协整配对，这里简化为与市场基准的相对强弱
        logger.debug(f"📊 {symbol} 开始配对交易分析")
        try:
            # 尝试获取配对基准数据（这里简化处理）
            pair_price = self._get_pair_price(symbol, data)
            if pair_price is None:
                logger.warning(f"⚠️ {symbol} 无法获取配对基准价格")
                return signals

            # 计算相对价差
            price_ratio = current_price / pair_price
            lookback = min(self.config['lookback_period'], len(data) - 1)

            logger.debug(f"🔗 {symbol} 配对分析 - 当前价格: ${current_price:.2f}, 基准价格: ${pair_price:.2f}, 相对比例: {price_ratio:.4f}")

            if len(data) >= lookback:
                ratios = []
                for i in range(len(data) - lookback, len(data)):
                    # 这里简化计算，实际应使用配对数据
                    ratios.append(data['Close'].iloc[i] / pair_price)

                if ratios:
                    ratio_mean = np.mean(ratios)
                    ratio_std = np.std(ratios)

                    logger.debug(f"📈 {symbol} 历史统计 - 均值: {ratio_mean:.4f}, 标准差: {ratio_std:.4f}")

                    if ratio_std > 0:
                        z_score = (price_ratio - ratio_mean) / ratio_std
                        logger.debug(f"🎯 {symbol} Z-Score计算: {z_score:.2f} (当前比例: {price_ratio:.4f}, 均值: {ratio_mean:.4f}, 标准差: {ratio_std:.4f})")

                        # 生成信号
                        signal = self._detect_pairs_signal(
                            symbol, data, current_price, z_score
                        )
                        if signal:
                            signal_hash = self._generate_signal_hash(signal)
                            if not self._is_signal_cooldown(signal_hash) and signal_hash not in self.executed_signals:
                                # 配对交易使用较小仓位
                                signal['position_size'] = int((self.equity * self.config['max_position_size']) / current_price)
                                signal['position_size'] = max(1, min(signal['position_size'], 50))  # 限制在合理范围内
                                signal['signal_hash'] = signal_hash
                                if signal['position_size'] > 0:
                                    signals.append(signal)
                                    self.executed_signals.add(signal_hash)

        except Exception as e:
            logger.debug(f"配对交易计算失败 {symbol}: {e}")
            return signals

        # 检查现有持仓的退出条件
        if symbol in self.positions and len(data) > 0:
            exit_signal = self.check_exit_conditions(symbol, current_price)
            if exit_signal:
                exit_signal['position_size'] = abs(self.positions[symbol]['size'])
                signals.append(exit_signal)

        # 记录信号统计
        if signals:
            self.signals_generated += len(signals)

        return signals

    def _get_pair_price(self, symbol: str, data: pd.DataFrame) -> Optional[float]:
        """获取配对基准价格（简化版）"""
        # 这里简化使用固定基准，实际应使用协整配对
        # 可以使用SMA作为基准，或者尝试获取SPY数据
        try:
            # 使用长期SMA作为基准
            sma_period = 50
            if len(data) >= sma_period:
                pair_price = data['Close'].rolling(window=sma_period).mean().iloc[-1]
                return pair_price
        except Exception:
            pass
        return None

    def _detect_pairs_signal(self, symbol: str, data: pd.DataFrame,
                           current_price: float, z_score: float) -> Optional[Dict]:
        """
        检测配对交易信号
        """

        entry_threshold = self.config['entry_threshold']

        # 相对低估 - 买入信号（价差过大，做多该股）
        if z_score < -entry_threshold:
            confidence = 0.5 + min(abs(z_score) / 5.0, 0.4)
            confidence = min(confidence, 0.9)

            logger.info(f"📈 {symbol} 配对交易低估 - Z-Score: {z_score:.2f}, 阈值: -{entry_threshold}, 置信度: {confidence:.2f}")

            return {
                'symbol': symbol,
                'signal_type': 'PAIRS_UNDERVALUED',
                'action': 'BUY',
                'price': current_price,
                'confidence': confidence,
                'reason': f"配对低估: Z-Score {z_score:.2f} < -{entry_threshold}",
                'indicators': {
                    'z_score': float(z_score),
                    'entry_threshold': entry_threshold,
                    'pair_symbol': self.config['pair_symbol']
                }
            }

        # 相对高估 - 卖出信号（价差过小，做空该股）
        elif z_score > entry_threshold:
            confidence = 0.5 + min(abs(z_score) / 5.0, 0.4)
            confidence = min(confidence, 0.9)

            logger.info(f"📉 {symbol} 配对交易高估 - Z-Score: {z_score:.2f}, 阈值: {entry_threshold}, 置信度: {confidence:.2f}")

            return {
                'symbol': symbol,
                'signal_type': 'PAIRS_OVERVALUED',
                'action': 'SELL',
                'price': current_price,
                'confidence': confidence,
                'reason': f"配对高估: Z-Score {z_score:.2f} > {entry_threshold}",
                'indicators': {
                    'z_score': float(z_score),
                    'entry_threshold': entry_threshold,
                    'pair_symbol': self.config['pair_symbol']
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
            logger.warning(f"⚠️ {symbol} A15触发止损: 亏损{price_change_pct*100:.2f}%")
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
            logger.info(f"✅ {symbol} A15触发止盈: 盈利{price_change_pct*100:.2f}%")
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