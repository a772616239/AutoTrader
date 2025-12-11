#!/usr/bin/env python3
"""
RSI震荡策略 (A8) - 增强卖出/退出逻辑
基于相对强弱指数检测超买超卖信号，增强卖出/反转逻辑（不新增配置字段）
"""
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
from strategies.base_strategy import BaseStrategy
from strategies.indicators import calculate_rsi

logger = logging.getLogger(__name__)

class A8RSIOscillatorStrategy(BaseStrategy):
    """RSI震荡策略 - A8（增强卖出逻辑）"""

    def _default_config(self) -> Dict:
        """默认配置 - 从config.py读取"""
        from config import CONFIG
        strategy_key = 'strategy_a8'
        if strategy_key in CONFIG:
            return CONFIG[strategy_key]
        else:
            # 降级到硬编码默认值（保持原有字段，不新增）
            return {
                # 资金管理
                'initial_capital': 40000.0,
                'risk_per_trade': 0.02,
                'max_position_size': 0.1,
                'per_trade_notional_cap': 4000.0,  # 单笔交易美元上限
                'max_position_notional': 60000.0,  # 单股总仓位上限（美元）

                # RSI参数
                'rsi_period': 14,
                'rsi_oversold': 30,
                'rsi_overbought': 70,
                'rsi_signal_threshold': 5,  # RSI距离阈值的距离

                # 风险管理
                'stop_loss_pct': 0.015,  # 降低限制
                'take_profit_pct': 0.025,  # 降低限制
                'max_holding_minutes': 90,  # 延长
                'trailing_stop_activation': 0.02,
                'trailing_stop_distance': 0.015,

                # 防重复交易
                'signal_cooldown_minutes': 10,

                # 交易参数
                'min_volume': 10000,
                'min_data_points': 20,

                # IB交易参数
                'ib_order_type': 'MKT',
                'ib_limit_offset': 0.01,
            }

    def generate_signals(self, symbol: str, data: pd.DataFrame,
                        indicators: Dict) -> List[Dict]:
        """生成交易信号（增强卖出/开空）"""
        signals = []

        # 基本数据检查
        if data.empty or len(data) < self.config['min_data_points']:
            return signals

        # 检查成交量（若存在）
        avg_volume = None
        if 'Volume' in data.columns:
            avg_volume = data['Volume'].rolling(window=10).mean().iloc[-1]
            if pd.isna(avg_volume) or avg_volume < self.config['min_volume']:
                # 没有足够成交量，降低频率：但不要直接返回——允许退出信号继续被触发
                logger.debug(f"{symbol} 成交量不足: {avg_volume}")
                # 继续，但会让开仓信号更谨慎
        # 计算RSI
        close_prices = data['Close']
        rsi_series = calculate_rsi(close_prices, self.config['rsi_period'])
        if rsi_series is None or rsi_series.empty:
            return signals
        current_rsi = rsi_series.iloc[-1]
        if np.isnan(current_rsi):
            return signals

        current_price = data['Close'].iloc[-1]
        atr = indicators.get('ATR', abs(current_price * 0.02))  # 默认2%的ATR

        # 先检查持仓退出（优先）
        if symbol in self.positions and len(data) > 0:
            exit_signal = self.check_exit_conditions(symbol, current_price)
            if exit_signal:
                exit_signal['position_size'] = abs(self.positions[symbol]['size'])
                signals.append(exit_signal)

            # 如果持有多头且出现强烈反转信号，可以同时考虑反向开仓（做空）
            # 注意：这里先发出退出信号；执行系统可决定是否合并为反向下单
            if symbol in self.positions:
                pos = self.positions[symbol]
                if pos['size'] > 0:
                    # 检测强烈的卖出信号（顶背离 / RSI强烈超买且短期动能转弱）
                    strong_bear = self._short_term_bearish_momentum(data, rsi_series)
                    divergence = self._detect_bearish_divergence(data, rsi_series)
                    if strong_bear or divergence:
                        # 构造更积极的开空信号（系统需确保先平多头）
                        sell_signal = {
                            'symbol': symbol,
                            'signal_type': 'RSI_REVERSAL_TO_SHORT',
                            'action': 'SELL',
                            'price': current_price,
                            'confidence': 0.75 + (0.15 if divergence else 0.0),
                            'reason': '多头持仓遇到RSI反转/顶背离，建议先平多再开空',
                            'indicators': {
                                'rsi': float(current_rsi),
                                'divergence': bool(divergence),
                            }
                        }
                        sell_signal['position_size'] = self.calculate_position_size(sell_signal, atr)
                        sell_signal['signal_hash'] = self._generate_signal_hash(sell_signal)
                        if not self._is_signal_cooldown(sell_signal['signal_hash']):
                            signals.append(sell_signal)
                            self.executed_signals.add(sell_signal['signal_hash'])

        # 当没有持仓或允许开空时，生成开仓信号（买或卖/做空）
        if symbol not in self.positions:
            base_signal = self._detect_rsi_signal(symbol, data, rsi_series, current_price, avg_volume)
            if base_signal:
                signal_hash = self._generate_signal_hash(base_signal)
                if (not self._is_signal_cooldown(signal_hash)) and (signal_hash not in self.executed_signals):
                    base_signal['position_size'] = self.calculate_position_size(base_signal, atr)
                    base_signal['signal_hash'] = signal_hash
                    # 过滤掉可能为0的仓位
                    if base_signal['position_size'] and abs(base_signal['position_size']) > 0:
                        signals.append(base_signal)
                        self.executed_signals.add(signal_hash)

        # 记录信号统计
        if signals:
            self.signals_generated += len(signals)

        return signals

    def _detect_rsi_signal(self, symbol: str, data: pd.DataFrame,
                          rsi_series: pd.Series, current_price: float,
                          avg_volume: Optional[float] = None) -> Optional[Dict]:
        """
        检测RSI信号（增强卖出/开空）
        - 返回信号字典 (action 为 'BUY' 或 'SELL')
        """
        current_rsi = float(rsi_series.iloc[-1])
        rsi_oversold = self.config['rsi_oversold']
        rsi_overbought = self.config['rsi_overbought']
        signal_threshold = self.config.get('rsi_signal_threshold', 5)

        # 计算距离阈值的程度，用于确定信号强度
        oversold_distance = rsi_oversold - current_rsi
        overbought_distance = current_rsi - rsi_overbought

        # 额外条件：短期均线/动量帮助确认方向（不新增配置项，直接用内联计算）
        short_ma = data['Close'].rolling(window=5).mean().iloc[-1] if len(data) >= 5 else None
        long_ma = data['Close'].rolling(window=20).mean().iloc[-1] if len(data) >= 20 else None

        # 超卖 -> 买入候选
        if current_rsi <= rsi_oversold:
            confidence = min(0.4 + (oversold_distance / max(1.0, rsi_oversold)) * 0.4, 0.85)
            # RSI仍在下降则更强
            if len(rsi_series) >= 2 and not np.isnan(rsi_series.iloc[-2]) and current_rsi < rsi_series.iloc[-2]:
                confidence += 0.05

            # 量能确认：如果最近成交量显著放大，则信号更可信
            if avg_volume is not None and 'Volume' in data.columns:
                recent_vol = data['Volume'].iloc[-1]
                if recent_vol > avg_volume * 1.2:
                    confidence += 0.05

            logger.info(f"📈 {symbol} RSI超卖买入候选 - RSI: {current_rsi:.1f}, 置信度: {confidence:.2f}")
            return {
                'symbol': symbol,
                'signal_type': 'RSI_OVERSOLD',
                'action': 'BUY',
                'price': current_price,
                'confidence': float(min(confidence, 1.0)),
                'reason': f"RSI超卖: {current_rsi:.1f} <= {rsi_oversold}",
                'indicators': {
                    'rsi': float(current_rsi),
                    'rsi_threshold': rsi_oversold,
                    'distance': float(oversold_distance)
                }
            }

        # 超买 -> 卖出/做空候选（增强逻辑）
        if current_rsi >= rsi_overbought:
            confidence = min(0.4 + (overbought_distance / max(1.0, (100 - rsi_overbought))) * 0.4, 0.85)

            # RSI仍在上升则更强
            if len(rsi_series) >= 2 and not np.isnan(rsi_series.iloc[-2]) and current_rsi > rsi_series.iloc[-2]:
                confidence += 0.05

            # 量能确认（若成交量放大，则更可信）
            if avg_volume is not None and 'Volume' in data.columns:
                recent_vol = data['Volume'].iloc[-1]
                if recent_vol > avg_volume * 1.2:
                    confidence += 0.05

            # 若存在顶背离（价格创高点但RSI未创新高） -> 明显增强卖出置信度
            divergence = self._detect_bearish_divergence(data, rsi_series)
            if divergence:
                confidence += 0.1

            # 若短期价格动量已转弱（短期MA下穿/价格低于短期MA） -> 增强
            short_term_bear = self._short_term_bearish_momentum(data, rsi_series)
            if short_term_bear:
                confidence += 0.1

            confidence = float(min(confidence, 0.99))

            logger.info(f"📉 {symbol} RSI超买卖出候选 - RSI: {current_rsi:.1f}, 置信度: {confidence:.2f}, divergence={divergence}, short_bear={short_term_bear}")

            return {
                'symbol': symbol,
                'signal_type': 'RSI_OVERBOUGHT',
                'action': 'SELL',
                'price': current_price,
                'confidence': confidence,
                'reason': f"RSI超买: {current_rsi:.1f} >= {rsi_overbought}",
                'indicators': {
                    'rsi': float(current_rsi),
                    'rsi_threshold': rsi_overbought,
                    'distance': float(overbought_distance),
                    'divergence': bool(divergence),
                    'short_term_bearish': bool(short_term_bear)
                }
            }

        # 非极端区域：也考虑中性区间的反转机会（更积极的平仓/卖出）
        neutral_upper = 55
        neutral_lower = 45
        # 如果RSI在中性区间但出现快速反转（比如从>neutral_upper回落到<neutral_upper），建议考虑减仓/平仓
        if len(rsi_series) >= 2:
            prev_rsi = rsi_series.iloc[-2]
            if prev_rsi >= neutral_upper and current_rsi < neutral_upper:
                # 中性上行被打断，构建卖出/减仓建议（置信度较中等）
                logger.info(f"🔄 {symbol} RSI中性区反转卖出候选 - prev {prev_rsi:.1f} -> curr {current_rsi:.1f}")
                return {
                    'symbol': symbol,
                    'signal_type': 'RSI_NEUTRAL_REVERSAL',
                    'action': 'SELL',
                    'price': current_price,
                    'confidence': 0.45,
                    'reason': f"RSI 从 {prev_rsi:.1f} 回落到 {current_rsi:.1f}",
                    'indicators': {'rsi': float(current_rsi)}
                }

        return None

    def check_exit_conditions(self, symbol: str, current_price: float,
                             current_time: datetime = None) -> Optional[Dict]:
        """
        检查卖出条件 - 增强版本
        优先考虑止损/止盈/超时/RSI反转/分批止盈/动量反转
        """
        if symbol not in self.positions:
            return None

        if current_time is None:
            current_time = datetime.now()

        position = self.positions[symbol]
        avg_cost = position['avg_cost']
        position_size = position['size']  # >0 long, <0 short

        entry_time = position.get('entry_time', current_time - timedelta(minutes=60))

        # 计算盈亏（按仓位方向）
        if position_size > 0:
            price_change_pct = (current_price - avg_cost) / avg_cost
        else:
            price_change_pct = (avg_cost - current_price) / avg_cost

        # 止损检查（强制平仓）
        stop_loss_pct = -abs(self.config['stop_loss_pct'])
        if price_change_pct <= stop_loss_pct:
            logger.warning(f"⚠️ {symbol} A8触发止损: 亏损{price_change_pct*100:.2f}%")
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

        # 止盈检查（完全止盈）
        take_profit_pct = abs(self.config['take_profit_pct'])
        if price_change_pct >= take_profit_pct:
            logger.info(f"✅ {symbol} A8触发止盈: 盈利{price_change_pct*100:.2f}%")
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
            logger.info(f"⏳ {symbol} 达到最大持仓时间，平仓 - 持仓{holding_minutes:.0f}分钟")
            return {
                'symbol': symbol,
                'signal_type': 'MAX_HOLDING',
                'action': 'SELL' if position_size > 0 else 'BUY',
                'price': current_price,
                'reason': f"超时平仓: 持仓{holding_minutes:.0f}分钟",
                'position_size': abs(position_size),
                'profit_pct': price_change_pct * 100
            }

        # RSI反转退出：若持有多头且RSI回落穿过中性位（例如55->50）则考虑部分/全部退出
        rsi_series = None
        try:
            # 尝试从历史数据缓存/指标获取RSI序列
            rsi_series = self._cached_indicators_for(symbol).get('RSI')
        except Exception:
            rsi_series = None

        # 如果没法从缓存拿到RSI序列，尝试计算（如果有历史价格访问接口）
        if rsi_series is None:
            # 如果策略有方法可以获取历史数据，这里应替换为实际获取方式；简化为 None
            rsi_series = None

        # 使用当前仓位方向的策略性退出（内部方法）
        reversal_signal = self._check_rsi_reversal(symbol, position_size, current_price)
        if reversal_signal:
            return reversal_signal

        # 分批退出：当出现轻度不利的RSI/动量信号且仍在小幅盈利/小幅亏损时，先减半持仓（如果系统支持）
        # 注意：不新增字段，仅返回一个 PARTIAL_EXIT 信号（position_size 表示要减仓的数量）
        if abs(price_change_pct) < 0.03:  # 在-3% ~ +3%区间内，更积极做分批处理
            # 当多头时 RSI < 50 或短期动量转弱 -> 减仓
            if position_size > 0:
                # 使用最近收盘价与5日均线判断动量
                # 若 data 不直接可得，这段逻辑以 try 为准（不会抛出）
                try:
                    hist = self._get_recent_price_df(symbol, lookback=20)
                    if hist is not None and not hist.empty:
                        short_ma = hist['Close'].rolling(window=5).mean().iloc[-1]
                        if hist['Close'].iloc[-1] < short_ma:
                            logger.info(f"{symbol} 多头动量转弱，建议部分减仓")
                            return {
                                'symbol': symbol,
                                'signal_type': 'PARTIAL_EXIT',
                                'action': 'SELL',
                                'price': current_price,
                                'reason': '多头动量转弱，建议部分减仓',
                                'position_size': max(1, int(abs(position_size) * 0.5)),
                                'profit_pct': price_change_pct * 100,
                                'confidence': 0.6
                            }
                except Exception:
                    pass

            # 当为空头时 RSI > 50 或短期动量回升 -> 部分减仓（回补）
            if position_size < 0:
                try:
                    hist = self._get_recent_price_df(symbol, lookback=20)
                    if hist is not None and not hist.empty:
                        short_ma = hist['Close'].rolling(window=5).mean().iloc[-1]
                        if hist['Close'].iloc[-1] > short_ma:
                            logger.info(f"{symbol} 空头动量回升，建议部分回补")
                            return {
                                'symbol': symbol,
                                'signal_type': 'PARTIAL_EXIT',
                                'action': 'BUY',
                                'price': current_price,
                                'reason': '空头动量回升，建议部分回补',
                                'position_size': max(1, int(abs(position_size) * 0.5)),
                                'profit_pct': price_change_pct * 100,
                                'confidence': 0.6
                            }
                except Exception:
                    pass

        # 无其它退出条件
        return None

    def _check_rsi_reversal(self, symbol: str, position_size: int, current_price: float) -> Optional[Dict]:
        """
        检查RSI中性区反转，用于在适当的时候退出或部分退出
        - 对多头：如果RSI从 >55 回落到 <50 且短期动量/均线受损，建议卖出/减仓
        - 对空头：同理反向
        """
        # 尝试从缓存或外部接口拿到最近价格历史（这是策略内部辅助函数，若没有历史数据则不强制失败）
        try:
            hist = self._get_recent_price_df(symbol, lookback=30)
            if hist is None or hist.empty:
                return None
            rsi_series = calculate_rsi(hist['Close'], self.config['rsi_period'])
            if rsi_series is None or len(rsi_series) < 2:
                return None
            current_rsi = float(rsi_series.iloc[-1])
            prev_rsi = float(rsi_series.iloc[-2])
        except Exception:
            return None

        # 多头仓位处理
        if position_size > 0:
            # RSI从高位回落穿越中性并且短期均线下穿 -> 平仓/减仓
            if prev_rsi >= 55 and current_rsi < 50:
                # 短期动量
                short_ma = hist['Close'].rolling(window=5).mean().iloc[-1] if len(hist) >= 5 else None
                if short_ma is not None and hist['Close'].iloc[-1] < short_ma:
                    logger.info(f"🔻 {symbol} RSI回落且短期动量转弱，建议减仓/平仓 - RSI {prev_rsi:.1f}->{current_rsi:.1f}")
                    return {
                        'symbol': symbol,
                        'signal_type': 'RSI_REVERSAL_LONG',
                        'action': 'SELL',
                        'price': current_price,
                        'reason': f"RSI回落: {prev_rsi:.1f} -> {current_rsi:.1f}, 短期动量转弱",
                        'position_size': abs(position_size),
                        'confidence': 0.85
                    }

        # 空头仓位处理
        if position_size < 0:
            if prev_rsi <= 45 and current_rsi > 50:
                short_ma = hist['Close'].rolling(window=5).mean().iloc[-1] if len(hist) >= 5 else None
                if short_ma is not None and hist['Close'].iloc[-1] > short_ma:
                    logger.info(f"🔺 {symbol} 空头RSI反转，建议回补 - RSI {prev_rsi:.1f}->{current_rsi:.1f}")
                    return {
                        'symbol': symbol,
                        'signal_type': 'RSI_REVERSAL_SHORT',
                        'action': 'BUY',
                        'price': current_price,
                        'reason': f"空头RSI反转: {prev_rsi:.1f} -> {current_rsi:.1f}",
                        'position_size': abs(position_size),
                        'confidence': 0.85
                    }

        return None

    def _detect_bearish_divergence(self, data: pd.DataFrame, rsi_series: pd.Series) -> bool:
        """
        简单检测价格与RSI的顶背离：
        - 在最近 6~12 根bar内：价格创出新高而RSI未能跟随创高 -> 视为顶背离
        - 返回 True/False
        """
        try:
            lookback = min(12, len(data) - 1)
            if lookback < 4 or len(rsi_series) < lookback + 1:
                return False
            price = data['Close'].iloc[-(lookback+1):].values
            rsi = rsi_series.iloc[-(lookback+1):].values

            # 找到最近两个价格高点及对应RSI
            # 简化方法：取窗口内最大价与其前一个局部高点
            idx_max = int(np.argmax(price))
            if idx_max == 0:
                return False
            # 之前的次高点
            price_prefix = price[:idx_max]
            if len(price_prefix) < 1:
                return False
            idx_prev = int(np.argmax(price_prefix))
            # RSI 在两个高点对应位置是否下降
            rsi_at_max = rsi[idx_max]
            rsi_at_prev = rsi[idx_prev]
            # 若价格在第二个高点更高但RSI反而更低 -> 背离
            if price[idx_max] > price[idx_prev] and rsi_at_max < rsi_at_prev:
                return True
            return False
        except Exception:
            return False

    def _short_term_bearish_momentum(self, data: pd.DataFrame, rsi_series: pd.Series) -> bool:
        """
        简单判断短期动量是否转弱（用于增强卖出信号）：
        - 价格跌破5日均线或5日均线下穿20日均线，或RSI从高位回落速度较快
        """
        try:
            if len(data) < 10 or len(rsi_series) < 3:
                return False
            close = data['Close']
            ma5 = close.rolling(window=5).mean().iloc[-1]
            ma20 = close.rolling(window=20).mean().iloc[-1] if len(close) >= 20 else None
            # 价格下穿5日均线
            if close.iloc[-1] < ma5:
                # 若同时5日均线斜率为负，则动量更弱
                ma5_prev = close.rolling(window=5).mean().iloc[-2]
                if ma5 < ma5_prev:
                    return True
            # 5日下穿20日
            if ma20 is not None:
                ma5_prev = close.rolling(window=5).mean().iloc[-2]
                ma20_prev = close.rolling(window=20).mean().iloc[-2]
                if ma5_prev >= ma20_prev and ma5 < ma20:
                    return True
            # RSI 快速回落
            if rsi_series.iloc[-2] - rsi_series.iloc[-1] > 6:
                return True
            return False
        except Exception:
            return False

    # ---- 辅助/兼容函数（尽量不改变外部接口） ----
    def _cached_indicators_for(self, symbol: str) -> Dict[str, Any]:
        """
        尝试返回缓存的指标字典（如果基类/外部有缓存机制）
        这个方法为兼容性写法：若不存在则返回空字典
        """
        try:
            return getattr(self, 'indicator_cache', {}) or {}
        except Exception:
            return {}

    def _get_recent_price_df(self, symbol: str, lookback: int = 30) -> Optional[pd.DataFrame]:
        """
        尝试从基类或外部系统获取近期价格数据（若没有则返回 None）。
        这里不实现网络/IO，调用基类提供的方法（如果有）。
        目的：避免直接在策略中硬编码外部数据源。
        """
        try:
            if hasattr(self, 'get_historical_data'):
                return self.get_historical_data(symbol, lookback)
            # 回退：若基类保存了 last_price_df 字段
            if hasattr(self, 'last_price_dfs') and symbol in self.last_price_dfs:
                df = self.last_price_dfs[symbol]
                if isinstance(df, pd.DataFrame):
                    return df.tail(lookback)
            return None
        except Exception:
            return None
