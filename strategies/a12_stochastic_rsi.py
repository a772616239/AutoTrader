#!/usr/bin/env python3
"""
Stochastic RSI策略 (A12)
基于随机强弱指数的超买超卖信号
"""
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
from strategies.base_strategy import BaseStrategy
from strategies.indicators import calculate_stochastic_rsi

logger = logging.getLogger(__name__)

class A12StochasticRSIStrategy(BaseStrategy):
    """Stochastic RSI策略 - A12"""

    def _default_config(self) -> Dict:
        """默认配置 - 从config.py读取"""
        from config import CONFIG
        strategy_key = 'strategy_a12'
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

                # Stochastic RSI参数
                'rsi_period': 14,
                'stoch_period': 14,
                'oversold_level': 0.2,  # 超卖阈值
                'overbought_level': 0.8,  # 超买阈值

                # 风险管理
                'stop_loss_pct': 0.02,  # 降低限制
                'take_profit_pct': 0.04,  # 降低限制
                'max_holding_minutes': 120,  # 延长

                # 防重复交易
                'signal_cooldown_minutes': 15,

                # 交易参数
                'min_volume': 10000,
                'min_data_points': 30,  # 需要足够数据计算Stochastic RSI

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

        # 计算Stochastic RSI
        logger.debug(f"📊 {symbol} 开始计算Stochastic RSI指标")
        close_prices = data['Close']
        stoch_rsi = calculate_stochastic_rsi(
            close_prices,
            self.config['rsi_period'],
            self.config['stoch_period']
        )

        if stoch_rsi.empty:
            logger.warning(f"⚠️ {symbol} Stochastic RSI计算失败，返回空序列")
            return signals

        current_price = data['Close'].iloc[-1]
        current_stoch_rsi = stoch_rsi.iloc[-1]

        if np.isnan(current_stoch_rsi):
            logger.warning(f"⚠️ {symbol} 当前Stochastic RSI值为NaN，跳过信号生成")
            return signals

        # 获取前一个值用于交叉检测
        if len(stoch_rsi) >= 2:
            prev_stoch_rsi = stoch_rsi.iloc[-2]
        else:
            logger.warning(f"⚠️ {symbol} 数据点不足，无法进行交叉检测")
            return signals

        logger.debug(f"📈 {symbol} Stochastic RSI计算完成 - 当前值: {current_stoch_rsi:.4f}, 前值: {prev_stoch_rsi:.4f}, RSI周期: {self.config['rsi_period']}, Stoch周期: {self.config['stoch_period']}")

        atr = indicators.get('ATR', abs(current_price * 0.02))  # 默认2%的ATR

        # 检查现有持仓的退出条件
        if symbol in self.positions and len(data) > 0:
            exit_signal = self.check_exit_conditions(symbol, current_price)
            if exit_signal:
                exit_signal['position_size'] = abs(self.positions[symbol]['size'])
                signals.append(exit_signal)

        # 只在没有持仓时生成买入信号
        if symbol not in self.positions:
            logger.debug(f"🔍 {symbol} 检查买入信号条件 - 当前价格: ${current_price:.2f}, ATR: ${atr:.4f}")
            signal = self._detect_stoch_rsi_signal(
                symbol, data, current_stoch_rsi, prev_stoch_rsi, current_price
            )
            if signal:
                signal_hash = self._generate_signal_hash(signal)
                logger.debug(f"🎯 {symbol} 检测到信号 - 类型: {signal['signal_type']}, 哈希: {signal_hash[:8]}")

                if not self._is_signal_cooldown(signal_hash):
                    if signal_hash not in self.executed_signals:
                        # 计算仓位大小
                        position_size = self.calculate_position_size(signal, atr)
                        logger.info(f"📊 {symbol} 仓位计算 - 信号置信度: {signal['confidence']:.2f}, ATR: ${atr:.4f}, 计算股数: {position_size}")

                        if position_size > 0:
                            signal['position_size'] = position_size
                            signal['signal_hash'] = signal_hash
                            signals.append(signal)
                            self.executed_signals.add(signal_hash)
                            logger.info(f"✅ {symbol} 信号确认 - {signal['action']} {position_size}股 @ ${current_price:.2f}, 原因: {signal['reason']}")
                        else:
                            logger.warning(f"⚠️ {symbol} 仓位计算为0，跳过信号")
                    else:
                        logger.debug(f"🔄 {symbol} 信号已执行，跳过")
                else:
                    logger.debug(f"⏰ {symbol} 信号冷却中，跳过")
            else:
                logger.debug(f"❌ {symbol} 未检测到有效信号")

        # 记录信号统计
        if signals:
            self.signals_generated += len(signals)

        return signals

    def _detect_stoch_rsi_signal(self, symbol: str, data: pd.DataFrame,
                                current_stoch_rsi: float, prev_stoch_rsi: float,
                                current_price: float) -> Optional[Dict]:
        """
        检测Stochastic RSI信号
        """

        oversold_level = self.config['oversold_level']
        overbought_level = self.config['overbought_level']

        # 超卖 -> 买入信号
        if current_stoch_rsi <= oversold_level:
            logger.debug(f"📊 {symbol} 检测到超卖条件: {current_stoch_rsi:.4f} <= {oversold_level}")

            # 计算超卖程度（距离阈值越远信号越强）
            oversold_strength = oversold_level - current_stoch_rsi
            confidence = 0.5 + min(oversold_strength * 2.0, 0.4)  # 最大增加0.4
            logger.debug(f"💪 {symbol} 超卖强度: {oversold_strength:.4f}, 基础置信度: {confidence:.3f}")

            # 检查是否从超卖区域向上突破（更强的买入信号）
            breakout_bonus = 0.0
            if prev_stoch_rsi <= oversold_level and current_stoch_rsi > prev_stoch_rsi:
                breakout_bonus = 0.1
                confidence += breakout_bonus
                logger.debug(f"🚀 {symbol} 检测到向上突破，置信度增加: +{breakout_bonus}")

            confidence = min(confidence, 0.9)
            logger.debug(f"🎯 {symbol} 最终买入置信度: {confidence:.3f}")

            logger.info(f"📈 {symbol} Stochastic RSI超卖买入 - StochRSI: {current_stoch_rsi:.3f}, 阈值: {oversold_level}, 强度: {oversold_strength:.3f}, 置信度: {confidence:.2f}")

            return {
                'symbol': symbol,
                'signal_type': 'STOCH_RSI_OVERSOLD',
                'action': 'BUY',
                'price': current_price,
                'confidence': confidence,
                'reason': f"Stochastic RSI超卖: {current_stoch_rsi:.3f} <= {oversold_level}",
                'indicators': {
                    'stoch_rsi': float(current_stoch_rsi),
                    'oversold_level': oversold_level,
                    'overbought_level': overbought_level,
                    'rsi_period': self.config['rsi_period'],
                    'stoch_period': self.config['stoch_period']
                }
            }

        # 超买 -> 卖出信号
        elif current_stoch_rsi >= overbought_level:
            logger.debug(f"📊 {symbol} 检测到超买条件: {current_stoch_rsi:.4f} >= {overbought_level}")

            # 计算超买程度
            overbought_strength = current_stoch_rsi - overbought_level
            confidence = 0.5 + min(overbought_strength * 2.0, 0.4)  # 最大增加0.4
            logger.debug(f"💪 {symbol} 超买强度: {overbought_strength:.4f}, 基础置信度: {confidence:.3f}")

            # 检查是否从超买区域向下突破（更强的卖出信号）
            breakout_bonus = 0.0
            if prev_stoch_rsi >= overbought_level and current_stoch_rsi < prev_stoch_rsi:
                breakout_bonus = 0.1
                confidence += breakout_bonus
                logger.debug(f"📉 {symbol} 检测到向下突破，置信度增加: +{breakout_bonus}")

            confidence = min(confidence, 0.9)
            logger.debug(f"🎯 {symbol} 最终卖出置信度: {confidence:.3f}")

            logger.info(f"📉 {symbol} Stochastic RSI超买卖出 - StochRSI: {current_stoch_rsi:.3f}, 阈值: {overbought_level}, 强度: {overbought_strength:.3f}, 置信度: {confidence:.2f}")

            return {
                'symbol': symbol,
                'signal_type': 'STOCH_RSI_OVERBOUGHT',
                'action': 'SELL',
                'price': current_price,
                'confidence': confidence,
                'reason': f"Stochastic RSI超买: {current_stoch_rsi:.3f} >= {overbought_level}",
                'indicators': {
                    'stoch_rsi': float(current_stoch_rsi),
                    'oversold_level': oversold_level,
                    'overbought_level': overbought_level,
                    'rsi_period': self.config['rsi_period'],
                    'stoch_period': self.config['stoch_period']
                }
            }

        logger.debug(f"❌ {symbol} 未满足任何信号条件 - StochRSI: {current_stoch_rsi:.4f} (超卖阈值: {oversold_level}, 超买阈值: {overbought_level})")
        return None

    def check_exit_conditions(self, symbol: str, current_price: float,
                            current_time: datetime = None) -> Optional[Dict]:
        """
        检查卖出条件 - 重写基类方法
        """
        logger.debug(f"🔍 {symbol} 检查退出条件 - 当前价格: ${current_price:.2f}")

        if symbol not in self.positions:
            logger.debug(f"❌ {symbol} 无持仓，跳过退出检查")
            return None
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
        logger.debug(f"🛡️ {symbol} 止损检查 - 当前盈亏: {price_change_pct*100:.2f}%, 止损阈值: {stop_loss_pct*100:.2f}%")
        if price_change_pct <= stop_loss_pct:
            logger.warning(f"⚠️ {symbol} A12触发止损: 亏损{price_change_pct*100:.2f}% (阈值: {stop_loss_pct*100:.2f}%)")
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
        logger.debug(f"💰 {symbol} 止盈检查 - 当前盈亏: {price_change_pct*100:.2f}%, 止盈阈值: {take_profit_pct*100:.2f}%")
        if price_change_pct >= take_profit_pct:
            logger.info(f"✅ {symbol} A12触发止盈: 盈利{price_change_pct*100:.2f}% (阈值: {take_profit_pct*100:.2f}%)")
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
        max_holding = self.config['max_holding_minutes']
        logger.debug(f"⏰ {symbol} 持仓时间检查 - 已持仓: {holding_minutes:.1f}分钟, 最大限制: {max_holding}分钟")
        if holding_minutes > max_holding:
            logger.info(f"⏰ {symbol} A12触发超时平仓: 持仓{holding_minutes:.0f}分钟 > {max_holding}分钟限制")
            return {
                'symbol': symbol,
                'signal_type': 'MAX_HOLDING',
                'action': 'SELL' if position_size > 0 else 'BUY',
                'price': current_price,
                'reason': f"超时平仓: 持仓{holding_minutes:.0f}分钟",
                'position_size': abs(position_size),
                'profit_pct': price_change_pct * 100
            }

        logger.debug(f"✅ {symbol} 未触发任何退出条件，继续持仓")
        return None