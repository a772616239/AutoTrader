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
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from textblob import TextBlob

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

        # 新闻数据缓存
        self.news_cache = {}
        self.news_cache_duration = 600  # 新闻缓存10分钟
        self.news_lookback_hours = 24  # 新闻回顾小时数

        # API调用限制
        self.last_api_call = 0
        self.min_api_interval = 1.0  # 最小API调用间隔（秒）

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
                          lookback: int = 60, use_cache: bool = True) -> pd.DataFrame:
        """
        从 enhanced-data 接口获取日内数据
        """
        cache_key = f"{symbol}_{interval}"
        current_time = time.time()
        
        if use_cache and cache_key in self.data_cache:
            cache_age = current_time - self.data_cache[cache_key]['timestamp']
            if cache_age < self.cache_duration:
                cached_data = self.data_cache[cache_key]['data']
                if len(cached_data) >= min(lookback, 10):
                    # logger.info(f"使用缓存数据: {symbol} ({len(cached_data)} 条)")
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
        test_symbols = ['AAPL']
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

    def get_news_sentiment(self, symbol: str, api_key: str, lookback_hours: int = 24,
                           api_provider: str = 'polygon') -> List[Dict]:
        """
        从指定API获取新闻并进行情感分析

        Args:
            symbol: 股票代码
            api_key: API密钥
            lookback_hours: 回顾小时数
            api_provider: API提供商 ('alphavantage' 或 'newsapi')

        Returns:
            新闻情感分析结果列表
        """
        if api_provider.lower() == 'alphavantage':
            return self._get_news_from_alphavantage(symbol, api_key, lookback_hours)
        elif api_provider.lower() == 'newsapi':
            return self._get_news_from_newsapi(symbol, api_key, lookback_hours)
        else:  # polygon (default)
            return self._get_news_from_alphavantage(symbol, api_key, lookback_hours)

    def _get_news_from_alphavantage(self, symbol: str, api_key: str, lookback_hours: int = 24) -> List[Dict]:
        """从Alpha Vantage获取新闻"""
        cache_key = f"news_{symbol}_{lookback_hours}"
        current_time = time.time()

        # 检查缓存
        if cache_key in self.news_cache:
            cache_age = current_time - self.news_cache[cache_key]['timestamp']
            if cache_age < self.news_cache_duration:
                return self.news_cache[cache_key]['data']

        try:
            # Alpha Vantage新闻API
            url = "https://www.alphavantage.co/query"
            params = {
                'function': 'NEWS_SENTIMENT',
                'tickers': symbol,
                'apikey': api_key,
                'limit': 20,
                'sort': 'LATEST'
            }

            logger.info(f"从Alpha Vantage获取新闻: {symbol}")
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()

            data = response.json()
            logger.info(f"Alpha Vantage API响应:{data} --symbol: {symbol}--params{params}")  # 调试输出

            if 'feed' not in data:
                logger.warning(f"Alpha Vantage返回无效数据结构: {symbol} - 可用字段: {list(data.keys())}")
                if 'Error Message' in data:
                    logger.error(f"API错误: {data['Error Message']}")
                elif 'Note' in data:
                    logger.warning(f"API限制提示: {data['Note']}")
                    return []
                return []

            news_items = []
            for item in data['feed'][:20]:
                # 检查新闻时间是否在lookback_hours内
                try:
                    time_str = item['time_published']
                    if len(time_str) >= 15:
                        iso_time_str = f"{time_str[:4]}-{time_str[4:6]}-{time_str[6:8]}T{time_str[9:11]}:{time_str[11:13]}:{time_str[13:15]}"
                        news_time = datetime.fromisoformat(iso_time_str)
                        time_diff = datetime.now() - news_time
                        # print("解析时间:", iso_time_str, "时间差(秒):", time_diff.total_seconds(),"news_time，",news_time)  # 调试输出
                        if time_diff.total_seconds() > lookback_hours * 3600:
                            # print("跳过过期新闻:", lookback_hours * 3600)  # 调试输出
                            continue
                    else:
                        print("时间字符串格式错误:", time_str)
                        continue
                except Exception as e:
                    logger.warning(f"时间解析失败: {item['time_published']} - {e}")
                    continue

                # 提取新闻文本
                title = item.get('title', '')
                summary = item.get('summary', '')
                full_text = f"{title}. {summary}"

                # 情感分析
                sentiment_score = self._analyze_sentiment(full_text)
                logger.info("full_text:"+full_text+"---sentiment_score{sentiment_score}")
                # 相关性评分
                relevance_score = self._calculate_news_relevance(item, symbol)

                news_item = {
                    'symbol': symbol,
                    'title': title,
                    'summary': summary,
                    'time_published': item['time_published'],
                    'sentiment_score': sentiment_score,
                    'relevance_score': relevance_score,
                    'url': item.get('url', ''),
                    'source': item.get('source', ''),
                    'overall_sentiment_score': item.get('overall_sentiment_score', 0),
                    'overall_sentiment_label': item.get('overall_sentiment_label', ''),
                }

                news_items.append(news_item)

            # 按时间排序（最新的在前）
            news_items.sort(key=lambda x: x['time_published'], reverse=True)

            # 缓存结果
            self.news_cache[cache_key] = {
                'timestamp': current_time,
                'data': news_items
            }

            logger.info(f"✅ 从Alpha Vantage获取 {symbol} 新闻: {len(news_items)} 条")
            return news_items

        except Exception as e:
            logger.error(f"Alpha Vantage新闻获取失败 {symbol}: {e}")
            return []

    def _get_news_from_newsapi(self, symbol: str, api_key: str, lookback_hours: int = 24) -> List[Dict]:
        """从NewsAPI获取新闻（备用选项）"""
        try:
            url = "https://newsapi.org/v2/everything"
            params = {
                'q': f'"{self._get_company_name(symbol)}"',
                'apiKey': api_key,
                'language': 'en',
                'sortBy': 'publishedAt',
                'pageSize': 20,
                'from': (datetime.now() - timedelta(hours=lookback_hours)).strftime('%Y-%m-%dT%H:%M:%S')
            }

            logger.info(f"从NewsAPI获取新闻: {symbol}--url: {url}--params: {params}")
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()

            data = response.json()
            print("NewsAPI响应:", data)  # 调试输出
            if 'articles' not in data:
                logger.warning(f"NewsAPI返回无效数据: {symbol}")
                return []

            news_items = []
            for article in data['articles'][:15]:
                try:
                    published_at = article.get('publishedAt', '')
                    if not published_at:
                        continue

                    news_time = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                    time_diff = datetime.now() - news_time
                    if time_diff.total_seconds() > lookback_hours * 3600:
                        continue

                    title = article.get('title', '')
                    description = article.get('description', '')
                    full_text = f"{title}. {description}"

                    sentiment_score = self._analyze_sentiment(full_text)

                    # NewsAPI的相关性评分（简化版）
                    relevance_score = 0.5 if symbol.upper() in title.upper() else 0.3

                    news_item = {
                        'symbol': symbol,
                        'title': title,
                        'summary': description or '',
                        'time_published': published_at,
                        'sentiment_score': sentiment_score,
                        'relevance_score': relevance_score,
                        'url': article.get('url', ''),
                        'source': article.get('source', {}).get('name', ''),
                        'overall_sentiment_score': sentiment_score,
                        'overall_sentiment_label': 'Neutral',
                    }

                    news_items.append(news_item)

                except Exception as e:
                    logger.warning(f"NewsAPI文章处理失败: {e}")
                    continue

            logger.info(f"✅ 从NewsAPI获取 {symbol} 新闻: {len(news_items)} 条")
            return news_items

        except Exception as e:
            logger.error(f"NewsAPI新闻获取失败 {symbol}: {e}")
            return []

    def _get_news_from_polygon(self, symbol: str, api_key: str, lookback_hours: int = 24) -> List[Dict]:
        """从Polygon.io获取新闻"""
        try:
            # 检查API调用频率限制
            current_time = time.time()
            time_since_last_call = current_time - self.last_api_call
            if time_since_last_call < self.min_api_interval:
                sleep_time = self.min_api_interval - time_since_last_call
                logger.info(f"API调用频率限制，等待 {sleep_time:.1f} 秒")
                time.sleep(sleep_time)

            # Polygon股票新闻API
            url = f"https://api.polygon.io/v2/reference/news"
            params = {
                'ticker': symbol,
                'limit': 20,
                'apiKey': api_key,
                'published_utc.gte': (datetime.now() - timedelta(hours=lookback_hours)).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            }

            logger.info(f"从Polygon获取新闻: {symbol}")
            response = requests.get(url, params=params, timeout=15)

            # 更新最后调用时间
            self.last_api_call = time.time()

            # 处理API限制错误
            if response.status_code == 429:
                logger.warning(f"Polygon API调用频率超限: {symbol}")
                return []

            response.raise_for_status()

            data = response.json()

            if 'results' not in data:
                logger.warning(f"Polygon返回无效数据: {symbol}")
                return []

            news_items = []
            for article in data['results'][:15]:
                try:
                    published_utc = article.get('published_utc', '')
                    if not published_utc:
                        continue

                    # Polygon返回的时间格式是 '2025-12-06T08:09:05.123456Z'
                    # 需要移除微秒部分并正确处理时区
                    if 'T' in published_utc:
                        # 移除微秒和Z后缀
                        time_str = published_utc.split('.')[0]  # 移除微秒
                        news_time = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                    else:
                        # 如果不是ISO格式，尝试直接解析
                        news_time = datetime.fromisoformat(published_utc.replace('Z', '+00:00'))

                    time_diff = datetime.now() - news_time.replace(tzinfo=None)  # 移除时区信息进行比较
                    if time_diff.total_seconds() > lookback_hours * 3600:
                        continue

                    title = article.get('title', '')
                    description = article.get('description', '')
                    full_text = f"{title}. {description}"

                    sentiment_score = self._analyze_sentiment(full_text)

                    # Polygon的相关性评分（基于tickers匹配）
                    tickers = article.get('tickers', [])
                    relevance_score = 1.0 if symbol.upper() in tickers else 0.3

                    news_item = {
                        'symbol': symbol,
                        'title': title,
                        'summary': description or '',
                        'time_published': published_utc,
                        'sentiment_score': sentiment_score,
                        'relevance_score': relevance_score,
                        'url': article.get('article_url', ''),
                        'source': article.get('publisher', {}).get('name', ''),
                        'overall_sentiment_score': sentiment_score,
                        'overall_sentiment_label': 'Neutral',
                    }

                    news_items.append(news_item)

                except Exception as e:
                    logger.warning(f"Polygon文章处理失败: {e}")
                    continue

            logger.info(f"✅ 从Polygon获取 {symbol} 新闻: {len(news_items)} 条")
            return news_items

        except Exception as e:
            logger.error(f"Polygon新闻获取失败 {symbol}: {e}")
            return []

    def _get_company_name(self, symbol: str) -> str:
        """获取股票代码对应的公司名称（简化版）"""
        company_map = {
            'AAPL': 'Apple',
            'MSFT': 'Microsoft',
            'GOOGL': 'Google',
            'AMZN': 'Amazon',
            'TSLA': 'Tesla',
            'NVDA': 'NVIDIA',
            'META': 'Meta',
        }
        return company_map.get(symbol.upper(), symbol)

    def _analyze_sentiment(self, text: str) -> float:
        """使用TextBlob进行情感分析"""
        try:
            if not text or len(text.strip()) == 0:
                return 0.0

            blob = TextBlob(text)
            # 返回极性分数 (-1 到 1)
            return float(blob.sentiment.polarity)
        except Exception as e:
            logger.warning(f"情感分析失败: {e}")
            return 0.0

    def _calculate_news_relevance(self, news_item: Dict, symbol: str) -> float:
        """计算新闻与股票的相关性"""
        try:
            relevance = 0.0

            # 检查标题和摘要中是否提到股票代码
            title = news_item.get('title', '').upper()
            summary = news_item.get('summary', '').upper()

            symbol_upper = symbol.upper()

            # 直接提到股票代码
            if symbol_upper in title or symbol_upper in summary:
                relevance += 0.8

            # 检查公司名称关键词（简化版）
            company_keywords = {
                'AAPL': ['APPLE', 'TIM COOK'],
                'MSFT': ['MICROSOFT', 'SATYA NADELLA'],
                'GOOGL': ['GOOGLE', 'ALPHABET'],
                'AMZN': ['AMAZON', 'JEFF BEZOS'],
                'TSLA': ['TESLA', 'ELON MUSK'],
                'NVDA': ['NVIDIA', 'JENSEN HUANG'],
                'META': ['META', 'FACEBOOK', 'MARK ZUCKERBERG'],
            }

            keywords = company_keywords.get(symbol_upper, [])
            for keyword in keywords:
                if keyword in title or keyword in summary:
                    relevance += 0.5
                    break

            # 基于情感强度调整相关性
            sentiment_score = abs(news_item.get('overall_sentiment_score', 0))
            relevance *= (0.5 + 0.5 * sentiment_score)  # 情感越强，相关性越高

            return min(relevance, 1.0)

        except Exception as e:
            logger.warning(f"计算新闻相关性失败: {e}")
            return 0.0

    def get_recent_news_impact(self, symbol: str, api_key: str, window_minutes: int = 30) -> Dict:
        """
        计算最近新闻对价格波动的影响

        Args:
            symbol: 股票代码
            api_key: Alpha Vantage API密钥
            window_minutes: 分析窗口（分钟）

        Returns:
            新闻影响分析结果
        """
        try:
            # 获取最近的新闻
            news_items = self.get_news_sentiment(symbol, api_key, self.news_lookback_hours)

            if not news_items:
                logger.info("not news_items")
                return {'impact_score': 0.0, 'significant_news': [], 'news_count': 0}

            # 获取价格数据
            price_data = self.get_intraday_data(symbol, interval='5m', lookback=240, use_cache=False)  # 20小时数据，强制刷新

            # if price_data.empty:
            #     logger.info("price_data.empty")
            #     return {'impact_score': 0.0, 'significant_news': []}

            # 确保索引为DatetimeIndex并移除时区信息
            price_data.index = pd.to_datetime(price_data.index)
            if hasattr(price_data.index, 'tz') and price_data.index.tz is not None:
                price_data.index = price_data.index.tz_convert(None)

            significant_news = []
            total_impact = 0.0

            for news in news_items:
                try:
                    # 解析新闻发布时间 (Alpha Vantage格式: YYYYMMDDTHHMMSS)
                    news_time_str = news['time_published']
                    news_time = datetime.strptime(news_time_str, '%Y%m%dT%H%M%S')

                    # 查找新闻发布后的价格变动
                    news_window_start = news_time
                    news_window_end = news_time + timedelta(minutes=window_minutes)

                    logger.info(f"新闻时间: {news_time}, 价格数据范围: {price_data.index.min()} 到 {price_data.index.max()}")

                    # 过滤窗口内的价格数据
                    # 确保比较的datetime都是timezone-naive
                    window_data = price_data[
                        (price_data.index >= news_window_start) &
                        (price_data.index <= news_window_end)
                    ]

                    if len(window_data) < 2:
                        logger.info(f"window_data为空，跳过: {symbol} - 新闻时间: {news_time}, window_data长度: {len(window_data)}")
                        continue

                    # 计算价格波动
                    start_price = window_data['Close'].iloc[0]
                    max_price = window_data['High'].max()
                    min_price = window_data['Low'].min()

                    # 计算波动幅度
                    volatility = max(
                        abs(max_price - start_price) / start_price,
                        abs(min_price - start_price) / start_price
                    )

                    # 结合情感和波动计算影响分数
                    sentiment_abs = abs(float(news['overall_sentiment_score']))
                    relevance = news['relevance_score']
                    logger.info(f"情感分析 - sentiment_abs: {sentiment_abs}, relevance: {relevance}")
                    impact_score = sentiment_abs * relevance * volatility * 100  # 百分比形式

                    if impact_score > 0.5:  # 显著影响阈值（降低阈值）
                        significant_news.append({
                            'news': news,
                            'impact_score': impact_score,
                            'volatility': volatility,
                            'time_diff_minutes': (datetime.now() - news_time).total_seconds() / 60
                        })

                        total_impact += impact_score

                except Exception as e:
                    logger.warning(f"分析新闻影响失败: {e}")
                    continue

            return {
                'impact_score': total_impact,
                'significant_news': significant_news[:5],  # 最多返回5条显著新闻
                'news_count': len(news_items)
            }

        except Exception as e:
            logger.error(f"计算新闻影响失败 {symbol}: {e}")
            return {'impact_score': 0.0, 'significant_news': []}