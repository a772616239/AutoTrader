import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import talib
import warnings
warnings.filterwarnings('ignore')

class EnhancedStockData:
    """增强版股票数据获取与特征工程"""
    
    def __init__(self):
        self.indicators = {}
    
    def get_enhanced_data(self, symbol, period="1mo", interval="1d"):
        """
        获取增强版股票数据，包含多维度特征
        """
        try:
            # 1. 基础行情数据
            # 检查是否有代理配置 (Yahoo Finance 在某些地区需要代理)
            import os
            if not os.environ.get('https_proxy') and not os.environ.get('HTTPS_PROXY'):
                print("⚠️ Warning: No HTTPS_PROXY detected. Yahoo Finance might be blocked.")

            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=period, interval=interval)
            
            if hist.empty:
                return {"error": "No data available"}
            
            # 2. 基本信息
            info = ticker.info
            company_info = {
                'symbol': symbol,
                'name': info.get('longName', info.get('shortName', symbol)),
                'sector': info.get('sector', 'Unknown'),
                'industry': info.get('industry', 'Unknown'),
                'marketCap': info.get('marketCap', 0),
                'peRatio': info.get('trailingPE', 0),
                'dividendYield': info.get('dividendYield', 0) * 100 if info.get('dividendYield') else 0,
                'beta': info.get('beta', 0),
                '52WeekHigh': info.get('fiftyTwoWeekHigh', 0),
                '52WeekLow': info.get('fiftyTwoWeekLow', 0),
                'avgVolume': info.get('averageVolume', 0)
            }
            
            # 3. 技术指标计算 (单点，用于摘要)
            indicators = self._calculate_indicators(hist)
            
            # 3.1 添加技术指标序列 (用于绘图)
            hist = self._add_technical_indicators(hist)
            
            # 3.2 添加基本面衍生数据
            hist = self._add_fundamental_data(hist, info)
            
            # 4. 价量特征工程
            price_features = self._extract_price_features(hist)
            
            # 5. 日内特征（如果有分钟数据）
            intraday_features = {}
            if interval in ["1m", "5m", "15m", "30m", "60m"]:
                intraday_features = self._extract_intraday_features(hist)
            
            # 6. 市场相对表现
            market_comparison = self._market_comparison(symbol, hist)
            
            # 7. 数据标准化（供模型使用）
            normalized_data = self._normalize_features({
                **indicators,
                **price_features
            })
            
            # 8. 构建完整数据包
            enhanced_data = {
                'metadata': {
                    'symbol': symbol,
                    'period': period,
                    'interval': interval,
                    'data_points': len(hist),
                    'last_updated': datetime.now().isoformat(),
                    'currency': info.get('currency', 'USD')
                },
                'company_info': company_info,
                'raw_data': self._format_raw_data(hist),
                'technical_indicators': indicators,
                'price_features': price_features,
                'intraday_features': intraday_features,
                'market_comparison': market_comparison,
                'normalized_features': normalized_data,
                'trading_signals': self._generate_trading_signals(hist, indicators),
                'risk_metrics': self._calculate_risk_metrics(hist)
            }
            
            return enhanced_data
            
        except Exception as e:
            return {"error": f"Data fetching failed: {str(e)}"}

    # ... (Keep existing methods) ...

    def _format_raw_data(self, df):
        """格式化原始数据"""
        formatted = []
        
        # 将 NaN 替换为 None 以便 JSON 序列化
        df_clean = df.where(pd.notnull(df), None)
        
        for idx, row in df_clean.iterrows():
            record = {
                'time': idx.isoformat() if hasattr(idx, 'isoformat') else str(idx),
                'open': float(row['Open']) if row['Open'] is not None else None,
                'high': float(row['High']) if row['High'] is not None else None,
                'low': float(row['Low']) if row['Low'] is not None else None,
                'close': float(row['Close']) if row['Close'] is not None else None,
                'volume': int(row['Volume']) if 'Volume' in row and row['Volume'] is not None else 0,
            }
            
            # 添加指标字段 (如果存在)
            optional_fields = ['MA5', 'MA10', 'MA20', 'MA50', 'MA200', 'BB_upper', 'BB_middle', 'BB_lower', 
                               'RSI', 'MACD', 'MACD_Signal', 'MACD_Hist', 'Turnover', 'TurnoverRate', 'PE']
            for field in optional_fields:
                if field in row:
                    val = row[field]
                    if val is not None:
                        record[field] = float(val)
                    else:
                        record[field] = None
                        
            formatted.append(record)
        return formatted

    def _calculate_indicators(self, df):
        """计算技术指标"""
        closes = df['Close'].values.astype(np.float64)
        highs = df['High'].values.astype(np.float64)
        lows = df['Low'].values.astype(np.float64)
        volumes = df['Volume'].values.astype(np.float64) # 成交量也转换以确保兼容性
            # 安全地处理成交量：如果存在则转换，否则创建零数组
        if 'Volume' in df.columns and not df['Volume'].isna().all():
            volumes = df['Volume'].values.astype(np.float64)
        else:
            volumes = np.zeros(len(closes), dtype=np.float64)
        # 确保数据足够长
        min_period = min(len(closes), 50)
        
        indicators = {}
        
        # 趋势指标
        if len(closes) >= 5:
            indicators['MA_5'] = talib.SMA(closes, timeperiod=5)[-1]
            indicators['MA_10'] = talib.SMA(closes, timeperiod=10)[-1] if len(closes) >= 10 else None
            indicators['MA_20'] = talib.SMA(closes, timeperiod=20)[-1] if len(closes) >= 20 else None
            indicators['MA_50'] = talib.SMA(closes, timeperiod=50)[-1] if len(closes) >= 50 else None
            
            # EMA
            indicators['EMA_12'] = talib.EMA(closes, timeperiod=12)[-1] if len(closes) >= 12 else None
            indicators['EMA_26'] = talib.EMA(closes, timeperiod=26)[-1] if len(closes) >= 26 else None
            
            # MACD
            macd, signal, hist = talib.MACD(closes, fastperiod=12, slowperiod=26, signalperiod=9)
            indicators['MACD'] = macd[-1] if not np.isnan(macd[-1]) else None
            indicators['MACD_Signal'] = signal[-1] if len(signal) > 0 and not np.isnan(signal[-1]) else None
        
        # 动量指标
        if len(closes) >= 14:
            indicators['RSI'] = talib.RSI(closes, timeperiod=14)[-1]
            
            # 随机指标
            slowk, slowd = talib.STOCH(highs, lows, closes, 
                                      fastk_period=14, slowk_period=3, 
                                      slowk_matype=0, slowd_period=3, slowd_matype=0)
            indicators['Stoch_K'] = slowk[-1] if len(slowk) > 0 else None
            indicators['Stoch_D'] = slowd[-1] if len(slowd) > 0 else None
        
        # 波动率指标
        if len(closes) >= 20:
            indicators['ATR'] = talib.ATR(highs, lows, closes, timeperiod=14)[-1]
            indicators['BB_upper'], indicators['BB_middle'], indicators['BB_lower'] = talib.BBANDS(
                closes, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0
            )
            indicators['BB_upper'] = indicators['BB_upper'][-1]
            indicators['BB_middle'] = indicators['BB_middle'][-1]
            indicators['BB_lower'] = indicators['BB_lower'][-1]
        
        # 成交量指标
        if len(volumes) >= 20:
            indicators['OBV'] = talib.OBV(closes, volumes)[-1] if len(closes) == len(volumes) else None
            indicators['Volume_SMA'] = np.mean(volumes[-20:])
            indicators['Volume_Ratio'] = volumes[-1] / indicators['Volume_SMA'] if indicators['Volume_SMA'] > 0 else 1
        
        return indicators

    def _add_technical_indicators(self, df):
        """向DataFrame添加技术指标列 (用于绘图)"""
        if len(df) < 2:
            return df
            
        closes = df['Close'].values.astype(np.float64)
        highs = df['High'].values.astype(np.float64)
        lows = df['Low'].values.astype(np.float64)
        
        # MA - 使用较短周期以提高覆盖率
        df['MA5'] = talib.SMA(closes, timeperiod=5)
        df['MA10'] = talib.SMA(closes, timeperiod=10)
        df['MA20'] = talib.SMA(closes, timeperiod=20)
        
        # Bollinger Bands - 保持20周期
        upper, middle, lower = talib.BBANDS(closes, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)
        df['BB_upper'] = upper
        df['BB_middle'] = middle
        df['BB_lower'] = lower
        
        # RSI - 保持14周期（标准）
        df['RSI'] = talib.RSI(closes, timeperiod=14)
        
        # MACD - 保持标准参数
        macd, signal, hist = talib.MACD(closes, fastperiod=12, slowperiod=26, signalperiod=9)
        df['MACD'] = macd
        df['MACD_Signal'] = signal
        df['MACD_Hist'] = hist
        
        return df

    def _add_fundamental_data(self, df, info):
        """添加基本面衍生数据 (PE, 换手率等)"""
        # 获取股本和EPS
        shares_outstanding = info.get('sharesOutstanding', 0)
        trailing_eps = info.get('trailingEps', 0)
        
        # 1. Turnover (成交额) - 近似值
        df['Turnover'] = df['Close'] * df['Volume']
        
        # 2. TurnoverRate (换手率)
        if shares_outstanding and shares_outstanding > 0:
            df['TurnoverRate'] = (df['Volume'] / shares_outstanding) * 100 # 百分比
        else:
            df['TurnoverRate'] = 0
            
        # 3. PE (市盈率) - 动态估算:收盘价/最近EPS
        if trailing_eps and trailing_eps > 0:
            df['PE'] = df['Close'] / trailing_eps
        else:
            df['PE'] = 0
            
        return df
    
    def _extract_price_features(self, df):
        """提取价量特征"""
        if len(df) < 5:
            return {}
        
        closes = df['Close'].values
        volumes = df['Volume'].values
        
        features = {}
        
        # 价格变动特征
        features['last_close'] = closes[-1]
        features['price_change_1d'] = ((closes[-1] - closes[-2]) / closes[-2] * 100) if len(closes) >= 2 else 0
        features['price_change_5d'] = ((closes[-1] - closes[-5]) / closes[-5] * 100) if len(closes) >= 5 else 0
        features['price_change_20d'] = ((closes[-1] - closes[-20]) / closes[-20] * 100) if len(closes) >= 20 else 0
        
        # 波动特征
        returns = np.diff(closes) / closes[:-1]
        features['volatility_5d'] = np.std(returns[-5:]) * np.sqrt(252) * 100 if len(returns) >= 5 else 0
        features['volatility_20d'] = np.std(returns[-20:]) * np.sqrt(252) * 100 if len(returns) >= 20 else 0
        
        # 量价关系
        if len(volumes) >= 5:
            volume_change = ((volumes[-1] - np.mean(volumes[-5:-1])) / np.mean(volumes[-5:-1]) * 100) if len(volumes) >= 5 else 0
            features['volume_change'] = volume_change
            
            # 量价背离检测
            price_trend = closes[-1] > closes[-5]
            volume_trend = volumes[-1] > np.mean(volumes[-5:-1])
            features['price_volume_divergence'] = 1 if price_trend != volume_trend else 0
        
        # 支撑阻力特征
        if len(closes) >= 20:
            features['support_level'] = np.min(closes[-20:])
            features['resistance_level'] = np.max(closes[-20:])
            features['price_position'] = (closes[-1] - features['support_level']) / (features['resistance_level'] - features['support_level']) * 100 if features['resistance_level'] > features['support_level'] else 50
        
        # 日内特征（如果有多日数据）
        if 'Open' in df.columns and 'High' in df.columns and 'Low' in df.columns:
            features['daily_range'] = ((df['High'].iloc[-1] - df['Low'].iloc[-1]) / df['Close'].iloc[-1] * 100) if df['Close'].iloc[-1] > 0 else 0
            features['close_position'] = ((df['Close'].iloc[-1] - df['Low'].iloc[-1]) / (df['High'].iloc[-1] - df['Low'].iloc[-1]) * 100) if (df['High'].iloc[-1] > df['Low'].iloc[-1]) else 50
        
        return features
    
    def _extract_intraday_features(self, df):
        """提取日内特征（分钟级数据）"""
        features = {}
        
        if len(df) < 10:
            return features
        
        # 时间特征
        if hasattr(df.index[-1], 'hour'):
            features['hour_of_day'] = df.index[-1].hour
            features['is_morning'] = 1 if 9 <= df.index[-1].hour < 12 else 0
            features['is_afternoon'] = 1 if 13 <= df.index[-1].hour < 16 else 0
        
        # 日内波动
        if len(df) >= 5:
            intraday_returns = df['Close'].pct_change().dropna()
            features['intraday_volatility'] = intraday_returns.std() * np.sqrt(252) * 100 if len(intraday_returns) > 0 else 0
            
            # 成交量分布
            if 'Volume' in df.columns:
                features['volume_concentration'] = df['Volume'].iloc[-5:].sum() / df['Volume'].sum() if df['Volume'].sum() > 0 else 0
        
        return features
    
    def _market_comparison(self, symbol, df):
        """市场相对表现（简化版）"""
        comparison = {}
        
        # 这里可以添加与大盘指数的比较
        # 例如获取SPY（标普500ETF）数据进行比较
        
        return comparison
    
    def _normalize_features(self, features_dict):
        """特征标准化（0-1范围）"""
        normalized = {}
        
        for key, value in features_dict.items():
            if value is None:
                normalized[key] = 0.5  # 中性值
            elif isinstance(value, (int, float)):
                # 简单的标准化逻辑（实际应用中需要更复杂的标准化）
                if 'RSI' in key:
                    normalized[key] = value / 100  # RSI在0-100之间
                elif 'change' in key.lower() or 'ratio' in key.lower():
                    normalized[key] = 1 / (1 + np.exp(-value/10))  # Sigmoid函数
                else:
                    normalized[key] = value / (1 + abs(value)) if value != 0 else 0.5
            else:
                normalized[key] = 0.5
        
        return normalized
    
    def _generate_trading_signals(self, df, indicators):
        """生成交易信号"""
        signals = []
        
        # 基于多个指标的综合信号
        if 'RSI' in indicators and indicators['RSI']:
            if indicators['RSI'] < 30:
                signals.append({"type": "oversold", "indicator": "RSI", "strength": "high"})
            elif indicators['RSI'] > 70:
                signals.append({"type": "overbought", "indicator": "RSI", "strength": "high"})
        
        if 'MACD' in indicators and indicators['MACD'] and 'MACD_Signal' in indicators and indicators['MACD_Signal']:
            if indicators['MACD'] > indicators['MACD_Signal']:
                signals.append({"type": "bullish_crossover", "indicator": "MACD", "strength": "medium"})
            else:
                signals.append({"type": "bearish_crossover", "indicator": "MACD", "strength": "medium"})
        
        # 价格位置信号
        if len(df) >= 20:
            current_price = df['Close'].iloc[-1]
            support = df['Low'].iloc[-20:].min()
            resistance = df['High'].iloc[-20:].max()
            
            if current_price < support * 1.02:
                signals.append({"type": "near_support", "indicator": "price", "strength": "medium"})
            elif current_price > resistance * 0.98:
                signals.append({"type": "near_resistance", "indicator": "price", "strength": "medium"})
        
        return signals
    
    def _calculate_risk_metrics(self, df):
        """计算风险指标"""
        if len(df) < 5:
            return {}
        
        returns = df['Close'].pct_change().dropna()
        
        metrics = {
            'sharpe_ratio': 0,
            'max_drawdown': 0,
            'var_95': 0
        }
        
        if len(returns) > 0:
            # 夏普比率（简化，假设无风险利率为0）
            metrics['sharpe_ratio'] = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0
            
            # 最大回撤
            cumulative = (1 + returns).cumprod()
            running_max = cumulative.expanding().max()
            drawdown = (cumulative - running_max) / running_max
            metrics['max_drawdown'] = drawdown.min() * 100
            
            # 风险价值（95%置信度）
            metrics['var_95'] = np.percentile(returns, 5) * 100
        
        return metrics
    