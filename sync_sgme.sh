#!/bin/bash

LOG_FILE="/home/daniel/sgme/tunnel.log"
FRONTEND_DIR="/home/daniel/sgme/frontend"
JSON_FILE="$FRONTEND_DIR/servidor.json"

if [ ! -f "$LOG_FILE" ]; then
    echo "Aguardando arquivo de log..."
    exit 0
fi

# O parâmetro -a força o grep a ler o arquivo como texto mesmo com caracteres binários do QUIC
NOVA_URL=$(grep -a -o 'https://[^ "]*trycloudflare\.com' "$LOG_FILE" | tail -n 1)

if [ -z "$NOVA_URL" ]; then
    echo "Nenhuma URL encontrada no log."
    exit 0
fi

URL_ATUAL=""
if [ -f "$JSON_FILE" ]; then
    URL_ATUAL=$(grep -a -o 'https://[^ "]*trycloudflare\.com' "$JSON_FILE" | head -n 1)
fi

if [ "$NOVA_URL" != "$URL_ATUAL" ] || [ ! -f "$JSON_FILE" ]; then
    echo "[$(date)] Nova URL ativa detectada: $NOVA_URL"
    echo "{\"url\": \"$NOVA_URL\"}" > "$JSON_FILE"
    
    cd "$FRONTEND_DIR"
    git add servidor.json
    git commit -m "Auto-sync Cloudflare Tunnel URL: $NOVA_URL"
    git push origin main
    echo "[$(date)] servidor.json publicado com sucesso no GitHub Pages!"
else
    echo "URL já está atualizada no GitHub Pages: $URL_ATUAL"
fi
