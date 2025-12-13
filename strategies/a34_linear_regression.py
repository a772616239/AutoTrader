#!/usr/bin/env python3
"""
线性回归策略 (A34)
基于scikit-learn线性回归模型的价格预测和交易信号
"""
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
import os
import pickle
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error

from strategies.base_strategy import BaseStrategy

logger = logging.getLogger(__name__)

class A34LinearRegressionStrategy(BaseStrategy):
    """A34: 线性回归价格预测策略"""

    def _default_config(self) -> Dict:
        """默认配置"""
        from config import CONFIG
        strategy_key = 'strategy_a34'
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

                # 线性回归参数
                'lookback_period': 30,  # 训练数据回溯期
                'prediction_horizon': 1,  # 预测期（天）
                'retrain_frequency': 5,  # 每5个交易日重新训练模型
                'prediction_threshold': 0.02,  # 预测价格变化阈值（2%）

                # 风险管理
                'stop_loss_pct': 0.03,
                'take_profit_pct': 0.05,
                'max_holding_minutes': 240,  # 4小时

                # 防重复交易
                'signal_cooldown_minutes': 30,

                # 交易参数
                'min_volume': 10000,
                'min_data_points': 50,  # 需要足够的历史数据

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
        self.model_dir = os.path.join(os.getcwd(), 'models', 'a34_linear_regression')
        self.performance_metrics = {
            'total_predictions': 0,
            'correct_predictions': 0,
            'total_return': 0.0,
            'avg_prediction_error': 0.0
        }

        # 创建模型目录
        os.makedirs(self.model_dir, exist_ok=True)

        # 尝试加载已保存的模型
        self._load_model()

        logger.info("A34 线性回归策略初始化完成")

    def _save_model(self) -> bool:
        """保存模型到文件"""
        try:
            if self.model is None:
                return False

            model_data = {
                'model': self.model,
                'scaler': self.scaler,
                'last_trained': self.last_trained,
                'performance_metrics': self.performance_metrics,
                'config': self.config
            }

            model_path = os.path.join(self.model_dir, 'model.pkl')
            with open(model_path, 'wb') as f:
                pickle.dump(model_data, f)

            logger.info(f"✅ A34 模型已保存到 {model_path}")
            return True

        except Exception as e:
            logger.error(f"保存模型时出错: {e}")
            return False

    def _load_model(self) -> bool:
        """从文件加载模型"""
        try:
            model_path = os.path.join(self.model_dir, 'model.pkl')
            if not os.path.exists(model_path):
                logger.info("A34 模型文件不存在，将重新训练")
                return False

            with open(model_path, 'rb') as f:
                model_data = pickle.load(f)

            self.model = model_data.get('model')
            self.scaler = model_data.get('scaler', StandardScaler())
            self.last_trained = model_data.get('last_trained')
            self.performance_metrics = model_data.get('performance_metrics', self.performance_metrics)

            logger.info(f"✅ A34 模型已从 {model_path} 加载")
            return True

        except Exception as e:
            logger.error(f"加载模型时出错: {e}")
            return False

    def _update_performance_metrics(self, actual_change: float, predicted_change: float,
                                   trade_result: float = 0.0):
        """更新性能指标"""
        try:
            self.performance_metrics['total_predictions'] += 1

            # 判断预测方向是否正确
            actual_direction = 1 if actual_change > 0 else -1
            predicted_direction = 1 if predicted_change > 0 else -1

            if actual_direction == predicted_direction:
                self.performance_metrics['correct_predictions'] += 1

            # 更新预测误差
            error = abs(actual_change - predicted_change)
            total_error = self.performance_metrics['avg_prediction_error'] * (self.performance_metrics['total_predictions'] - 1)
            self.performance_metrics['avg_prediction_error'] = (total_error + error) / self.performance_metrics['total_predictions']

            # 更新总收益
            self.performance_metrics['total_return'] += trade_result

        except Exception as e:
            logger.error(f"更新性能指标时出错: {e}")

    def _prepare_features(self, data: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """准备特征数据 - 优化的特征工程"""
        try:
            close_prices = data['Close'].values
            high_prices = data['High'].values
            low_prices = data['Low'].values
            open_prices = data['Open'].values if 'Open' in data.columns else close_prices
            volume = data['Volume'].values if 'Volume' in data.columns else np.ones(len(data))

            features = []

            # 1. 基础价格特征
            features.append(close_prices)  # 收盘价
            features.append((high_prices + low_prices) / 2)  # 典型价格
            features.append(high_prices - low_prices)  # 日内波动范围

            # 2. 标准化成交量
            if len(volume) > 0 and volume.mean() > 0:
                normalized_volume = volume / volume.mean()
                features.append(normalized_volume)
            else:
                features.append(np.ones(len(close_prices)))

            # 3. 技术指标特征
            # 移动平均及其斜率
            for period in [5, 10, 20]:
                if len(close_prices) >= period:
                    sma = pd.Series(close_prices).rolling(period).mean()
                    sma_values = sma.bfill().values
                    features.append(sma_values)

                    # 移动平均斜率 (趋势强度)
                    if len(sma_values) > 1:
                        sma_slope = np.diff(sma_values, prepend=sma_values[0])
                        features.append(sma_slope)

            # 4. 动量指标
            for period in [1, 3, 5]:
                if len(close_prices) > period:
                    momentum = np.diff(close_prices, period, prepend=np.full(period, close_prices[0]))
                    features.append(momentum)

            # 5. 波动率指标
            if len(close_prices) >= 10:
                returns = np.diff(close_prices) / close_prices[:-1]
                # 多种周期的波动率
                for period in [5, 10]:
                    vol_series = pd.Series(returns).rolling(period).std()
                    vol_values = vol_series.fillna(vol_series.mean()).values
                    if len(vol_values) < len(close_prices):
                        vol_values = np.concatenate([np.full(len(close_prices) - len(vol_values), vol_series.mean()), vol_values])
                    features.append(vol_values)

            # 6. 价格位置指标
            if len(close_prices) >= 10:
                # 价格相对位置 (相对于过去10天的范围)
                rolling_max = pd.Series(close_prices).rolling(10).max().bfill()
                rolling_min = pd.Series(close_prices).rolling(10).min().bfill()
                price_position = (close_prices - rolling_min.values) / (rolling_max.values - rolling_min.values + 1e-10)
                features.append(price_position)

            # 组合所有特征
            X = np.column_stack(features)

            # 处理NaN和无穷大值
            X = np.nan_to_num(X, nan=0.0, posinf=1.0, neginf=-1.0)

            # 目标变量：未来价格变化百分比
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
            import traceback
            logger.error(traceback.format_exc())
            return np.array([]), np.array([])

    def _train_model(self, data: pd.DataFrame) -> bool:
        """训练线性回归模型"""
        try:
            if len(data) < self.config.get('min_data_points', 50):
                logger.warning(f"数据点不足({len(data)})，跳过模型训练")
                return False

            # 准备训练数据
            X, y = self._prepare_features(data)

            if len(X) == 0 or len(y) == 0:
                logger.warning("特征准备失败，跳过模型训练")
                return False

            # 数据标准化
            X_scaled = self.scaler.fit_transform(X)

            # 训练模型
            self.model = LinearRegression()
            self.model.fit(X_scaled, y)

            # 记录训练时间
            self.last_trained = datetime.now()

            # 计算训练误差
            y_pred = self.model.predict(X_scaled)
            mse = mean_squared_error(y, y_pred)
            rmse = np.sqrt(mse)

            logger.info(f"✅ A34 线性回归模型训练完成 - MSE: {mse:.6f}, RMSE: {rmse:.6f}, 数据点: {len(X)}")

            # 保存模型
            self._save_model()

            return True

        except Exception as e:
            logger.error(f"训练模型时出错: {e}")
            return False

    def _should_retrain(self) -> bool:
        """检查是否需要重新训练模型"""
        if self.last_trained is None:
            return True

        retrain_freq = self.config.get('retrain_frequency', 5)
        days_since_train = (datetime.now() - self.last_trained).days

        return days_since_train >= retrain_freq

    def _predict_price_change(self, data: pd.DataFrame) -> float:
        """预测价格变化"""
        try:
            if self.model is None:
                return 0.0

            # 准备预测数据（使用足够的历史数据来计算所有特征）
            # 需要足够的数据来计算滚动特征
            min_data_points = 25  # 确保有足够的数据计算所有特征
            if len(data) < min_data_points:
                return 0.0

            predict_data = data.tail(min_data_points).copy()
            X, _ = self._prepare_features(predict_data)

            if len(X) == 0:
                return 0.0

            # 使用最新的数据点进行预测
            X_latest = X[-1:].copy()  # 取最后一行

            # 标准化并预测
            X_scaled = self.scaler.transform(X_latest)
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
            if data.empty or len(data) < self.config.get('min_data_points', 50):
                return signals

            # 检查成交量
            from config import CONFIG
            skip_volume_check = CONFIG.get('trading', {}).get('skip_volume_check', False)
            if not skip_volume_check and not self._is_pre_market_hours() and 'Volume' in data.columns:
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

            logger.info(f"📊 {symbol} A34 预测 - 当前价格: {current_price:.2f}, "
                       f"预测变化: {predicted_change:.4f} ({predicted_change*100:.2f}%), "
                       f"预测价格: {predicted_price:.2f}")

            # 检查现有持仓的退出条件
            if symbol in self.positions:
                current_time = datetime.now()

                # 优先检查强制止损止盈
                forced_exit = self.check_forced_exit_conditions(symbol, current_price, current_time, data)
                if forced_exit:
                    forced_exit['position_size'] = abs(self.positions[symbol]['size'])
                    signals.append(forced_exit)
                    return signals  # 强制退出直接返回

                exit_signal = self.check_exit_conditions(symbol, current_price)
                if exit_signal:
                    exit_signal['position_size'] = abs(self.positions[symbol]['size'])
                    signals.append(exit_signal)

            # 只在没有持仓时生成买入信号
            if symbol not in self.positions:
                threshold = self.config.get('prediction_threshold', 0.02)

                if predicted_change > threshold:
                    # 预测上涨 - 买入信号
                    confidence = min(predicted_change * 5, 0.9)  # 预测变化越大，置信度越高

                    signal = {
                        'symbol': symbol,
                        'signal_type': 'LINEAR_REGRESSION_BUY',
                        'action': 'BUY',
                        'price': current_price,
                        'confidence': confidence,
                        'reason': f'线性回归预测上涨: {predicted_change*100:.2f}%',
                        'indicators': {
                            'predicted_change': predicted_change,
                            'predicted_price': predicted_price,
                            'model_trained': self.last_trained.isoformat() if self.last_trained else None
                        }
                    }

                    signal_hash = self._generate_signal_hash(signal)
                    if not self._is_signal_cooldown(signal_hash) and signal_hash not in self.executed_signals:
                        signal['position_size'] = self.calculate_position_size(signal, current_price * 0.02)
                        signal['signal_hash'] = signal_hash
                        if signal['position_size'] > 0:
                            signals.append(signal)
                            self.executed_signals.add(signal_hash)
                            logger.info(f"🚀 {symbol} A34 生成买入信号 - 预测上涨 {predicted_change*100:.2f}%")

                elif predicted_change < -threshold:
                    # 预测下跌 - 卖出信号（做空）
                    confidence = min(abs(predicted_change) * 5, 0.9)

                    signal = {
                        'symbol': symbol,
                        'signal_type': 'LINEAR_REGRESSION_SELL',
                        'action': 'SELL',
                        'price': current_price,
                        'confidence': confidence,
                        'reason': f'线性回归预测下跌: {predicted_change*100:.2f}%',
                        'indicators': {
                            'predicted_change': predicted_change,
                            'predicted_price': predicted_price,
                            'model_trained': self.last_trained.isoformat() if self.last_trained else None
                        }
                    }

                    signal_hash = self._generate_signal_hash(signal)
                    if not self._is_signal_cooldown(signal_hash) and signal_hash not in self.executed_signals:
                        signal['position_size'] = self.calculate_position_size(signal, current_price * 0.02)
                        signal['signal_hash'] = signal_hash
                        if signal['position_size'] > 0:
                            signals.append(signal)
                            self.executed_signals.add(signal_hash)
                            logger.info(f"🔻 {symbol} A34 生成卖出信号 - 预测下跌 {predicted_change*100:.2f}%")

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
            logger.warning(f"⚠️ {symbol} A34触发止损: 亏损{price_change_pct*100:.2f}%")
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
            logger.info(f"✅ {symbol} A34触发止盈: 盈利{price_change_pct*100:.2f}%")
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