#!/usr/bin/env python3
"""
Z-Score均值回归策略 (策略A2) — 增强卖出/出场逻辑，收紧买入条件
"""
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
from strategies.base_strategy import BaseStrategy
from strategies import indicators as tech_indicators

logger = logging.getLogger(__name__)

class A2ZScoreStrategy(BaseStrategy):
    """Z-Score均值回归策略"""
    
    def _default_config(self) -> Dict:
        """默认配置"""
        return {
            # 资金管理
            'initial_capital': 40000.0,
            'risk_per_trade': 0.02,
            'max_position_size': 0.1,
            'per_trade_notional_cap': 4000.0,  # 单笔交易美元上限
            'max_position_notional': 60000.0,  # 单股总仓位上限（美元）
            
            # Z-Score参数
            'zscore_lookback': 20,  # Z-Score计算窗口
            'zscore_entry_threshold': 2.0,  # 入场阈值
            'zscore_exit_threshold': 0.5,  # 出场阈值
            'price_mean_window': 20,  # 均值计算窗口
            'price_std_window': 20,  # 标准差计算窗口
            
            # 入场过滤条件
            'min_zscore_magnitude': 1.5,  # 最小Z-Score绝对值
            'max_zscore_magnitude': 3.5,  # 最大Z-Score绝对值
            'volume_confirmation': True,  # 需要成交量确认
            'min_volume_ratio': 2,  # 最小成交量比率（更严格）
            'min_confidence': 0.65,  # 最小置信度才能发出信号
            'min_price': 5.0,  # 最低价格过滤，避免极低价股票
            'max_price': None,  # 最高价格过滤（可选）
            'max_signals_per_cycle': 2,  # 本策略每周期最多执行的信号数量（仅在单实例下有效）
            
            # 风险管理
            'stop_loss_pct': 0.03,  # 止损百分比
            'take_profit_pct': 0.05,  # 止盈百分比
            'max_holding_days': 5,  # 最大持有天数
            
            # 时间过滤
            'trading_hours_only': True,  # 只在交易时间交易
            'avoid_earnings': True,  # 避开财报期
            
            # 信号管理
            'signal_cooldown_hours': 6,  # 信号冷却时间（小时）
            
            # IB交易参数
            'ib_order_type': 'LMT',  # 使用限价单
            'ib_limit_offset': 0.005,  # 限价单偏移量
        }
    
    def detect_oversold_entry(self, symbol: str, data: pd.DataFrame, 
                             indicators: Dict) -> Optional[Dict]:
        """
        检测超卖入场信号（Z-Score < -阈值）
        收紧入场：更严格的 RSI / 成交量 / 趋势过滤，以减少无效买入
        """
        if len(data) < self.config['zscore_lookback']:
            return None
        
        if symbol in self.positions:
            return None
        
        latest = data.iloc[-1]
        
        # 计算Z-Score
        prices = data['Close']
        zscore = tech_indicators.calculate_zscore(prices, window=self.config['zscore_lookback'])
        current_zscore = zscore.iloc[-1]
        
        # Z-Score入场条件：必须显著低于负阈值
        if current_zscore >= -self.config['zscore_entry_threshold']:
            return None
        
        # Z-Score幅度限制
        if abs(current_zscore) < self.config['min_zscore_magnitude']:
            return None
        if abs(current_zscore) > self.config['max_zscore_magnitude']:
            return None
        
        # 成交量确认（对买入更严格）
        if self.config['volume_confirmation'] and 'Volume' in data.columns:
            if len(data) >= 10:
                avg_volume = data['Volume'].iloc[-10:].mean()
                volume_ratio = latest['Volume'] / (avg_volume + 1e-9)
                # 买入需要更强的量能（避免在低量的超卖中频繁买入）
                if volume_ratio < self.config['min_volume_ratio'] * 1.2:
                    return None
        
        # 价格趋势过滤（避免在明显下跌趋势中买入）
        if len(data) >= 20:
            short_ma = data['Close'].rolling(window=5).mean().iloc[-1]
            long_ma = data['Close'].rolling(window=20).mean().iloc[-1]
            # 更严格：短期均线若明显低于长期均线则拒绝买入
            if short_ma < long_ma * 0.995:
                logger.info(f"{symbol} 处于下跌趋势，跳过超卖买入信号")
                return None
        
        # 计算信号强度（对买入起点更保守）
        zscore_magnitude = abs(current_zscore)
        confidence = min(0.2 + (zscore_magnitude - 1.5) / 5.0, 0.7)  # 基线更低，减少过度买入
        
        # 获取其他技术指标确认（用传入的 indicators）
        rsi = indicators.get('RSI', 50)
        # 对买入要求更严：RSI进一步低于阈值时才加分
        if rsi < 35:
            confidence += 0.15
        
        logger.info(f"✅ {symbol} Z-Score超卖信号(收紧): Z={current_zscore:.2f}, RSI={rsi:.1f}, 置信度: {confidence:.2f}")
        
        signal = {
            'symbol': symbol,
            'signal_type': 'ZSCORE_OVERSOLD',
            'action': 'BUY',
            'price': latest['Close'],
            'confidence': confidence,
            'reason': f"Z-Score超卖: Z={current_zscore:.2f}, RSI={rsi:.1f}",
            'indicators': {
                'zscore': current_zscore,
                'rsi': rsi,
                'price': latest['Close'],
                'mean': prices.rolling(window=self.config['price_mean_window']).mean().iloc[-1],
                'std': prices.rolling(window=self.config['price_std_window']).std().iloc[-1]
            }
        }
        
        return signal
    
    def detect_overbought_entry(self, symbol: str, data: pd.DataFrame, 
                              indicators: Dict) -> Optional[Dict]:
        """
        检测超买入场信号（Z-Score > 阈值）
        强化卖出：提高置信、允许在高Z-Score且有确认时即使处于上行趋势也可以卖出
        """
        if len(data) < self.config['zscore_lookback']:
            return None
        
        if symbol in self.positions:
            return None
        
        latest = data.iloc[-1]
        
        # 计算Z-Score
        prices = data['Close']
        zscore = tech_indicators.calculate_zscore(prices, window=self.config['zscore_lookback'])
        current_zscore = zscore.iloc[-1]
        
        # Z-Score入场条件
        if current_zscore <= self.config['zscore_entry_threshold']:
            return None
        
        # Z-Score幅度限制
        if abs(current_zscore) < self.config['min_zscore_magnitude']:
            return None
        if abs(current_zscore) > self.config['max_zscore_magnitude']:
            return None
        
        # 成交量确认（对卖出稍宽松，允许在量不那么强时也可触发）
        if self.config['volume_confirmation'] and 'Volume' in data.columns:
            if len(data) >= 10:
                avg_volume = data['Volume'].iloc[-10:].mean()
                volume_ratio = latest['Volume'] / (avg_volume + 1e-9)
                # 卖出允许略低的量比（比买入放宽），但依然拒绝极低量
                if volume_ratio < self.config['min_volume_ratio'] * 0.9:
                    return None
        else:
            volume_ratio = 1.0
        
        # 价格趋势过滤（对卖出策略放宽：若上行趋势非常强且Z不够大则跳过；但当Z很大或有其他确认时允许卖出）
        if len(data) >= 20:
            short_ma = data['Close'].rolling(window=5).mean().iloc[-1]
            long_ma = data['Close'].rolling(window=20).mean().iloc[-1]
            # 只有在短期明显高于长期且Z不是非常大的情况下才跳过
            if short_ma > long_ma * 1.02 and current_zscore < self.config['zscore_entry_threshold'] * 1.5:
                logger.info(f"{symbol} 处于强上涨趋势且Z不够强，跳过超买卖出信号")
                return None
        
        # 计算信号强度（卖出更积极，提升置信）
        zscore_magnitude = abs(current_zscore)
        confidence = min(0.35 + (zscore_magnitude - 1.5) / 4.0, 0.95)
        
        # 其他确认（RSI、价格远离均值）
        rsi = indicators.get('RSI', 50)
        if rsi > 65:
            confidence += 0.15  # RSI 较高，卖出确认更强
        
        mean_price = prices.rolling(window=self.config['price_mean_window']).mean().iloc[-1]
        std_price = prices.rolling(window=self.config['price_std_window']).std().iloc[-1]
        if latest['Close'] > mean_price + 1.5 * (std_price if std_price > 0 else 0):
            confidence += 0.10  # 价格远离均值，卖出动机更强
        
        logger.info(f"✅ {symbol} Z-Score超买信号(强化): Z={current_zscore:.2f}, RSI={rsi:.1f}, 置信度: {confidence:.2f}")
        
        signal = {
            'symbol': symbol,
            'signal_type': 'ZSCORE_OVERBOUGHT',
            'action': 'SELL',
            'price': latest['Close'],
            'confidence': confidence,
            'reason': f"Z-Score超买: Z={current_zscore:.2f}, RSI={rsi:.1f}",
            'indicators': {
                'zscore': current_zscore,
                'rsi': rsi,
                'price': latest['Close'],
                'mean': mean_price,
                'std': std_price
            }
        }
        
        return signal
    
    def check_zscore_exit(self, symbol: str, data: pd.DataFrame, 
                         position: Dict) -> Optional[Dict]:
        """
        检查Z-Score出场信号
        增补条件：当趋势转弱或出现成交量放大伴随下跌时，优先出场（卖出）
        """
        if len(data) < self.config['zscore_lookback']:
            return None
        
        prices = data['Close']
        zscore = tech_indicators.calculate_zscore(prices, window=self.config['zscore_lookback'])
        current_zscore = zscore.iloc[-1]
        
        avg_cost = position['avg_cost']
        position_size = position['size']
        current_price = data['Close'].iloc[-1]
        latest = data.iloc[-1]
        
        # 计算移动平均用于趋势判断
        short_ma = data['Close'].rolling(window=5).mean().iloc[-1] if len(data) >= 5 else data['Close'].iloc[-1]
        long_ma = data['Close'].rolling(window=20).mean().iloc[-1] if len(data) >= 20 else data['Close'].iloc[-1]
        
        # 近10日平均成交量
        avg_volume_10 = data['Volume'].iloc[-10:].mean() if 'Volume' in data.columns and len(data) >= 10 else None
        
        # 计算盈亏
        if position_size > 0:  # 多头持仓：考虑卖出（回吐或趋势变弱）
            price_change_pct = (current_price - avg_cost) / avg_cost
            
            # 1) Z-Score回归到接近均值：优先出场
            if current_zscore > -self.config['zscore_exit_threshold']:
                return {
                    'symbol': symbol,
                    'signal_type': 'ZSCORE_EXIT',
                    'action': 'SELL',
                    'price': current_price,
                    'reason': f"Z-Score回归: Z={current_zscore:.2f}, 盈利{price_change_pct*100:.1f}%",
                    'position_size': abs(position_size),
                    'profit_pct': price_change_pct * 100,
                    'indicators': {
                        'zscore': current_zscore,
                        'exit_threshold': -self.config['zscore_exit_threshold']
                    }
                }
            
            # 2) 趋势弱化：短期均线跌破长期均线 -> 提前出场
            if len(data) >= 20 and short_ma < long_ma * 0.995:
                return {
                    'symbol': symbol,
                    'signal_type': 'TREND_WEAK_EXIT',
                    'action': 'SELL',
                    'price': current_price,
                    'reason': f"趋势转弱: short_ma({short_ma:.2f}) < long_ma({long_ma:.2f})",
                    'position_size': abs(position_size),
                    'profit_pct': price_change_pct * 100,
                    'indicators': {
                        'zscore': current_zscore,
                        'short_ma': short_ma,
                        'long_ma': long_ma
                    }
                }
            
            # 3) 成交量异常且价格下行（恐慌卖出信号）
            if avg_volume_10 is not None:
                if latest['Volume'] > avg_volume_10 * (self.config['min_volume_ratio'] * 1.5) and current_price < data['Close'].iloc[-2]:
                    return {
                        'symbol': symbol,
                        'signal_type': 'VOLUME_DUMP_EXIT',
                        'action': 'SELL',
                        'price': current_price,
                        'reason': f"成交量放大伴随下跌，可能加速回撤",
                        'position_size': abs(position_size),
                        'profit_pct': price_change_pct * 100,
                        'indicators': {
                            'zscore': current_zscore,
                            'volume_ratio': latest['Volume'] / (avg_volume_10 + 1e-9)
                        }
                    }
        else:  # 空头持仓：考虑回补（买入）
            price_change_pct = (avg_cost - current_price) / avg_cost
            
            # Z-Score回归到均值附近 -> 回补
            if current_zscore < self.config['zscore_exit_threshold']:
                return {
                    'symbol': symbol,
                    'signal_type': 'ZSCORE_EXIT',
                    'action': 'BUY',
                    'price': current_price,
                    'reason': f"Z-Score回归: Z={current_zscore:.2f}, 盈利{price_change_pct*100:.1f}%",
                    'position_size': abs(position_size),
                    'profit_pct': price_change_pct * 100,
                    'indicators': {
                        'zscore': current_zscore,
                        'exit_threshold': self.config['zscore_exit_threshold']
                    }
                }
            
            # 趋势反转向上 -> 回补空头
            if len(data) >= 20 and short_ma > long_ma * 1.005:
                return {
                    'symbol': symbol,
                    'signal_type': 'TREND_REVERSAL_EXIT',
                    'action': 'BUY',
                    'price': current_price,
                    'reason': f"趋势反转向上: short_ma({short_ma:.2f}) > long_ma({long_ma:.2f})",
                    'position_size': abs(position_size),
                    'profit_pct': price_change_pct * 100,
                    'indicators': {
                        'zscore': current_zscore,
                        'short_ma': short_ma,
                        'long_ma': long_ma
                    }
                }
        
        return None
    
    def generate_signals(self, symbol: str, data: pd.DataFrame, 
                        indicators: Dict) -> List[Dict]:
        """生成交易信号"""
        signals = []
        # 不在此处计数每周期下单，上限由主线程统一控制（避免工作线程提前耗尽名额）
        
        # 基本数据检查
        if data.empty or len(data) < max(self.config['zscore_lookback'], 30):
            return signals
        
        # 检查是否有持仓需要卖出
        if symbol in self.positions and len(data) > 0:
            # Z-Score出场信号
            exit_signal = self.check_zscore_exit(symbol, data, self.positions[symbol])
            if exit_signal:
                signals.append(exit_signal)
            
            # 传统止损止盈
            current_price = data['Close'].iloc[-1]
            traditional_exit = self.check_exit_conditions(symbol, current_price)
            if traditional_exit:
                signals.append(traditional_exit)
        
        # 只在没有持仓时生成入场信号
        if symbol not in self.positions:
            # 超卖入场信号（买）
            oversold_signal = self.detect_oversold_entry(symbol, data, indicators)
            if oversold_signal:
                # 生成信号并做二次过滤（价格 / 置信度）
                signal_hash = self._generate_signal_hash(oversold_signal)
                if not self._is_signal_cooldown(signal_hash) and signal_hash not in self.executed_signals:
                    price = oversold_signal.get('price', 0)
                    min_p = float(self.config.get('min_price', 0) or 0)
                    max_p = self.config.get('max_price')
                    if price < min_p or (max_p and price > float(max_p)):
                        logger.info(f"{symbol} 价格过滤：{price} 不在 [{min_p}, {max_p}] 范围内")
                    else:
                        conf = oversold_signal.get('confidence', 0)
                        if conf < float(self.config.get('min_confidence', 0.5)):
                            logger.info(f"{symbol} 信号置信度太低: {conf:.2f} < {self.config.get('min_confidence')}")
                        else:
                            if 'ATR' in indicators and indicators['ATR'] > 0:
                                atr = indicators['ATR']
                            else:
                                atr = data['Close'].std() * 0.01
                            oversold_signal['position_size'] = self.calculate_position_size(oversold_signal, atr)
                            oversold_signal['signal_hash'] = signal_hash
                            if oversold_signal['position_size'] > 0:
                                signals.append(oversold_signal)
                                self.executed_signals.add(signal_hash)
            
            # 超买入场信号（卖）
            overbought_signal = self.detect_overbought_entry(symbol, data, indicators)
            if overbought_signal:
                signal_hash = self._generate_signal_hash(overbought_signal)
                if not self._is_signal_cooldown(signal_hash) and signal_hash not in self.executed_signals:
                    price = overbought_signal.get('price', 0)
                    min_p = float(self.config.get('min_price', 0) or 0)
                    max_p = self.config.get('max_price')
                    if price < min_p or (max_p and price > float(max_p)):
                        logger.info(f"{symbol} 价格过滤：{price} 不在 [{min_p}, {max_p}] 范围内")
                    else:
                        conf = overbought_signal.get('confidence', 0)
                        if conf < float(self.config.get('min_confidence', 0.5)):
                            logger.info(f"{symbol} 信号置信度太低: {conf:.2f} < {self.config.get('min_confidence')}")
                        else:
                            if 'ATR' in indicators and indicators['ATR'] > 0:
                                atr = indicators['ATR']
                            else:
                                atr = data['Close'].std() * 0.01
                            overbought_signal['position_size'] = self.calculate_position_size(overbought_signal, atr)
                            overbought_signal['signal_hash'] = signal_hash
                            if overbought_signal['position_size'] > 0:
                                signals.append(overbought_signal)
                                self.executed_signals.add(signal_hash)
        
        # 记录信号统计
        if signals:
            self.signals_generated += len(signals)
        
        return signals
    
    def check_exit_conditions(self, symbol: str, current_price: float, 
                             current_time: datetime = None) -> Optional[Dict]:
        """
        检查传统卖出条件
        """
        if symbol not in self.positions:
            return None
        
        if current_time is None:
            current_time = datetime.now()
        
        position = self.positions[symbol]
        avg_cost = position['avg_cost']
        position_size = position['size']
        
        entry_time = position.get('entry_time', current_time - timedelta(days=1))
        
        # 计算盈亏
        if position_size > 0:
            price_change_pct = (current_price - avg_cost) / avg_cost
        else:
            price_change_pct = (avg_cost - current_price) / avg_cost
        
        # 止损
        if price_change_pct <= -self.config['stop_loss_pct']:
            return {
                'symbol': symbol,
                'signal_type': 'STOP_LOSS',
                'action': 'SELL' if position_size > 0 else 'BUY',
                'price': current_price,
                'reason': f"止损: 亏损{price_change_pct*100:.1f}%",
                'position_size': abs(position_size),
                'profit_pct': price_change_pct * 100
            }
        
        # 止盈
        if price_change_pct >= self.config['take_profit_pct']:
            return {
                'symbol': symbol,
                'signal_type': 'TAKE_PROFIT',
                'action': 'SELL' if position_size > 0 else 'BUY',
                'price': current_price,
                'reason': f"止盈: 盈利{price_change_pct*100:.1f}%",
                'position_size': abs(position_size),
                'profit_pct': price_change_pct * 100
            }
        
        # 最大持有时间
        holding_days = (current_time - entry_time).total_seconds() / (24 * 3600)
        if holding_days > self.config['max_holding_days']:
            return {
                'symbol': symbol,
                'signal_type': 'MAX_HOLDING',
                'action': 'SELL' if position_size > 0 else 'BUY',
                'price': current_price,
                'reason': f"超时平仓: 持仓{holding_days:.1f}天",
                'position_size': abs(position_size),
                'profit_pct': price_change_pct * 100
            }
        
        return None
    
    def _add_signal_to_cache(self, signal_hash: str):
        """重写缓存方法，使用小时级冷却"""
        cooldown_hours = self.config['signal_cooldown_hours']
        expiration = datetime.now() + timedelta(hours=cooldown_hours)
        self.signal_cache[signal_hash] = expiration
        
        current_time = datetime.now()
        expired_keys = [k for k, v in self.signal_cache.items() if v < current_time]
        for key in expired_keys:
            del self.signal_cache[key]
