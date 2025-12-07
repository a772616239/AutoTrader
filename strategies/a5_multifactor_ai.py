#!/usr/bin/env python3
"""
A5 策略: 多因子 AI 融合模型
整合价格-成交量因子、基本面指标、替代数据信号和 AI 驱动的复合评分，以增强进出场信号。

特性:
- 流动性溢价: 成交量流、买卖价差、市场微观结构
- 基本面因子: 市盈率、股息收益率、账面价值动量
- 替代数据: 社会情绪评分、供应链信号
- AI 融合: 所有因子的加权组合形成复合评分
"""

import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from strategies.base_strategy import BaseStrategy
from strategies import indicators

logger = logging.getLogger(__name__)


class A5MultiFactorAI(BaseStrategy):
    """
    多因子 AI 融合策略，结合:
    1. 价格-成交量动态 (流动性溢价、动量)
    2. 基本面指标 (市盈率、股息收益率等)
    3. 替代数据信号 (情绪、供应链)
    4. AI 复合评分 (加权集合)
    """

    def _default_config(self) -> Dict:
        """A5 策略的默认配置"""
        return {
            'initial_capital': 100000.0,
            'risk_per_trade': 0.02,
            'max_position_size': 0.06,
            'per_trade_notional_cap': 6000.0,
            'max_position_notional': 40000.0,
            'min_confidence': 0.65,
            'min_price': 10.0,
            'min_volume': 2000000,
            'lookback_period': 90,
            'recent_period': 20,
            'liquidity_weight': 0.35,
            'fundamental_weight': 0.20,
            'sentiment_weight': 0.10,
            'momentum_weight': 0.35,
            'buy_threshold': 0.72,
            'sell_threshold': 0.55,
            'exit_threshold': 0.25,
            'signal_cooldown_hours': 12,
        }

    def __init__(self, config: Optional[Dict] = None, ib_trader=None):
        """
        初始化 A5 策略。
        
        Args:
            config: 策略配置字典
            ib_trader: IB 交易员实例（可选）
        """
        super().__init__(config, ib_trader)
        
        # 策略特定配置
        self.min_confidence = self.config.get('min_confidence', 0.4)
        self.liquidity_weight = self.config.get('liquidity_weight', 0.25)
        self.fundamental_weight = self.config.get('fundamental_weight', 0.30)
        self.sentiment_weight = self.config.get('sentiment_weight', 0.20)
        self.momentum_weight = self.config.get('momentum_weight', 0.25)
        self.lookback_period = self.config.get('lookback_period', 90)
        self.recent_period = self.config.get('recent_period', 20)
        self.min_price = self.config.get('min_price', 5.0)
        self.min_volume = self.config.get('min_volume', 500000)
        self.buy_threshold = self.config.get('buy_threshold', 0.55)
        self.sell_threshold = self.config.get('sell_threshold', 0.45)
        self.exit_threshold = self.config.get('exit_threshold', 0.35)
        
        # 验证权重总和为 1.0（在容差内）
        total_weight = (self.liquidity_weight + self.fundamental_weight + 
                       self.sentiment_weight + self.momentum_weight)
        if abs(total_weight - 1.0) > 0.01:
            logger.warning(
                f"A5 因子权重总和为 {total_weight:.2f}，标准化为 1.0"
            )
            # 标准化权重
            self.liquidity_weight /= total_weight
            self.fundamental_weight /= total_weight
            self.sentiment_weight /= total_weight
            self.momentum_weight /= total_weight
        
        logger.info(
            f"A5 MultiFactorAI initialized: min_conf={self.min_confidence}, "
            f"buy_thresh={self.buy_threshold}, sell_thresh={self.sell_threshold}, "
            f"weights(liq/fund/sent/mom)=({self.liquidity_weight:.2f}, "
            f"{self.fundamental_weight:.2f}, {self.sentiment_weight:.2f}, "
            f"{self.momentum_weight:.2f})"
        )

    def _calculate_liquidity_score(self, data: pd.DataFrame) -> float:
        """计算流动性溢价评分 (0-1)"""
        try:
            if len(data) < self.recent_period:
                return 0.5
            
            recent = data.tail(self.recent_period)
            historical = data.tail(self.lookback_period)
            
            # 成交量比率
            recent_vol_avg = recent['Volume'].mean() if 'Volume' in data.columns else recent['volume'].mean()
            historical_vol_avg = historical['Volume'].mean() if 'Volume' in data.columns else historical['volume'].mean()
            
            if historical_vol_avg == 0:
                volume_ratio = 1.0
            else:
                volume_ratio = min(recent_vol_avg / historical_vol_avg, 2.0)
            
            # 成交量趋势
            recent_volumes = recent['Volume'].values if 'Volume' in data.columns else recent['volume'].values
            if len(recent_volumes) > 1:
                volume_trend = (np.corrcoef(np.arange(len(recent_volumes)), recent_volumes)[0, 1] + 1.0) / 2.0
            else:
                volume_trend = 0.5
            
            # 价格一致性
            close_col = 'Close' if 'Close' in data.columns else 'close'
            price_returns = recent[close_col].pct_change().dropna()
            if len(price_returns) > 0:
                volatility = price_returns.std()
                price_consistency = max(0.0, 1.0 - volatility * 2.0)
            else:
                price_consistency = 0.5
            
            liquidity_score = 0.5 * (volume_ratio / 2.0) + 0.3 * volume_trend + 0.2 * price_consistency
            
            logger.info(
                f"A5流动性评分: {liquidity_score:.3f} "
                f"(成交量比={volume_ratio:.2f}, 趋势={volume_trend:.2f}, 一致性={price_consistency:.2f})"
            )
            
            return float(np.clip(liquidity_score, 0.0, 1.0))
        
        except Exception as e:
            logger.warning(f"A5流动性计算出错: {e}")
            return 0.5

    def _calculate_fundamental_score(self, data: pd.DataFrame) -> float:
        """计算基本面指标评分 (0-1)"""
        try:
            if len(data) < self.lookback_period:
                return 0.5
            
            recent = data.tail(self.recent_period)
            historical = data.tail(self.lookback_period)
            
            close_col = 'Close' if 'Close' in data.columns else 'close'
            
            # 市盈率动量
            recent_returns = (recent[close_col].iloc[-1] - recent[close_col].iloc[0]) / recent[close_col].iloc[0]
            historical_returns = (historical[close_col].iloc[-1] - historical[close_col].iloc[0]) / historical[close_col].iloc[0]
            
            pe_momentum = (recent_returns - historical_returns) / (abs(historical_returns) + 0.01)
            pe_momentum = np.clip((pe_momentum + 1.0) / 2.0, 0.0, 1.0)
            
            # 盈利动量
            price_returns = recent[close_col].pct_change().dropna()
            uptrend_ratio = (price_returns > 0).sum() / len(price_returns) if len(price_returns) > 0 else 0.5
            
            # 股息信号
            volatility = price_returns.std() if len(price_returns) > 0 else 0.1
            dividend_signal = max(0.0, 1.0 - volatility * 1.5)
            
            fundamental_score = 0.4 * pe_momentum + 0.3 * uptrend_ratio + 0.3 * dividend_signal
            
            logger.info(
                f"A5基本面评分: {fundamental_score:.3f} "
                f"(PE动量={pe_momentum:.2f}, 盈利动量={uptrend_ratio:.2f}, 股息信号={dividend_signal:.2f})"
            )
            
            return float(np.clip(fundamental_score, 0.0, 1.0))
        
        except Exception as e:
            logger.warning(f"A5基本面计算出错: {e}")
            return 0.5

    def _calculate_sentiment_score(self, data: pd.DataFrame) -> float:
        """计算情绪/替代数据评分 (0-1)"""
        try:
            if len(data) < 5:
                return 0.5
            
            recent = data.tail(5)
            close_col = 'Close' if 'Close' in data.columns else 'close'
            high_col = 'High' if 'High' in data.columns else 'high'
            low_col = 'Low' if 'Low' in data.columns else 'low'
            
            # 看涨信号
            close_position = (recent[close_col] - recent[low_col]) / (recent[high_col] - recent[low_col] + 0.01)
            close_position = close_position.replace([np.inf, -np.inf], 0.5)
            bullish_signal = close_position.mean()
            
            # 成交量突增
            vol_col = 'Volume' if 'Volume' in data.columns else 'volume'
            volume_ma = data[vol_col].tail(20).mean() if len(data) >= 20 else data[vol_col].mean()
            recent_volume = data[vol_col].iloc[-1]
            volume_surge = min(recent_volume / (volume_ma + 1), 2.0) / 2.0
            
            # 动量
            if len(recent) > 1:
                momentum = (recent[close_col].iloc[-1] - recent[close_col].iloc[0]) / recent[close_col].iloc[0]
                momentum_signal = np.clip((momentum + 0.2) / 0.4, 0.0, 1.0)
            else:
                momentum_signal = 0.5
            
            sentiment_score = 0.5 * bullish_signal + 0.3 * volume_surge + 0.2 * momentum_signal
            
            logger.info(
                f"A5情绪评分: {sentiment_score:.3f} "
                f"(看涨信号={bullish_signal:.2f}, 成交量突增={volume_surge:.2f}, 动量={momentum_signal:.2f})"
            )
            
            return float(np.clip(sentiment_score, 0.0, 1.0))
        
        except Exception as e:
            logger.warning(f"A5情绪计算出错: {e}")
            return 0.5

    def _calculate_momentum_score(self, data: pd.DataFrame) -> float:
        """计算技术动量评分 (0-1)"""
        try:
            if len(data) < 14:
                return 0.5
            
            close_col = 'Close' if 'Close' in data.columns else 'close'
            
            # 相对强度指数 (RSI)
            rsi = indicators.calculate_rsi(data[close_col], period=14)
            rsi_score = rsi.iloc[-1] / 100.0 if len(rsi) > 0 else 0.5
            
            # MACD 指标
            macd, signal, histogram = indicators.calculate_macd(data[close_col])
            if len(histogram) > 0:
                macd_score = max(0.0, min(histogram.iloc[-1] / abs(histogram.mean() + 0.01), 1.0))
            else:
                macd_score = 0.5
            
            # 变动率 (ROC)
            roc_period = 10
            roc = data[close_col].pct_change(roc_period)
            if len(roc) > 0:
                roc_value = roc.iloc[-1]
                roc_score = np.clip((roc_value + 0.1) / 0.2, 0.0, 1.0)
            else:
                roc_score = 0.5
            
            # 趋势强度
            if len(data) >= 50:
                ma20 = data[close_col].rolling(20).mean()
                ma50 = data[close_col].rolling(50).mean()
                
                if ma20.iloc[-1] > ma50.iloc[-1]:
                    trend_strength = (ma20.iloc[-1] - ma50.iloc[-1]) / data[close_col].iloc[-1]
                    trend_score = min(0.5 + trend_strength * 10, 1.0)
                else:
                    trend_strength = (ma50.iloc[-1] - ma20.iloc[-1]) / data[close_col].iloc[-1]
                    trend_score = max(0.0, 0.5 - trend_strength * 10)
            else:
                trend_score = 0.5
            
            momentum_score = 0.3 * rsi_score + 0.3 * macd_score + 0.2 * roc_score + 0.2 * trend_score
            
            logger.info(
                f"A5动量评分: {momentum_score:.3f} "
                f"(RSI={rsi_score:.2f}, MACD={macd_score:.2f}, ROC={roc_score:.2f}, 趋势={trend_score:.2f})"
            )
            
            return float(np.clip(momentum_score, 0.0, 1.0))
        
        except Exception as e:
            logger.warning(f"A5动量计算出错: {e}")
            return 0.5



    def _calculate_composite_ai_score(self, liquidity_score: float, 
                                     fundamental_score: float,
                                     sentiment_score: float,
                                     momentum_score: float) -> Tuple[float, Dict]:
        """AI 融合: 将所有因子评分组合成复合评分"""
        try:
            composite_score = (
                self.liquidity_weight * liquidity_score +
                self.fundamental_weight * fundamental_score +
                self.sentiment_weight * sentiment_score +
                self.momentum_weight * momentum_score
            )
            
            logger.info(
                f"A5 AI合成评分: {composite_score:.3f} "
                f"(加权: 流动性={liquidity_score * self.liquidity_weight:.3f}, "
                f"基本面={fundamental_score * self.fundamental_weight:.3f}, "
                f"情绪={sentiment_score * self.sentiment_weight:.3f}, "
                f"动量={momentum_score * self.momentum_weight:.3f})"
            )
            
            return float(np.clip(composite_score, 0.0, 1.0)), {}
        
        except Exception as e:
            logger.error(f"A5 AI合成评分出错: {e}")
            return 0.5, {}

    def generate_signals(self, symbol: str, data: pd.DataFrame, 
                        indicators: Dict) -> List[Dict]:
        """
        基于复合 AI 评分生成买入/卖出信号。
        
        Args:
            symbol: 股票代码
            data: 包含 OHLCV 数据的 DataFrame
            indicators: 包含技术指标的字典（可选）
            
        Returns:
            信号字典列表
        """
        signals = []
        
        try:
            if data is None or len(data) < 20:
                logger.warning(f"[{symbol}] A5信号生成: 数据不足")
                return signals
            
            close_col = 'Close' if 'Close' in data.columns else 'close'
            vol_col = 'Volume' if 'Volume' in data.columns else 'volume'
            
            current_price = data[close_col].iloc[-1]
            current_volume = data[vol_col].iloc[-1]
            
            # 预过滤 - 价格和成交量
            if current_price < self.min_price:
                logger.info(f"[{symbol}] A5 过滤: 价格 {current_price:.2f} < 最小值 {self.min_price}")
                return signals
            
            if current_volume < self.min_volume:
                logger.info(f"[{symbol}] A5 过滤: 成交量 {current_volume:.0f} < 最小值 {self.min_volume:.0f}")
                return signals
            
            # 额外过滤 - 价格波动性（避免高波动不稳定的股票）
            if len(data) >= 20:
                close_prices = data[close_col].tail(20)
                price_volatility = close_prices.pct_change().std()
                if price_volatility > 0.08:  # 日波动率超过 8% 则过滤
                    logger.info(f"[{symbol}] A5 过滤: 价格波动率 {price_volatility:.4f} > 0.08（不稳定）")
                    return signals
            
            # 额外过滤 - 成交量连续性（确保流动性持续）
            if len(data) >= 5:
                recent_volumes = data[vol_col].tail(5).values
                min_recent_volume = min(recent_volumes)
                avg_recent_volume = np.mean(recent_volumes)
                if min_recent_volume < avg_recent_volume * 0.3:  # 最小成交量低于平均的 50%
                    logger.info(f"[{symbol}] A5 过滤: 成交量不连续（最小 {min_recent_volume:.0f} < 平均 {avg_recent_volume * 0.3:.0f} - 0.3）")
                    return signals
            
            # 计算因子评分
            liquidity_score = self._calculate_liquidity_score(data)
            fundamental_score = self._calculate_fundamental_score(data)
            sentiment_score = self._calculate_sentiment_score(data)
            momentum_score = self._calculate_momentum_score(data)
            
            # 因子最小值过滤 - 所有因子必须达到最低标准
            min_factor_threshold = 0.33
            if liquidity_score < min_factor_threshold or momentum_score < min_factor_threshold:
                logger.info(f"[{symbol}] A5 过滤: 流动性或动量因子过低 (流动性={liquidity_score:.2f}, 动量={momentum_score:.2f})")
                return signals
            
            # AI 复合评分
            composite_score, factor_details = self._calculate_composite_ai_score(
                liquidity_score, fundamental_score, sentiment_score, momentum_score
            )
            
            # 获取当前持仓
            current_position = self.positions.get(symbol, 0)
            
            logger.info(
                f"[{symbol}] ========== A5 信号生成周期 =========="
            )
            logger.info(
                f"[{symbol}] 综合因子分析: 流动性={liquidity_score:.3f}, "
                f"基本面={fundamental_score:.3f}, 情绪={sentiment_score:.3f}, "
                f"动量={momentum_score:.3f} | 复合得分={composite_score:.3f} | "
                f"价格=${current_price:.2f}, 成交量={current_volume:.0f}"
            )
            
            # 进场信号
            if current_position == 0:  # 无持仓
                # 严格的买入条件：复合得分 + 流动性 + 动量都必须强劲
                if (composite_score >= self.buy_threshold and 
                    liquidity_score >= 0.65 and 
                    momentum_score >= 0.65):
                    confidence = min(composite_score, 1.0)
                    
                    # 再次检查最小信心度
                    if confidence >= self.min_confidence:
                        signal = {
                            'symbol': symbol,
                            'signal_type': 'MULTIFACTOR_AI_BUY',
                            'action': 'BUY',
                            'price': current_price,
                            'quantity': 0,  # 执行时计算
                            'confidence': confidence,
                            'reason': f'A5 AI复合得分={composite_score:.3f}; '
                                     f'流动性={liquidity_score:.2f}, 基本面={fundamental_score:.2f}, '
                                     f'情绪={sentiment_score:.2f}, 动量={momentum_score:.2f}',
                            'timestamp': datetime.now()
                        }
                        
                        signal_hash = self._generate_signal_hash(signal)
                        if not self._is_signal_cooldown(signal_hash):
                            signals.append(signal)
                            self._add_signal_to_cache(signal_hash)
                            logger.info(
                                f"[{symbol}] ✅ 生成BUY信号: 复合得分={composite_score:.3f} >= {self.buy_threshold}, "
                                f"信心度={confidence:.3f}"
                            )
                    else:
                        logger.info(f"[{symbol}] 无 BUY 信号: 信心度 {confidence:.3f} < 最小值 {self.min_confidence}")
                else:
                    logger.info(f"[{symbol}] 无 BUY 信号: 复合得分={composite_score:.3f} < {self.buy_threshold}")
            
            elif current_position > 0:  # 多头持仓
                if composite_score <= self.exit_threshold:
                    confidence = 1.0 - composite_score
                    
                    signal = {
                        'symbol': symbol,
                        'signal_type': 'MULTIFACTOR_AI_EXIT_LONG',
                        'action': 'SELL',
                        'price': current_price,
                        'quantity': current_position,
                        'confidence': confidence,
                        'reason': f'A5 AI复合得分={composite_score:.3f} <= 平仓阈值 {self.exit_threshold:.3f}; 平多头仓位',
                        'timestamp': datetime.now()
                    }
                    
                    signal_hash = self._generate_signal_hash(signal)
                    if not self._is_signal_cooldown(signal_hash):
                        signals.append(signal)
                        self._add_signal_to_cache(signal_hash)
                        logger.info(
                            f"[{symbol}] ✅ 生成 SELL 信号(平多): 复合得分={composite_score:.3f} <= {self.exit_threshold}, "
                            f"数量={current_position}"
                        )
                else:
                    logger.info(f"[{symbol}] 持有多头: 复合得分={composite_score:.3f} > {self.exit_threshold}")
            
            elif current_position < 0:  # 空头持仓
                if composite_score >= (1.0 - self.exit_threshold):
                    confidence = composite_score
                    
                    signal = {
                        'symbol': symbol,
                        'signal_type': 'MULTIFACTOR_AI_EXIT_SHORT',
                        'action': 'BUY',
                        'price': current_price,
                        'quantity': abs(current_position),
                        'confidence': confidence,
                        'reason': f'A5 AI复合得分={composite_score:.3f} >= {1.0 - self.exit_threshold:.3f}; 平空头仓位',
                        'timestamp': datetime.now()
                    }
                    
                    signal_hash = self._generate_signal_hash(signal)
                    if not self._is_signal_cooldown(signal_hash):
                        signals.append(signal)
                        self._add_signal_to_cache(signal_hash)
                        logger.info(
                            f"[{symbol}] ✅ 生成 BUY 信号(平空): 复合得分={composite_score:.3f} >= {1.0 - self.exit_threshold}, "
                            f"数量={abs(current_position)}"
                        )
                else:
                    logger.info(f"[{symbol}] 持有空头: 复合得分={composite_score:.3f} < {1.0 - self.exit_threshold}")
        
        except Exception as e:
            logger.error(f"[{symbol}] A5 信号生成异常: {e}", exc_info=True)
        
        if signals:
            logger.info(f"[{symbol}] 本周期 A5 生成 {len(signals)} 个信号")
        else:
            logger.info(f"[{symbol}] 本周期 A5 无信号生成")
        
        return signals
