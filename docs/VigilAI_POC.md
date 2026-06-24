# VigilAI — Webcam Prompt Detection POC

> **版本**：POC v0.1（討論用草案）
> **日期**：2026-06-24
> **作者**：John C. Chang
> **定位**：驗證「瀏覽器 webcam + 自訂 Prompt + VLM 偵測 + Telegram 通知」端到端可行性
> **與 PRD 關係**：本文是 [`VigilAI_PRD_v0.1.md`](./VigilAI_PRD_v0.1.md) 的**最小驗證子集**，刻意砍掉多攝影機、DB、多租戶、權限等，只留一條最短的價值鏈路。

---

## 1. POC 目標（一句話）

> 打開網頁 → 授權 webcam → 輸入一句自然語言 prompt（描述要偵測什麼，**可儲存、下次直接讀取沿用**）→ 系統持續看畫面 → 命中時透過 Telegram bot 把「畫面截圖 + 說明」推到手機。

**驗收標準（Definition of Done）**：以下四個情境各能成功推一則 Telegram 通知

| # | 情境 | Prompt 範例 | 觸發型態 |
|---|---|---|---|
| 1 | OCR 數值比較 | 讀出畫面中溫度計的數字 | 數值 `>= 38` |
| 2 | 手勢偵測 | 畫面中的人是否比出「讚」的手勢？ | 布林 |
| 3 | 火災偵測 | 畫面中是否有火焰或濃煙？ | 布林 |
| 4 | 打瞌睡偵測 | 畫面中的人是否閉眼/低頭打瞌睡？ | 布林 |

---

## 2. 明確的範圍切割（In / Out）

| 項目 | POC 納入 | POC 不做（留給 PRD/MVP） |
|---|---|---|
| 攝影機 | **瀏覽器單一 webcam**（getUserMedia） | RTSP / MJPEG / USB server-side、多攝影機 |
| 偵測來源 | 瀏覽器逐幀截圖上傳 | 後端主動抓流 |
| Rule 數量 | 1～N 條（同一支 webcam） | 多攝影機 × 多 rule |
| 模型 | 固定 `qwen2.5vl:7b`（單一外部端點） | 多模型、雲端 fallback、模型比較 |
| 通知 | **Telegram bot（sendPhoto）** | 通用 Webhook、Slack/LINE/Discord、HMAC 簽名 |
| 持久化 | **無 DB**，rule（prompt）存後端 `rules.json`（掛 volume，可儲存/讀取沿用） | PostgreSQL、事件中心、報表 |
| 權限 | 無登入（或單一存取密碼，見 §9） | JWT、RBAC、多租戶 |
| 部署 | **單一容器、單一對外 port 4014** | Nginx + Next + Celery + Redis + PG 全套 |

---

## 3. 架構（刻意最小化）

POC 用**單一 FastAPI 服務**同時做三件事，全部掛在 port 4014：
1. 提供靜態前端頁面（一頁 vanilla JS，負責 webcam + 截圖迴圈 + UI）
2. `/api/analyze`：收一張圖 + rule，呼叫 Ollama VLM，回傳結構化結果
3. 命中時呼叫 Telegram Bot API 發通知

```
┌──────────────────────── 使用者瀏覽器 (Chrome) ────────────────────────┐
│  index.html + app.js                                                  │
│   1. getUserMedia() 取得 webcam <video>                               │
│   2. 每 N 秒：<video> → <canvas> → toBlob(jpeg, 768px)               │
│   3. POST /api/analyze { image, rules[] }                            │
│   4. 顯示即時 log（每條 rule 的 VLM 回傳 + 是否觸發）                  │
└───────────────────────────────┬──────────────────────────────────────┘
                                 │ HTTP (同一 origin, port 4014)
┌───────────────────────────────▼──────────────────────────────────────┐
│                  FastAPI 單一容器 (對外 port 4014)                     │
│  GET  /                 → 回傳 index.html / 靜態檔                     │
│  POST /api/analyze      → 影像 → VLM → 解析 → 判斷觸發                 │
│                           → 觸發則 sendPhoto 到 Telegram             │
│  GET/POST/DELETE /api/rules → rule（prompt）的儲存 / 讀取 / 刪除      │
│  GET  /api/health       → 檢查 Ollama / Telegram 可達                 │
│  in-memory: 每條 rule 的 cooldown 狀態                                │
│  持久化:    rules.json（掛 volume，容器重啟/換瀏覽器都還在）          │
└──────────────┬──────────────────────────────────┬────────────────────┘
               │ POST /v1/chat/completions          │ POST /botXXX/sendPhoto
               │ Bearer Transfer168                 │
┌──────────────▼───────────────┐      ┌────────────▼────────────────────┐
│  Ollama 外部端點              │      │  Telegram Bot API                │
│  ollama.transferhelper.com   │      │  api.telegram.org                │
│  model: qwen2.5vl:7b         │      │  sendPhoto(chat_id, photo, cap)  │
└──────────────────────────────┘      └──────────────────────────────────┘
```

> **為什麼後端要當 proxy 而不是瀏覽器直接打 Ollama？**
> 因為 `Transfer168` API key 和 Telegram bot token **不能曝露在前端**。所有對外密鑰呼叫都必須走後端。

> **為什麼迴圈由瀏覽器驅動？**
> 影像來源是 `getUserMedia`，只存在於瀏覽器分頁。後端拿不到 webcam，所以「每 N 秒截一張」這件事只能瀏覽器做。

---

## 4. 核心流程（單次偵測 tick）

```
[瀏覽器] 每 N 秒一次：
  1. 從 <video> 畫到 <canvas>，縮到長邊 768px，輸出 JPEG (quality 0.7)
  2. 把目前啟用的 rules 一起 POST 到 /api/analyze

[後端] 收到 /api/analyze：
  3. 對每一條 rule：
     a. cooldown 檢查：此 rule 在冷卻中 → 跳過（仍回傳「冷卻中」給前端顯示）
     b. 組 VLM 請求（system prompt + rule prompt + 強制 JSON 輸出 + 影像 base64）
     c. 呼叫 qwen2.5vl:7b，解析回傳 JSON
     d. 依 rule 的條件型態判斷是否觸發：
          - boolean   → detected == true 且 confidence >= 門檻
          - numeric   → 取出數值，用 operator/value 比較（>=、<=、==、區間）
     e. 觸發 → Telegram sendPhoto（附截圖 + caption）+ 設定 cooldown
  4. 回傳每條 rule 的結果陣列給前端（VLM 原文、parsed、是否觸發、是否冷卻）

[瀏覽器] 收到結果 → 更新即時 log 與狀態燈
```

---

## 5. Rule 資料結構（POC 版）

一條 rule 就是一個偵測任務（含使用者輸入的自然語言 prompt）。POC 用前端表單建立，**存到後端 `rules.json`（掛 Docker volume）持久化**，下次開頁面自動從 `GET /api/rules` 讀回沿用，不會因為重整或換瀏覽器而消失。

**Rules 持久化 API：**

| Method | Endpoint | 說明 |
|---|---|---|
| GET | `/api/rules` | 讀取所有已儲存的 rule（開頁載入用） |
| POST | `/api/rules` | 新增 / 更新一條 rule（含 prompt、condition、cooldown 等） |
| DELETE | `/api/rules/{id}` | 刪除一條 rule |

> POC 偵測時，前端仍把「目前啟用的 rules」連同影像 POST 給 `/api/analyze`；`rules.json` 只負責「跨 session 記住使用者寫過的 prompt」，後端推理本身維持無狀態（cooldown 除外）。

```jsonc
{
  "id": "rule_1",
  "name": "高溫警報",
  "enabled": true,
  "prompt": "讀出畫面中溫度計顯示的數字",   // 使用者自然語言描述
  "condition": {
    "type": "numeric",                      // "numeric" | "boolean"
    "operator": ">=",                       // numeric 用：>=, <=, ==, >, <
    "value": 38
  },
  "confidence_threshold": 60,               // boolean 用：0-100
  "cooldown_sec": 60,                       // 觸發後冷卻，避免洪水通知
  "notify_text": "⚠️ 偵測到高溫"            // Telegram caption 前綴（可選）
}
```

**布林型 rule 範例：**
```jsonc
{
  "id": "rule_2",
  "name": "火災偵測",
  "enabled": true,
  "prompt": "畫面中是否有火焰或濃煙？",
  "condition": { "type": "boolean" },
  "confidence_threshold": 70,
  "cooldown_sec": 120,
  "notify_text": "🔥 疑似火災"
}
```

> **設計重點：數值比較交給程式，不是 VLM。**
> Prompt 只要求 VLM「讀出數字」，`>= 38` 的判斷由後端用 `condition` 做。
> 原因：VLM 對「大於等於」這類邏輯判斷不穩定，但「OCR 讀數字」相對可靠。把感知（VLM）和決策（程式）分開，誤判率較低也較好除錯。

---

## 6. VLM 呼叫規格（強制結構化輸出）

VLM 預設回自由文字，難以程式化判斷。POC 一律要求回**固定 JSON**。

**Boolean rule 的組裝（system + user + image）：**
```
System: 你是影像偵測助手。只輸出 JSON，不要多餘文字。
User:
  {rule.prompt}
  請依畫面回答，只輸出以下 JSON：
  {"detected": true|false, "confidence": 0-100, "reason": "簡短說明"}
[image: data:image/jpeg;base64,...]
```

**Numeric rule 的組裝：**
```
System: 你是影像偵測助手。只輸出 JSON，不要多餘文字。
User:
  {rule.prompt}
  只輸出以下 JSON（value 為純數字，讀不到填 null）：
  {"value": <number|null>, "confidence": 0-100, "reason": "簡短說明"}
[image: data:image/jpeg;base64,...]
```

**對應的 HTTP 請求（OpenAI 相容 / vision content）：**
```bash
curl -s https://ollama.transferhelper.com/v1/chat/completions \
  -H "Authorization: Bearer Transfer168" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5vl:7b",
    "temperature": 0,
    "messages": [
      {"role": "system", "content": "你是影像偵測助手。只輸出 JSON，不要多餘文字。"},
      {"role": "user", "content": [
        {"type": "text", "text": "畫面中是否有火焰或濃煙？只輸出 {\"detected\":true|false,\"confidence\":0-100,\"reason\":\"...\"}"},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
      ]}
    ]
  }'
```

**解析容錯**：VLM 可能在 JSON 前後夾雜文字 → 後端用 regex 抓第一個 `{...}` 區塊再 `json.loads`；解析失敗則該 tick 視為「未觸發」並記 log（POC 不重試，或最多 retry 1 次）。

> `temperature: 0`：偵測任務要求可重現、少幻覺，溫度設 0。

---

## 7. Telegram 整合

**Bot 已建立（2026-06-24）：**
- Bot：**`@VigilAi_beta_bot`**（連結 <https://t.me/VigilAi_beta_bot>）
- Bot Token：`8719405273:AAFMQclCVOZxv1dPScESfD3wssNpODCnyxM`
  ⚠️ 此 token 等同 bot 的完整控制權，正式環境請改用 `.env` / secret 帶入，勿寫死在程式或公開 repo。

**還需要 chat_id（你要做一次）：**
1. 用手機打開 <https://t.me/VigilAi_beta_bot> → 對 bot 傳任意一則訊息（例如 `/start`）
2. POC 提供 `GET /api/telegram/probe` 端點：後端呼叫 `getUpdates` 把最近對話的 `chat_id` 撈出來顯示，填進設定即可。

**觸發時送出（帶圖）：**
```bash
curl -s "https://api.telegram.org/bot<TOKEN>/sendPhoto" \
  -F "chat_id=<CHAT_ID>" \
  -F "photo=@frame.jpg" \
  -F "caption=🔥 疑似火災 (rule: 火災偵測, confidence 88)
時間: 2026-06-24 11:32:05
VLM: 畫面右側出現明亮火光與煙霧"
```

POC 把觸發當下那張 JPEG 直接當 photo 送出，caption 帶：rule 名稱、confidence/數值、時間、VLM reason。

---

## 8. Docker 與對外 port

POC 用**單一 image、單一 container**，對外只開 4014。

```yaml
# docker-compose.yml（POC）
services:
  vigilai-poc:
    build: .
    ports:
      - "4014:8000"          # 對外唯一 port
    environment:
      # 密鑰一律從 .env 帶入，compose 不寫死；缺值用 :? 讓 compose 直接報錯
      OLLAMA_BASE_URL: "${OLLAMA_BASE_URL:-https://ollama.transferhelper.com/v1}"
      OLLAMA_API_KEY:  "${OLLAMA_API_KEY:?OLLAMA_API_KEY is required}"
      OLLAMA_MODEL:    "${OLLAMA_MODEL:-qwen2.5vl:7b}"
      TELEGRAM_BOT_TOKEN: "${TELEGRAM_BOT_TOKEN:?TELEGRAM_BOT_TOKEN is required}"
      TELEGRAM_CHAT_ID:   "${TELEGRAM_CHAT_ID:-}"
      ACCESS_PASSWORD: "${ACCESS_PASSWORD:?ACCESS_PASSWORD must be set}"
    volumes:
      - ./data:/app/data        # rules.json 等持久化檔案
    restart: unless-stopped
```

對應 `.env`（**所有密鑰只放這裡**，已被 `.gitignore` 排除，勿提交）：

```dotenv
OLLAMA_API_KEY=Transfer168
TELEGRAM_BOT_TOKEN=8719405273:AAFMQclCVOZxv1dPScESfD3wssNpODCnyxM
TELEGRAM_CHAT_ID=          # 用 /api/telegram/probe 撈到後填入
ACCESS_PASSWORD=Transfer123
```

> **安全處理（依自動審查調整）**：compose 與程式碼**不再寫死任何密鑰**，全部走 `.env`；
> `ACCESS_PASSWORD` 未設定時服務 **fail closed**（受保護端點回 503，不會放行）；
> 密碼比對用 `hmac.compare_digest`（防 timing attack）。

- 後端 FastAPI 監聽容器內 8000，對外映射 4014。
- 前端靜態檔由 FastAPI `StaticFiles` 直接 serve，**不需要 Nginx / Next.js**。
- rule（prompt）持久化在 `./data/rules.json`，掛 volume 後容器重啟仍保留。
- `docker compose up -d` 後開 `http://localhost:4014`。

---

## 9. 關鍵技術風險與限制（務必先讀）

| # | 風險/限制 | 說明 | POC 對策 |
|---|---|---|---|
| **R1** | **getUserMedia 只在 secure context 可用** | 瀏覽器只允許 `https://` 或 `http://localhost` 存取 webcam。若用 `http://<區網IP>:4014` 從別台電腦開，**webcam 會直接拿不到** | (a) 只在跑服務的本機用 `localhost`；或 (b) 加自簽憑證走 https；或 (c) 用 Cloudflare Tunnel/ngrok 給 https 網址。**這點要先決定**（見討論 Q2） |
| R2 | VLM 延遲 | qwen2.5vl:7b 單張約 1–3 秒，無法做高 fps | 截圖間隔預設 **3 秒**，可調；UI 顯示「分析中」避免重疊送出 |
| R3 | 外部端點速率/併發限制 | 共用端點，限制未知；多 rule × 高頻會塞爆 | 同一 tick 內 rule **序列**呼叫；間隔拉長；POC 建議 rule 數 ≤ 3 |
| R4 | 通知洪水 | 火災一旦出現會連續幀都命中 | per-rule **cooldown**（預設 60–120 秒）|
| R5 | 誤報 / 漏報 | 7B 模型對細微手勢、打瞌睡判斷不一定準 | confidence 門檻 + 事後人工看 log 調 prompt；POC 接受一定誤報 |
| R6 | 隱私 | 影像會送到外部 transferhelper 端點 | POC 階段告知即可；正式版才談本地部署 |
| R7 | 金鑰/濫用 | 任何能連到 4014 的人都能用你的 VLM key 和 bot | 加一個簡單 `ACCESS_PASSWORD`（前端輸入、後端比對）擋路人（見討論 Q4）|
| R8 | Token 成本/解析度 | 圖越大 token 越多、越慢 | 上傳前縮到長邊 768px、JPEG q0.7 |

---

## 10. 你需要提供 / 待確認的東西（缺什麼）

**必須提供（否則無法 demo）：**
- [x] **Telegram Bot Token** — 已建立 `@VigilAi_beta_bot`，token `8719405273:AAFMQclCVOZxv1dPScESfD3wssNpODCnyxM`
- [ ] **Telegram Chat ID** — 你對 `@VigilAi_beta_bot` 傳一則訊息後，用 `/api/telegram/probe` 撈出
- [ ] 確認外部 Ollama 端點現在仍可用、`qwen2.5vl:7b` 仍在清單（PRD 註記是 2026-06-10 實測；動工前我會先打一次 `/v1/models` 驗證）

### 已確認決策（2026-06-24）

| # | 決策 | 結論 | 影響 |
|---|---|---|---|
| Q1 | 偵測間隔 / cooldown | 截圖間隔預設 **3 秒**；cooldown 預設 60–120 秒（per-rule 可調） | 偵測引擎參數 |
| Q2 | 存取方式 | ✅ **只在本機 localhost 用** | **不需要 TLS / tunnel**；webcam 直接可用，部署最簡單。⚠️ 換成別台機器開頁面就會失效，屆時才需補 https |
| Q3 | 多 rule 呼叫策略 | ✅ **一條 rule 一次 VLM 呼叫**（序列） | 結果乾淨好除錯；建議 rule 數 ≤ 3 控制延遲 |
| Q4 | 存取密碼 | ✅ **加一道簡單密碼**：`ACCESS_PASSWORD = Transfer123`（前端輸入→後端比對） | 擋路人誤用 VLM key / bot |
| Q5 | 前端 UI | ✅ **完整單頁**：即時畫面 + 每 rule 狀態燈 + 即時 VLM log + rule 新增/啟停（單頁 vanilla JS） | demo 效果完整 |

---

## 11. 里程碑（POC，建議 1 條人力）

| 步驟 | 內容 | 估時 |
|---|---|---|
| P0 | FastAPI 骨架 + Dockerfile + compose（port 4014）+ `/api/health` | 2h |
| P1 | 前端一頁：getUserMedia + canvas 截圖迴圈 + rule 表單(localStorage) | 3h |
| P2 | `/api/analyze`：VLM 呼叫 + JSON 解析 + boolean/numeric 判斷 | 3h |
| P3 | Telegram sendPhoto + cooldown | 2h |
| P4 | 四情境實測調 prompt（溫度/手勢/火災/瞌睡）+ 寫驗收記錄 | 3h |
| | **合計** | **~13h** |

---

*VigilAI POC v0.1 | 2026-06-24 | For Internal Discussion*
