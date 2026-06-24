# VigilAI POC — Webcam Prompt Detection

打開網頁 → 授權 webcam → 用自然語言寫 prompt 描述要偵測什麼 → 系統持續看畫面 →
命中時透過 Telegram bot 把「截圖 + 說明」推到手機。

完整設計見 [`docs/VigilAI_POC.md`](docs/VigilAI_POC.md)。

## 架構

單一 FastAPI 容器，對外 port **4014**：

- `GET /` — 前端單頁（webcam 截圖迴圈、規則管理、即時 log）
- `POST /api/analyze` — 影像 → `qwen2.5vl:7b` → JSON 解析 → 觸發判斷 → Telegram
- `GET/POST/DELETE /api/rules` — 規則（prompt）持久化（`data/rules.json`）
- `GET /api/telegram/probe` — 撈 chat_id
- `GET /api/health` — 健康檢查

偵測由瀏覽器驅動（`getUserMedia` 只在 **localhost 或 https** 可用）；
API key 與 bot token 只存在後端。

## 快速開始（Docker）

```bash
cp .env.example .env        # 已內含 bot token；填 ACCESS_PASSWORD（預設 Transfer123）
docker compose up -d --build
# 開瀏覽器（務必本機）：
open http://localhost:4014
```

1. 輸入存取密碼（預設 `Transfer123`）
2. 按「開啟攝影機」授權 webcam
3. Telegram：用手機對 [@VigilAi_beta_bot](https://t.me/VigilAi_beta_bot) 傳一則 `/start`，
   回網頁按「撈 chat_id」→「測試通知」確認能收到
4. 「+ 新增」規則，例如：
   - 火災（布林）：prompt「畫面中是否有火焰或濃煙？」
   - 高溫（數值）：prompt「讀出畫面中溫度計的數字」，條件 `>= 38`
5. 按「開始偵測」，畫面命中時手機會收到 Telegram 通知

## 本機開發（不經 Docker）

```bash
pip install -r requirements.txt
export ACCESS_PASSWORD=Transfer123 DATA_DIR=./data
export TELEGRAM_BOT_TOKEN=8719405273:AAFMQclCVOZxv1dPScESfD3wssNpODCnyxM
uvicorn app.main:app --reload --port 4014
```

## 注意

- **webcam 只能在 `localhost` 或 `https` 開**。用區網 IP（`http://192.168.x.x:4014`）會打不開相機。
- bot token 等同 bot 控制權，勿提交到公開 repo（`.env` 已被 `.gitignore` 排除）。
- 影像會送到外部 Ollama 端點（transferhelper），POC 階段請知悉。
