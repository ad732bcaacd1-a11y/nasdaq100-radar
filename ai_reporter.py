"""
每小時 AI 財經情報官 (Gemini 旗艦級大腦)
功能：
1. 自動抓取 QQQ / 納斯達克最新重大外電新聞
2. 調用 Google Gemini API 旗艦模型提煉華爾街深度情報
3. 每整點自動發送 LINE 推播至手機
"""

import urllib.request
import xml.etree.ElementTree as ET
import requests
import json
import logging

logger = logging.getLogger("AIReporter")

def fetch_latest_market_news() -> str:
    """從 Google News RSS 抓取即時 QQQ / 納斯達克頭條新聞"""
    try:
        url = 'https://news.google.com/rss/search?q=QQQ+OR+NASDAQ+stock+market&hl=en-US&gl=US&ceid=US:en'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        content = urllib.request.urlopen(req, timeout=10).read()
        root = ET.fromstring(content)
        
        items = []
        for item in root.findall('./channel/item')[:6]:
            title = item.find('title').text
            pubDate = item.find('pubDate').text
            items.append(f"• {title} ({pubDate})")
            
        return "\n".join(items) if items else "暫無最新新聞"
    except Exception as e:
        logger.error(f"抓取新聞失敗: {e}")
        return "無法連線至新聞來源"

def generate_ai_market_summary(gemini_api_key: str, news_text: str, model_name: str = "gemini-2.5-pro") -> str:
    """調用 Gemini 旗艦模型總整新聞"""
    if not gemini_api_key:
        return "【QQQ 納指快訊】(尚未填入 Gemini API Key，顯示原始新聞)：\n" + news_text[:300]
        
    prompt = f"""
你是一位身價百億的華爾街頂級避險基金宏觀量化策略師。
以下是過去一小時內關於納斯達克 100 (QQQ) 與美股市場的最即時外電新聞：

{news_text}

請用繁體中文為你的操盤團隊提煉一份「每小時 QQQ 戰情報告」，排版必須極度專業俐落，適合手機閱讀：
1. 💥【當前最重大核心焦點】(1~2句話一針見血直擊要害)
2. 📈【對 QQQ/科技股短線走勢預判】(明確指出：偏多、偏空或高檔震盪，並說明核心邏輯)
3. 🎯【盤中緊盯焦點與風險】(指出受影響巨頭如 NVDA, AAPL, MSFT 或利率/就業關鍵動向)

字數請嚴格控制在 250 字左右，使用專業金融用語與乾淨的 Emoji 標記。
"""

    # 嘗試呼叫 Gemini API (支援多個模型版本防呆)
    models_to_try = [model_name, "gemini-2.5-pro", "gemini-1.5-pro", "gemini-2.0-flash"]
    
    for m in models_to_try:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={gemini_api_key}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.2,
                    "maxOutputTokens": 800
                }
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                return text.strip()
            else:
                logger.warning(f"模型 {m} 回應錯誤 ({resp.status_code}): {resp.text}")
        except Exception as e:
            logger.error(f"調用 {m} 失敗: {e}")
            
    return "AI 連線逾時，請檢查 API Key 是否正確。\n\n原始新聞摘要：\n" + news_text[:250]
