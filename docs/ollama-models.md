# Ollama 可用模型清單

- **Endpoint**: `https://ollama.transferhelper.com/v1`
- **API Key**: `Transfer168`（透過 `Authorization: Bearer Transfer168` header 帶入）
- **查詢日期**: 2026-06-10
- **查詢方式**: `GET /v1/models`

```bash
curl -s https://ollama.transferhelper.com/v1/models \
  -H "Authorization: Bearer Transfer168"
```

---

## 對話 / 推理類 (chat)

| 模型 ID | 說明 |
|---|---|
| `qwen35-35b-a3b-reasoning:latest` | Qwen3.5 35B MoE，推理特化（最新最大） |
| `qwen3.5:9b` | Qwen3.5 9B |
| `gemma4:26b` | Gemma4 26B |
| `qwen3:32b` | Qwen3 32B |
| `qwen3:30b` | Qwen3 30B |
| `qwen3:14b` | Qwen3 14B |
| `qwen3:8b` | Qwen3 8B |
| `qwen3:4b` | Qwen3 4B |
| `gpt-oss:20b` | OpenAI 開源權重 20B |
| `qwen2.5:32b` | Qwen2.5 32B |
| `qwen2.5:14b` | Qwen2.5 14B |
| `qwen2.5:7b` | Qwen2.5 7B |
| `gemma3:27b` | Gemma3 27B |
| `gemma3:12b` | Gemma3 12B |
| `gemma3:4b` | Gemma3 4B |
| `llama3.1:latest` | Llama 3.1 |
| `llama3.2:3b` | Llama 3.2 3B |

## 視覺 / 多模態 (vision)

| 模型 ID | 說明 |
|---|---|
| `qwen2.5vl:32b` | Qwen2.5-VL 32B 看圖 |
| `qwen2.5vl:7b` | Qwen2.5-VL 7B 看圖 |
| `qwen2.5vl:3b` | Qwen2.5-VL 3B 看圖 |
| `llama3.2-vision:11b` | Llama 3.2 Vision 11B |

## 向量 (embedding)

| 模型 ID | 說明 |
|---|---|
| `bge-m3:latest` | 多語向量，常用 |
| `qwen3-embedding:latest` | Qwen3 向量 |
| `nomic-embed-text:latest` | Nomic 文字向量 |

---

## 呼叫範例

### Chat completion
```bash
curl -s https://ollama.transferhelper.com/v1/chat/completions \
  -H "Authorization: Bearer Transfer168" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3:32b",
    "messages": [{"role": "user", "content": "你好"}]
  }'
```

### Embedding
```bash
curl -s https://ollama.transferhelper.com/v1/embeddings \
  -H "Authorization: Bearer Transfer168" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "bge-m3:latest",
    "input": "要轉成向量的文字"
  }'
```
