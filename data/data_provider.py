#!/usr/bin/env python3
"""
数据提供器 - 从 enhanced-data 接口获取真实数据
"""
import json
import time
import pandas as pd
import numpy as np
import requests
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)

class DataProvider:
    """数据提供器 - 仅从 enhanced-data 接口获取真实数据"""
    
    def __init__(self, base_url="http://localhost:8001", max_retries=3):
        self.base_url = base_url
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.timeout = 15
        self.session.headers.update({
            'User-Agent': 'TradingSystem/1.0',
            'Accept': 'application/json'
        })
        
        self.data_cache = {}
        self.cache_duration = 300
        
        logger.info(f"数据提供器初始化 - 服务器地址: {base_url}")
        self._test_connection()
    
    def _test_connection(self):
        """测试与数据服务器的连接"""
        try:
            test_url = f"{self.base_url}/enhanced-data?symbol=AAPL&period=1d&interval=5m"
            response = self.session.get(test_url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                if 'error' not in data:
                    logger.info("✅ 数据服务器连接成功")
                    return True
                else:
                    logger.warning(f"⚠️  服务器返回错误: {data.get('error', '未知错误')}")
                    return False
            else:
                logger.error(f"❌ 服务器响应异常: HTTP {response.status_code}")
                return False
                
        except requests.exceptions.ConnectionError:
            logger.error("❌ 无法连接到数据服务器")
            logger.error("请确保已运行: python enhanced_http_server.py")
            return False
        except Exception as e:
            logger.error(f"❌ 连接测试失败: {e}")
            return False
    
    def get_intraday_data(self, symbol: str, interval: str = '5m', 
                         lookback: int = 60) -> pd.DataFrame:
        """
        从 enhanced-data 接口获取日内数据
        """
        cache_key = f"{symbol}_{interval}"
        current_time = time.time()
        
        if cache_key in self.data_cache:
            cache_age = current_time - self.data_cache[cache_key]['timestamp']
            if cache_age < self.cache_duration:
                cached_data = self.data_cache[cache_key]['data']
                if len(cached_data) >= min(lookback, 10):
                    return cached_data.copy()
        
        period = self._calculate_period(interval, lookback)
        url = f"{self.base_url}/enhanced-data"
        params = {
            'symbol': symbol,
            'period': period,
            'interval': interval
        }
        
        for attempt in range(self.max_retries):
            try:
                logger.info(f"请求数据: {symbol} ({interval}, {period}) [尝试 {attempt+1}/{self.max_retries}]")
                
                response = self.session.get(url, params=params, timeout=10)
                
                if response.status_code != 200:
                    logger.warning(f"HTTP错误 {response.status_code}, 重试中...")
                    time.sleep(1 * (attempt + 1))
                    continue
                
                data = response.json()
                
                if 'error' in data:
                    logger.error(f"接口错误: {data['error']}, symbol: {symbol}")
                    return pd.DataFrame()
                
                df = self._process_raw_data(data, symbol)
                
                if df.empty:
                    logger.warning(f"处理后的数据为空: {symbol}")
                    return df
                
                if lookback and len(df) > lookback:
                    df = df.iloc[-lookback:]
                
                self.data_cache[cache_key] = {
                    'timestamp': current_time,
                    'data': df.copy()
                }
                
                logger.info(f"✅ 成功获取 {symbol}: {len(df)} 条数据")
                return df
                
            except requests.exceptions.Timeout:
                logger.warning(f"请求超时 {symbol}, 重试中...")
                time.sleep(2 * (attempt + 1))
            except requests.exceptions.ConnectionError:
                logger.error(f"连接错误 {symbol}, 重试中...")
                time.sleep(3 * (attempt + 1))
            except Exception as e:
                logger.error(f"获取 {symbol} 数据时出错: {e}")
                break
        
        logger.error(f"❌ 所有重试失败: {symbol}")
        return pd.DataFrame()
    
    def _calculate_period(self, interval: str, lookback: int) -> str:
        """根据间隔和数据点需求计算period参数"""
        period_map = {
            '1m': '1d',
            '5m': '5d',
            '15m': '10d',
            '30m': '20d',
            '60m': '30d',
            '1d': '3mo'
        }
        
        base_period = period_map.get(interval, '5d')
        
        if lookback > 100:
            if interval == '5m':
                return '10d'
            elif interval == '15m':
                return '20d'
            elif interval == '30m':
                return '60d'
            elif interval == '60m':
                return '90d'
        
        return base_period
    
    def _process_raw_data(self, api_data: Dict, symbol: str) -> pd.DataFrame:
        """处理API返回的原始数据"""
        try:
            raw_data = api_data.get('raw_data', [])
            if not raw_data:
                logger.warning(f"无原始数据: {symbol}")
                return pd.DataFrame()
            
            df = pd.DataFrame(raw_data)
            
            column_mapping = {}
            for col in df.columns:
                col_lower = col.lower()
                if col_lower in ['timestamp', 'date', 'time']:
                    column_mapping[col] = 'timestamp'
                elif col_lower == 'open':
                    column_mapping[col] = 'Open'
                elif col_lower == 'high':
                    column_mapping[col] = 'High'
                elif col_lower == 'low':
                    column_mapping[col] = 'Low'
                elif col_lower == 'close':
                    column_mapping[col] = 'Close'
                elif col_lower == 'volume':
                    column_mapping[col] = 'Volume'
            
            df.rename(columns=column_mapping, inplace=True)
            
            if 'timestamp' in df.columns:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df.set_index('timestamp', inplace=True)
            else:
                df.index = pd.date_range(end=datetime.now(), 
                                       periods=len(df), 
                                       freq='5min')
            
            required_cols = ['Open', 'High', 'Low', 'Close']
            missing_cols = [col for col in required_cols if col not in df.columns]
            
            if missing_cols:
                logger.warning(f"缺失必需列 {missing_cols}: {symbol}")
                return pd.DataFrame()
            
            if 'Volume' not in df.columns:
                df['Volume'] = 1000000
            
            for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df = df.dropna()
            df.sort_index(inplace=True)
            
            return df
            
        except Exception as e:
            logger.error(f"处理 {symbol} 数据时出错: {e}")
            return pd.DataFrame()
    
    def get_technical_indicators(self, symbol: str, 
                               period: str = '1d', 
                               interval: str = '5m') -> Dict:
        """直接从接口获取技术指标"""
        try:
            url = f"{self.base_url}/enhanced-data"
            params = {
                'symbol': symbol,
                'period': period,
                'interval': interval
            }
            
            response = self.session.get(url, params=params, timeout=8)
            
            if response.status_code == 200:
                data = response.json()
                return data.get('technical_indicators', {})
        except Exception as e:
            logger.error(f"获取技术指标失败 {symbol}: {e}")
        
        return {}
    
    def get_market_status(self) -> Dict:
        """获取市场状态"""
        test_symbols = ['AAPL', 'SPY']
        status = {
            'server_available': False,
            'symbols_available': [],
            'test_time': datetime.now().isoformat()
        }
        
        try:
            test_response = self.session.get(self.base_url, timeout=5)
            status['server_available'] = test_response.status_code == 200
        except:
            status['server_available'] = False
        
        for symbol in test_symbols:
            try:
                df = self.get_intraday_data(symbol, interval='5m', lookback=5)
                if not df.empty and len(df) >= 3:
                    status['symbols_available'].append(symbol)
            except:
                continue
        
        return status