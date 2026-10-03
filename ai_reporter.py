"""
高頻 AI 財經情報官 (Gemini 3 旗艦模型 - 每 10 分鐘極速版)
1. 自動抓取最新 QQQ / 納斯達克重大頭條新聞
2. Gemini 3 旗艦模型每 10 分鐘深度提煉多空戰報
3. 支援 Web 網頁專區即時查閱 + LINE 每 10 分鐘定時推播
"""

import urllib.request
import xml.etree.ElementTree as ET
import requests
import json
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("AIReporter")

# 儲存最近產生的 AI 報告歷史 (供網頁展示)
news_reports_history = []

def fetch_latest_market_news() -> list:
    """從 Google News RSS 抓取即時 QQQ / 納斯達克 / 科技巨頭頭條新聞"""
    try:
        url = 'https://news.google.com/rss/search?q=QQQ+OR+NASDAQ+stock+market&hl=en-US&gl=US&ceid=US:en'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        content = urllib.request.urlopen(req, timeout=10).read()
        root = ET.fromstring(content)
        
        items = []
        for item in root.findall('./channel/item')[:8]:
            title = item.find('title').text
            pubDate = item.find('pubDate').text
            link = item.find('link').text if item.find('link') is not None else ""
            items.append({
                "title": title,
                "pubDate": pubDate,
                "link": link
            })
            
        return items
    except Exception as e:
        logger.error(f"抓取新聞失敗: {e}")
        return []

def generate_ai_market_summary(gemini_api_key: str, news_items: list, model_name: str = "gemini-3-flash-preview") -> dict:
    """調用 Gemini 旗艦模型深度提煉新聞"""
    tw_now = datetime.now(timezone(timedelta(hours=8))).strftime("%H:%M")
    
    if not news_items:
        return {
            "time": tw_now,
            "headline": "暫無重大即時外電",
            "content": "目前市場暫無最新突發外電，大盤處於常態運行中。",
            "sentiment": "中性觀望",
            "sources": []
        }
        
    news_text = "\n".join([f"• {n['title']} ({n['pubDate']})" for n in news_items])
    
    if not gemini_api_key:
        return {
            "time": tw_now,
            "headline": "美股即時快訊 (未配置 AI Key)",
            "content": news_text[:300],
            "sentiment": "中性",
            "sources": news_items[:3]
        }
        
    prompt = f"""
你是一位身價百億的華爾街頂級避險基金宏觀量化策略師。
以下是過去 10 分鐘內關於納斯達克 100 (QQQ) 與美股市場的最即時外電新聞：

{news_text}

請用繁體中文為你的操盤團隊提煉一份「10分鐘極速 QQQ 操盤戰報」，排版精準俐落：
1. 💥【當前最重大核心焦點】(1~2句話直擊要害)
2. 📈【對 QQQ/科技股短線走勢預判】(明確指出：偏多、偏空或高檔震盪，並簡述核心邏輯)
3. 🎯【盤中緊盯焦點與重點個股】(指出受影響巨頭如 NVDA, AAPL, MSFT, TSLA 或關鍵數據)

字數嚴格控制在 200 字以內，使用專業乾淨的 Emoji 標記。
"""

    models_to_try = [model_name, "gemini-3-flash-preview", "gemini-flash-latest"]
    
    for m in models_to_try:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={gemini_api_key}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": 600
                }
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                analysis_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                
                # 判定市場情緒標籤
                sentiment = "📈 偏多動能" if any(w in analysis_text for w in ["偏多", "大漲", "上漲", "高點", "降息", "樂觀"]) else \
                            "📉 偏空防禦" if any(w in analysis_text for w in ["偏空", "下跌", "重挫", "升息", "恐慌", "走弱"]) else "⚖️ 區間震盪"
                
                report = {
                    "time": tw_now,
                    "sentiment": sentiment,
                    "content": analysis_text,
                    "sources": news_items[:4]
                }
                news_reports_history.append(report)
                if len(news_reports_history) > 30:
                    news_reports_history.pop(0)
                return report
        except Exception as e:
            logger.error(f"調用 {m} 失敗: {e}")
            
    fallback_report = {
        "time": tw_now,
        "sentiment": "⚖️ 連線備援",
        "content": "AI 連線逾時，為您顯示即時新聞：\n" + news_text[:200],
        "sources": news_items[:3]
    }
    return fallback_report
