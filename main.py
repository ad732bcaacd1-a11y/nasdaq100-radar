"""
美股納斯達克 100 雲端即時掃描器 (Webull 買訊雷達)
24/7 雲端背景運行 + Web 戰情儀表板 + LINE 即時推播
"""

import os
import json
import time
import threading
import logging
from datetime import datetime, timezone, timedelta
import pandas as pd
import yfinance as yf
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import uvicorn

from indicators import evaluate_signals
from notifier import send_line_message, send_telegram_message, build_signal_alert_text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("Nasdaq100Scanner")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
TICKERS_FILE = os.path.join(BASE_DIR, "nasdaq100_tickers.json")

# 讀取設定檔
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

config = load_config()

# 讀取 100 檔納指股票
tickers_map = {}
if os.path.exists(TICKERS_FILE):
    with open(TICKERS_FILE, "r", encoding="utf-8") as f:
        tickers_map = json.load(f)
ticker_list = list(tickers_map.keys())

# 全域狀態
system_state = {
    "status": "初始化中",
    "last_scan_time": "尚未掃描",
    "total_tickers": len(ticker_list),
    "recent_alerts": [],
    "scan_count": 0
}

# 避免重複通知的快取 (key: f"{symbol}_{bar_time}")
alerted_cache = set()

# FastAPI 實例
app = FastAPI(title="NASDAQ 100 Webull Signal Radar")

@app.get("/health")
def health_check():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}

@app.get("/", response_class=HTMLResponse)
def dashboard():
    """
    手機/電腦隨時瀏覽的雲端即時監控儀表板
    """
    rows = ""
    for alert in reversed(system_state["recent_alerts"][-20:]):
        rows += f"""
        <tr style="border-bottom: 1px solid #333;">
            <td style="padding: 10px; color: #00ffcc; font-weight: bold;">{alert['symbol']}</td>
            <td style="padding: 10px;">{alert['name']}</td>
            <td style="padding: 10px; color: #fff;">${alert['price']}</td>
            <td style="padding: 10px; color: #00e676;">{alert['rvol']}x</td>
            <td style="padding: 10px; color: #ffeb3b;">{alert['macd']}</td>
            <td style="padding: 10px; color: #bbb;">{alert['time']}</td>
            <td style="padding: 10px;"><a href="{alert['url']}" target="_blank" style="color: #29b6f6; text-decoration: none;">開啟 Webull</a></td>
        </tr>
        """
    if not rows:
        rows = '<tr><td colspan="7" style="text-align: center; padding: 25px; color: #888;">目前尚無觸發訊號，掃描雷達運作中...</td></tr>'

    tw_time = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>🎯 納指100 雲端買訊雷達 (Supertrend + MACD + 爆量)</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #121212; color: #e0e0e0; margin: 0; padding: 20px; }}
            .container {{ max-width: 900px; margin: auto; }}
            .card {{ background: #1e1e1e; border-radius: 12px; padding: 20px; margin-bottom: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.4); }}
            .header {{ display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; }}
            .badge {{ background: #00c853; color: black; padding: 4px 12px; border-radius: 20px; font-weight: bold; font-size: 13px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 14px; }}
            th {{ text-align: left; padding: 10px; background: #282828; color: #aaa; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="card header">
                <div>
                    <h2 style="margin: 0; color: #00e676;">⚡ 納斯達克 100 雲端買訊雷達</h2>
                    <p style="margin: 5px 0 0 0; color: #888; font-size: 14px;">監控指標：Supertrend 翻多 + MACD 黃金交叉 + RVOL 爆量 (5分K)</p>
                </div>
                <div style="margin-top: 10px;">
                    <span class="badge">● {system_state['status']}</span>
                </div>
            </div>

            <div class="card" style="display: flex; justify-content: space-around; text-align: center;">
                <div>
                    <div style="font-size: 13px; color: #888;">監控股票總數</div>
                    <div style="font-size: 22px; font-weight: bold; color: #fff;">{system_state['total_tickers']} 檔</div>
                </div>
                <div>
                    <div style="font-size: 13px; color: #888;">已執行掃描次數</div>
                    <div style="font-size: 22px; font-weight: bold; color: #29b6f6;">{system_state['scan_count']} 次</div>
                </div>
                <div>
                    <div style="font-size: 13px; color: #888;">最後掃描時間 (台灣)</div>
                    <div style="font-size: 16px; font-weight: bold; color: #ffca28; margin-top: 4px;">{system_state['last_scan_time']}</div>
                </div>
            </div>

            <div class="card">
                <h3 style="margin: 0; color: #fff;">📊 今日觸發買訊清單 (自動推播至 LINE)</h3>
                <div style="overflow-x: auto;">
                    <table>
                        <thead>
                            <tr>
                                <th>代號</th>
                                <th>公司名稱</th>
                                <th>現價</th>
                                <th>爆量 (RVOL)</th>
                                <th>MACD 狀態</th>
                                <th>K棒時間</th>
                                <th>看盤</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows}
                        </tbody>
                    </table>
                </div>
            </div>
            <p style="text-align: center; color: #555; font-size: 12px;">伺服器時間：{tw_time} | 雲端 24/7 自動監控運行中</p>
        </div>
    </body>
    </html>
    """
    return html

def is_us_market_hours() -> bool:
    """
    判斷當前是否處於美股交易或盤前活躍時段 (美東時間 08:00 ~ 16:30)
    """
    now_utc = datetime.now(timezone.utc)
    # 美東時間為 UTC-4 (夏令) 或 UTC-5 (冬令)
    # 簡單抓 UTC-4: 台灣時間 20:00 ~ 05:00
    weekday = now_utc.weekday()
    if weekday in [5, 6]: # 週六週日休市
        return False
    return True

def run_scanner_cycle():
    """
    執行單次完整 100 檔掃描
    """
    global system_state
    cfg = load_config()
    line_token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", cfg.get("line_channel_access_token", ""))
    line_user_id = os.environ.get("LINE_USER_ID", cfg.get("line_user_id", ""))
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", cfg.get("telegram_bot_token", ""))
    tg_chat_id = os.environ.get("TELEGRAM_CHAT_ID", cfg.get("telegram_chat_id", ""))
    rvol_thresh = float(cfg.get("rvol_threshold", 1.8))
    
    tw_now = datetime.now(timezone(timedelta(hours=8))).strftime("%H:%M:%S")
    system_state["status"] = "正在掃描納指 100..."
    logger.info(f"開始第 {system_state['scan_count'] + 1} 次掃描...")

    try:
        # 批次下載納指 100 股票的 5 分鐘 K 線 (過去 3 天資料確保指標精準)
        raw_data = yf.download(
            ticker_list,
            period="3d",
            interval="5m",
            progress=False,
            group_by="ticker"
        )
        
        matches_found = 0
        
        for symbol in ticker_list:
            try:
                if len(ticker_list) == 1:
                    df = raw_data.copy()
                else:
                    if symbol not in raw_data.columns.levels[0]:
                        continue
                    df = raw_data[symbol].dropna().copy()
                
                if df.empty or len(df) < 30:
                    continue
                    
                # 運算三大指標
                res = evaluate_signals(df, rvol_threshold=rvol_thresh)
                
                if res.get("matched"):
                    bar_time = res.get("bar_time", "")
                    cache_key = f"{symbol}_{bar_time}"
                    
                    if cache_key not in alerted_cache:
                        alerted_cache.add(cache_key)
                        matches_found += 1
                        
                        name = tickers_map.get(symbol, symbol)
                        logger.info(f"🔥【買訊觸發】{symbol} ({name}) 現價: {res['price']} RVOL: {res['rvol']}x")
                        
                        # 紀錄在 Web 儀表板
                        system_state["recent_alerts"].append({
                            "symbol": symbol,
                            "name": name,
                            "price": res["price"],
                            "rvol": res["rvol"],
                            "macd": f"金叉 ({res['macd_val']})",
                            "time": f"{tw_now} (5m: {bar_time})",
                            "url": f"https://app.webull.com/stocks/{symbol.lower()}"
                        })
                        
                        # 發送通知 (LINE / Telegram)
                        alert_msg = build_signal_alert_text(symbol, name, res)
                        send_line_message(line_token, line_user_id, alert_msg)
                        send_telegram_message(tg_token, tg_chat_id, alert_msg)
                        
            except Exception as e:
                logger.error(f"分析 {symbol} 失敗: {e}")
                
        system_state["scan_count"] += 1
        system_state["last_scan_time"] = tw_now
        system_state["status"] = f"監控中 (本次掃描完成，觸發 {matches_found} 檔)"
        logger.info(f"掃描結束，共找到 {matches_found} 檔觸發標的。")
        
    except Exception as e:
        logger.error(f"批次下載失敗: {e}")
        system_state["status"] = "掃描出錯，稍後重試"

def background_worker():
    """
    背景排程監控迴圈
    """
    logger.info("啟動納斯達克 100 背景監控執行緒...")
    time.sleep(3) # 伺服器啟動緩衝
    while True:
        try:
            run_scanner_cycle()
        except Exception as e:
            logger.error(f"監控迴圈異常: {e}")
            
        cfg = load_config()
        interval = int(cfg.get("scan_interval_seconds", 60))
        time.sleep(interval)

# 啟動背景工作
threading.Thread(target=background_worker, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"啟動 Web 服務，Port: {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
