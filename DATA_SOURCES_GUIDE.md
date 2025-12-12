# 选股策略数据源指南

## 📊 当前演示数据源

### MockDataProvider (演示用模拟数据)

演示脚本中使用的是 `MockDataProvider`，它生成**模拟数据**用于测试和演示：

#### **股票价格数据**
- **数据类型**: OHLCV (开盘价、最高价、最低价、收盘价、成交量)
- **时间范围**: 2022-01-01 至 2024-01-01 (2年日线数据)
- **股票池**: AAPL, MSFT, GOOGL, AMZN, TSLA, NVDA, META, NFLX (8只美股)
- **生成方法**: 使用随机游走模型 + 真实波动特征

#### **基本面数据**
- **财务指标**: ROE, ROA, 债务比率, 营收增长, 净利润增长, 股息率等
- **公司信息**: 市值, PE比率, PB比率, 行业分类
- **生成方法**: 在合理范围内随机生成，保持相对真实性

#### **基准指数数据**
- **指数**: S&P 500 (^GSPC)
- **用途**: Minervini策略的相对强度计算

```python
# 模拟数据生成示例
np.random.seed(hash(symbol) % 2**32)  # 确保每只股票数据一致
initial_price = np.random.uniform(50, 200)
price_changes = np.random.normal(0.001, 0.02, len(dates))  # 随机游走
prices = initial_price * np.exp(np.cumsum(price_changes))
```

## 🌐 真实数据源接入方案

### 1. Yahoo Finance (推荐首选)

#### **优点**
- ✅ 免费使用
- ✅ 数据全面 (价格 + 基本面)
- ✅ 更新及时
- ✅ API稳定

#### **接入方式**
```python
import yfinance as yf

# 获取股票数据
stock = yf.Ticker("AAPL")
data = stock.history(period="2y")  # 获取2年数据

# 获取基本面数据
info = stock.info
fundamentals = {
    'market_cap': info.get('marketCap'),
    'pe_ratio': info.get('trailingPE'),
    'pb_ratio': info.get('priceToBook'),
    'roe': info.get('returnOnEquity'),
    'debt_ratio': info.get('debtToEquity'),
    'dividend_yield': info.get('dividendYield', 0),
}
```

#### **安装和使用**
```bash
pip install yfinance
```

### 2. Alpha Vantage (专业财务数据)

#### **优点**
- ✅ 专业财务数据
- ✅ 历史数据完整
- ✅ RESTful API
- ✅ JSON格式

#### **接入方式**
```python
import requests

# 获取基本面数据
url = f"https://www.alphavantage.co/query?function=OVERVIEW&symbol=AAPL&apikey=YOUR_API_KEY"
response = requests.get(url)
data = response.json()

fundamentals = {
    'market_cap': float(data.get('MarketCapitalization', 0)),
    'pe_ratio': float(data.get('PERatio', 0)),
    'pb_ratio': float(data.get('PriceToBookRatio', 0)),
    'roe': float(data.get('ReturnOnEquityTTM', 0)),
    'debt_ratio': float(data.get('DebtToEquity', 0)),
    'dividend_yield': float(data.get('DividendYield', 0)),
    'revenue_growth': float(data.get('QuarterlyRevenueGrowthYOY', 0)),
}
```

#### **获取API Key**
1. 访问 [Alpha Vantage](https://www.alphavantage.co/support/#api-key)
2. 注册账号获取免费API Key
3. 每日限制100次调用 (免费版)

### 3. Financial Modeling Prep

#### **优点**
- ✅ 丰富的财务比率
- ✅ 行业分析数据
- ✅ 批量获取能力

#### **接入方式**
```python
# 获取财务比率
url = f"https://financialmodelingprep.com/api/v3/ratios/AAPL?apikey=YOUR_API_KEY"
ratios = requests.get(url).json()

# 获取关键指标
roe = ratios[0].get('returnOnEquity', 0)
roa = ratios[0].get('returnOnAssets', 0)
debt_ratio = ratios[0].get('debtRatio', 0)
```

### 4. 东方财富/同花顺 (A股数据)

#### **适用于中国市场**
```python
# 使用 akshare 或 tushare
import akshare as ak

# 获取A股基本面数据
stock_financial = ak.stock_financial_report_sina(symbol="000001")
```

## 🏗️ 数据提供者架构

### 统一接口设计

```python
class DataProvider(ABC):
    """数据提供者抽象基类"""

    @abstractmethod
    def get_stock_data(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        """获取股票价格数据"""
        pass

    @abstractmethod
    def get_fundamental_data(self, symbol: str) -> dict:
        """获取基本面数据"""
        pass

    @abstractmethod
    def get_market_data(self, index: str) -> pd.DataFrame:
        """获取市场指数数据"""
        pass
```

### 具体实现类

```python
class YahooDataProvider(DataProvider):
    """Yahoo Finance数据提供者"""
    def get_stock_data(self, symbol, period="1y"):
        import yfinance as yf
        return yf.Ticker(symbol).history(period=period)

    def get_fundamental_data(self, symbol):
        import yfinance as yf
        info = yf.Ticker(symbol).info
        return self._parse_yahoo_fundamentals(info)

class AlphaVantageProvider(DataProvider):
    """Alpha Vantage数据提供者"""
    def __init__(self, api_key):
        self.api_key = api_key

    def get_fundamental_data(self, symbol):
        # 实现Alpha Vantage API调用
        pass
```

## 🔧 实际使用配置

### 1. 创建真实数据提供者

```python
# config/data_config.py
class DataConfig:
    YAHOO_API = None  # Yahoo Finance 免费使用
    ALPHA_VANTAGE_API_KEY = "YOUR_API_KEY"  # 从Alpha Vantage获取
    FMP_API_KEY = "YOUR_API_KEY"  # 从Financial Modeling Prep获取

# data/real_data_provider.py
from config.data_config import DataConfig
import yfinance as yf
import requests

class RealDataProvider:
    def __init__(self):
        self.config = DataConfig()

    def get_stock_data(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        """获取真实股票数据"""
        try:
            stock = yf.Ticker(symbol)
            data = stock.history(period=period)

            # 数据验证和清理
            if data.empty:
                raise ValueError(f"未找到股票 {symbol} 的数据")

            return data
        except Exception as e:
            logger.error(f"获取股票数据失败 {symbol}: {e}")
            return pd.DataFrame()

    def get_fundamental_data(self, symbol: str) -> dict:
        """获取真实基本面数据"""
        try:
            stock = yf.Ticker(symbol)
            info = stock.info

            return {
                'roe': info.get('returnOnEquity'),
                'roa': info.get('returnOnAssets'),
                'debt_ratio': info.get('debtToEquity'),
                'revenue_growth': info.get('revenueGrowth'),
                'net_income_growth': info.get('earningsGrowth'),
                'dividend_yield': info.get('dividendYield', 0),
                'market_cap': info.get('marketCap'),
                'pe_ratio': info.get('trailingPE'),
                'pb_ratio': info.get('priceToBook'),
                'sector': info.get('sector'),
            }
        except Exception as e:
            logger.error(f"获取基本面数据失败 {symbol}: {e}")
            return {}
```

### 2. 在策略中使用真实数据

```python
# 将MockDataProvider替换为真实数据提供者
from data.real_data_provider import RealDataProvider

# 初始化真实数据提供者
data_provider = RealDataProvider()

# 创建选股管理器
screener_manager = ScreenerManager(data_provider)

# 执行选股策略
results = screener_manager.run_screener('fundamental', config)
```

## ⚠️ 数据质量和限制

### **数据时效性**
- Yahoo Finance: 实时数据 (15分钟延迟)
- Alpha Vantage: 每日更新
- 基本面数据: 季度/年度更新

### **API限制**
- **Yahoo Finance**: 无限制 (免费)
- **Alpha Vantage**: 每日500次调用 (免费版)
- **Financial Modeling Prep**: 每月250次调用 (免费版)

### **数据覆盖**
- **美股**: 完整覆盖
- **A股**: 部分覆盖 (需要特定数据源)
- **港股**: 基本覆盖

### **错误处理**
```python
def safe_get_data(provider, symbol, retries=3):
    """安全的获取数据，带重试机制"""
    for attempt in range(retries):
        try:
            data = provider.get_stock_data(symbol)
            if not data.empty:
                return data
        except Exception as e:
            logger.warning(f"获取数据失败 {symbol} (尝试 {attempt+1}/{retries}): {e}")
            time.sleep(1)

    return pd.DataFrame()  # 返回空数据
```

## 🚀 推荐实施方案

### **初级用户 (免费方案)**
1. 使用 Yahoo Finance (完全免费)
2. 每月手动更新基本面数据
3. 适用于个人投资分析

### **进阶用户 (付费方案)**
1. Alpha Vantage + Yahoo Finance 组合
2. 自动数据更新和缓存
3. 适用于量化交易系统

### **专业用户 (企业方案)**
1. 多个数据源组合使用
2. 实时数据流处理
3. 高可用性和容错机制

## 📝 数据源切换示例

```python
# 演示环境
if DEMO_MODE:
    from Test.test_screeners import MockDataProvider
    data_provider = MockDataProvider()
else:
    from data.real_data_provider import RealDataProvider
    data_provider = RealDataProvider()

# 后续代码保持不变
screener_manager = ScreenerManager(data_provider)
results = screener_manager.run_screener('rsi')
```

通过这种设计，你可以在演示和生产环境之间轻松切换数据源！🎯</content>
</xai:function_call">## 📊 选股策略数据源详解

你问得很好！让我详细解释演示中使用的数据源，以及如何在实际应用中接入真实数据。

## 🎭 当前演示数据源

### **MockDataProvider - 模拟数据 (仅用于演示)**

演示脚本使用的是**模拟数据生成器**，不是真实数据：

```python
class MockDataProvider:
    def _generate_mock_data(self):
        # 模拟8只美股: AAPL, MSFT, GOOGL, AMZN, TSLA, NVDA, META, NFLX
        symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'NVDA', 'META', 'NFLX']

        # 生成2年随机价格数据 (2022-2024)
        dates = pd.date_range(start='2022-01-01', end='2024-01-01', freq='D')

        for symbol in symbols:
            # 使用随机游走模型生成价格
            np.random.seed(hash(symbol) % 2**32)  # 确保每只股票数据一致
            initial_price = np.random.uniform(50, 200)
            price_changes = np.random.normal(0.001, 0.02, len(dates))
            prices = initial_price * np.exp(np.cumsum(price_changes))

            # 生成OHLCV数据
            df = pd.DataFrame({
                'Open': prices * (1 + np.random.normal(0, 0.01, len(dates))),
                'High': prices * (1 + np.random.normal(0.005, 0.01, len(dates))),
                'Low': prices * (1 - np.random.normal(0.005, 0.01, len(dates))),
                'Close': prices,
                'Volume': np.random.uniform(100000, 1000000, len(dates))
            }, index=dates)

            self.stock_data[symbol] = df

            # 生成随机基本面数据
            self.fundamental_data[symbol] = {
                'roe': np.random.uniform(0.05, 0.25),        # ROE: 5%-25%
                'roa': np.random.uniform(0.02, 0.15),        # ROA: 2%-15%
                'debt_ratio': np.random.uniform(0.1, 2.0),   # 债务比率: 10%-200%
                'revenue_growth': np.random.uniform(-0.1, 0.3), # 营收增长: -10%到30%
                'net_income_growth': np.random.uniform(-0.2, 0.4), # 利润增长: -20%到40%
                'dividend_yield': np.random.uniform(0, 0.05), # 股息率: 0-5%
                # ... 其他指标
            }
```

**为什么使用模拟数据？**
- ✅ **安全测试**: 不依赖外部API
- ✅ **一致性**: 每次运行结果相同
- ✅ **离线可用**: 不需要网络连接
- ✅ **快速演示**: 立即可用

## 🌐 真实数据源接入方案

### **1. Yahoo Finance (推荐 - 完全免费)**

#### **安装和使用**
```bash
pip install yfinance
```

#### **获取股票价格数据**
```python
import yfinance as yf

# 获取苹果公司1年日线数据
aapl = yf.Ticker("AAPL")
data = aapl.history(period="1y")

print(data.head())
#                  Open        High         Low       Close     Volume
# Date
# 2023-12-12  197.32  199.62  196.16  197.96  53442800
# 2023-12-13  198.26  198.90  194.83  197.79  56398800
# ...
```

#### **获取基本面数据**
```python
# 获取基本面信息
info = aapl.info

fundamentals = {
    'market_cap': info.get('marketCap'),           # 市值
    'pe_ratio': info.get('trailingPE'),           # PE比率
    'pb_ratio': info.get('priceToBook'),          # PB比率
    'roe': info.get('returnOnEquity'),            # ROE
    'roa': info.get('returnOnAssets'),            # ROA
    'debt_ratio': info.get('debtToEquity'),       # 债务比率
    'revenue_growth': info.get('revenueGrowth'),  # 营收增长
    'dividend_yield': info.get('dividendYield', 0), # 股息率
    'sector': info.get('sector'),                 # 行业
}
```

### **2. Alpha Vantage (专业财务数据)**

#### **获取API Key**
1. 访问 [Alpha Vantage](https://www.alphavantage.co/support/#api-key)
2. 免费注册获取API Key
3. 免费版限制: 每日500次调用

#### **使用示例**
```python
import requests

API_KEY = "YOUR_API_KEY"  # 替换为你的API Key

# 获取公司概览数据
url = f"https://www.alphavantage.co/query?function=OVERVIEW&symbol=AAPL&apikey={API_KEY}"
response = requests.get(url)
data = response.json()

fundamentals = {
    'market_cap': float(data.get('MarketCapitalization', 0)),
    'pe_ratio': float(data.get('PERatio', 0)),
    'pb_ratio': float(data.get('PriceToBookRatio', 0)),
    'roe': float(data.get('ReturnOnEquityTTM', 0)),
    'debt_ratio': float(data.get('DebtToEquity', 0)),
    'dividend_yield': float(data.get('DividendYield', 0)),
    'revenue_growth': float(data.get('QuarterlyRevenueGrowthYOY', 0)),
}
```

### **3. Financial Modeling Prep**

#### **特点**
- 每月250次免费调用
- 丰富的财务比率数据
- 支持批量获取

```python
# 获取财务比率
url = f"https://financialmodelingprep.com/api/v3/ratios/AAPL?apikey=YOUR_API_KEY"
ratios = requests.get(url).json()

if ratios:
    latest = ratios[0]  # 获取最新数据
    fundamentals = {
        'roe': latest.get('returnOnEquity'),
        'roa': latest.get('returnOnAssets'),
        'debt_ratio': latest.get('debtRatio'),
        # ... 更多指标
    }
```

## 🏗️ 创建真实数据提供者

### **替换演示数据源**

```python
# data/real_data_provider.py
import yfinance as yf
import pandas as pd
import logging

logger = logging.getLogger(__name__)

class RealDataProvider:
    """真实数据提供者 - 使用Yahoo Finance"""

    def get_stock_data(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        """获取真实股票价格数据"""
        try:
            stock = yf.Ticker(symbol)
            data = stock.history(period=period)

            if data.empty:
                logger.warning(f"未找到股票 {symbol} 的数据")
                return pd.DataFrame()

            # 数据清理
            data = data.dropna()
            return data

        except Exception as e:
            logger.error(f"获取股票数据失败 {symbol}: {e}")
            return pd.DataFrame()

    def get_fundamental_data(self, symbol: str) -> dict:
        """获取真实基本面数据"""
        try:
            stock = yf.Ticker(symbol)
            info = stock.info

            return {
                'roe': info.get('returnOnEquity'),
                'roa': info.get('returnOnAssets'),
                'debt_ratio': info.get('debtToEquity'),
                'revenue_growth': info.get('revenueGrowth'),
                'net_income_growth': info.get('earningsGrowth'),
                'dividend_yield': info.get('dividendYield', 0),
                'market_cap': info.get('marketCap'),
                'pe_ratio': info.get('trailingPE'),
                'pb_ratio': info.get('priceToBook'),
                'sector': info.get('sector'),
            }

        except Exception as e:
            logger.error(f"获取基本面数据失败 {symbol}: {e}")
            return {}
```

### **在策略中使用真实数据**

```python
# 替换这行
# from Test.test_screeners import MockDataProvider
# data_provider = MockDataProvider()

# 改为
from data.real_data_provider import RealDataProvider
data_provider = RealDataProvider()

# 后续代码保持不变
screener_manager = ScreenerManager(data_provider)
results = screener_manager.run_screener('fundamental')
```

## ⚠️ 数据源限制和注意事项

### **API限制**
| 数据源 | 每日限制 | 费用 | 特点 |
|--------|----------|------|------|
| Yahoo Finance | 无限制 | 免费 | 价格+基本面，实时更新 |
| Alpha Vantage | 500次 | 免费 | 专业财务数据 |
| Financial Modeling Prep | 250次 | 免费 | 丰富财务比率 |

### **数据质量**
- **价格数据**: 通常实时或15分钟延迟
- **基本面数据**: 按季度/年度更新
- **覆盖范围**: 美股最完整，A股/港股需额外数据源

### **错误处理**
```python
def safe_get_data(provider, symbol, retries=3):
    """带重试的数据获取"""
    for attempt in range(retries):
        try:
            data = provider.get_stock_data(symbol)
            if not data.empty:
                return data
        except Exception as e:
            logger.warning(f"尝试 {attempt+1} 失败: {e}")
            time.sleep(1)  # 避免频繁请求

    return pd.DataFrame()  # 返回空数据
```

## 🚀 快速开始使用真实数据

### **步骤1: 安装依赖**
```bash
pip install yfinance pandas numpy
```

### **步骤2: 创建数据提供者文件**
创建 `data/real_data_provider.py` 并复制上面的代码。

### **步骤3: 修改演示脚本**
```python
# 在任何演示脚本顶部修改
# from Test.test_screeners import MockDataProvider  # 注释掉
from data.real_data_provider import RealDataProvider  # 启用

# data_provider = MockDataProvider()  # 注释掉
data_provider = RealDataProvider()  # 启用
```

### **步骤4: 运行测试**
```bash
python demo_screener.py
```

现在你就能使用真实的美股数据进行选股分析了！🎯📈

**总结**: 演示使用模拟数据是为了快速展示功能，实际使用时可以轻松切换到Yahoo Finance等真实数据源。