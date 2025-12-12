#!/usr/bin/env python3
"""
CCI策略 (A17)
基于顺势指标(Commodity Channel Index)的超买超卖策略
"""
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
from strategies.base_strategy import BaseStrategy
from strategies.indicators import calculate_cci

logger = logging.getLogger(__name__)

class A17CCIStrategy(BaseStrategy):
    """CCI顺势指标策略 - A17"""

    def _default_config(self) -> Dict:
        """默认配置 - 从config.py读取"""
        from config import CONFIG
        strategy_key = 'strategy_a17'
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

                # CCI参数
                'cci_period': 20,
                'overbought_level': 100,  # CCI > 100 为超买
                'oversold_level': -100,   # CCI < -100 为超卖

                # 风险管理
                'stop_loss_pct': 0.03,  # 止损百分比
                'take_profit_pct': 0.06,  # 止盈百分比
                'max_holding_minutes': 120,  # 最大持有时间

                # 防重复交易
                'signal_cooldown_minutes': 15,

                # 交易参数
                'min_volume': 10000,
                'min_data_points': 25,  # 需要足够数据计算CCI

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

        # 计算CCI
        logger.info(f"📊 {symbol} 开始计算CCI指标")
        high_prices = data['High']
        low_prices = data['Low']
        close_prices = data['Close']
        cci = calculate_cci(high_prices, low_prices, close_prices, self.config['cci_period'])

        if cci.empty:
            logger.warning(f"⚠️ {symbol} CCI计算失败，返回空序列")
            logger.info(f"❌ {symbol} 指标计算失败，跳过信号生成")
            return signals

        current_price = data['Close'].iloc[-1]
        current_cci = cci.iloc[-1]

        if np.isnan(current_cci):
            logger.warning(f"⚠️ {symbol} 当前CCI值为NaN，跳过信号生成")
            logger.info(f"❌ {symbol} 指标值无效，跳过信号生成")
            return signals

        # 获取前一个值用于交叉检测
        if len(cci) >= 2:
            prev_cci = cci.iloc[-2]
        else:
            logger.warning(f"⚠️ {symbol} 数据点不足，无法进行交叉检测")
            logger.info(f"❌ {symbol} 数据不足以进行分析，跳过信号生成")
            return signals

        logger.info(f"📈 {symbol} CCI计算完成 - 当前CCI: {current_cci:.2f}, 前值: {prev_cci:.2f}, 周期: {self.config['cci_period']}, 当前价格: {current_price:.2f}")

        atr = indicators.get('ATR', abs(current_price * 0.02))  # 默认2%的ATR

        # 检查现有持仓的退出条件
        if symbol in self.positions and len(data) > 0:
            exit_signal = self.check_exit_conditions(symbol, current_price)
            if exit_signal:
                exit_signal['position_size'] = abs(self.positions[symbol]['size'])
                signals.append(exit_signal)

        # 只在没有持仓时生成买入信号
        if symbol not in self.positions:
            signal = self._detect_cci_signal(
                symbol, data, current_price, current_cci, prev_cci
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

        logger.info(f"📊 {symbol} A17信号生成完成 - 生成信号数量: {len(signals)}")
        return signals

    def _detect_cci_signal(self, symbol: str, data: pd.DataFrame,
                          current_price: float, current_cci: float, prev_cci: float) -> Optional[Dict]:
        """
        检测CCI信号
        """

        overbought_level = self.config['overbought_level']
        oversold_level = self.config['oversold_level']

        # 超卖信号 - CCI从超卖区域向上突破
        if current_cci < oversold_level:
            # 计算超卖程度
            oversold_strength = oversold_level - current_cci
            confidence = 0.5 + min(oversold_strength / 50.0, 0.4)  # 最大增加0.4

            # 检查是否从超卖区域向上突破（更强的信号）
            if prev_cci <= oversold_level and current_cci > prev_cci:
                confidence += 0.1

            confidence = min(confidence, 0.9)

            logger.info(f"📈 {symbol} CCI超卖反弹 - CCI: {current_cci:.2f}, 超卖线: {oversold_level}, 置信度: {confidence:.2f}")

            return {
                'symbol': symbol,
                'signal_type': 'CCI_OVERSOLD',
                'action': 'BUY',
                'price': current_price,
                'confidence': confidence,
                'reason': f"CCI超卖: {current_cci:.2f} < {oversold_level}",
                'indicators': {
                    'cci': float(current_cci),
                    'cci_period': self.config['cci_period'],
                    'overbought_level': overbought_level,
                    'oversold_level': oversold_level
                }
            }

        # 超买信号 - CCI跌破超买线
        elif current_cci > overbought_level:
            # 计算超买程度
            overbought_strength = current_cci - overbought_level
            confidence = 0.5 + min(overbought_strength / 50.0, 0.4)  # 最大增加0.4

            # 检查是否从超买区域向下突破（更强的信号）
            if prev_cci >= overbought_level and current_cci < prev_cci:
                confidence += 0.1

            confidence = min(confidence, 0.9)

            logger.info(f"📉 {symbol} CCI超买回落 - CCI: {current_cci:.2f}, 超买线: {overbought_level}, 置信度: {confidence:.2f}")

            return {
                'symbol': symbol,
                'signal_type': 'CCI_OVERBOUGHT',
                'action': 'SELL',
                'price': current_price,
                'confidence': confidence,
                'reason': f"CCI超买: {current_cci:.2f} > {overbought_level}",
                'indicators': {
                    'cci': float(current_cci),
                    'cci_period': self.config['cci_period'],
                    'overbought_level': overbought_level,
                    'oversold_level': oversold_level
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
            logger.warning(f"⚠️ {symbol} A17触发止损: 亏损{price_change_pct*100:.2f}%")
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
            logger.info(f"✅ {symbol} A17触发止盈: 盈利{price_change_pct*100:.2f}%")
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