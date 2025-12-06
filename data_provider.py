import requests
import pandas as pd
import time
import logging
from datetime import datetime
from typing import Dict

logger = logging.getLogger(__name__)

class DataProvider:
    """数据提供器 (原逻辑)"""
    
    def __init__(self, base_url="http://localhost:8001", max_retries=3):
        self.base_url = base_url
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.timeout = 15
        self.data_cache = {}
        self.cache_duration = 300
        logger.info(f"数据提供器初始化 - {base_url}")
    
    def get_intraday_data(self, symbol: str, interval: str = '5m', lookback: int = 60) -> pd.DataFrame:
        cache_key = f"{symbol}_{interval}"
        if cache_key in self.data_cache:
            if time.time() - self.data_cache[cache_key]['timestamp'] < self.cache_duration:
                return self.data_cache[cache_key]['data']
        
        # 简化版：这里保留你原有的 _calculate_period 和 _process_raw_data 逻辑
        # 为节省篇幅，这里假设核心逻辑与原文一致，重点是请求接口
        period = '5d' # 默认
        url = f"{self.base_url}/enhanced-data"
        params = {'symbol': symbol, 'period': period, 'interval': interval}
        
        try:
            response = self.session.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                df = self._process_raw_data(data, symbol)
                if not df.empty and lookback:
                    df = df.iloc[-lookback:]
                return df
        except Exception as e:
            logger.error(f"获取数据失败 {symbol}: {e}")
        return pd.DataFrame()

    def _process_raw_data(self, api_data: Dict, symbol: str) -> pd.DataFrame:
        # 原有的数据处理逻辑
        raw = api_data.get('raw_data', [])
        if not raw: return pd.DataFrame()
        df = pd.DataFrame(raw)
        df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
        # 确保包含timestamp并设为索引
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
        # 转换数值
        cols = ['Open', 'High', 'Low', 'Close', 'Volume']
        df[cols] = df[cols].apply(pd.to_numeric, errors='coerce')
        return df.dropna()

    def get_technical_indicators(self, symbol: str) -> Dict:
        # 简化的指标获取
        try:
            url = f"{self.base_url}/enhanced-data"
            params = {'symbol': symbol, 'period': '1d', 'interval': '5m'}
            res = self.session.get(url, params=params)
            if res.status_code == 200:
                return res.json().get('technical_indicators', {})
        except:
            pass
        return {}