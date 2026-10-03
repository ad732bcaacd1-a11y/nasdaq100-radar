"""
通知發送模組 (自動支援 Broadcast 全域推播與 Push Message)
"""

import requests
import json
import logging

logger = logging.getLogger("Notifier")

def send_line_message(token: str, user_id: str, message_text: str) -> bool:
    """
    發送 LINE 訊息：
    若有 user_id 則使用 Push Message；
    若無 user_id 則使用 Broadcast（直接發給所有好友/自己）
    """
    if not token:
        logger.warning("LINE Token 尚未設定，跳過 LINE 發送。")
        return False
        
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    if user_id and user_id.startswith("U"):
        url = "https://api.line.me/v2/bot/message/push"
        payload = {
            "to": user_id,
            "messages": [{"type": "text", "text": message_text}]
        }
    else:
        # 直接使用全域廣播（發給加好友的自己）
        url = "https://api.line.me/v2/bot/message/broadcast"
        payload = {
            "messages": [{"type": "text", "text": message_text}]
        }
    
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        if resp.status_code == 200:
            logger.info("LINE 推播成功！")
            return True
        else:
            logger.error(f"LINE 發送失敗 (代碼 {resp.status_code}): {resp.text}")
            return False
    except Exception as e:
        logger.error(f"連線 LINE 伺服器異常: {e}")
        return False

def send_telegram_message(bot_token: str, chat_id: str, message_text: str) -> bool:
    if not bot_token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message_text,
        "parse_mode": "HTML"
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        return resp.status_code == 200
    except:
        return False

def build_signal_alert_text(symbol: str, name: str, signal_info: dict) -> str:
    price = signal_info.get("price", 0.0)
    pct = signal_info.get("pct_change_5m", 0.0)
    rvol = signal_info.get("rvol", 1.0)
    bar_time = signal_info.get("bar_time", "")
    direction_emoji = "🟢" if pct >= 0 else "🔴"
    
    webull_url = f"https://app.webull.com/stocks/{symbol.lower()}"
    
    text = (
        f"🚨【Webull 納指100 買訊共振通知】\n"
        f"─────────────────\n"
        f"🎯 標的：{symbol} ({name})\n"
        f"💰 當前現價：${price:.2f} ({direction_emoji} {pct:+.2f}%)\n"
        f"⏰ K棒週期：5分鐘 K線 [{bar_time}]\n"
        f"─────────────────\n"
        f"🔥 觸發三大條件：\n"
        f" 1. Supertrend：🟢 翻多買訊 (Buy Signal)\n"
        f" 2. MACD：🌟 黃金交叉 (DIF: {signal_info.get('macd_val')} > DEA: {signal_info.get('macd_signal')})\n"
        f" 3. RVOL 爆量：💥 {rvol:.1f}倍均量 (標準 > 1.8x)\n"
        f"─────────────────\n"
        f"📱 Webull 看盤：\n"
        f"{webull_url}\n"
    )
    return text
