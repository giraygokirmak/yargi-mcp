FROM python:3.11-slim

WORKDIR /app

# Önce bağımlılıklar (katman önbelleği)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY mcp_server_main.py ./
COPY yargitay_mcp_module ./yargitay_mcp_module
COPY danistay_mcp_module ./danistay_mcp_module
COPY emsal_mcp_module ./emsal_mcp_module
COPY uyusmazlik_mcp_module ./uyusmazlik_mcp_module
COPY anayasa_mcp_module ./anayasa_mcp_module

# Non-root yogun kullanici + log dizini izinleri.
# `logs/` alt dizinini image build asamasinda yaratip chown ediyoruz ki
# compose'un `yargi-logs` named-volume'u ilk mount'ta /app/logs'un sahip
# bilgisini (yargi:yargi) miras alsin; boylece PermissionError olusmaz.
RUN useradd --create-home --uid 10001 yargi \
    && mkdir -p /app/logs \
    && chown -R yargi:yargi /app
USER yargi

EXPOSE 8890

# Varsayilan: streamable-http, tum arayuzlerde dinle
ENV MCP_TRANSPORT=streamable-http \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8890

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import socket,os;s=socket.create_connection((os.environ.get('MCP_HOST','127.0.0.1') if os.environ.get('MCP_HOST','0.0.0.0')!='0.0.0.0' else '127.0.0.1', int(os.environ.get('MCP_PORT','8890'))),3);s.close()" || exit 1

CMD ["python", "mcp_server_main.py"]
