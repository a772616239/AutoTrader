#!/usr/bin/env python3
"""
A18: Isolation Forest 异常检测交易策略

基于机器学习的异常检测策略，使用Isolation Forest算法识别价格异常，
当检测到异常时进行交易。

策略逻辑:
- 使用Isolation Forest检测价格异常
- 异常价格高于均价时卖出
- 异常价格低于均价且冷却期结束后买入
- 包含7天的交易冷却机制
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
from sklearn.ensemble import IsolationForest

from .base_strategy import BaseStrategy
from .indicators import calculate_atr

logger = logging.getLogger(__name__)

class IsolationForestModel:
    """Isolation Forest 模型封装"""

    def __init__(self, data, contamination=0.001, behaviour="new"):
        """
        初始化Isolation Forest模型

        Args:
            data: 训练数据
            contamination: 异常值比例
            behaviour: 模型行为参数
        """
        normalized_data = (data - data.mean()) / data.std()
        self.iso = IsolationForest(contamination=contamination, behaviour=behaviour, random_state=42)
        self.iso.fit(normalized_data)
        self.data_mean = data.mean()
        self.data_std = data.std()

    def predict_outlier(self, data):
        """
        预测数据点是否为异常值

        Args:
            data: 输入数据

        Returns:
            int: -1表示异常，1表示正常
        """
        normalized_data = (data - self.data_mean) / self.data_std
        return self.iso.predict(normalized_data)

class A18IsolationForestStrategy(BaseStrategy):
    """A18: Isolation Forest 异常检测交易策略"""

    def _default_config(self) -> Dict:
        """默认配置"""
        config = super()._default_config()
        config.update({
            'contamination': 0.001,  # 异常值比例
            'cooldown_days': 7,      # 交易冷却期（天）
            'min_data_points': 50,   # 最小数据点数量
            'model_retrain_days': 30,  # 模型重训练间隔（天）
            'stop_loss_pct': 0.02,   # 止损百分比
            'take_profit_pct': 0.05, # 止盈百分比
        })
        return config

    def __init__(self, config: Dict = None, ib_trader=None):
        super().__init__(config, ib_trader)

        # 模型缓存
        self.models = {}  # symbol -> {'model': IsolationForestModel, 'last_train': datetime}
        self.cooldowns = {}  # symbol -> cooldown_end_time

        logger.info("A18 IsolationForest策略初始化完成")

    def _should_retrain_model(self, symbol: str) -> bool:
        """检查是否需要重训练模型"""
        if symbol not in self.models:
            return True

        last_train = self.models[symbol]['last_train']
        retrain_interval = timedelta(days=self.config.get('model_retrain_days', 30))
        return datetime.now() - last_train > retrain_interval

    def _train_model(self, symbol: str, data: pd.DataFrame) -> bool:
        """
        训练Isolation Forest模型

        Args:
            symbol: 股票代码
            data: 历史数据

        Returns:
            bool: 训练是否成功
        """
        try:
            if len(data) < self.config.get('min_data_points', 50):
                logger.warning(f"{symbol} 数据点不足({len(data)})，跳过模型训练")
                return False

            # 准备训练数据：开盘价、最高价、最低价、收盘价、成交量
            train_data = data[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()

            if len(train_data) < self.config.get('min_data_points', 50):
                logger.warning(f"{symbol} 有效数据点不足({len(train_data)})，跳过模型训练")
                return False

            # 训练模型
            logger.debug(f"🤖 {symbol} 开始训练IsolationForest模型 - 污染率: {self.config.get('contamination', 0.001)}")
            model = IsolationForestModel(
                train_data,
                contamination=self.config.get('contamination', 0.001)
            )

            self.models[symbol] = {
                'model': model,
                'last_train': datetime.now()
            }

            logger.info(f"✅ {symbol} IsolationForest模型训练完成，使用{len(train_data)}个数据点，历史均价: ${model.data_mean['Close']:.2f}")
            return True

        except Exception as e:
            logger.error(f"训练{symbol}模型时出错: {e}")
            return False

    def _is_in_cooldown(self, symbol: str) -> bool:
        """检查是否在交易冷却期"""
        if symbol not in self.cooldowns:
            return False
        return datetime.now() < self.cooldowns[symbol]

    def _set_cooldown(self, symbol: str):
        """设置交易冷却期"""
        cooldown_end = datetime.now() + timedelta(days=self.config.get('cooldown_days', 7))
        self.cooldowns[symbol] = cooldown_end
        logger.info(f"🔄 {symbol} 进入冷却期至 {cooldown_end.strftime('%Y-%m-%d %H:%M')}")

    def generate_signals(self, symbol: str, data: pd.DataFrame,
                        indicators: Dict) -> List[Dict]:
        """
        生成交易信号

        Args:
            symbol: 股票代码
            data: 价格数据
            indicators: 技术指标数据

        Returns:
            List[Dict]: 交易信号列表
        """
        signals = []

        try:
            # 检查数据是否足够
            if len(data) < self.config.get('min_data_points', 50):
                logger.debug(f"{symbol} 数据不足，跳过信号生成")
                return signals

            # 检查是否在冷却期
            if self._is_in_cooldown(symbol):
                logger.debug(f"{symbol} 正在冷却期，跳过信号生成")
                return signals

            # 检查是否需要重训练模型
            if self._should_retrain_model(symbol):
                if not self._train_model(symbol, data):
                    return signals

            model_info = self.models.get(symbol)
            if not model_info:
                logger.warning(f"{symbol} 模型不存在")
                return signals

            model = model_info['model']

            # 获取最新数据点
            latest_data = data.iloc[-1]
            current_price = latest_data['Close']

            # 准备预测数据
            predict_data = pd.DataFrame([[
                latest_data['Open'],
                latest_data['High'],
                latest_data['Low'],
                latest_data['Close'],
                latest_data['Volume']
            ]], columns=['Open', 'High', 'Low', 'Close', 'Volume'])

            # 预测是否为异常
            prediction = model.predict_outlier(predict_data)

            if prediction == -1:  # 检测到异常
                logger.info(f"🚨 {symbol} 检测到价格异常 @ ${current_price:.2f}")

                # 计算历史均价
                historical_mean = model.data_mean['Close']

                # 计算ATR用于仓位管理
                atr = calculate_atr(data['High'], data['Low'], data['Close']).iloc[-1]
                if np.isnan(atr) or atr <= 0:
                    atr = current_price * 0.02  # 默认2%的ATR

                if current_price > historical_mean:
                    # 价格异常且高于均价 - 卖出信号
                    signal = {
                        'symbol': symbol,
                        'signal_type': 'ISOLATION_FOREST_OUTLIER_SELL',
                        'action': 'SELL',
                        'price': current_price,
                        'reason': f'IsolationForest检测到异常: 价格${current_price:.2f}高于均价${historical_mean:.2f}',
                        'confidence': 0.8,
                        'atr': atr
                    }
                    signals.append(signal)
                    logger.info(f"📈 {symbol} 生成卖出信号 - 异常高价")

                elif not self._is_in_cooldown(symbol):
                    # 价格异常且低于均价且不在冷却期 - 买入信号
                    signal = {
                        'symbol': symbol,
                        'signal_type': 'ISOLATION_FOREST_OUTLIER_BUY',
                        'action': 'BUY',
                        'price': current_price,
                        'reason': f'IsolationForest检测到异常: 价格${current_price:.2f}低于均价${historical_mean:.2f}',
                        'confidence': 0.7,
                        'atr': atr
                    }
                    signals.append(signal)
                    logger.info(f"📉 {symbol} 生成买入信号 - 异常低价")

                    # 设置冷却期
                    self._set_cooldown(symbol)

        except Exception as e:
            logger.error(f"生成{symbol}信号时出错: {e}")
            import traceback
            logger.debug(traceback.format_exc())

        return signals

    def calculate_position_size(self, signal: Dict, atr: float = None) -> int:
        """计算仓位大小 - 使用ATR进行风险管理"""
        if atr is None:
            atr = signal.get('atr', signal['price'] * 0.02)

        # 使用基础类的仓位计算，但传入ATR
        return super().calculate_position_size(signal, atr)

    def check_exit_conditions(self, symbol: str, current_price: float,
                            current_time: datetime = None) -> Optional[Dict]:
        """检查退出条件 - 添加异常检测特定的退出逻辑"""
        # 首先检查基础退出条件
        base_exit = super().check_exit_conditions(symbol, current_price, current_time)
        if base_exit:
            return base_exit

        # IsolationForest特定的退出条件
        if symbol in self.positions:
            position = self.positions[symbol]
            entry_time = position.get('entry_time', datetime.now() - timedelta(hours=1))

            # 如果持仓时间超过一定天数，检查是否仍然异常
            holding_days = (datetime.now() - entry_time).total_seconds() / (24 * 3600)
            if holding_days > 1:  # 持仓超过1天
                try:
                    # 如果当前价格不再异常，可以考虑退出
                    if symbol in self.models:
                        model = self.models[symbol]['model']
                        historical_mean = model.data_mean['Close']

                        # 如果价格回到正常范围附近，退出
                        if abs(current_price - historical_mean) / historical_mean < 0.02:  # 2%以内
                            return {
                                'symbol': symbol,
                                'signal_type': 'ISOLATION_FOREST_NORMALIZED',
                                'action': 'SELL' if position['size'] > 0 else 'BUY',
                                'price': current_price,
                                'reason': f'价格已回到正常范围: ${current_price:.2f} vs 均价${historical_mean:.2f}',
                                'position_size': abs(position['size']),
                                'profit_pct': 0.0,  # 中性退出
                                'confidence': 0.6
                            }
                except Exception as e:
                    logger.debug(f"检查{symbol}异常恢复时出错: {e}")

        return None