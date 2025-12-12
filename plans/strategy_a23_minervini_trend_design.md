# A23: 米涅维尼趋势模板策略详细设计文档

## 📊 策略概述

**策略名称**: 米涅维尼趋势模板策略  
**策略编号**: A23  
**基础算法**: Finance/find_stocks/minervini_screener.py  
**策略类型**: 趋势跟踪 + 多因子筛选策略  
**复杂度**: 中等  
**预期胜率**: 60-70%  
**预期年化收益**: 20-35% (在强趋势市场中表现优秀)

## 🎯 策略逻辑

### 核心原理
基于Mark Minervini的趋势模板理论，结合相对强度分析和多重技术指标筛选。该策略强调在强趋势股票中建立头寸，并严格遵循趋势模板的入场和退出规则。

### 米涅维尼趋势模板八大条件
1. **基本面**: 公司基本面强劲 (收入增长、盈利增长等)
2. **相对强度**: 股票表现优于大盘 (RS_Rating > 70)
3. **当前价格**: 价格高于150日均线和200日均线
4. **150日均线**: 150日均线高于200日均线
5. **200日均线**: 200日均线上升 (高于20周前水平)
6. **50日均线**: 价格高于50日均线
7. **52周价格**: 价格在52周最高价的75%以内
8. **52周低点**: 价格较52周最低点上涨30%以上

## ⚙️ 关键参数

### 趋势模板参数
```python
'rs_rating_threshold': 70,      # 相对强度阈值
'sma_50_period': 50,            # 50日均线周期
'sma_150_period': 150,          # 150日均线周期
'sma_200_period': 200,          # 200日均线周期
'week_52_high_pct': 0.75,       # 52周最高价百分比
'week_52_low_multiplier': 1.3,  # 52周最低价乘数
'trend_strength_min': 0.5,      # 最小趋势强度
```

### 入场过滤参数
```python
'volume_confirmation': True,     # 成交量确认
'min_volume_ratio': 1.2,         # 最小成交量比率
'fundamental_filters': True,     # 基本面过滤
'earnings_quality': True,        # 盈利质量检查
'min_market_cap': 1000000000,   # 最小市值 (10亿)
```

### 风险管理参数
```python
'initial_capital': 50000.0,      # 初始资金
'risk_per_trade': 0.015,         # 单笔风险 (1.5%)
'max_position_size': 0.08,       # 最大仓位 (8%)
'stop_loss_pct': 0.08,           # 止损百分比 (8%)
'take_profit_pct': 0.15,         # 止盈百分比 (15%)
'max_holding_days': 30,          # 最大持有天数
'trailing_stop_pct': 0.05,       # 追踪止损 (5%)
```

## 🔄 信号生成流程

### 1. 股票筛选阶段
```python
def screen_stocks_minervini(universe: List[str]) -> List[str]:
    """应用米涅维尼趋势模板筛选股票"""

    qualified_stocks = []

    for symbol in universe:
        try:
            data = get_market_data(symbol, lookback=300)  # 一年数据

            if self._passes_trend_template(data):
                # 计算相对强度
                rs_rating = self._calculate_rs_rating(symbol, data)

                if rs_rating >= self.config['rs_rating_threshold']:
                    # 基本面检查
                    if self._passes_fundamental_filters(symbol):
                        qualified_stocks.append(symbol)

        except Exception as e:
            logger.warning(f"筛选股票 {symbol} 时出错: {e}")
            continue

    return qualified_stocks
```

### 2. 趋势模板验证
```python
def _passes_trend_template(self, data: pd.DataFrame) -> bool:
    """验证米涅维尼趋势模板条件"""

    if len(data) < self.config['sma_200_period']:
        return False

    current_price = data['Close'].iloc[-1]

    # 计算均线
    sma_50 = data['Close'].rolling(self.config['sma_50_period']).mean().iloc[-1]
    sma_150 = data['Close'].rolling(self.config['sma_150_period']).mean().iloc[-1]
    sma_200 = data['Close'].rolling(self.config['sma_200_period']).mean().iloc[-1]

    # 52周价格范围
    high_52w = data['High'].rolling(252).max().iloc[-1]  # 252个交易日
    low_52w = data['Low'].rolling(252).min().iloc[-1]

    # 趋势模板条件
    conditions = [
        # 1. 价格高于150日和200日均线
        current_price > sma_150 > sma_200,

        # 2. 150日均线高于200日均线
        sma_150 > sma_200,

        # 3. 200日均线上升 (高于20周前)
        sma_200 > data['Close'].rolling(200).mean().iloc[-21],  # 20个交易日大约4周

        # 4. 价格高于50日均线
        current_price > sma_50,

        # 5. 价格在52周最高价的75%以内
        current_price >= high_52w * self.config['week_52_high_pct'],

        # 6. 价格较52周最低点上涨30%以上
        current_price >= low_52w * self.config['week_52_low_multiplier']
    ]

    return all(conditions)
```

### 3. 相对强度计算
```python
def _calculate_rs_rating(self, symbol: str, data: pd.DataFrame) -> float:
    """计算相对强度评级"""

    # 获取基准数据 (S&P 500)
    benchmark_data = get_benchmark_data('^GSPC', data.index[0], data.index[-1])

    # 计算收益率
    stock_returns = data['Close'].pct_change().cumprod().iloc[-1]
    benchmark_returns = benchmark_data['Close'].pct_change().cumprod().iloc[-1]

    # 相对强度倍数
    rs_multiple = stock_returns / benchmark_returns if benchmark_returns != 0 else 1.0

    # 转换为百分位评级 (0-100)
    # 这里需要历史数据来计算百分位，简化版使用固定映射
    if rs_multiple >= 1.5:
        rs_rating = 95
    elif rs_multiple >= 1.3:
        rs_rating = 85
    elif rs_multiple >= 1.1:
        rs_rating = 75
    elif rs_multiple >= 0.9:
        rs_rating = 65
    else:
        rs_rating = 50

    return rs_rating
```

### 4. 入场时机选择
```python
def detect_entry_signal(self, symbol: str, data: pd.DataFrame) -> Optional[Dict]:
    """检测入场信号"""

    # 首先验证趋势模板
    if not self._passes_trend_template(data):
        return None

    current_price = data['Close'].iloc[-1]

    # 等待合适的入场点
    entry_signal = self._find_optimal_entry(data, current_price)

    if entry_signal:
        # 成交量确认
        if self.config['volume_confirmation']:
            volume_ok = self._check_volume_confirmation(data)
            if not volume_ok:
                return None

        # 创建买入信号
        signal = {
            'symbol': symbol,
            'signal_type': 'MINERVINI_ENTRY',
            'action': 'BUY',
            'price': current_price,
            'reason': f'米涅维尼趋势模板: RS={entry_signal["rs_rating"]:.1f}',
            'confidence': entry_signal['confidence'],
            'trend_template': entry_signal['template_score']
        }

        return signal

    return None
```

### 5. 退出策略
```python
def detect_exit_signal(self, symbol: str, data: pd.DataFrame) -> Optional[Dict]:
    """检测退出信号"""

    if symbol not in self.positions:
        return None

    current_price = data['Close'].iloc[-1]
    entry_price = self.positions[symbol]['avg_cost']

    # 趋势模板破坏
    if not self._passes_trend_template(data):
        return self._create_exit_signal(symbol, current_price, "TREND_BREAK")

    # 相对强度下降
    current_rs = self._calculate_rs_rating(symbol, data)
    if current_rs < self.config['rs_rating_threshold'] * 0.8:  # RS下降20%
        return self._create_exit_signal(symbol, current_price, "RS_DECLINE")

    # 技术性退出
    technical_exit = self._check_technical_exits(data, entry_price, current_price)
    if technical_exit:
        return technical_exit

    return None
```

## 💰 仓位管理

### 基于趋势强度和RS评级的仓位调整
```python
def calculate_position_size_minervini(self, signal: Dict, data: pd.DataFrame) -> int:
    """基于米涅维尼因子的仓位计算"""

    current_price = signal['price']
    rs_rating = signal.get('rs_rating', 70)
    trend_strength = signal.get('trend_strength', 0.5)

    # 基础风险金额
    risk_amount = self.equity * self.config['risk_per_trade']

    # RS评级调整 (RS越高，仓位越大)
    rs_multiplier = 1.0 + (rs_rating - 70) / 100  # 70为基准

    # 趋势强度调整
    trend_multiplier = 1.0 + trend_strength

    # 波动率调整 (使用ATR)
    atr = calculate_atr(data['High'], data['Low'], data['Close'], 14).iloc[-1]
    volatility = atr / current_price

    if volatility > 0.03:  # 高波动
        vol_multiplier = 0.8
    elif volatility < 0.01:  # 低波动
        vol_multiplier = 1.2
    else:
        vol_multiplier = 1.0

    # 计算风险单位
    risk_per_share = atr * 2  # 2倍ATR作为风险单位
    base_position = risk_amount / risk_per_share

    # 应用调整因子
    adjusted_position = base_position * rs_multiplier * trend_multiplier * vol_multiplier

    # 限制最大仓位
    max_position = (self.equity * self.config['max_position_size']) / current_price
    final_position = min(int(adjusted_position), int(max_position))

    return max(final_position, 1)
```

## 🛡️ 风险管理

### 多层风控体系
```python
def apply_risk_management_minervini(self, signal: Dict, data: pd.DataFrame) -> Dict:
    """米涅维尼策略特有的风险管理"""

    current_price = signal['price']

    # 1. 基于ATR的动态止损
    atr = calculate_atr(data['High'], data['Low'], data['Close'], 14).iloc[-1]
    stop_loss_distance = atr * 2  # 2倍ATR

    # 2. 趋势模板保护 (如果破50日线，止损收紧)
    sma_50 = data['Close'].rolling(50).mean().iloc[-1]
    if current_price < sma_50:
        stop_loss_distance *= 0.8  # 收紧20%

    # 3. RS评级保护 (RS越高，止损越宽松)
    rs_rating = signal.get('rs_rating', 70)
    rs_adjustment = 1.0 + (rs_rating - 70) / 200  # 最多调整50%
    stop_loss_distance *= rs_adjustment

    # 设置止损价
    signal['stop_loss_price'] = current_price - stop_loss_distance

    # 4. 追踪止损 (盈利后启动)
    signal['trailing_stop_pct'] = self.config['trailing_stop_pct']

    # 5. 最大持有期 (趋势策略可持较长时间)
    signal['max_holding_days'] = self.config['max_holding_days']

    return signal
```

### 趋势退化检测
```python
def detect_trend_degradation(self, symbol: str, data: pd.DataFrame) -> bool:
    """检测趋势退化"""

    # 检查均线排列是否恶化
    sma_50 = data['Close'].rolling(50).mean().iloc[-1]
    sma_150 = data['Close'].rolling(150).mean().iloc[-1]
    sma_200 = data['Close'].rolling(200).mean().iloc[-1]

    current_price = data['Close'].iloc[-1]

    # 严重退化条件
    degradation_conditions = [
        current_price < sma_50,  # 跌破50日线
        sma_150 < sma_200,       # 150日线下穿200日线
        current_price < sma_150 * 0.95  # 价格显著低于150日线
    ]

    return any(degradation_conditions)
```

## 📈 性能优化

### 市场适应性调整
```python
def adapt_to_market_conditions(self, market_data: Dict) -> None:
    """根据市场条件调整参数"""

    market_trend = market_data.get('trend', 'sideways')
    volatility = market_data.get('volatility', 0.2)

    if market_trend == 'bull':
        # 牛市: 放宽入场条件，提高仓位
        self.config['rs_rating_threshold'] = 65
        self.config['max_position_size'] = 0.1
        self.config['take_profit_pct'] = 0.2

    elif market_trend == 'bear':
        # 熊市: 收紧入场条件，降低仓位
        self.config['rs_rating_threshold'] = 80
        self.config['max_position_size'] = 0.05
        self.config['stop_loss_pct'] = 0.05

    else:
        # 震荡市: 平衡参数
        self.config['rs_rating_threshold'] = 75
        self.config['max_position_size'] = 0.07
        self.config['take_profit_pct'] = 0.12
```

### 股票池动态更新
```python
def update_stock_universe(self) -> None:
    """定期更新符合条件的股票池"""

    # 获取市场数据
    market_data = get_market_data()

    # 应用趋势模板筛选
    candidates = self.screen_stocks_minervini(self.universe)

    # 按RS评级排序
    ranked_candidates = self._rank_by_rs_rating(candidates)

    # 更新活跃股票池
    self.active_stocks = ranked_candidates[:50]  # 保留前50名

    logger.info(f"更新股票池: {len(self.active_stocks)} 只股票符合米涅维尼趋势模板")
```

## 🧪 回测结果预期

### 历史表现预期
- **总收益率**: 120% (3年)
- **年化收益率**: 28%
- **夏普比率**: 1.75
- **最大回撤**: 15%
- **胜率**: 65%
- **平均盈利/亏损**: 2.5

### 市场条件适应性
- **强牛市**: 优秀 (胜率>70%, 年化>30%)
- **震荡市**: 良好 (胜率55-60%)
- **熊市**: 一般 (胜率40-50%，但回撤控制好)

## 🔧 实现细节

### 代码结构
```python
class A23MinerviniTrendStrategy(BaseStrategy):
    def __init__(self):
        super().__init__()
        self.active_stocks = []  # 符合条件的股票池

    def _default_config(self) -> Dict:
        # 返回默认配置

    def screen_stocks_minervini(self, universe: List[str]) -> List[str]:
        # 趋势模板筛选

    def _passes_trend_template(self, data: pd.DataFrame) -> bool:
        # 验证趋势模板

    def _calculate_rs_rating(self, symbol: str, data: pd.DataFrame) -> float:
        # 计算相对强度

    def detect_entry_signal(self, symbol: str, data: pd.DataFrame) -> Optional[Dict]:
        # 入场信号检测

    def detect_exit_signal(self, symbol: str, data: pd.DataFrame) -> Optional[Dict]:
        # 退出信号检测

    def generate_signals(self, symbol: str, data: pd.DataFrame,
                        indicators: Dict) -> List[Dict]:
        # 主信号生成方法
```

### 依赖指标
- 简单移动平均线 (SMA 50, 150, 200)
- 相对强度计算
- ATR (平均真实波幅)
- 成交量分析

### 测试用例
```python
def test_minervini_template():
    # 1. 测试趋势模板条件验证
    # 2. 测试RS评级计算
    # 3. 测试入场时机选择
    # 4. 测试退出条件
    # 5. 测试仓位大小计算
```

## 📋 验收标准

- [ ] 米涅维尼趋势模板条件正确验证
- [ ] 相对强度评级准确计算
- [ ] 股票筛选逻辑有效
- [ ] 入场和退出信号正确生成
- [ ] 风险管理机制有效
- [ ] 市场适应性调整正常
- [ ] 回测表现符合预期
- [ ] 文档和注释完整

## 🔗 相关链接

- 基础算法: `Finance/find_stocks/minervini_screener.py`
- 指标库: `strategies/indicators.py`
- 基类: `strategies/base_strategy.py`
- 配置: `config.py`

---

*此文档定义了A23米涅维尼趋势模板策略的完整实现规范。*