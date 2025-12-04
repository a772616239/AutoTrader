#!/usr/bin/env python3
"""
为大模型优化的数据格式化
"""
import json
from datetime import datetime

class LLMDataFormatter:
    """专门为LLM优化的数据格式化"""
    
    @staticmethod
    def format_for_llm(enhanced_data, style="detailed"):
        """
        将增强数据格式化为适合LLM处理的格式
        
        Args:
            enhanced_data: EnhancedStockData返回的数据
            style: "detailed"|"concise"|"analytical"
        """
        if 'error' in enhanced_data:
            return enhanced_data
        
        if style == "concise":
            return LLMDataFormatter._concise_format(enhanced_data)
        elif style == "analytical":
            return LLMDataFormatter._analytical_format(enhanced_data)
        else:
            return LLMDataFormatter._detailed_format(enhanced_data)
    
    @staticmethod
    def _detailed_format(data):
        """详细格式，包含所有数据"""
        formatted = {
            "股票分析数据": {
                "基本信息": {
                    "代码": data.get('metadata', {}).get('symbol', ''),
                    "名称": data.get('company_info', {}).get('name', ''),
                    "行业": data.get('company_info', {}).get('industry', ''),
                    "市值": data.get('company_info', {}).get('marketCap', 0),
                    "更新日期": data.get('metadata', {}).get('last_updated', '')
                },
                "当前状态": {
                    "最新价格": data.get('price_features', {}).get('last_close', 0),
                    "日涨跌幅": f"{data.get('price_features', {}).get('price_change_1d', 0):.2f}%",
                    "周涨跌幅": f"{data.get('price_features', {}).get('price_change_5d', 0):.2f}%",
                    "月涨跌幅": f"{data.get('price_features', {}).get('price_change_20d', 0):.2f}%"
                },
                "技术指标": data.get('technical_indicators', {}),
                "交易信号": data.get('trading_signals', []),
                "风险指标": data.get('risk_metrics', {}),
                "特征数据": {
                    "价格特征": data.get('price_features', {}),
                    "标准化特征": data.get('normalized_features', {})
                }
            },
            "分析提示": LLMDataFormatter._generate_analysis_prompt(data)
        }
        
        return formatted
    
    @staticmethod
    def _concise_format(data):
        """简洁格式，只包含关键信息"""
        indicators = data.get('technical_indicators', {})
        
        return {
            "股票": data.get('metadata', {}).get('symbol', ''),
            "价格": data.get('price_features', {}).get('last_close', 0),
            "涨跌": f"{data.get('price_features', {}).get('price_change_1d', 0):.2f}%",
            "RSI": indicators.get('RSI', 0),
            "MACD": indicators.get('MACD', 0),
            "趋势": "看涨" if indicators.get('MA_5', 0) > indicators.get('MA_20', 0) else "看跌",
            "波动率": f"{data.get('price_features', {}).get('volatility_20d', 0):.1f}%",
            "信号": [s['type'] for s in data.get('trading_signals', [])]
        }
    
    @staticmethod
    def _analytical_format(data):
        """分析格式，结构化分析框架"""
        indicators = data.get('technical_indicators', {})
        features = data.get('price_features', {})
        
        analysis = {
            "分析框架": {
                "时间": datetime.now().isoformat(),
                "标的": data.get('metadata', {}).get('symbol', ''),
                "分析维度": ["趋势", "动量", "波动", "风险", "量价"]
            },
            "多维评估": {
                "趋势分析": {
                    "短期趋势": "上涨" if features.get('price_change_5d', 0) > 0 else "下跌",
                    "均线排列": "多头" if indicators.get('MA_5', 0) > indicators.get('MA_20', 0) else "空头",
                    "趋势强度": abs(features.get('price_change_20d', 0)) / 20
                },
                "动量分析": {
                    "RSI状态": "超买" if indicators.get('RSI', 0) > 70 else "超卖" if indicators.get('RSI', 0) < 30 else "中性",
                    "MACD方向": "金叉" if (indicators.get('MACD') or 0) > (indicators.get('MACD_Signal') or 0) else "死叉",
                    "随机指标": f"K:{indicators.get('Stoch_K', 0):.1f}, D:{indicators.get('Stoch_D', 0):.1f}"
                },
                "波动分析": {
                    "历史波动": f"{features.get('volatility_20d', 0):.1f}%",
                    "ATR": indicators.get('ATR', 0),
                    "布林带位置": "上轨" if features.get('last_close', 0) > indicators.get('BB_upper', 0) 
                                 else "下轨" if features.get('last_close', 0) < indicators.get('BB_lower', 0) 
                                 else "中轨附近"
                },
                "量价分析": {
                    "成交量变化": f"{features.get('volume_change', 0):.1f}%",
                    "量价关系": "健康" if features.get('price_volume_divergence', 0) == 0 else "背离",
                    "OBV趋势": "上升" if indicators.get('OBV', 0) > 0 else "下降"
                },
                "风险分析": {
                    "最大回撤": f"{data.get('risk_metrics', {}).get('max_drawdown', 0):.1f}%",
                    "夏普比率": data.get('risk_metrics', {}).get('sharpe_ratio', 0),
                    "风险等级": "低" if abs(data.get('risk_metrics', {}).get('max_drawdown', 0)) < 10 else "中"
                }
            },
            "综合评分": LLMDataFormatter._calculate_composite_score(data),
            "关注要点": LLMDataFormatter._extract_key_points(data)
        }
        
        return analysis
    
    @staticmethod
    def _generate_analysis_prompt(data):
        """生成分析提示"""
        symbol = data.get('metadata', {}).get('symbol', '')
        indicators = data.get('technical_indicators', {})
        
        prompts = [
            f"基于提供的{symbol}多维度数据，请进行综合分析：",
            "1. 评估当前趋势方向和强度",
            "2. 识别主要技术信号和交易机会",
            "3. 分析风险水平和潜在回撤",
            "4. 给出具体的操作建议（如买入/卖出/持有）",
            "5. 提供关键支撑阻力位参考"
        ]
        
        # 添加特定提示
        if indicators.get('RSI', 0) < 30:
            prompts.append("注意：RSI显示超卖，关注反弹机会")
        elif indicators.get('RSI', 0) > 70:
            prompts.append("注意：RSI显示超买，警惕回调风险")
        
        return prompts
    
    @staticmethod
    def _calculate_composite_score(data):
        """计算综合评分（0-100）"""
        indicators = data.get('technical_indicators', {})
        features = data.get('price_features', {})
        risk = data.get('risk_metrics', {})
        
        score = 50  # 基准分
        
        # 趋势加分（20分）
        if features.get('price_change_5d', 0) > 0:
            score += 5
        if features.get('price_change_20d', 0) > 0:
            score += 10
        if indicators.get('MA_5', 0) > indicators.get('MA_20', 0):
            score += 5
        
        # 动量调整（15分）
        rsi = indicators.get('RSI', 50)
        if 40 <= rsi <= 60:
            score += 10
        elif 30 <= rsi < 40 or 60 < rsi <= 70:
            score += 5
        
        # 风险调整（15分）
        if abs(risk.get('max_drawdown', 0)) < 5:
            score += 10
        elif abs(risk.get('max_drawdown', 0)) < 10:
            score += 5
        
        return min(max(score, 0), 100)
    
    @staticmethod
    def _extract_key_points(data):
        """提取关键要点"""
        points = []
        indicators = data.get('technical_indicators', {})
        features = data.get('price_features', {})
        
        # 价格相关
        price_change = features.get('price_change_1d', 0)
        if abs(price_change) > 3:
            points.append(f"价格波动较大，日内涨跌{price_change:.1f}%")
        
        # 技术指标相关
        if indicators.get('RSI', 50) < 30:
            points.append("RSI进入超卖区域，可能存在技术性反弹机会")
        elif indicators.get('RSI', 50) > 70:
            points.append("RSI进入超买区域，注意短期回调风险")
        
        # 量价关系
        if features.get('price_volume_divergence', 0) == 1:
            points.append("出现量价背离现象，需关注趋势持续性")
        
        # 风险提示
        if abs(data.get('risk_metrics', {}).get('max_drawdown', 0)) > 15:
            points.append("历史最大回撤较大，需注意风险控制")
        
        return points