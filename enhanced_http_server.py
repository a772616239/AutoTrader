#!/usr/bin/env python3
"""
增强版HTTP服务器，提供多维股票数据
curl "http://localhost:8001/enhanced-data?symbol=AAPL&period=3mo"
curl "http://localhost:8001/analysis-report?symbol=MSFT"

"""
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import enhanced_stock_data as esd
from datetime import datetime
class EnhancedStockAPIHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.data_provider = esd.EnhancedStockData()
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        parsed = urlparse(self.path)
        
        # 根路径
        if parsed.path == '/':
            self._send_html_response()
            return
            
        # 增强数据接口
        elif parsed.path == '/enhanced-data':
            params = parse_qs(parsed.query)
            symbol = params.get('symbol', ['AAPL'])[0]
            period = params.get('period', ['1mo'])[0]
            interval = params.get('interval', ['1d'])[0]
            
            data = self.data_provider.get_enhanced_data(symbol, period, interval)
            self._send_json_response(data)
            return
            
        # 批量获取接口
        elif parsed.path == '/batch-data':
            params = parse_qs(parsed.query)
            symbols = params.get('symbols', ['AAPL,MSFT'])[0].split(',')
            
            batch_result = {}
            for symbol in symbols[:5]:  # 限制最多5个
                batch_result[symbol] = self.data_provider.get_enhanced_data(
                    symbol.strip(), '1mo', '1d'
                )
            
            self._send_json_response(batch_result)
            return
            
        # 分析报告接口
        elif parsed.path == '/analysis-report':
            params = parse_qs(parsed.query)
            symbol = params.get('symbol', ['AAPL'])[0]
            
            data = self.data_provider.get_enhanced_data(symbol, '3mo', '1d')
            report = self._generate_analysis_report(data)
            self._send_json_response(report)
            return
    
    def do_POST(self):
        """处理POST请求，用于复杂查询"""
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        
        try:
            data = json.loads(post_data)
            symbol = data.get('symbol', 'AAPL')
            features = data.get('features', ['all'])
            
            # 根据请求的特征类型返回数据
            result = self.data_provider.get_enhanced_data(symbol, '1mo', '1d')
            
            # 如果指定了特定特征，只返回需要的部分
            if features != ['all']:
                filtered = {}
                for feature in features:
                    if feature in result:
                        filtered[feature] = result[feature]
                result = filtered
            
            self._send_json_response(result)
            
        except Exception as e:
            self._send_json_response({'error': str(e)})
    
    def _send_html_response(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        html = """
        <html>
        <head><title>增强版股票数据API</title></head>
        <body>
            <h1>增强版股票数据API服务</h1>
            <h3>可用接口：</h3>
            <ul>
                <li><a href="/enhanced-data?symbol=AAPL">单股票增强数据</a></li>
                <li><a href="/batch-data?symbols=AAPL,MSFT,GOOGL">批量股票数据</a></li>
                <li><a href="/analysis-report?symbol=AAPL">分析报告</a></li>
            </ul>
            <h3>示例：</h3>
            <code>GET /enhanced-data?symbol=600519.SS&period=3mo&interval=1d</code>
        </body>
        </html>
        """
        self.wfile.write(html.encode())
    
    def _send_json_response(self, data):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, indent=2).encode())
    
    def _generate_analysis_report(self, data):
        """生成分析报告"""
        if 'error' in data:
            return data
        
        report = {
            'summary': {
                'symbol': data.get('metadata', {}).get('symbol', ''),
                'analysis_time': datetime.now().isoformat(),
                'data_quality': 'good' if data.get('data_points', 0) > 20 else 'limited'
            },
            'key_metrics': {},
            'recommendations': [],
            'risk_assessment': {}
        }
        
        # 提取关键指标
        indicators = data.get('technical_indicators', {})
        features = data.get('price_features', {})
        
        # 趋势判断
        ma_signal = "neutral"
        if 'MA_5' in indicators and 'MA_20' in indicators:
            if indicators['MA_5'] > indicators['MA_20']:
                ma_signal = "bullish"
            else:
                ma_signal = "bearish"
        
        # RSI状态
        rsi_signal = "neutral"
        if 'RSI' in indicators:
            if indicators['RSI'] < 30:
                rsi_signal = "oversold"
            elif indicators['RSI'] > 70:
                rsi_signal = "overbought"
        
        report['key_metrics'] = {
            'trend': ma_signal,
            'momentum': rsi_signal,
            'volatility': features.get('volatility_20d', 0),
            'volume_trend': features.get('volume_change', 0)
        }
        
        # 生成建议
        signals = data.get('trading_signals', [])
        for signal in signals:
            if signal['type'] == 'oversold' and signal['strength'] == 'high':
                report['recommendations'].append({
                    'action': '考虑分批买入',
                    'reason': 'RSI显示超卖，可能有反弹机会',
                    'confidence': 'medium'
                })
        
        # 风险评估
        risk_metrics = data.get('risk_metrics', {})
        report['risk_assessment'] = {
            'max_drawdown': risk_metrics.get('max_drawdown', 0),
            'risk_level': 'low' if abs(risk_metrics.get('max_drawdown', 0)) < 10 else 'medium'
        }
        
        return report

def run_enhanced_server(port=8001):
    """启动增强版服务器"""
    server_address = ('', port)
    httpd = HTTPServer(server_address, EnhancedStockAPIHandler)
    print(f'🚀 增强版数据服务器启动成功，端口 {port}')
    print(f'📊 提供技术指标、特征工程、分析报告')
    print(f'🌐 访问 http://localhost:{port} 查看接口文档')
    httpd.serve_forever()

if __name__ == '__main__':
    run_enhanced_server(port=8001)