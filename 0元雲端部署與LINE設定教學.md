# 🎯 美股納指 100 雲端買訊雷達 (0元免花錢雲端部署指南)

本系統專為 **Webull（微牛）美股交易者** 設計，符合你的核心要求：
1. **三大指標共振**：Supertrend 翻多買訊 + MACD 5m 黃金交叉 + RVOL 爆量（>1.8x）
2. **全自動監控**：納斯達克 100 檔成分股（NVDA, AAPL, MSFT, TSLA, AMZN...）
3. **附帶 Webull 快速看盤**：推播訊息直接附上該股票在 Webull 的直達連結
4. **完全 0 元免花錢**：使用 Render / Hugging Face 永久免費雲端額度
5. **電腦完全關機**：24 小時在雲端運作，手機 LINE 即時收通知！

---

## 📌 第一步：取得免費 LINE 推播金鑰（只需 2 分鐘）

因為 LINE Notify 官方已退場，目前皆使用官方推薦的 **LINE Messaging API (LINE Bot)**，完全免費且訊息更即時、排版更漂亮：

1. 前往 **[LINE Developers Console](https://developers.line.biz/console/)**
2. 點擊右上角 **Log in**，使用你個人的 **LINE 帳號** 登入
3. 點選 **Create a new provider**（建立提供者），輸入名稱（例如：`MyStockAlert`）
4. 點選 **Create a Messaging API channel**：
   - Channel type: `Messaging API`
   - Channel name: `Webull納指雷達`（機器人顯示名稱）
   - Channel description: `美股買訊通知`
   - Category / Subcategory: 隨意選擇（例如：Tools / Utility）
   - 勾選同意服務條款，按 **Create** 建立
5. **取得 2 個關鍵參數**：
   - **User ID**（你的個人接收帳號）：
     - 點進剛建好的 Channel ➔ 切換到 **Basic settings** 分頁
     - 往下拉到底，會看到 **Your user ID**（以 `U...` 開頭的一長串代碼），複製它！
   - **Channel Access Token**（推播授權金鑰）：
     - 切換到 **Messaging API** 分頁
     - 往下拉到底，找到 **Channel access token**，點擊 **Issue**（發行），複製整串金鑰！
6. **加入機器人為好友**：
   - 在 **Messaging API** 分頁最上方有 **QR code**，用你的手機 LINE 掃描並加入好友！

> 💡 拿到這兩串代碼後，你就可以填入 `config.json`，或在雲端平台設定為環境變數！

---

## 📌 第二步：一鍵部署到免費雲端（電腦關機照跑）

推薦使用 **[Render.com](https://render.com/)**（全球最大免費開發者雲端平台之一，免綁信用卡即可使用）：

### 步驟：
1. 註冊並登入 **[Render.com](https://render.com/)**（可以用 GitHub 帳號 1 秒登入）。
2. 將本專案資料夾推送到你的 GitHub（私有倉庫即可）：
   - 如果你有安裝 GitHub Desktop，直接把 `美股納指100雲端掃描器` 資料夾拖進去發布成 Private 倉庫。
3. 在 Render 儀表板點選 **New +** ➔ 選擇 **Web Service**。
4. 連接你的 GitHub 倉庫，選擇剛才的倉庫。
5. 設定基本資訊：
   - **Name**: `nasdaq100-radar`
   - **Region**: 選擇 `Singapore` 或 `Oregon`
   - **Environment**: 選擇 `Docker`
   - **Instance Type**: 選擇 **Free ($0/month)**
6. 在下方 **Environment Variables（環境變數）** 新增兩筆：
   - `LINE_CHANNEL_ACCESS_TOKEN` = 你的 LINE Access Token
   - `LINE_USER_ID` = 你的 LINE User ID
7. 點擊最下方 **Create Web Service**！

🎉 **大功告成！**
- Render 會自動建置並啟動服務。
- 它會產生一個網址（例如 `https://nasdaq100-radar.onrender.com`），用手機打開就能看到 **即時戰情儀表板**。
- 美股開盤時，雲端機器人會在背景自動每分鐘掃描 100 檔股票，一旦符合 Supertrend + MACD 金叉 + 爆量，手機 LINE 秒響警報！
- **現在你可以放心地將 Mac 電腦關機或休眠！**
