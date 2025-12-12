#!/usr/bin/env python3
"""
MLP神经网络策略 (A35)
基于scikit-learn多层感知器神经网络的价格预测策略
"""
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error

from strategies.base_strategy import BaseStrategy

logger = logging.getLogger(__name__)

class A35MLPNeuralNetworkStrategy(BaseStrategy):
    """A35: MLP神经网络价格预测策略"""

    def _default_config(self) -> Dict:
        """默认配置"""
        from config import CONFIG
        strategy_key = 'strategy_a35'
        if strategy_key in CONFIG:
            return CONFIG[strategy_key]
        else:
            return {
                # 资金管理
                'initial_capital': 40000.0,
                'risk_per_trade': 0.02,
                'max_position_size': 0.1,
                'per_trade_notional_cap': 4000.0,
                'max_position_notional': 60000.0,

                # MLP神经网络参数
                'lookback_period': 30,  # 训练数据回溯期
                'prediction_horizon': 1,  # 预测期（天）
                'retrain_frequency': 10,  # 每10个交易日重新训练模型
                'prediction_threshold': 0.025,  # 预测价格变化阈值（2.5%）

                # 神经网络架构
                'hidden_layers': (100, 50, 25),  # 更深的隐藏层结构
                'activation': 'relu',  # 激活函数
                'solver': 'adam',  # 优化器
                'max_iter': 1000,  # 增加最大迭代次数
                'learning_rate': 'adaptive',  # 学习率策略
                'alpha': 0.0001,  # L2正则化参数
                'early_stopping': True,  # 启用早停
                'validation_fraction': 0.2,  # 验证集比例

                # 风险管理
                'stop_loss_pct': 0.03,
                'take_profit_pct': 0.06,
                'max_holding_minutes': 300,  # 5小时

                # 防重复交易
                'signal_cooldown_minutes': 45,

                # 交易参数
                'min_volume': 10000,
                'min_data_points': 60,  # 需要更多数据训练神经网络

                # IB交易参数
                'ib_order_type': 'MKT',
                'ib_limit_offset': 0.01,
            }

    def __init__(self, config: Dict = None, ib_trader=None):
        super().__init__(config, ib_trader)

        # 模型相关
        self.model = None
        self.scaler = StandardScaler()
        self.last_trained = None
        self.prediction_history = []

        logger.info("A35 MLP神经网络策略初始化完成")

    def _prepare_features(self, data: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """准备特征数据 - 简化的特征集"""
        try:
            close_prices = data['Close'].values
            high_prices = data['High'].values
            low_prices = data['Low'].values
            open_prices = data['Open'].values if 'Open' in data.columns else close_prices
            volume = data['Volume'].values if 'Volume' in data.columns else np.ones(len(data))

            # 简化的特征集
            features = []

            # 基础价格特征
            features.append(close_prices)
            features.append(high_prices)
            features.append(low_prices)
            features.append(open_prices)
            features.append(volume)

            # 简单移动平均
            for period in [5, 10, 20]:
                if len(close_prices) >= period:
                    sma = pd.Series(close_prices).rolling(period).mean().fillna(close_prices[-1]).values
                    features.append(sma)
                else:
                    features.append(np.full(len(close_prices), close_prices[-1]))

            # 价格动量
            if len(close_prices) > 1:
                momentum = np.diff(close_prices, prepend=close_prices[0])
                features.append(momentum)
            else:
                features.append(np.zeros(len(close_prices)))

            # 波动率 (简化计算)
            if len(close_prices) >= 5:
                returns = np.diff(close_prices) / close_prices[:-1]
                volatility = pd.Series(returns).rolling(5).std().fillna(0.02).values
                # 确保长度一致
                if len(volatility) < len(close_prices):
                    volatility = np.concatenate([np.full(len(close_prices) - len(volatility), 0.02), volatility])
                features.append(volatility)
            else:
                features.append(np.full(len(close_prices), 0.02))

            # 组合特征
            X = np.column_stack(features)

            # 处理NaN值
            X = np.nan_to_num(X, nan=0.0)

            # 目标变量：未来N天的价格变化百分比
            horizon = self.config.get('prediction_horizon', 1)
            if len(close_prices) > horizon:
                future_prices = np.roll(close_prices, -horizon)
                future_prices[-horizon:] = close_prices[-1]
                y = (future_prices - close_prices) / close_prices
            else:
                y = np.zeros(len(close_prices))

            return X, y

        except Exception as e:
            logger.error(f"准备特征数据时出错: {e}")
            return np.array([]), np.array([])

    def _calculate_rsi_for_features(self, prices: np.ndarray, period: int) -> np.ndarray:
        """计算RSI用于特征工程"""
        rsi = np.full(len(prices), 50.0)  # 默认中性值

        if len(prices) < period + 1:
            return rsi

        gains = np.zeros(len(prices))
        losses = np.zeros(len(prices))

        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            if change > 0:
                gains[i] = change
            else:
                losses[i] = abs(change)

        # 计算初始平均值
        avg_gain = np.mean(gains[1:period+1])
        avg_loss = np.mean(losses[1:period+1])

        if avg_loss == 0:
            rsi[period] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[period] = 100 - (100 / (1 + rs))

        # 计算后续值
        for i in range(period+1, len(prices)):
            avg_gain = (avg_gain * (period-1) + gains[i]) / period
            avg_loss = (avg_loss * (period-1) + losses[i]) / period

            if avg_loss == 0:
                rsi[i] = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi[i] = 100 - (100 / (1 + rs))

        return rsi

    def _train_model(self, data: pd.DataFrame) -> bool:
        """训练MLP神经网络模型"""
        try:
            if len(data) < self.config.get('min_data_points', 60):
                logger.warning(f"数据点不足({len(data)})，跳过模型训练")
                return False

            # 准备训练数据
            X, y = self._prepare_features(data)

            if len(X) == 0 or len(y) == 0:
                logger.warning("特征准备失败，跳过模型训练")
                return False

            # 数据标准化
            X_scaled = self.scaler.fit_transform(X)

            # 创建和训练MLP模型
            hidden_layers = self.config.get('hidden_layers', (100, 50, 25))
            self.model = MLPRegressor(
                hidden_layer_sizes=hidden_layers,
                activation=self.config.get('activation', 'relu'),
                solver=self.config.get('solver', 'adam'),
                max_iter=self.config.get('max_iter', 1000),
                learning_rate=self.config.get('learning_rate', 'adaptive'),
                alpha=self.config.get('alpha', 0.0001),
                random_state=42,
                early_stopping=self.config.get('early_stopping', True),
                validation_fraction=self.config.get('validation_fraction', 0.2),
                n_iter_no_change=10
            )

            self.model.fit(X_scaled, y)

            # 记录训练时间
            self.last_trained = datetime.now()

            # 计算训练误差
            y_pred = self.model.predict(X_scaled)
            mse = mean_squared_error(y, y_pred)
            rmse = np.sqrt(mse)

            logger.info(f"✅ A35 MLP神经网络模型训练完成 - MSE: {mse:.6f}, RMSE: {rmse:.6f}, "
                       f"数据点: {len(X)}, 隐藏层: {hidden_layers}")
            return True

        except Exception as e:
            logger.error(f"训练模型时出错: {e}")
            return False

    def _should_retrain(self) -> bool:
        """检查是否需要重新训练模型"""
        if self.last_trained is None:
            return True

        retrain_freq = self.config.get('retrain_frequency', 10)
        days_since_train = (datetime.now() - self.last_trained).days

        return days_since_train >= retrain_freq

    def _predict_price_change(self, data: pd.DataFrame) -> float:
        """预测价格变化"""
        try:
            if self.model is None:
                return 0.0

            # 准备预测数据
            latest_data = data.tail(1).copy()
            X, _ = self._prepare_features(latest_data)

            if len(X) == 0:
                return 0.0

            # 标准化并预测
            X_scaled = self.scaler.transform(X)
            prediction = self.model.predict(X_scaled)[0]

            return float(prediction)

        except Exception as e:
            logger.error(f"预测价格变化时出错: {e}")
            return 0.0

    def generate_signals(self, symbol: str, data: pd.DataFrame,
                        indicators: Dict) -> List[Dict]:
        """生成交易信号"""
        signals = []

        try:
            # 基本数据检查
            if data.empty or len(data) < self.config.get('min_data_points', 60):
                return signals

            # 检查成交量
            if not self._is_pre_market_hours() and 'Volume' in data.columns:
                avg_volume = data['Volume'].rolling(window=10).mean().iloc[-1]
                if pd.isna(avg_volume) or avg_volume < self.config['min_volume']:
                    return signals

            # 检查是否需要重新训练模型
            if self._should_retrain():
                if not self._train_model(data):
                    logger.warning(f"{symbol} 模型训练失败，跳过信号生成")
                    return signals

            # 获取当前价格
            current_price = data['Close'].iloc[-1]

            # 预测价格变化
            predicted_change = self._predict_price_change(data)
            predicted_price = current_price * (1 + predicted_change)

            logger.info(f"🧠 {symbol} A35 神经网络预测 - 当前价格: {current_price:.2f}, "
                       f"预测变化: {predicted_change:.4f} ({predicted_change*100:.2f}%), "
                       f"预测价格: {predicted_price:.2f}")

            # 检查现有持仓的退出条件
            if symbol in self.positions:
                exit_signal = self.check_exit_conditions(symbol, current_price)
                if exit_signal:
                    exit_signal['position_size'] = abs(self.positions[symbol]['size'])
                    signals.append(exit_signal)

            # 只在没有持仓时生成买入信号
            if symbol not in self.positions:
                threshold = self.config.get('prediction_threshold', 0.025)

                if predicted_change > threshold:
                    # 预测上涨 - 买入信号
                    confidence = min(predicted_change * 4, 0.9)

                    signal = {
                        'symbol': symbol,
                        'signal_type': 'MLP_NN_BUY',
                        'action': 'BUY',
                        'price': current_price,
                        'confidence': confidence,
                        'reason': f'MLP神经网络预测上涨: {predicted_change*100:.2f}%',
                        'indicators': {
                            'predicted_change': predicted_change,
                            'predicted_price': predicted_price,
                            'model_trained': self.last_trained.isoformat() if self.last_trained else None,
                            'network_layers': self.config.get('hidden_layers', (64, 32))
                        }
                    }

                    signal_hash = self._generate_signal_hash(signal)
                    if not self._is_signal_cooldown(signal_hash) and signal_hash not in self.executed_signals:
                        signal['position_size'] = self.calculate_position_size(signal, current_price * 0.02)
                        signal['signal_hash'] = signal_hash
                        if signal['position_size'] > 0:
                            signals.append(signal)
                            self.executed_signals.add(signal_hash)
                            logger.info(f"🚀 {symbol} A35 生成买入信号 - 神经网络预测上涨 {predicted_change*100:.2f}%")

                elif predicted_change < -threshold:
                    # 预测下跌 - 卖出信号
                    confidence = min(abs(predicted_change) * 4, 0.9)

                    signal = {
                        'symbol': symbol,
                        'signal_type': 'MLP_NN_SELL',
                        'action': 'SELL',
                        'price': current_price,
                        'confidence': confidence,
                        'reason': f'MLP神经网络预测下跌: {predicted_change*100:.2f}%',
                        'indicators': {
                            'predicted_change': predicted_change,
                            'predicted_price': predicted_price,
                            'model_trained': self.last_trained.isoformat() if self.last_trained else None,
                            'network_layers': self.config.get('hidden_layers', (64, 32))
                        }
                    }

                    signal_hash = self._generate_signal_hash(signal)
                    if not self._is_signal_cooldown(signal_hash) and signal_hash not in self.executed_signals:
                        signal['position_size'] = self.calculate_position_size(signal, current_price * 0.02)
                        signal['signal_hash'] = signal_hash
                        if signal['position_size'] > 0:
                            signals.append(signal)
                            self.executed_signals.add(signal_hash)
                            logger.info(f"🔻 {symbol} A35 生成卖出信号 - 神经网络预测下跌 {predicted_change*100:.2f}%")

        except Exception as e:
            logger.error(f"生成{symbol}信号时出错: {e}")

        if signals:
            self.signals_generated += len(signals)

        return signals

    def check_exit_conditions(self, symbol: str, current_price: float,
                             current_time: datetime = None) -> Optional[Dict]:
        """检查退出条件"""
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
            logger.warning(f"⚠️ {symbol} A35触发止损: 亏损{price_change_pct*100:.2f}%")
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
            logger.info(f"✅ {symbol} A35触发止盈: 盈利{price_change_pct*100:.2f}%")
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