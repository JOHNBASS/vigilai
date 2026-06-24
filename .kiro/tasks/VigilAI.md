# VigilAI — 實作 Task List

> 版本：v1.0 | 日期：2026-06-10 | 狀態：Ready for Implementation

---

## 決策紀錄（已確認，不再討論）

| # | 決策 | 結論 |
|---|---|---|
| D1 | Motion Detection | ✅ 進 MVP，per-Rule `exec_mode: all_frames \| motion_only` |
| D2 | Ollama | ✅ 外部端點 `https://ollama.transferhelper.com/v1`，key=`Transfer168` |
| D3 | 截圖儲存 | ✅ Local FS + FastAPI static serve（MinIO 留 Phase 2） |
| D4 | 多租戶 Schema | ✅ 所有 table 含 `organization_id`，API hardcode `org_id = 1` |
| D5 | Admin 初始化 | ✅ ENV seed admin + `POST /api/auth/login`（用戶管理留 Phase 2） |
| G1 | Confidence 計算 | ✅ Prompt 要求 VLM 回傳 0-100，解析失敗預設 1.0 |
| G2 | WebSocket Auth | ✅ Query param `?token=<jwt>` |
| G3 | 截圖 URL | ✅ `http://host:4014/storage/events/<event_id>/screenshot.jpg` |
| G4 | 截圖清理 | ✅ Celery beat 每日 00:00 cleanup，預設保留 30 天 |
| G5 | Rule Test API | ✅ 立刻截一張圖 + 執行 Rule 推理，回傳 VLM 原始輸出 |

---

## 現有 Code 盤點

**專案為純 Greenfield（目前只有 `docs/` 資料夾），無既有程式碼。**

---

## 服務架構（Docker Compose）

```
對外: port 4014 (Nginx)
  ├── /           → frontend:3000   (Next.js 14)
  ├── /api/*      → api:8000        (FastAPI)
  ├── /ws/*       → api:8000        (WebSocket)
  └── /storage/*  → api:8000        (截圖靜態檔)

內部服務（不對外）:
  api     :8000   FastAPI
  worker  (no port) Celery Worker
  beat    (no port) Celery Beat Scheduler
  db      :5432   PostgreSQL 16
  redis   :6379   Redis 7

外部依賴:
  Ollama  https://ollama.transferhelper.com/v1  (Bearer Transfer168)
```

---

## Agent 說明

| Agent | 負責範圍 |
|---|---|
| **A** | Backend：FastAPI、Celery、偵測引擎、DB migrations |
| **B** | Frontend：Next.js 14、所有 UI 頁面 |
| **C** | Infrastructure：Docker Compose、Nginx、部署腳本 |

---

## 平行執行說明

```
Phase 0 (C) → 完成後解鎖 Phase 1 (A) 和 Phase 4 (B) 可平行跑
Phase 1 (A) → 解鎖 Phase 2、3 (A)
Phase 2 (A) → Phase 4 (B) 可同時進行（B 用 mock API）
Phase 5 (C) → 等所有服務完成後整合
```

---

## Tasks

---

### Phase 0：基礎設施 & 專案骨架

- [ ] **0.1 專案目錄結構 & 工具設定** `[Agent C]` ⏱ 2h
  - 建立 monorepo 結構：`backend/`、`frontend/`、`infra/`、`scripts/`
  - `backend/`: `pyproject.toml`（uv）、`src/vigil/` package 骨架
  - `frontend/`: `create-next-app` (TypeScript + Tailwind CSS + App Router)
  - 根目錄：`.gitignore`、`.env.example`（列出所有必要環境變數）
  - `.env.example` 必含：`ADMIN_EMAIL`、`ADMIN_PASSWORD`、`OLLAMA_BASE_URL`、`OLLAMA_API_KEY`、`SECRET_KEY`、`DATABASE_URL`
  - _需求對應：NFR 安全性、部署需求_

- [ ] **0.2 Docker Compose 初始設定** `[Agent C]` ⏱ 2h
  - 依賴：0.1
  - `docker-compose.yml`：7 services（nginx、api、worker、beat、frontend、db、redis）
  - 每個 service 設定：image/build、environment（從 `.env` 讀）、volumes、depends_on、healthcheck
  - db volume：`./data/postgres`；截圖 volume：`./data/storage`
  - `docker-compose.prod.yml`：關閉 hot-reload、設定 `restart: unless-stopped`、resource limits
  - _需求對應：單機部署、port 4014 唯一對外_

- [ ] **0.3 Nginx 反向代理設定** `[Agent C]` ⏱ 1h
  - 依賴：0.2
  - `infra/nginx/nginx.conf`：listen 80（container 內），對應 docker port 4014:80
  - Location 規則：`/api/` → `http://api:8000/api/`、`/ws/` → `http://api:8000/ws/`、`/storage/` → `http://api:8000/storage/`、`/` → `http://frontend:3000/`
  - WebSocket upgrade headers（`Connection: Upgrade`、`Upgrade: $http_upgrade`）
  - Client max body size 10MB（截圖上傳）
  - _需求對應：單一對外 port 4014_

---

### Phase 1：後端核心 API

- [ ] **1.1 DB Schema & Alembic Migrations** `[Agent A]` ⏱ 3h
  - 依賴：0.1
  - SQLAlchemy 2.0 + Alembic 初始化
  - 建立 7 個 model（全含 `organization_id` FK）：
    - `Organization`：id, name, settings_json
    - `Camera`：id, org_id, name, stream_url, stream_type(RTSP/MJPEG/USB), description, location_tag, status, capture_interval_sec, resolution, enabled, last_seen_at
    - `ModelConfig`：id, org_id, camera_id(FK), provider, endpoint_url, model_name, temperature, max_tokens, system_prompt
    - `Rule`：id, org_id, camera_id(FK), name, prompt, output_format(YES_NO/JSON_SCHEMA/FREE_TEXT), trigger_condition, confidence_threshold, cooldown_sec, exec_mode(ALL_FRAMES/MOTION_ONLY), enabled
    - `Webhook`：id, org_id, rule_id(FK), url, headers_json, enabled, retry_max
    - `Event`：id, org_id, rule_id(FK), triggered_at, screenshot_path, vlm_raw_response, vlm_parsed, confidence, reviewed_as(NULL/TP/FP)
    - `WebhookDelivery`：id, webhook_id(FK), event_id(FK), status(PENDING/SUCCESS/FAILED), attempt, response_code, response_body, sent_at
  - Alembic：`alembic init`、第一個 migration（`0001_initial_schema.py`）
  - Seed script：啟動時建立 default org（id=1）+ admin user（從 ENV 讀）
  - _需求對應：PRD §5 資料模型_

- [ ] **1.2 Auth 模組** `[Agent A]` ⏱ 2h
  - 依賴：1.1
  - `User` model（id, org_id, email, hashed_password, role: SUPER_ADMIN/ADMIN/OPERATOR/VIEWER）
  - `POST /api/auth/login`：email+password → JWT（HS256，24h 過期）
  - `GET /api/auth/me`：回傳當前用戶資訊
  - FastAPI dependency：`get_current_user`、`require_role(min_role)`
  - 啟動時 seed admin（ENV: `ADMIN_EMAIL`、`ADMIN_PASSWORD`）
  - Alembic migration 補 User table
  - _需求對應：PRD §4.7 用戶與權限管理、NFR JWT_

- [ ] **1.3 Camera CRUD API** `[Agent A]` ⏱ 3h
  - 依賴：1.2
  - `GET /api/cameras`：列出所有攝影機（含 status、last_seen_at）
  - `POST /api/cameras`：新增攝影機（Admin+）
  - `GET /api/cameras/:id`：詳情（Viewer+）
  - `PATCH /api/cameras/:id`：更新（Admin+），更新後若 enabled 狀態變更需通知 worker
  - `DELETE /api/cameras/:id`：刪除（Admin+），cascade delete Rules/Events
  - `GET /api/cameras/:id/snapshot`：回傳最新截圖（302 redirect 到 /storage/...）
  - Pydantic schemas：`CameraCreate`、`CameraUpdate`、`CameraResponse`
  - _需求對應：PRD §4.1 攝影機管理 MVP_

- [ ] **1.4 ModelConfig API** `[Agent A]` ⏱ 2h
  - 依賴：1.2
  - `GET /api/models/configs`：列出所有 config（Admin+）
  - `POST /api/models/configs`：新增（Admin+）
  - `PATCH /api/models/configs/:id`：更新（Admin+）
  - `DELETE /api/models/configs/:id`：刪除（Admin+）
  - `POST /api/models/configs/:id/test`：向 Ollama endpoint 發送測試請求，回傳 latency + model list
  - Ollama client：帶 `Authorization: Bearer <key>` header，OpenAI-compatible `/v1/chat/completions`
  - _需求對應：PRD §4.2 VLM 模型設定 MVP_

- [ ] **1.5 Rule CRUD API** `[Agent A]` ⏱ 2h
  - 依賴：1.3、1.4
  - `GET /api/cameras/:id/rules`：列出該攝影機所有規則（Viewer+）
  - `POST /api/cameras/:id/rules`：新增規則（Admin+，含綁定 ModelConfig）
  - `GET /api/rules/:id`：詳情（Viewer+）
  - `PATCH /api/rules/:id`：更新（Admin+）
  - `DELETE /api/rules/:id`：刪除（Admin+）
  - `POST /api/rules/:id/test`：立刻截圖 + 執行此 Rule 推理，回傳 VLM 原始輸出 + parsed result
  - _需求對應：PRD §4.3 Prompt Rule 管理 MVP_

- [ ] **1.6 Webhook CRUD API** `[Agent A]` ⏱ 2h
  - 依賴：1.5
  - `GET /api/rules/:id/webhooks`：列出該規則的 Webhooks（Admin+）
  - `POST /api/rules/:id/webhooks`：新增 Webhook（Admin+）
  - `PATCH /api/webhooks/:id`：更新（Admin+）
  - `DELETE /api/webhooks/:id`：刪除（Admin+）
  - `POST /api/webhooks/:id/test`：發送測試 Payload（Admin+）
  - `GET /api/webhooks/:id/deliveries`：查看送達記錄（Admin+）
  - _需求對應：PRD §4.5 Webhook 系統 MVP_

- [ ] **1.7 Event API** `[Agent A]` ⏱ 2h
  - 依賴：1.1
  - `GET /api/events`：列出事件，支援 query params 篩選：`camera_id`、`rule_id`、`start`、`end`、`reviewed_as`；分頁（`limit`/`offset`）
  - `GET /api/events/:id`：詳情，含 WebhookDelivery 狀態
  - `PATCH /api/events/:id/review`：標記 TP/FP（Operator+）
  - `GET /api/cameras/:id/events/stats`：今日事件數、觸發率（Dashboard 用）
  - _需求對應：PRD §4.6 事件中心 MVP_

- [ ] **1.8 截圖靜態 Serve & 儲存工具** `[Agent A]` ⏱ 1h
  - 依賴：0.1
  - FastAPI `StaticFiles` mount：`/storage` → `./data/storage/`
  - `StorageService`：`save_screenshot(event_id, image_bytes) → str`（路徑），`get_screenshot_url(event_id) → str`
  - 截圖路徑格式：`data/storage/events/<event_id>/screenshot.jpg`
  - _需求對應：截圖儲存設計（D3）_

- [ ] **1.9 健康檢查端點** `[Agent A]` ⏱ 1h
  - 依賴：1.2
  - `GET /api/health`：回傳各子系統狀態（JSON）
    ```json
    { "status": "ok", "db": "ok", "redis": "ok", "ollama": "ok|error", "workers": 2 }
    ```
  - DB：嘗試 `SELECT 1`；Redis：`PING`；Ollama：`GET /v1/models`
  - Docker healthcheck 用：`CMD curl -f http://localhost:8000/api/health`
  - _需求對應：部署需求、NFR 可用性_

---

### Phase 2：偵測引擎

- [ ] **2.1 影像擷取模組 (CameraCapture)** `[Agent A]` ⏱ 3h
  - 依賴：0.1
  - `CameraCapture` class，支援三種 stream type：
    - `RTSP`：`cv2.VideoCapture(rtsp_url)`
    - `MJPEG`：HTTP GET stream，逐幀解析 multipart boundary
    - `USB`：`cv2.VideoCapture(/dev/video0)`
  - `capture_frame() → PIL.Image`：擷取一張圖、縮放至設定解析度（原始/640px/720p/1080p）、JPEG 85% 壓縮
  - `check_connection() → CameraStatus`（ONLINE/OFFLINE/ERROR）
  - 連線失敗例外處理，更新 DB `camera.status` 與 `last_seen_at`
  - _需求對應：PRD §4.1 截圖間隔、解析度；§4.4 Frame Capture_

- [ ] **2.2 Motion Filter 模組** `[Agent A]` ⏱ 2h
  - 依賴：2.1
  - `MotionFilter` class（OpenCV `BackgroundSubtractorMOG2`）
  - `has_motion(frame: PIL.Image) → bool`：轉 grayscale → apply subtractor → 計算非零像素比例 > threshold
  - `threshold` 可設定（預設 0.5%，代表畫面 0.5% 以上面積有變化才算 motion）
  - per-Camera 獨立 MotionFilter instance（保留 background model）
  - _需求對應：PRD §4.3 exec_mode motion_only；§4.4 Motion Filter_

- [ ] **2.3 VLM 推理模組 (OllamaVLMClient)** `[Agent A]` ⏱ 3h
  - 依賴：1.4
  - `OllamaVLMClient`：
    - `infer(image: PIL.Image, rule: Rule, model_config: ModelConfig) → VLMResult`
    - 圖片轉 base64，組 OpenAI-compatible messages（含 system_prompt + user prompt + image）
    - 根據 `output_format`：
      - `YES_NO`：Prompt 結尾加「回傳 JSON：`{"answer": "yes|no", "confidence": 0-100, "reason": "..."}`」
      - `JSON_SCHEMA`：Prompt 結尾加指定 schema 格式要求
      - `FREE_TEXT`：直接回傳，confidence 預設 1.0
    - `VLMResult`：`triggered: bool`、`confidence: float`、`raw_response: str`、`parsed_value: Any`
    - confidence 解析失敗預設 1.0
  - Retry 2 次，間隔 2 秒（`tenacity`）
  - 推理時間記錄（`inference_ms`）
  - _需求對應：PRD §4.2 VLM 模型設定；§4.4 VLM 推理；G1 Confidence_

- [ ] **2.4 Cooldown 機制** `[Agent A]` ⏱ 1h
  - 依賴：1.5
  - Redis key：`vigil:cooldown:<rule_id>`，TTL = `rule.cooldown_sec`
  - `CooldownService.is_cooling(rule_id) → bool`
  - `CooldownService.set_cooldown(rule_id, seconds)`：SET key EX seconds
  - _需求對應：PRD §4.3 Cooldown 設定_

- [ ] **2.5 Camera Worker (Celery Periodic Task)** `[Agent A]` ⏱ 4h
  - 依賴：2.1、2.2、2.3、2.4、1.8
  - Celery app 初始化（broker=Redis, backend=Redis）
  - `capture_and_detect(camera_id)` Celery task：
    ```
    1. 取得 Camera + Rules + ModelConfig（DB query）
    2. CameraCapture.capture_frame()
    3. 儲存最新截圖到 camera.latest_snapshot_path
    4. 對每條 enabled Rule：
       a. exec_mode=MOTION_ONLY → MotionFilter.has_motion() → False 跳過
       b. CooldownService.is_cooling() → True 跳過
       c. OllamaVLMClient.infer()
       d. result.triggered → 建立 Event、StorageService.save_screenshot()
       e. CooldownService.set_cooldown()
       f. trigger_webhooks.delay(event_id)  ← 非同步
    5. 更新 Camera.status / last_seen_at
    ```
  - Celery Beat：每台 Camera 動態建立 PeriodicTask，間隔 = `camera.capture_interval_sec`
  - Camera enable/disable 時動態新增/移除 PeriodicTask（`django-celery-beat` 替代：用 `celery.conf.beat_schedule` + Redis pub/sub 通知）
  - VLM 推理 rate limiting：同一 Ollama endpoint 最多 3 個並行請求（`Semaphore`）
  - _需求對應：PRD §4.4 偵測引擎完整流程_

- [ ] **2.6 Webhook Sender (Celery Task)** `[Agent A]` ⏱ 2h
  - 依賴：2.5
  - `send_webhooks(event_id)` Celery task：
    - 查詢 Event + Rule + Camera（組 Payload）
    - 依 PRD §7 格式組裝 JSON Payload（`vigil_version: "1.0"`）
    - 對每個 enabled Webhook：
      - 建立 `WebhookDelivery`（status=PENDING）
      - HTTP POST with custom headers + JSON body
      - 更新 Delivery status/response_code/response_body
  - 失敗重試：指數退避 1→2→4→8→16 秒，最多 5 次（Celery `max_retries` + `countdown`）
  - _需求對應：PRD §4.5 Webhook 系統、失敗重試_

---

### Phase 3：WebSocket & 即時推播

- [ ] **3.1 WebSocket 端點** `[Agent A]` ⏱ 2h
  - 依賴：1.2、2.5
  - FastAPI WebSocket：
    - `ws://host/ws/cameras`：攝影機狀態變更推播（Camera status update 時 publish）
    - `ws://host/ws/events`：新 Event 建立時即時推播（含 thumbnail URL + Rule name）
  - JWT auth：WebSocket handshake 時驗證 query param `?token=<jwt>`，失敗 close(4001)
  - 廣播機制：Celery worker 完成後 publish 到 Redis channel（`vigil:ws:events`），WebSocket manager subscribe 並廣播給所有連線 client
  - `ConnectionManager` class：管理所有 active WS 連線
  - _需求對應：PRD §6 WebSocket；G2 WS Auth_

---

### Phase 4：前端（可與 Phase 2、3 平行執行）

- [ ] **4.1 Frontend 基礎骨架** `[Agent B]` ⏱ 2h
  - 依賴：0.1
  - Next.js 14 App Router + TypeScript + Tailwind CSS + shadcn/ui 初始化
  - `lib/api.ts`：fetch wrapper（自動帶 `Authorization: Bearer <jwt>`、統一 error 處理）
  - `lib/auth.ts`：JWT 儲存（localStorage）、login/logout helper
  - Layout：`app/layout.tsx` - Sidebar 導航 + Header（用戶名 + logout）
  - Sidebar 連結：Dashboard、攝影機管理、事件中心、設定
  - _需求對應：PRD §4.6 儀表板；NFR 瀏覽器支援_

- [ ] **4.2 Auth Pages** `[Agent B]` ⏱ 2h
  - 依賴：1.2、4.1
  - `app/(auth)/login/page.tsx`：Email + Password form、呼叫 `POST /api/auth/login`
  - JWT 儲存、登入成功跳轉 Dashboard
  - Protected route middleware（`middleware.ts`）：未登入自動 redirect `/login`
  - _需求對應：PRD §4.7 Auth_

- [ ] **4.3 Dashboard 頁面** `[Agent B]` ⏱ 3h
  - 依賴：4.1、1.3、1.7（等 API 完成；可先用 mock data）
  - `app/(dashboard)/page.tsx`
  - 系統健康 KPI 卡片：在線攝影機數 / 今日事件數 / Webhook 成功率
  - 攝影機 Grid：每格顯示 name + status badge（Online/Offline/Error）+ 最新截圖縮圖（polling 每 5 秒）
  - 即時事件 Feed（右側 panel）：連接 `ws://host/ws/events?token=<jwt>`，新事件即時插入頂部
  - _需求對應：PRD §4.6 Dashboard_

- [ ] **4.4 攝影機管理頁面** `[Agent B]` ⏱ 3h
  - 依賴：1.3、4.1
  - `app/(dashboard)/cameras/page.tsx`：攝影機列表 table（name, type, status, interval, enabled toggle）
  - `app/(dashboard)/cameras/new/page.tsx`：新增表單（stream URL、名稱、地點標籤、解析度、截圖間隔）
  - `app/(dashboard)/cameras/[id]/page.tsx`：詳情頁（Preview 截圖 + 設定）
  - stream_type radio：RTSP / MJPEG / USB
  - Enabled toggle 即時呼叫 `PATCH /api/cameras/:id`
  - _需求對應：PRD §4.1 攝影機管理 MVP_

- [ ] **4.5 Model Config & Rule 設定頁面** `[Agent B]` ⏱ 3h
  - 依賴：1.4、1.5、4.4
  - 攝影機詳情頁內 tabs：「偵測規則」+ 「模型設定」
  - ModelConfig tab：endpoint URL、model_name（下拉，從 `/api/models/configs/:id/test` 取模型清單）、temperature、system_prompt、[測試連線] 按鈕
  - Rules tab：Rule 列表 + 新增/編輯 modal
    - Rule 表單：名稱、Prompt（textarea）、output_format（radio）、exec_mode（toggle）、cooldown（number）、confidence_threshold（slider 0-1）
    - [立即測試] 按鈕：呼叫 `POST /api/rules/:id/test`，顯示 VLM 回傳結果
  - _需求對應：PRD §4.2、§4.3 MVP_

- [ ] **4.6 Webhook 設定頁面** `[Agent B]` ⏱ 2h
  - 依賴：1.6、4.5
  - Rule 詳情頁內 Webhook 管理區塊
  - Webhook 列表：URL + headers（collapsed JSON）+ 最後送達狀態
  - 新增/刪除 Webhook
  - 自訂 Headers：key-value pair 動態增刪
  - [測試] 按鈕：呼叫 `POST /api/webhooks/:id/test`，顯示送達結果
  - 送達記錄：最近 10 筆（狀態 badge + response_code + timestamp）
  - _需求對應：PRD §4.5 Webhook 系統_

- [ ] **4.7 事件中心頁面** `[Agent B]` ⏱ 3h
  - 依賴：1.7、4.1
  - `app/(dashboard)/events/page.tsx`
  - 篩選 bar：攝影機下拉、Rule 下拉、時間範圍 picker、reviewed_as（全部/未審/TP/FP）
  - 事件列表 table：thumbnail 縮圖 + camera + rule + triggered_at + confidence badge + review 狀態
  - 點擊開 detail drawer：
    - 大圖截圖
    - VLM 原始回傳（code block）
    - Webhook 送達狀態 list
    - [標記 TP] / [標記 FP] 按鈕
  - _需求對應：PRD §4.6 事件中心_

---

### Phase 5：維運 & 完整部署

- [ ] **5.1 截圖清理排程** `[Agent A]` ⏱ 1h
  - 依賴：2.5
  - Celery beat task：`cleanup_old_screenshots`，每日 00:00 執行
  - 查詢 `triggered_at < now - retention_days`（預設 30 天，可從 ENV 設定）
  - 刪除 `data/storage/events/<event_id>/` 目錄
  - 更新 Event.screenshot_path = NULL
  - _需求對應：PRD §4.6 截圖保留策略；G4_

- [ ] **5.2 Docker Compose 完整設定 & 調整** `[Agent C]` ⏱ 2h
  - 依賴：所有服務完成後
  - 確認所有 service volume mount 正確
  - api service：`volumes: ./data/storage:/app/data/storage`
  - 加入 `OLLAMA_BASE_URL`、`OLLAMA_API_KEY` 到 api + worker + beat env
  - DB init：`db` service 設 `POSTGRES_DB`、`POSTGRES_USER`、`POSTGRES_PASSWORD`
  - Redis：`redis:7-alpine`，加 `--save 60 1` 開啟 RDB persistence
  - Healthcheck 完整設定：api `GET /api/health`、db `pg_isready`、redis `redis-cli ping`
  - `docker-compose.prod.yml` override：`api` replicas、log rotation
  - _需求對應：完整部署需求_

- [ ] **5.3 部署腳本 deploy.sh** `[Agent C]` ⏱ 2h
  - 依賴：5.2
  - `scripts/deploy.sh`（bash）：
    ```bash
    #!/bin/bash
    # 1. 前置檢查：docker, docker-compose, curl
    # 2. 確認 .env 存在（否則 cp .env.example .env 並提示修改）
    # 3. 確認 Ollama endpoint 可達：curl $OLLAMA_BASE_URL/v1/models
    # 4. docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
    # 5. docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --wait
    # 6. DB migration: docker compose exec api alembic upgrade head
    # 7. 健康檢查：curl -f http://localhost:4014/api/health
    # 8. 列出服務狀態：docker compose ps
    ```
  - 加上 `set -euo pipefail`、顏色 output（INFO/ERROR）
  - 在 prod 機器上執行：`chmod +x scripts/deploy.sh && ./scripts/deploy.sh`
  - _需求對應：deploy script 一鍵部署_

- [ ] **5.4 端到端驗收測試** `[Agent A+B+C]` ⏱ 3h
  - 依賴：所有 task 完成
  - 本地 E2E 流程驗收：
    1. `./scripts/deploy.sh` 執行成功
    2. 開啟 `http://localhost:4014`，登入 admin
    3. 新增 ModelConfig（PoC endpoint + `qwen2.5vl:7b`）→ 測試連線通過
    4. 新增攝影機（RTSP 或測試 MJPEG stream）→ 狀態 ONLINE
    5. 新增 Rule（溺水偵測 prompt）→ 測試，得到 VLM 回傳
    6. 新增 Webhook URL（`https://webhook.site/...`）→ 測試送達成功
    7. 等待偵測循環觸發 → 事件出現在事件中心
    8. 事件 detail：截圖顯示、VLM 回傳顯示、Webhook delivery SUCCESS
    9. WebSocket：開兩個 tab，確認新事件即時推播
  - 記錄驗收結果到 `docs/ACCEPTANCE.md`
  - _需求對應：M0 技術 PoC 打通_

---

## 相依關係總覽

```
0.1 → 0.2 → 0.3
0.1 → 1.1 → 1.2 → 1.3 → 1.5 → 1.6
                → 1.4 ↗
              → 1.7
              → 1.9
0.1 → 1.8
0.1 → 2.1 → 2.2 → 2.5 → 2.6 → 3.1
         → 2.3 ↗
1.5 → 2.4 ↗
1.4 → 2.3
1.8 → 2.5
0.1 → 4.1 → 4.2 (需 1.2)
           → 4.3 (需 1.3, 1.7, 3.1)
           → 4.4 (需 1.3)
           → 4.5 (需 1.4, 1.5, 4.4)
           → 4.6 (需 1.6, 4.5)
           → 4.7 (需 1.7)
2.5 → 5.1
5.2 → 5.3 → 5.4 (需全部完成)
```

## 平行執行分組

| 批次 | 可平行執行的 Tasks |
|---|---|
| Batch 1 | 0.1 |
| Batch 2 | 0.2, 0.3（依賴 0.1）|
| Batch 3 | 1.1 + 4.1（依賴 0.1，A/B 可同時開工）|
| Batch 4 | 1.2 + 2.1（1.2 依賴 1.1；2.1 只依賴 0.1）|
| Batch 5 | 1.3 + 1.4 + 1.7 + 1.8 + 1.9 + 2.2（部分平行）|
| Batch 6 | 1.5 + 2.3 + 4.2（部分平行）|
| Batch 7 | 1.6 + 2.4 + 4.3 + 4.4（部分平行）|
| Batch 8 | 2.5 + 4.5 + 4.6（部分平行）|
| Batch 9 | 2.6 + 3.1 + 4.7（部分平行）|
| Batch 10 | 5.1 + 5.2（同時）|
| Batch 11 | 5.3 → 5.4 |

## 工時估計總覽

| Phase | Tasks | 估計工時 | 主要 Agent |
|---|---|---|---|
| Phase 0 | 0.1~0.3 | 5h | C |
| Phase 1 | 1.1~1.9 | 18h | A |
| Phase 2 | 2.1~2.6 | 15h | A |
| Phase 3 | 3.1 | 2h | A |
| Phase 4 | 4.1~4.7 | 18h | B |
| Phase 5 | 5.1~5.4 | 8h | A+B+C |
| **總計** | **23 tasks** | **~66h** | |

> 平行執行預估壓縮到約 **30-35h** wall-clock（A+B 同時進行 Phase 1+4）

---

*VigilAI Task List v1.0 | 2026-06-10*
