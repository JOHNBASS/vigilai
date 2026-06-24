# VigilAI
## Webcam Vision Intelligence Platform
### 產品需求文件（PRD）v0.1

> **版本**：0.1 Draft  
> **狀態**：內部討論用  
> **日期**：2026-06-10  
> **作者**：John C. Chang  
> ⚠️ 本文件為內部機密，請勿對外傳閱

---

## 目錄

1. [專案概述與命名](#1-專案概述與命名)
2. [問題陳述](#2-問題陳述)
3. [目標用戶](#3-目標用戶)
4. [功能需求](#4-功能需求)
   - 4.1 攝影機管理
   - 4.2 VLM 模型設定
   - 4.3 Prompt Rule 管理
   - 4.4 偵測引擎
   - 4.5 Webhook 系統
   - 4.6 儀表板與事件中心
   - 4.7 用戶與權限管理
5. [資料模型設計](#5-資料模型設計)
6. [API 規格草案](#6-api-規格草案)
7. [Webhook Payload 規格](#7-webhook-payload-規格)
8. [系統架構](#8-系統架構)
9. [非功能需求（NFR）](#9-非功能需求nfr)
10. [技術選型建議](#10-技術選型建議)
11. [開放討論點（Open Questions）](#11-開放討論點open-questions)
12. [里程碑規劃](#12-里程碑規劃草案)

---

## 1. 專案概述與命名

### 1.1 專案名稱

| | |
|---|---|
| **正式名稱** | VigilAI — Webcam Vision Intelligence Platform |
| **副標語** | "Connect any camera. Define what matters. Get notified instantly." |
| **域名建議** | vigil-ai.io / vigilai.app / getvigilai.com |

### 1.2 命名說明

**Vigil**（守望、警戒）+ **AI**，呼應「讓 AI 持續守望每一台鏡頭」的核心價值主張。發音自然，英中文環境皆適用。

### 1.3 一句話定義

> VigilAI 是一個多攝影機 AI 視覺監控平台，讓使用者透過自訂 Prompt 定義要偵測的事件，並在事件發生時透過 Webhook 觸發下游自動化流程。

---

## 2. 問題陳述

傳統攝影機監控系統有以下痛點：

- 需要購買昂貴的專用 NVR / VMS 硬體，且幾乎無法擴充 AI 能力
- 雲端 VLM API 成本高，且資料需上傳至第三方（隱私疑慮）
- 市面上沒有「以 Prompt 為核心配置」的彈性視覺偵測平台
- 各種場景（安全、品管、零售、醫療）需要完全不同的偵測邏輯，無法共用
- 偵測結果無法直接串接到現有的自動化工作流（Slack、LINE Bot、IFTTT、n8n 等）

**VigilAI 解決方案：**

- 本地 VLM（Ollama）+ 雲端 API 雙模式，隱私與成本可自行選擇
- Prompt-first 設計，非技術人員也能定義偵測規則
- 標準 Webhook 輸出，任何自動化平台都能接入

---

## 3. 目標用戶

| 用戶類型 | 場景範例 | 主要需求 |
|---|---|---|
| 系統整合商 / SI | 為客戶建置智慧監控方案 | 彈性設定、白標、API 整合 |
| 中小型企業 IT | 辦公室安全、訪客偵測 | 低門檻設定、Webhook 通知 |
| 工廠品管主管 | 生產線瑕疵偵測、人員安全 | 高準確率、即時告警 |
| 游泳池 / 健康場所 | 溺水偵測、人數統計 | 可靠性、低誤報率 |
| 零售業主 | 客流量分析、異常行為 | 數據統計、報表輸出 |
| IoT / AI 開發者 | PoC 驗證、多模型比較 | 開放 API、多 VLM 支援 |

---

## 4. 功能需求

### 4.1 攝影機管理（Camera Management）

#### MVP

- 新增攝影機：支援 RTSP URL、HTTP MJPEG Stream、本地 USB Device（`/dev/video*`）
- 攝影機名稱、描述、地點標籤設定
- 即時 Preview 縮圖（每 5 秒刷新）
- 攝影機啟用 / 停用 Toggle
- 連線狀態監控：Online / Offline / Error，附帶最後連線時間
- 設定截圖間隔：最短 1 秒，最長 5 分鐘
- 設定截圖解析度：原始 / 自動縮圖到 640px / 720p / 1080p

#### Phase 2

- 多台攝影機群組管理（Group）
- ROI（Region of Interest）區域圈選，只對指定區域送 VLM 分析
- 排程設定：指定時段才啟動偵測（例如：平日 08:00–22:00）

---

### 4.2 VLM 模型設定（Model Configuration）

#### MVP

- 支援本地 / 自架 Ollama 端點（OpenAI 相容 API）
  - 本地：`http://localhost:11434/v1`
  - PoC 共用端點：`https://ollama.transferhelper.com/v1`（需帶 `Authorization: Bearer <key>`）
- 可設定多個 Ollama 端點（不同機器）
- 每台攝影機獨立綁定一個 Model Config
- 設定 Temperature、Max Tokens、System Prompt
- 連線測試：發送測試圖片確認端點可用

#### 可用 VLM 模型（截至 2026-06-10，依 PoC 端點實測）

> 偵測引擎需「看圖」，故僅 **multimodal / vision** 模型可綁定到攝影機 Rule。
> 完整模型清單與呼叫範例見 [`ollama-models.md`](./ollama-models.md)。

| 模型 ID | 參數量 | 適用場景 | 備註 |
|---|---|---|---|
| `qwen2.5vl:32b` | 32B | 高準確率偵測（瑕疵、複雜場景、讀值/車牌） | 最強，推理較慢，建議搭 GPU |
| `qwen2.5vl:7b` | 7B | 一般偵測（入侵、人數、火煙） | **MVP 預設推薦**，速度/準確率平衡 |
| `qwen2.5vl:3b` | 3B | 高頻截圖、低資源邊緣裝置 | 最快，準確率較低 |
| `llama3.2-vision:11b` | 11B | 一般偵測，Qwen-VL 的替代/比較對象 | 多模型比較用 |

> ⚠️ 原 PRD 列舉的 `llava`、`llava-llama3`、`llava-phi3`、`bakllava`、`moondream` 在目前 PoC 端點上**未提供**；
> 端點另有 Qwen3 / Gemma3 / GPT-OSS 等純文字模型與 bge-m3 等 embedding 模型，皆無法吃影像，不納入偵測用。

#### Phase 2

- 支援 Anthropic Claude API / Google Gemini API / OpenAI Vision API（雲端 fallback）
- Model 效能統計：平均推理時間、月 token 用量追蹤
- 事件語意搜尋 / 相似事件比對：使用端點上的 embedding 模型（`bge-m3`、`qwen3-embedding`、`nomic-embed-text`）建立事件向量索引

---

### 4.3 Prompt Rule 管理（Rule Engine）

#### 核心設計理念

每台攝影機可設定多條 Prompt Rule，每條 Rule 是一個獨立的偵測任務。

#### MVP

- 每台攝影機可新增 N 條 Rule（建議上限 10 條/台）
- 每條 Rule 包含：
  - Rule 名稱（例如：溺水偵測、入侵警報）
  - 偵測 Prompt（自然語言描述）
  - VLM 回傳格式要求（JSON Schema 或 Yes/No 模式）
  - 觸發條件：VLM 判斷為 True / 信心度 > 閾值
  - Cooldown 設定：事件觸發後，N 秒內不重複觸發（避免洪水告警）
- Rule 啟用 / 停用 Toggle
- Rule 執行模式：
  - `all_frames`：每張圖都跑
  - `motion_only`：Motion detected 才跑（搭配 OpenCV motion filter）

#### Prompt Template 範例

| 場景 | Prompt 範例 | 回傳格式 |
|---|---|---|
| 溺水偵測 | 畫面中是否有人呈現溺水跡象（漂浮、靜止、臉朝下）？ | Yes/No + reason |
| 人員入侵 | 畫面中是否出現任何人員？ | Yes/No + count |
| 儀表板讀值 | 請讀取畫面中最大的數字顯示器的數值，只回傳數字 | number |
| 火焰 / 煙霧 | 畫面中是否有火焰或濃煙？ | Yes/No + location |
| 車牌辨識 | 請辨識畫面中的車牌號碼 | string |
| 工廠瑕疵 | 產品表面是否有裂縫、缺損或異物？ | Yes/No + description |

---

### 4.4 偵測引擎（Detection Engine）

#### 核心流程

```
1. Frame Capture        按設定間隔從攝影機截取一張圖片
2. Motion Filter        （可選）OpenCV 判斷畫面是否有變化，無變化跳過
3. ROI 裁切             （可選）只保留設定的感興趣區域
4. 影像前處理           壓縮至設定解析度、JPEG 壓縮 85%
5. VLM 推理             依序執行該攝影機所有啟用的 Rule Prompt
6. 結果解析             解析 VLM 回傳的 JSON / 文字，判斷是否符合觸發條件
7. Cooldown 檢查        確認該 Rule 未在 Cooldown 期間內
8. 事件記錄             寫入事件 DB，儲存觸發截圖
9. Webhook 觸發         傳送 Webhook Payload 到設定的 URL
```

#### 並發設計

- 每台攝影機一個獨立的 Worker（Process / Thread），互不影響
- VLM 推理 Queue：避免對同一 Ollama 端點並發過多請求
- 失敗重試：VLM 推理失敗自動 retry 2 次，間隔 2 秒

---

### 4.5 Webhook 系統

#### MVP

- 每條 Rule 可設定多個 Webhook URL（1 對多）
- HTTP POST，JSON Payload（見第 7 節規格）
- 自訂 Headers（例如 `Authorization: Bearer <token>`）
- Webhook 送達狀態記錄：Pending / Success / Failed
- 失敗自動重試：指數退避，最多 5 次（1s → 2s → 4s → 8s → 16s）
- Webhook 測試功能：手動觸發一次測試 Payload

#### Phase 2

- Webhook 簽名驗證：Header 附上 HMAC-SHA256 簽名供接收方驗證
- Webhook Template：自訂 Payload 結構（Handlebars 語法）
- 內建整合：Slack、LINE Notify、Discord、PagerDuty 一鍵設定

---

### 4.6 儀表板與事件中心

#### Dashboard

- 攝影機總覽 Grid：所有攝影機的狀態 + 最新截圖縮圖
- 系統健康指標：在線攝影機數量、今日事件數、Webhook 成功率
- 即時事件 Feed：最新觸發事件列表（含截圖 thumbnail）

#### 事件中心（Event Center）

- 事件列表：可依攝影機、Rule、時間範圍篩選
- 事件詳情：觸發時截圖、VLM 原始回傳、Webhook 送達狀態
- 事件確認 / 標記：Human review 標記為 True Positive / False Positive
- 截圖保留策略：預設保留 30 天，可設定

#### 分析報表（Phase 2）

- 每日 / 週 / 月事件趨勢圖
- 各 Rule 觸發頻率統計
- VLM 推理時間分佈

---

### 4.7 用戶與權限管理

| 角色 | 攝影機 | 規則設定 | Webhook | 事件查看 | 用戶管理 |
|---|---|---|---|---|---|
| Super Admin | 完整 | 完整 | 完整 | 完整 | 完整 |
| Admin | 完整 | 完整 | 完整 | 完整 | ✗ |
| Operator | 查看 | 只讀 | 查看 | 完整 | ✗ |
| Viewer | 查看 | 只讀 | ✗ | 查看 | ✗ |

---

## 5. 資料模型設計

### Entity 關係

```
Organization
  └── Camera (1:N)
        ├── ModelConfig (1:1)
        └── Rule (1:N)
              ├── Webhook (1:N)
              │     └── WebhookDelivery (1:N)
              └── Event (1:N)
                    └── WebhookDelivery (1:N)
```

### Entity 定義

| Entity | 關鍵欄位 | 關係 |
|---|---|---|
| Organization | id, name, plan, settings | 1:N Camera |
| Camera | id, name, stream_url, stream_type, status, capture_interval_sec, resolution, enabled | 1:1 ModelConfig, 1:N Rule |
| ModelConfig | id, camera_id, provider, endpoint_url, model_name, temperature, max_tokens, system_prompt | N:1 Camera |
| Rule | id, camera_id, name, prompt, output_format, trigger_condition, confidence_threshold, cooldown_sec, exec_mode, enabled | N:1 Camera, 1:N Webhook, 1:N Event |
| Webhook | id, rule_id, url, headers_json, enabled, retry_max | N:1 Rule, 1:N Delivery |
| Event | id, rule_id, triggered_at, screenshot_url, vlm_raw_response, vlm_parsed, confidence, reviewed_as | N:1 Rule |
| WebhookDelivery | id, webhook_id, event_id, status, attempt, response_code, response_body, sent_at | N:1 Webhook, N:1 Event |

---

## 6. API 規格草案

### RESTful API 主要端點

| Method | Endpoint | 說明 | 權限 |
|---|---|---|---|
| GET | `/api/cameras` | 列出所有攝影機 | Viewer+ |
| POST | `/api/cameras` | 新增攝影機 | Admin+ |
| GET | `/api/cameras/:id` | 攝影機詳情 | Viewer+ |
| PATCH | `/api/cameras/:id` | 更新攝影機設定 | Admin+ |
| DELETE | `/api/cameras/:id` | 刪除攝影機 | Admin+ |
| GET | `/api/cameras/:id/snapshot` | 取得最新截圖 | Viewer+ |
| GET | `/api/cameras/:id/rules` | 列出該攝影機的所有規則 | Viewer+ |
| POST | `/api/cameras/:id/rules` | 新增規則 | Admin+ |
| GET | `/api/rules/:id` | 規則詳情 | Viewer+ |
| PATCH | `/api/rules/:id` | 更新規則 | Admin+ |
| DELETE | `/api/rules/:id` | 刪除規則 | Admin+ |
| POST | `/api/rules/:id/test` | 手動觸發一次偵測測試 | Admin+ |
| GET | `/api/events` | 列出事件（支援篩選） | Operator+ |
| GET | `/api/events/:id` | 事件詳情 | Operator+ |
| PATCH | `/api/events/:id/review` | 標記事件（TP/FP） | Operator+ |
| GET | `/api/webhooks/:id/deliveries` | 查看 Webhook 送達記錄 | Admin+ |
| POST | `/api/webhooks/:id/test` | 測試 Webhook | Admin+ |
| GET | `/api/models/configs` | 列出所有 Model Config | Admin+ |
| POST | `/api/models/configs` | 新增 Model Config | Admin+ |
| POST | `/api/models/configs/:id/test` | 測試 VLM 端點連線 | Admin+ |

### WebSocket（即時推播）

```
ws://host/ws/cameras    攝影機狀態變更推播
ws://host/ws/events     新事件即時推播到 Dashboard
```

---

## 7. Webhook Payload 規格

VigilAI 觸發 Webhook 時，以 HTTP POST 傳送以下 JSON Payload：

```json
{
  "vigil_version": "1.0",
  "event_id": "evt_01J3K2M4N5P6Q7R8S9T",
  "triggered_at": "2026-06-10T14:23:01.234Z",
  "camera": {
    "id": "cam_abc123",
    "name": "泳池北側攝影機",
    "location": "Taipei HQ Pool"
  },
  "rule": {
    "id": "rule_xyz789",
    "name": "溺水偵測",
    "prompt": "畫面中是否有人呈現溺水跡象？"
  },
  "detection": {
    "triggered": true,
    "confidence": 0.91,
    "vlm_response": "Yes. A person appears motionless and face-down in the water.",
    "parsed_value": "yes"
  },
  "screenshot_url": "https://vigil-ai.app/storage/events/evt_01J3K.../screenshot.jpg",
  "meta": {
    "model": "qwen2.5vl:7b",
    "inference_ms": 1842,
    "frame_resolution": "1280x720"
  }
}
```

### Webhook 驗證 Header（Phase 2）

```
X-VigilAI-Signature: sha256=<HMAC_SHA256_of_payload_body>
X-VigilAI-Timestamp: 1749564181
X-VigilAI-Event-ID: evt_01J3K2M4N5P6Q7R8S9T
```

---

## 8. 系統架構

### 架構概覽

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend                             │
│                Next.js 14 (App Router)                      │
│         Dashboard / 事件中心 / 攝影機管理 / 設定              │
└───────────────────────────┬─────────────────────────────────┘
                            │ REST / WebSocket
┌───────────────────────────▼─────────────────────────────────┐
│                      Backend API                            │
│                   FastAPI (Python 3.12)                     │
│           REST API / WebSocket / Auth / Business Logic      │
└──────┬──────────────────────────────────────┬───────────────┘
       │ Enqueue Jobs                          │ Read/Write
┌──────▼──────────────────┐    ┌──────────────▼──────────────┐
│    Task Queue           │    │       PostgreSQL 16          │
│  Celery + Redis         │    │  Camera / Rule / Event /     │
│                         │    │  Webhook / Delivery          │
│  ┌─────────────────┐    │    └─────────────────────────────┘
│  │ Camera Workers  │    │
│  │ (1 per camera)  │    │    ┌─────────────────────────────┐
│  └────────┬────────┘    │    │      MinIO / Local FS        │
│           │             │    │   截圖長期儲存（Event Images）│
│  ┌────────▼────────┐    │    └─────────────────────────────┘
│  │ VLM Infer Queue │    │
│  └────────┬────────┘    │    ┌─────────────────────────────┐
│           │             │    │   Prometheus + Grafana       │
│  ┌────────▼────────┐    │    │   系統指標 / Worker 健康監控 │
│  │ Webhook Sender  │    │    └─────────────────────────────┘
│  └─────────────────┘    │
└─────────────────────────┘
           │
┌──────────▼──────────────┐
│    Ollama (Local VLM)   │
│  qwen2.5vl:7b/32b /     │
│  llama3.2-vision:11b    │
└─────────────────────────┘
```

### 部署模式

| 模式 | 工具 | 適合規模 |
|---|---|---|
| 單機部署 | docker-compose | 1–10 台攝影機 |
| 小規模集群 | Kubernetes + Helm | 10–100 台 |
| SaaS 多租戶 | K8s + Namespace 隔離 | 100+ 台 |

---

## 9. 非功能需求（NFR）

| 類別 | 指標 | 目標 |
|---|---|---|
| 延遲 | 事件觸發到 Webhook 送出 | < 5 秒（含 VLM 推理） |
| 可用性 | 平台 API 可用率 | 99.5% / 月 |
| 攝影機規模 | 單機部署支援 | 最多 20 台同時偵測 |
| 安全 | API 認證 | JWT Bearer Token，HTTPS only |
| 安全 | 攝影機串流 | RTSP over TLS（rtsps://）支援 |
| 隱私 | 截圖資料 | 支援本地儲存，不強制上傳雲端 |
| 瀏覽器支援 | Dashboard | Chrome 120+, Firefox 120+, Safari 17+ |
| 行動裝置 | 事件通知 | 支援 PWA，可在手機接收告警 |

---

## 10. 技術選型建議

| 項目 | 選型 | 理由 |
|---|---|---|
| Backend | FastAPI (Python 3.12) | 非同步、VLM 生態相容性最好 |
| Task Queue | Celery + Redis | 成熟穩定、支援 rate limiting / retry / 定時任務 |
| Frontend | Next.js 14 | SSR + WebSocket 整合方便，TypeScript 型別安全 |
| VLM 本地 | Ollama | 目前最易部署的本地 VLM runtime，支援最多模型 |
| 影像處理 | OpenCV + Pillow | 截圖、ROI、motion detection、壓縮 |
| 資料庫 ORM | SQLAlchemy 2.0 + Alembic | 型別安全、migration 管理 |
| 截圖儲存 | MinIO（S3-compatible） | 本地部署、可無縫遷移至 S3 |
| 部署 | Docker Compose / Helm Chart | 單機到 K8s 平滑遷移 |
| 監控 | Prometheus + Grafana | 開源、易整合 Celery / FastAPI metrics |

---

## 11. 開放討論點（Open Questions）

### 技術面

1. **Motion Detection 是否為 MVP 必要功能？** 沒有的話高頻攝影機成本顯著提高，但加入會增加複雜度。
2. **ROI 圈選工具做到什麼程度？** 矩形（簡單）vs. 任意多邊形（彈性但複雜）。
3. **Webhook 失敗後是否需要 Dead Letter Queue？** 供人工確認後手動重送。
4. **VLM 輸出格式支援範圍？** 目前設計：Yes/No、JSON Schema、自由文字，是否足夠？
5. **信心度（Confidence）如何計算？** VLM 不直接輸出機率，需靠 prompt 引導或解析語氣。

### 商業面

1. **定價模式**：Per camera / Per event / 月訂閱？建議以「攝影機台數 × 方案」為主。
2. **白標（White Label）需求**：SI 合作夥伴是否需要自訂 Logo 和域名？
3. **On-Premise 版本**：是否提供離線授權制？（影響架構複雜度）
4. **首批目標行業**：泳池安全、工廠品管、零售？決定後影響 Prompt Template 優先順序。

---

## 12. 里程碑規劃（草案）

| 里程碑 | 內容 | 預估週期 |
|---|---|---|
| **M0：技術 PoC** | Ollama + 單台攝影機 + Webhook 端到端打通 | 2 週 |
| **M1：MVP Alpha** | 攝影機管理、Rule 設定、Webhook、基本 Dashboard | 6 週 |
| **M2：MVP Beta** | Cooldown、截圖儲存、事件中心、Motion Filter | 4 週 |
| **M3：商業化準備** | 多租戶、計費模組、Webhook 簽名、雲端 VLM 整合 | 6 週 |
| **M4：Scale Up** | Kubernetes 部署、白標、進階分析報表 | 8 週 |

---

*VigilAI PRD v0.1 | 2026-06-10 | For Internal Discussion Only*