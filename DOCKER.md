# yargi-mcp — Standalone Docker Container

Türk hukuk veritabanları (Yargıtay, Danıştay, Emsal, Uyuşmazlık Mahkemesi, Anayasa Mahkemesi norm denetimi + bireysel başvuru) için MCP sunucusu. Bu paket, sunucuyu bağımsız Docker container olarak streamable-http transport ile çalıştırır; OpenClaw native registry'ye `mcp.servers` altında eklenebilir.

## Mimari

- **Transport:** FastMCP 2.14.7 `streamable-http` (varsayılan), geriye dönük SSE de desteklenir.
- **Giriş noktası:** `mcp_server_main.py`; transport/host/port ortam değişkenleriyle seçilir:
  - `MCP_TRANSPORT` = `streamable-http` (varsayılan) | `sse`
  - `MCP_HOST` = `0.0.0.0` (container için varsayılan; SSE modunda geriye uyumluluk için eskiden `127.0.0.1`)
  - `MCP_PORT` = `8890` (varsayılan)
- Healthcheck: TCP port bağlantısı (Python socket). Loglar `/app/logs/mcp_server.log` (compose volume: `yargi-logs`).

## Build ve çalıştırma

```bash
docker build -t yargi-mcp:latest .
docker run -d --name yargi-mcp --restart unless-stopped -p 8890:8890 yargi-mcp:latest
```

veya compose ile:

```bash
docker compose up -d --build
```

Endpoint: `http://<host>:8890/mcp` (FastMCP streamable-http varsayılan yolu `/mcp`).

## OpenClaw kaydı

`openclaw.json` → `mcp.servers.yargi-mcp`:

```json
{
  "type": "streamableHttp",
  "url": "http://192.168.2.10:8890/mcp",
  "enabled": true
}
```

Ardından `openclaw config validate` ve `openclaw mcp probe yargi-mcp` (beklenen: tool listesi).

## SSE geriye dönük mod

Lokal geliştirmede eski SSE davranışı:

```bash
MCP_TRANSPORT=sse MCP_HOST=127.0.0.1 MCP_PORT=8890 python mcp_server_main.py
```

## Tool'lar

- `search_yargitay_detailed`, `get_yargitay_document_markdown`
- `search_danistay_by_keyword`, `search_danistay_detailed`, `get_danistay_document_markdown`
- `search_emsal_detailed`, `get_emsal_document_markdown`
- `search_uyusmazlik`, `get_uyusmazlik_document_markdown`
- `search_anayasa_norm_denetimi`, `get_anayasa_norm_denetimi_document_markdown`
- `search_anayasa_bireysel_basvuru_report`, `get_anayasa_bireysel_basvuru_document_markdown`

(Listeyi canlı doğrulamak için: `openclaw mcp probe yargi-mcp`.)

## Notlar

- Server sadece upstream resmi API/site'lere istek atar; kullanıcı verisi saklamaz. Log dosyasında tool çağrı parametreleri görünür — volume'u host paylaşımına açma.
- `markitdown` bağımlılığı ağırdır; ileride hafifletmek istersen sadece `markitdown[pdf,docx]` alt seti denenebilir.
