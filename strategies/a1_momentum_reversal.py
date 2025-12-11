#!/usr/bin/env python3
"""
增强版动量反转策略 - 移除尾盘强制平仓（类名保持原样）
"""
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
from strategies.base_strategy import BaseStrategy

logger = logging.getLogger(__name__)

class A1MomentumReversalStrategy(BaseStrategy):
    """增强版动量反转策略 - 无尾盘强制平仓"""
    
    def _default_config(self) -> Dict:
        """默认配置"""
        return {
            # 资金管理
            'initial_capital': 40000.0,
            'risk_per_trade': 0.02,
            'max_position_size': 0.1,
            'per_trade_notional_cap': 4000.0,
            'max_position_notional': 60000.0,
            
            # 时间分区
            'morning_session': ('09:30', '10:30'),
            'midday_session': ('10:30', '14:30'),
            'afternoon_session': ('14:30', '15:00'),
            
            # 信号参数
            'rsi_overbought': 72,
            'rsi_oversold': 28,
            'price_deviation_threshold': 2.5,
            'volume_surge_multiplier': 1.5,
            
            # 风险管理
            'stop_loss_atr_multiple': 1.5,
            'take_profit_atr_multiple': 3.0,
            'trailing_stop_activation': 0.02,  # 2%激活移动止损
            'trailing_stop_distance': 0.015,   # 移动止损距离1.5%
            'volatility_stop_multiple': 2.0,   # 波动性止损倍数
            
            # 卖出条件
            'min_profit_pct': 0.01,           # 最小盈利阈值
            'max_holding_minutes': 240,       # 延长持仓时间，因为没有尾盘平仓
            'quick_loss_cutoff': -0.03,        # 快速止损阈值
            'profit_target_1': 0.015,          # 第一目标位 1.5%
            'profit_target_2': 0.03,           # 第二目标位 3%
            'partial_profit_ratio': 0.5,       # 部分止盈比例
            
            # 技术指标卖出信号
            'sell_rsi_threshold': 70,          # RSI卖出阈值
            'sell_volume_divergence': True,    # 启用量价背离卖出
            'sell_macd_cross': True,           # MACD死叉卖出
            'sell_bollinger_exit': True,       # 布林带卖出
            
            # 市场状态适应
            'market_regime_adjustment': True,  # 市场状态调整
            'trending_stop_multiplier': 1.2,   # 趋势市场止损倍数
            'ranging_take_profit_multiplier': 0.8,  # 震荡市场止盈倍数
            
            # 防重复交易
            'signal_cooldown_minutes': 5,
            'same_symbol_cooldown': 15,
            
            # 交易参数
            'min_volume': 10000,
            'min_data_points': 30,
            'commission_rate': 0.0005,
            
            # IB交易参数
            'ib_order_type': 'MKT',
            'ib_limit_offset': 0.01,
            
            # 尾盘参数（仅用于信号生成，不平仓）
            'avoid_late_trade_minutes': 30,    # 避免收盘前30分钟开新仓
        }
    
    def analyze_market_regime(self, data: pd.DataFrame) -> Dict[str, Any]:
        """分析市场状态"""
        if len(data) < 20:
            return {"regime": "INSUFFICIENT_DATA", "volatility": 0, "trend": 0}
        
        returns = data['Close'].pct_change().dropna()
        volatility = returns.std() * np.sqrt(252)
        price_change = (data['Close'].iloc[-1] / data['Close'].iloc[0] - 1) * 100
        
        # 计算趋势强度
        if len(data) >= 50:
            ma20 = data['Close'].rolling(window=20).mean()
            ma50 = data['Close'].rolling(window=50).mean()
            trend_strength = abs((ma20.iloc[-1] - ma50.iloc[-1]) / ma50.iloc[-1] * 100)
        else:
            trend_strength = 0
        
        regime = "RANGING"
        if volatility > 0.25:
            regime = "HIGH_VOLATILITY"
        elif abs(price_change) > 3 and trend_strength > 1:
            regime = "TRENDING"
        
        return {
            "regime": regime,
            "volatility": volatility,
            "trend": trend_strength,
            "price_change": price_change
        }
    
    def detect_technical_sell_signals(self, symbol: str, data: pd.DataFrame, 
                                    indicators: Dict) -> List[Dict]:
        """检测技术性卖出信号"""
        sell_signals = []
        if len(data) < 20:
            return sell_signals
        
        latest = data.iloc[-1]
        prev = data.iloc[-2] if len(data) >= 2 else latest
        
        # 1. RSI超买信号
        rsi = indicators.get('RSI', 50)
        if rsi > self.config['sell_rsi_threshold']:
            sell_signals.append({
                'type': 'RSI_OVERBOUGHT',
                'strength': min((rsi - 70) / 30, 1.0),
                'reason': f"RSI超买: {rsi:.1f} > {self.config['sell_rsi_threshold']}"
            })
        
        # 2. 量价背离卖出
        if self.config['sell_volume_divergence'] and len(data) >= 10:
            # 价格创新高但成交量下降
            recent_high_idx = data['High'].iloc[-10:].idxmax()
            recent_high_volume = data['Volume'].loc[recent_high_idx]
            current_volume = latest['Volume']
            
            if latest['Close'] > data['Close'].iloc[-11:-1].max() and current_volume < recent_high_volume * 0.8:
                sell_signals.append({
                    'type': 'VOLUME_DIVERGENCE',
                    'strength': 0.6,
                    'reason': "量价背离: 价格创新高但成交量下降"
                })
        
        # 3. MACD死叉
        if self.config['sell_macd_cross'] and 'MACD' in indicators and 'MACD_Signal' in indicators:
            macd = indicators['MACD']
            signal = indicators['MACD_Signal']
            if macd < signal and prev.get('MACD_hist', 0) > 0:
                sell_signals.append({
                    'type': 'MACD_DEATH_CROSS',
                    'strength': 0.7,
                    'reason': "MACD死叉信号"
                })
        
        # 4. 布林带上轨卖出
        if self.config['sell_bollinger_exit'] and 'BB_Upper' in indicators:
            bb_upper = indicators['BB_Upper']
            bb_middle = indicators.get('BB_Middle', None)
            if bb_middle and latest['Close'] > bb_upper:
                sell_signals.append({
                    'type': 'BOLLINGER_EXIT',
                    'strength': 0.5,
                    'reason': f"价格突破布林带上轨: {latest['Close']:.2f} > {bb_upper:.2f}"
                })
        
        # 5. 跌破重要移动平均线
        ma_keys = ['MA_20', 'MA_50']
        for ma_key in ma_keys:
            if ma_key in indicators and indicators[ma_key] is not None:
                ma_value = indicators[ma_key]
                if latest['Close'] < ma_value and prev['Close'] >= ma_value:
                    sell_signals.append({
                        'type': f'BREAK_{ma_key}',
                        'strength': 0.4 if '20' in ma_key else 0.6 if '50' in ma_key else 0.8,
                        'reason': f"价格跌破{ma_key}: {latest['Close']:.2f} < {ma_value:.2f}"
                    })
        
        return sell_signals
    
    def calculate_dynamic_stop_loss(self, symbol: str, entry_price: float, 
                                  current_price: float, indicators: Dict,
                                  market_regime: Dict) -> Tuple[float, str]:
        """计算动态止损水平"""
        atr = indicators.get('ATR', 0)
        volatility = market_regime.get('volatility', 0)
        
        # 基础止损
        if atr > 0:
            base_stop = entry_price - (self.config['stop_loss_atr_multiple'] * atr)
        else:
            base_stop = entry_price * (1 - 0.03)  # 默认3%止损
        
        # 根据市场状态调整
        if market_regime['regime'] == 'HIGH_VOLATILITY':
            stop_multiplier = self.config.get('volatility_stop_multiple', 2.0)
            dynamic_stop = entry_price - (stop_multiplier * atr) if atr > 0 else base_stop
            reason = "高波动市场扩大止损"
        elif market_regime['regime'] == 'TRENDING':
            # 趋势市场使用较宽松的止损
            dynamic_stop = base_stop * 0.95  # 放宽5%
            reason = "趋势市场放宽止损"
        else:
            dynamic_stop = base_stop
            reason = "标准止损"
        
        # 移动止损（如果盈利足够）
        profit_pct = (current_price - entry_price) / entry_price
        if profit_pct > self.config['trailing_stop_activation']:
            trailing_stop = current_price * (1 - self.config['trailing_stop_distance'])
            dynamic_stop = max(dynamic_stop, trailing_stop)
            reason = f"移动止损激活: {trailing_stop:.2f}"
        
        return dynamic_stop, reason
    
    def check_exit_conditions(self, symbol: str, current_price: float, 
                             current_time: datetime = None,
                             indicators: Dict = None,
                             market_regime: Dict = None) -> Optional[Dict]:
        """
        检查卖出条件 - 无尾盘强制平仓
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
        price_change_pct = (current_price - avg_cost) / avg_cost if position_size > 0 else 0
        
        # 获取市场状态
        if market_regime is None:
            market_regime = {"regime": "RANGING", "volatility": 0}
        
        # 1. 技术性卖出信号
        if indicators and len(self.detect_technical_sell_signals(symbol, pd.DataFrame(), indicators)) >= 2:
            tech_signals = self.detect_technical_sell_signals(symbol, pd.DataFrame(), indicators)
            if tech_signals and price_change_pct > self.config['min_profit_pct']:
                logger.info(f"📉 {symbol} 技术卖出信号触发")
                return {
                    'symbol': symbol,
                    'signal_type': 'TECHNICAL_SELL',
                    'action': 'SELL' if position_size > 0 else 'BUY',
                    'price': current_price,
                    'reason': f"多重技术卖出信号: {', '.join([s['reason'] for s in tech_signals[:2]])}",
                    'position_size': abs(position_size),
                    'profit_pct': price_change_pct * 100,
                    'confidence': 0.8
                }
        
        # 2. 动态止损
        dynamic_stop, stop_reason = self.calculate_dynamic_stop_loss(
            symbol, avg_cost, current_price, indicators or {}, market_regime
        )
        
        if position_size > 0 and current_price <= dynamic_stop:
            logger.warning(f"⚠️ {symbol} 动态止损触发: {stop_reason}")
            return {
                'symbol': symbol,
                'signal_type': 'DYNAMIC_STOP_LOSS',
                'action': 'SELL',
                'price': current_price,
                'reason': f"动态止损: {stop_reason} (成本: ${avg_cost:.2f}, 止损: ${dynamic_stop:.2f})",
                'position_size': abs(position_size),
                'profit_pct': price_change_pct * 100,
                'confidence': 1.0
            }
        
        # 3. 分级止盈
        if price_change_pct >= self.config['profit_target_2']:
            # 达到第二目标位，全部止盈
            logger.info(f"🎯 {symbol} 达到第二止盈目标: +{price_change_pct*100:.2f}%")
            return {
                'symbol': symbol,
                'signal_type': 'FULL_TAKE_PROFIT',
                'action': 'SELL',
                'price': current_price,
                'reason': f"达到第二止盈目标: +{price_change_pct*100:.2f}%",
                'position_size': abs(position_size),
                'profit_pct': price_change_pct * 100,
                'confidence': 1.0
            }
        elif price_change_pct >= self.config['profit_target_1']:
            # 达到第一目标位，部分止盈
            partial_ratio = self.config['partial_profit_ratio']
            partial_size = int(abs(position_size) * partial_ratio)
            if partial_size > 0:
                logger.info(f"🎯 {symbol} 达到第一止盈目标，部分止盈{partial_ratio*100:.0f}%")
                return {
                    'symbol': symbol,
                    'signal_type': 'PARTIAL_TAKE_PROFIT',
                    'action': 'SELL',
                    'price': current_price,
                    'reason': f"部分止盈: 达到第一目标+{price_change_pct*100:.2f}%",
                    'position_size': partial_size,
                    'profit_pct': price_change_pct * 100,
                    'confidence': 0.9,
                    'partial_exit': True
                }
        
        # 4. 快速止损
        if price_change_pct <= self.config['quick_loss_cutoff']:
            return {
                'symbol': symbol,
                'signal_type': 'QUICK_LOSS',
                'action': 'SELL',
                'price': current_price,
                'reason': f"快速止损: 亏损{price_change_pct*100:.1f}%",
                'position_size': abs(position_size),
                'profit_pct': price_change_pct * 100
            }
        
        # 5. 最大持仓时间
        holding_minutes = (current_time - entry_time).total_seconds() / 60
        if holding_minutes > self.config['max_holding_minutes']:
            logger.info(f"⏰ {symbol} 持仓超时: {holding_minutes:.0f}分钟")
            return {
                'symbol': symbol,
                'signal_type': 'MAX_HOLDING',
                'action': 'SELL',
                'price': current_price,
                'reason': f"超时平仓: 持仓{holding_minutes:.0f}分钟",
                'position_size': abs(position_size),
                'profit_pct': price_change_pct * 100
            }
        
        # 6. 市场状态改变平仓
        if market_regime['regime'] == 'HIGH_VOLATILITY' and price_change_pct > 0.02:
            # 高波动市场中，有盈利就考虑退出
            return {
                'symbol': symbol,
                'signal_type': 'VOLATILITY_EXIT',
                'action': 'SELL',
                'price': current_price,
                'reason': f"高波动市场获利了结: +{price_change_pct*100:.2f}%",
                'position_size': abs(position_size),
                'profit_pct': price_change_pct * 100,
                'confidence': 0.7
            }
        
        return None
    
    def detect_counter_trend_sell(self, symbol: str, data: pd.DataFrame,
                                 indicators: Dict) -> Optional[Dict]:
        """检测逆势卖出信号（针对已有持仓的卖出）"""
        if symbol not in self.positions:
            return None
        
        position = self.positions[symbol]
        if position['size'] <= 0:  # 不是多头持仓
            return None
        
        if len(data) < 20:
            return None
        
        latest = data.iloc[-1]
        
        # 1. 价格与关键阻力位的距离
        if 'BB_Upper' in indicators and indicators['BB_Upper'] is not None:
            resistance = indicators['BB_Upper']
            distance_to_resistance = (resistance - latest['Close']) / latest['Close']
            if distance_to_resistance < 0.01:  # 距离阻力位小于1%
                return {
                    'symbol': symbol,
                    'signal_type': 'RESISTANCE_SELL',
                    'action': 'SELL',
                    'price': latest['Close'],
                    'confidence': 0.6,
                    'reason': f"接近布林带上轨阻力: {latest['Close']:.2f} (阻力: {resistance:.2f})"
                }
        
        # 2. 动量衰竭
        if len(data) >= 10:
            recent_gains = []
            for i in range(1, 6):
                if len(data) >= i+1:
                    gain = (data['Close'].iloc[-i] - data['Close'].iloc[-i-1]) / data['Close'].iloc[-i-1]
                    recent_gains.append(gain)
            
            if len(recent_gains) >= 3:
                momentum_slowing = all(recent_gains[i] > recent_gains[i+1] for i in range(len(recent_gains)-1))
                if momentum_slowing and max(recent_gains) < 0.02:  # 动量持续减缓
                    return {
                        'symbol': symbol,
                        'signal_type': 'MOMENTUM_DECAY',
                        'action': 'SELL',
                        'price': latest['Close'],
                        'confidence': 0.5,
                        'reason': "动量衰竭，上涨动能减弱"
                    }
        
        return None
    
    def is_late_session(self, current_time: datetime = None) -> bool:
        """判断是否接近收盘（仅用于避免开新仓，不平仓）"""
        if current_time is None:
            current_time = datetime.now()
        
        current_time_of_day = current_time.time()
        avoid_minutes = self.config.get('avoid_late_trade_minutes', 30)
        
        # 计算收盘时间（假设15:00收盘）
        close_time = dt_time(15, 0, 0)
        
        # 计算距离收盘的时间差（分钟）
        close_datetime = datetime.combine(current_time.date(), close_time)
        minutes_to_close = (close_datetime - current_time).total_seconds() / 60
        
        return minutes_to_close <= avoid_minutes
    
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
            if avg_volume < self.config['min_volume']:
                return signals
        
        # 分析市场状态
        market_regime = self.analyze_market_regime(data)
        
        # 获取ATR
        atr = indicators.get('ATR', data['Close'].std() * 0.01)
        
        # 检查是否有持仓需要卖出
        if symbol in self.positions and len(data) > 0:
            current_price = data['Close'].iloc[-1]
            current_time = datetime.now()
            
            # 检查退出条件（无尾盘强制平仓）
            exit_signal = self.check_exit_conditions(
                symbol, current_price, current_time, indicators, market_regime
            )
            if exit_signal:
                exit_signal['position_size'] = abs(self.positions[symbol]['size'])
                signals.append(exit_signal)
            
            # 检测逆势卖出信号
            counter_sell = self.detect_counter_trend_sell(symbol, data, indicators)
            if counter_sell:
                counter_sell['position_size'] = abs(self.positions[symbol]['size'])
                signals.append(counter_sell)
        
        # 只在没有持仓时生成买入信号
        if symbol not in self.positions:
            current_time = datetime.now()
            
            # 避免在接近收盘时开新仓
            if self.is_late_session(current_time):
                logger.debug(f"⏰ {symbol} 接近收盘，避免开新仓")
                return signals
            
            # 早盘动量信号
            morning_signal = self.detect_morning_momentum(symbol, data, indicators)
            if morning_signal:
                signal_hash = self._generate_signal_hash(morning_signal)
                if not self._is_signal_cooldown(signal_hash) and signal_hash not in self.executed_signals:
                    morning_signal['position_size'] = self.calculate_position_size(morning_signal, atr)
                    morning_signal['signal_hash'] = signal_hash
                    if morning_signal['position_size'] > 0:
                        signals.append(morning_signal)
                        self.executed_signals.add(signal_hash)
            
            # 午盘/尾盘反转信号
            reversal_signal = self.detect_afternoon_reversal(symbol, data, indicators)
            if reversal_signal:
                signal_hash = self._generate_signal_hash(reversal_signal)
                if not self._is_signal_cooldown(signal_hash) and signal_hash not in self.executed_signals:
                    reversal_signal['position_size'] = self.calculate_position_size(reversal_signal, atr)
                    reversal_signal['signal_hash'] = signal_hash
                    if reversal_signal['position_size'] > 0:
                        signals.append(reversal_signal)
                        self.executed_signals.add(signal_hash)
        
        # 记录信号统计
        if signals:
            self.signals_generated += len(signals)
        
        return signals
    
    def calculate_position_size(self, signal: Dict, atr: float = None) -> float:
        """根据风险计算仓位大小"""
        if atr is None:
            atr = signal.get('price', 100) * 0.02  # 默认2%波动
        
        # 基础仓位计算
        risk_amount = self.current_capital * self.config['risk_per_trade']
        
        # 根据信号类型和置信度调整
        confidence = signal.get('confidence', 0.5)
        
        if signal['signal_type'] == 'MORNING_MOMENTUM':
            # 早盘动量使用较小的仓位
            base_position = risk_amount / (atr * self.config['stop_loss_atr_multiple'])
            adjusted_position = base_position * confidence * 0.8
        elif signal['signal_type'] == 'AFTERNOON_REVERSAL':
            # 反转信号使用正常仓位
            base_position = risk_amount / (atr * self.config['stop_loss_atr_multiple'])
            adjusted_position = base_position * confidence
        else:
            base_position = risk_amount / (atr * self.config['stop_loss_atr_multiple'])
            adjusted_position = base_position * 0.7
        
        # 应用上限
        max_position = min(
            self.current_capital * self.config['max_position_size'],
            self.config['per_trade_notional_cap'] / signal['price']
        )
        
        final_position = min(adjusted_position, max_position)
        
        # 如果是卖出信号，使用持仓大小
        if signal.get('action') == 'SELL' and 'symbol' in signal:
            if signal['symbol'] in self.positions:
                return abs(self.positions[signal['symbol']]['size'])
        
        return max(0, int(final_position))
    
    # 以下是从原策略A1复制过来的方法，确保兼容性
    def detect_morning_momentum(self, symbol: str, data: pd.DataFrame, 
                               indicators: Dict) -> Optional[Dict]:
        """
        检测早盘动量信号
        """
        if len(data) < 10:
            return None
        
        if symbol in self.positions:
            return None
        
        latest = data.iloc[-1]
        
        # RSI条件
        rsi = indicators.get('RSI', 50)
        if not (50 <= rsi <= 67):
            return None
        
        # 价格偏离均线
        ma_key = 'MA_20'
        if ma_key not in indicators or indicators[ma_key] is None:
            return None
        
        price_deviation = (latest['Close'] - indicators[ma_key]) / indicators[ma_key] * 100
        if abs(price_deviation) < 0.3:
            return None
        
        # 成交量确认
        if 'Volume' in data.columns and len(data) >= 5:
            recent_volume = data['Volume'].iloc[-5:].mean()
            if latest['Volume'] < recent_volume * 1.05:
                return None
        
        # 计算信号强度
        confidence = 0.5
        if price_deviation > 0:
            confidence += min(price_deviation / 5.0, 0.3)
        if rsi > 55:
            confidence += 0.1
        
        logger.info(f"✅ {symbol} 早盘动量信号，置信度: {confidence:.2f}")
        
        signal = {
            'symbol': symbol,
            'signal_type': 'MORNING_MOMENTUM',
            'action': 'BUY' if price_deviation > 0 else 'SELL',
            'price': latest['Close'],
            'confidence': min(confidence, 0.9),
            'reason': f"早盘动量: 价格偏离MA20 {price_deviation:.1f}%, RSI {rsi:.1f}",
            'indicators': {
                'rsi': rsi,
                'price_deviation': price_deviation,
                'ma20': indicators[ma_key]
            }
        }
        
        return signal
    
    def detect_afternoon_reversal(self, symbol: str, data: pd.DataFrame,
                                 indicators: Dict) -> Optional[Dict]:
        """
        检测午盘/尾盘反转信号
        """
        if symbol in self.positions:
            return None
        
        latest = data.iloc[-1]
        
        # RSI极端条件
        rsi = indicators.get('RSI', 50)
        is_overbought = rsi > self.config['rsi_overbought']
        is_oversold = rsi < self.config['rsi_oversold']
        
        if not (is_overbought or is_oversold):
            return None
        
        # 价格位置
        lookback = min(20, len(data))
        recent_high = data['High'].iloc[-lookback:].max()
        recent_low = data['Low'].iloc[-lookback:].min()
        
        current_price = latest['Close']
        near_high = current_price > recent_high * 0.98
        near_low = current_price < recent_low * 1.02
        
        if not ((is_overbought and near_high) or (is_oversold and near_low)):
            return None
        
        # 成交量确认
        volume_ok = True
        if 'Volume' in data.columns and len(data) >= 10:
            avg_volume = data['Volume'].iloc[-10:].mean()
            volume_ratio = latest['Volume'] / avg_volume
            volume_ok = 0.5 < volume_ratio < 2.5
        
        if not volume_ok:
            return None
        
        # 确定交易方向
        if is_overbought and near_high:
            action = 'SELL'
            reason = f"午盘反转: RSI超买 {rsi:.1f}, 接近近期高点"
            confidence = min(0.4 + (rsi - 70) / 30, 0.8)
        else:
            action = 'BUY'
            reason = f"午盘反转: RSI超卖 {rsi:.1f}, 接近近期低点"
            confidence = min(0.4 + (30 - rsi) / 30, 0.8)
        
        logger.info(f"✅ {symbol} 午盘反转信号，置信度: {confidence:.2f}")
        
        signal = {
            'symbol': symbol,
            'signal_type': 'AFTERNOON_REVERSAL',
            'action': action,
            'price': current_price,
            'confidence': confidence,
            'reason': reason,
            'indicators': {
                'rsi': rsi,
                'recent_high': recent_high,
                'recent_low': recent_low,
                'price_position': 'high' if near_high else 'low'
            }
        }
        
        return signal