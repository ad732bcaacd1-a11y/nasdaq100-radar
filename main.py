"""
美股納斯達克 100 雲端即時掃描器 (Webull 買訊雷達 + Gemini 3 旗艦 AI 財經情報官)
- 15秒即時高頻掃描 QQQ 100 檔股票 (Supertrend + MACD + RVOL 爆量)
- 每 10 分鐘自動抓取最新新聞，由 Google Gemini 3 深度提煉操盤戰報推播至 LINE
- Web 儀表板新增「實時 AI 財經情報專區」，支援手動即刻生成戰報
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
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

from indicators import evaluate_signals
from notifier import send_line_message, send_telegram_message, build_signal_alert_text
from ai_reporter import fetch_latest_market_news, generate_ai_market_summary, news_reports_history

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("Nasdaq100Scanner")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
TICKERS_FILE = os.path.join(BASE_DIR, "nasdaq100_tickers.json")

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            key = cfg.get("gemini_api_key", "")
            if key.startswith("QVEu"):
                import base64
                cfg["gemini_api_key"] = base64.b64decode(key.encode()).decode()
            return cfg
    return {}

config = load_config()

tickers_map = {}
if os.path.exists(TICKERS_FILE):
    with open(TICKERS_FILE, "r", encoding="utf-8") as f:
        tickers_map = json.load(f)
ticker_list = list(tickers_map.keys())

system_state = {
    "status": "準備就緒",
    "last_scan_time": "尚未掃描",
    "total_tickers": len(ticker_list),
    "recent_alerts": [],
    "scan_count": 0,
    "is_scanning": False,
    "last_scan_duration": 0,
    "last_news_time": "尚未分析",
    "latest_ai_report": None
}

alerted_cache = set()
scan_trigger_event = threading.Event()
news_trigger_event = threading.Event()

app = FastAPI(title="NASDAQ 100 Webull Radar & Gemini AI")

@app.get("/health")
def health_check():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}

@app.get("/api/status")
def get_status():
    return {
        "status": system_state["status"],
        "last_scan_time": system_state["last_scan_time"],
        "total_tickers": system_state["total_tickers"],
        "recent_alerts": system_state["recent_alerts"],
        "scan_count": system_state["scan_count"],
        "is_scanning": system_state["is_scanning"],
        "last_scan_duration": system_state["last_scan_duration"],
        "last_news_time": system_state["last_news_time"],
        "latest_ai_report": system_state["latest_ai_report"]
    }

@app.get("/api/news")
def get_news_history():
    return {"reports": list(reversed(news_reports_history[-10:]))}

@app.post("/api/scan_now")
def trigger_immediate_scan():
    scan_trigger_event.set()
    return {"message": "即刻掃描已觸發"}

@app.post("/api/news_now")
def trigger_immediate_news():
    """手動觸發立即生成 AI 新聞情報"""
    news_trigger_event.set()
    return {"message": "AI 戰報生成已觸發"}

@app.get("/", response_class=HTMLResponse)
def dashboard():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>🎯 納指100 實時雷達 & Gemini 3 財經情報官</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f1117; color: #e0e0e0; margin: 0; padding: 20px; }
            .container { max-width: 950px; margin: auto; }
            .card { background: #1a1d26; border: 1px solid #282d3d; border-radius: 14px; padding: 20px; margin-bottom: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.5); }
            .header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 15px; }
            .badge { display: inline-flex; align-items: center; gap: 6px; background: #00e676; color: #000; padding: 6px 14px; border-radius: 20px; font-weight: bold; font-size: 13px; }
            .pulse { width: 10px; height: 10px; background-color: #000; border-radius: 50%; animation: pulse-anim 1.5s infinite; }
            @keyframes pulse-anim { 0% { transform: scale(0.95); opacity: 1; } 50% { transform: scale(1.3); opacity: 0.5; } 100% { transform: scale(0.95); opacity: 1; } }
            .btn { color: #fff; border: none; padding: 9px 18px; border-radius: 8px; font-weight: bold; cursor: pointer; font-size: 13px; transition: 0.2s; }
            .btn-scan { background: linear-gradient(135deg, #00c853, #00b0ff); }
            .btn-ai { background: linear-gradient(135deg, #8b5cf6, #ec4899); }
            .btn:hover { opacity: 0.9; transform: translateY(-1px); }
            table { width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 14px; }
            th { text-align: left; padding: 12px; background: #222634; color: #8e99b0; border-radius: 4px; }
            td { padding: 12px; border-bottom: 1px solid #262b3b; }
            .webull-link { background: #1e3a5f; color: #38bdf8; padding: 4px 10px; border-radius: 6px; text-decoration: none; font-size: 12px; font-weight: bold; }
            .news-box { background: #131620; border-left: 4px solid #a855f7; border-radius: 8px; padding: 18px; margin-top: 15px; line-height: 1.6; white-space: pre-wrap; font-size: 14px; color: #f1f5f9; }
            .sentiment-badge { display: inline-block; padding: 4px 12px; border-radius: 6px; font-size: 12px; font-weight: bold; margin-left: 10px; background: #3b82f6; color: #fff; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="card header">
                <div>
                    <h2 style="margin: 0; color: #00e676;">⚡ 納指 100 實時雷達 & Gemini 3 操盤情報</h2>
                    <p style="margin: 6px 0 0 0; color: #8e99b0; font-size: 13px;">15秒極速量化掃描 | 🤖 每 10 分鐘 Gemini 3 深度提煉新聞推播 LINE</p>
                </div>
                <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
                    <button class="btn btn-ai" onclick="triggerNewsNow()">🤖 立即生成 AI 戰報</button>
                    <button class="btn btn-scan" onclick="triggerScanNow()">⚡ 立即掃描一輪</button>
                    <span class="badge" id="status-badge"><span class="pulse"></span><span id="status-text">實時連線中</span></span>
                </div>
            </div>

            <div class="card" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); text-align: center; gap: 15px;">
                <div>
                    <div style="font-size: 12px; color: #8e99b0;">監控股票總數</div>
                    <div style="font-size: 24px; font-weight: bold; color: #fff;" id="stat-total">--</div>
                </div>
                <div>
                    <div style="font-size: 12px; color: #8e99b0;">已掃描輪數</div>
                    <div style="font-size: 24px; font-weight: bold; color: #38bdf8;" id="stat-count">0 次</div>
                </div>
                <div>
                    <div style="font-size: 12px; color: #8e99b0;">上次更新時間</div>
                    <div style="font-size: 17px; font-weight: bold; color: #facc15; margin-top: 5px;" id="stat-time">--:--:--</div>
                </div>
                <div>
                    <div style="font-size: 12px; color: #8e99b0;">AI 戰報更新頻率</div>
                    <div style="font-size: 17px; font-weight: bold; color: #ec4899; margin-top: 5px;">每 10 分鐘一篇</div>
                </div>
            </div>

            <!-- 專屬 AI 新聞情報專區 -->
            <div class="card">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px;">
                    <div>
                        <h3 style="margin: 0; display: inline-flex; align-items: center; color: #c084fc;">
                            📰 Gemini 3 實時 AI 操盤情報專區
                        </h3>
                        <span class="sentiment-badge" id="news-sentiment">載入中...</span>
                    </div>
                    <span style="font-size: 12px; color: #8e99b0;" id="news-time">更新時間: --:--</span>
                </div>
                <div class="news-box" id="news-content">
正在連線 Google Gemini 3 旗艦模型提煉最新 QQQ 與納斯達克市場新聞...
                </div>
            </div>

            <!-- 買訊清單 -->
            <div class="card">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h3 style="margin: 0; color: #fff;">📊 今日觸發買訊 (自動推播至 LINE)</h3>
                    <span style="font-size: 12px; color: #8e99b0;">🔄 頁面每 2 秒實時動態刷新</span>
                </div>
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
                                <th>操作</th>
                            </tr>
                        </thead>
                        <tbody id="alerts-tbody">
                            <tr><td colspan="7" style="text-align: center; padding: 25px; color: #666;">雷達正在即時監控中...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>

        <script>
            async function refreshStatus() {
                try {
                    const res = await fetch('/api/status');
                    const data = await res.json();

                    document.getElementById('status-text').innerText = data.is_scanning ? '正在即時掃描 100 檔...' : data.status;
                    document.getElementById('status-badge').style.background = data.is_scanning ? '#ffca28' : '#00e676';
                    document.getElementById('stat-total').innerText = data.total_tickers + ' 檔';
                    document.getElementById('stat-count').innerText = data.scan_count + ' 次';
                    document.getElementById('stat-time').innerText = data.last_scan_time || '--';

                    // 更新 AI 最新新聞戰報
                    if (data.latest_ai_report) {
                        document.getElementById('news-time').innerText = '最新發布: ' + data.latest_ai_report.time;
                        document.getElementById('news-sentiment').innerText = data.latest_ai_report.sentiment || '實時動態';
                        document.getElementById('news-content').innerText = data.latest_ai_report.content;
                    }

                    const alerts = data.recent_alerts || [];
                    if (alerts.length > 0) {
                        let html = '';
                        alerts.slice().reverse().forEach(a => {
                            html += `
                                <tr>
                                    <td style="color: #00ffcc; font-weight: bold; font-size: 15px;">${a.symbol}</td>
                                    <td>${a.name}</td>
                                    <td style="color: #fff; font-weight: bold;">$${a.price}</td>
                                    <td style="color: #00e676; font-weight: bold;">${a.rvol}x</td>
                                    <td style="color: #facc15;">${a.macd}</td>
                                    <td style="color: #94a3b8;">${a.time}</td>
                                    <td><a class="webull-link" href="${a.url}" target="_blank">Webull 看盤</a></td>
                                </tr>
                            `;
                        });
                        document.getElementById('alerts-tbody').innerHTML = html;
                    }
                } catch(e) {}
            }

            async function triggerScanNow() {
                document.getElementById('status-text').innerText = '正在發起即刻掃描...';
                await fetch('/api/scan_now', { method: 'POST' });
                refreshStatus();
            }

            async function triggerNewsNow() {
                document.getElementById('news-sentiment').innerText = '正在召喚 Gemini 3 提煉情報...';
                await fetch('/api/news_now', { method: 'POST' });
                setTimeout(refreshStatus, 2000);
            }

            setInterval(refreshStatus, 2000);
            refreshStatus();
        </script>
    </body>
    </html>
    """
    return html

def run_scanner_cycle():
    global system_state
    system_state["is_scanning"] = True
    start_t = time.time()
    
    cfg = load_config()
    line_token = cfg.get("line_channel_access_token", "")
    line_user_id = cfg.get("line_user_id", "")
    rvol_thresh = float(cfg.get("rvol_threshold", 1.8))
    tw_now = datetime.now(timezone(timedelta(hours=8))).strftime("%H:%M:%S")

    try:
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
                    
                res = evaluate_signals(df, rvol_threshold=rvol_thresh)
                
                if res.get("matched"):
                    bar_time = res.get("bar_time", "")
                    cache_key = f"{symbol}_{bar_time}"
                    
                    if cache_key not in alerted_cache:
                        alerted_cache.add(cache_key)
                        matches_found += 1
                        
                        name = tickers_map.get(symbol, symbol)
                        logger.info(f"🔥【實時買訊】{symbol} ({name}) 現價: {res['price']} RVOL: {res['rvol']}x")
                        
                        system_state["recent_alerts"].append({
                            "symbol": symbol,
                            "name": name,
                            "price": res["price"],
                            "rvol": res["rvol"],
                            "macd": f"金叉 ({res['macd_val']})",
                            "time": f"{tw_now} [{bar_time}]",
                            "url": f"https://app.webull.com/stocks/{symbol.lower()}"
                        })
                        
                        alert_msg = build_signal_alert_text(symbol, name, res)
                        send_line_message(line_token, line_user_id, alert_msg)
                        
            except Exception as e:
                pass
                
        duration = round(time.time() - start_t, 1)
        system_state["scan_count"] += 1
        system_state["last_scan_time"] = tw_now
        system_state["last_scan_duration"] = duration
        system_state["status"] = f"實時監控中 (觸發 {matches_found} 檔)"
        logger.info(f"第 {system_state['scan_count']} 輪掃描完成 (耗時 {duration}s，觸發 {matches_found} 檔)")
        
    except Exception as e:
        logger.error(f"掃描失敗: {e}")
        system_state["status"] = "連線重試中"
    finally:
        system_state["is_scanning"] = False

def do_generate_and_push_news():
    """執行一次 AI 新聞生成並推播至 LINE"""
    global system_state
    try:
        cfg = load_config()
        gemini_key = cfg.get("gemini_api_key", "")
        line_token = cfg.get("line_channel_access_token", "")
        news_items = fetch_latest_market_news()
        report = generate_ai_market_summary(gemini_key, news_items, model_name="gemini-3-flash-preview")
        
        system_state["latest_ai_report"] = report
        system_state["last_news_time"] = report["time"]
        
        full_msg = (
            f"📰【QQQ 納斯達克 10分鐘 AI 戰報】({report['time']})\n"
            f"情緒方向：{report['sentiment']}\n"
            f"─────────────────\n"
            f"{report['content']}\n"
            f"─────────────────\n"
            f"🤖 Google Gemini 3 旗艦模型為您即時研判"
        )
        send_line_message(line_token, "", full_msg)
        logger.info(f"[{report['time']}] 成功生成並推播 10 分鐘 Gemini AI 新聞戰報至 LINE！")
    except Exception as e:
        logger.error(f"AI 新聞推播失敗: {e}")

def ten_min_news_worker():
    """每 10 分鐘自動抓取最新 QQQ 新聞，讓 Gemini 3 提煉並推播 LINE"""
    logger.info("🤖 Gemini 3 AI 每 10 分鐘高頻財經情報員已就位...")
    time.sleep(5) # 啟動緩衝
    do_generate_and_push_news() # 開機立即發送一則

    while True:
        cfg = load_config()
        interval = int(cfg.get("ai_news_interval_seconds", 600))
        news_trigger_event.wait(timeout=interval)
        news_trigger_event.clear()
        do_generate_and_push_news()

def background_worker():
    logger.info("⚡ 高頻實時掃描執行緒已就位 (間隔 15 秒)...")
    time.sleep(1)
    while True:
        try:
            run_scanner_cycle()
        except Exception as e:
            logger.error(f"迴圈異常: {e}")
            
        cfg = load_config()
        interval = int(cfg.get("scan_interval_seconds", 15))
        scan_trigger_event.wait(timeout=interval)
        scan_trigger_event.clear()

threading.Thread(target=background_worker, daemon=True).start()
threading.Thread(target=ten_min_news_worker, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    logger.info(f"啟動高頻實時 Web 服務，Port: {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
