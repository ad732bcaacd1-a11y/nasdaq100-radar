"""
美股納斯達克 100 雲端即時掃描器 (Webull 買訊雷達) - 高頻極速實時版
15秒即時輪詢 + 網頁動態無感秒級刷新 + 觸發聲音提示 + 手動即刻掃描
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
            return json.load(f)
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
    "last_scan_duration": 0
}

alerted_cache = set()
scan_trigger_event = threading.Event()

app = FastAPI(title="NASDAQ 100 Webull Signal Radar")

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
        "last_scan_duration": system_state["last_scan_duration"]
    }

@app.post("/api/scan_now")
def trigger_immediate_scan():
    """手動觸發立即秒級掃描"""
    scan_trigger_event.set()
    return {"message": "即刻掃描已觸發"}

@app.get("/", response_class=HTMLResponse)
def dashboard():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>🎯 納指100 實時極速買訊雷達</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f1117; color: #e0e0e0; margin: 0; padding: 20px; }
            .container { max-width: 950px; margin: auto; }
            .card { background: #1a1d26; border: 1px solid #282d3d; border-radius: 14px; padding: 20px; margin-bottom: 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.5); }
            .header { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 15px; }
            .badge { display: inline-flex; align-items: center; gap: 6px; background: #00e676; color: #000; padding: 6px 14px; border-radius: 20px; font-weight: bold; font-size: 13px; }
            .pulse { width: 10px; height: 10px; background-color: #000; border-radius: 50%; animation: pulse-anim 1.5s infinite; }
            @keyframes pulse-anim { 0% { transform: scale(0.95); opacity: 1; } 50% { transform: scale(1.3); opacity: 0.5; } 100% { transform: scale(0.95); opacity: 1; } }
            .btn-scan { background: linear-gradient(135deg, #00c853, #00b0ff); color: #fff; border: none; padding: 10px 20px; border-radius: 8px; font-weight: bold; cursor: pointer; transition: 0.2s; font-size: 14px; }
            .btn-scan:hover { opacity: 0.9; transform: translateY(-1px); }
            table { width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 14px; }
            th { text-align: left; padding: 12px; background: #222634; color: #8e99b0; border-radius: 4px; }
            td { padding: 12px; border-bottom: 1px solid #262b3b; }
            .webull-link { background: #1e3a5f; color: #38bdf8; padding: 4px 10px; border-radius: 6px; text-decoration: none; font-size: 12px; font-weight: bold; }
            .webull-link:hover { background: #2563eb; color: #fff; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="card header">
                <div>
                    <h2 style="margin: 0; color: #00e676;">⚡ 納斯達克 100 實時高頻買訊雷達</h2>
                    <p style="margin: 6px 0 0 0; color: #8e99b0; font-size: 13px;">即時監控：Supertrend 翻多買訊 + 5分K MACD 黃金交叉 + RVOL 爆量 (>1.8x)</p>
                </div>
                <div style="display: flex; gap: 10px; align-items: center;">
                    <button class="btn-scan" onclick="triggerScanNow()">⚡ 立即掃描一輪</button>
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
                    <div style="font-size: 12px; color: #8e99b0;">最近耗時</div>
                    <div style="font-size: 24px; font-weight: bold; color: #a78bfa;" id="stat-duration">0.0s</div>
                </div>
                <div>
                    <div style="font-size: 12px; color: #8e99b0;">上次更新時間</div>
                    <div style="font-size: 17px; font-weight: bold; color: #facc15; margin-top: 5px;" id="stat-time">--:--:--</div>
                </div>
            </div>

            <div class="card">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h3 style="margin: 0; color: #fff;">📊 今日觸發買訊 (自動推播至 LINE)</h3>
                    <span style="font-size: 12px; color: #8e99b0;">🔄 頁面每 2 秒實時無感動態刷新</span>
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
                            <tr><td colspan="7" style="text-align: center; padding: 25px; color: #666;">雷達正在連線即時抓取中...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
            <p style="text-align: center; color: #475569; font-size: 12px;">Webull 納指100 實時雷達 | 15 秒極速輪詢架構</p>
        </div>

        <script>
            let prevCount = 0;
            const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            function playBeep() {
                try {
                    const osc = audioCtx.createOscillator();
                    const gain = audioCtx.createGain();
                    osc.type = 'sine';
                    osc.frequency.setValueAtTime(587.33, audioCtx.currentTime); // D5
                    osc.frequency.setValueAtTime(880, audioCtx.currentTime + 0.1); // A5
                    gain.gain.setValueAtTime(0.3, audioCtx.currentTime);
                    gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + 0.35);
                    osc.connect(gain);
                    gain.connect(audioCtx.destination);
                    osc.start();
                    osc.stop(audioCtx.currentTime + 0.35);
                } catch(e) {}
            }

            async function refreshStatus() {
                try {
                    const res = await fetch('/api/status');
                    const data = await res.json();

                    document.getElementById('status-text').innerText = data.is_scanning ? '正在即時掃描 100 檔...' : data.status;
                    document.getElementById('status-badge').style.background = data.is_scanning ? '#ffca28' : '#00e676';
                    document.getElementById('stat-total').innerText = data.total_tickers + ' 檔';
                    document.getElementById('stat-count').innerText = data.scan_count + ' 次';
                    document.getElementById('stat-duration').innerText = (data.last_scan_duration || 0) + ' 秒';
                    document.getElementById('stat-time').innerText = data.last_scan_time || '--';

                    const alerts = data.recent_alerts || [];
                    if (alerts.length > prevCount && prevCount !== 0) {
                        playBeep(); // 叮咚聲音提示！
                    }
                    prevCount = alerts.length;

                    if (alerts.length === 0) {
                        document.getElementById('alerts-tbody').innerHTML = '<tr><td colspan="7" style="text-align: center; padding: 25px; color: #666;">目前尚未出現三大共振訊號，雷達每 15 秒實時監控中...</td></tr>';
                    } else {
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
    line_token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", cfg.get("line_channel_access_token", ""))
    line_user_id = os.environ.get("LINE_USER_ID", cfg.get("line_user_id", ""))
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN", cfg.get("telegram_bot_token", ""))
    tg_chat_id = os.environ.get("TELEGRAM_CHAT_ID", cfg.get("telegram_chat_id", ""))
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
                        send_telegram_message(tg_token, tg_chat_id, alert_msg)
                        
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
        
        # 等待 15 秒或直到手動觸發事件
        scan_trigger_event.wait(timeout=interval)
        scan_trigger_event.clear()

threading.Thread(target=background_worker, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"啟動高頻實時 Web 服務，Port: {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
