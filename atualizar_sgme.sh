#!/bin/bash
set -e

SGME_DIR="/home/daniel/sgme"
TAR_FILE="$SGME_DIR/sgme.tar"
VENV_PYTHON="$SGME_DIR/backend/venv/bin/python"

echo "=========================================================="
echo "      SGME - Script de Atualização e Reinício"
echo "=========================================================="
echo "Data/Hora: $(date '+%d/%m/%Y %H:%M:%S')"
echo "Diretório: $SGME_DIR"
echo ""

cd "$SGME_DIR"

# 1. Extrair pacote .tar se existir
if [ -f "$TAR_FILE" ]; then
    echo "[1/5] Arquivo sgme.tar detectado. Extraindo arquivos..."
    tar -xf "$TAR_FILE" -C "$SGME_DIR"
    echo "      Arquivos extraídos com sucesso."
    rm -f "$TAR_FILE"
    echo "      Arquivo $TAR_FILE removido após extração."
else
    echo "[1/5] Nenhum arquivo sgme.tar encontrado em $SGME_DIR. Mantendo arquivos existentes."
fi

# 2. Ajustar permissões de execução
echo "[2/5] Ajustando permissões de scripts..."
chmod +x "$SGME_DIR"/scripts/*.sh "$SGME_DIR"/scripts/*.py "$SGME_DIR"/backend/*.py "$SGME_DIR"/*.sh 2>/dev/null || true

# 3. Executar migrações pendentes no banco de dados (se houver venv)
echo "[3/5] Verificando e aplicando migrações de banco de dados..."
if [ -f "$VENV_PYTHON" ]; then
    if [ -f "$SGME_DIR/backend/migrar_pmoc.py" ]; then
        $VENV_PYTHON "$SGME_DIR/backend/migrar_pmoc.py" || true
    fi
    if [ -f "$SGME_DIR/backend/migrar_os_instalacao.py" ]; then
        $VENV_PYTHON "$SGME_DIR/backend/migrar_os_instalacao.py" || true
    fi
else
    echo "      Ambiente virtual Python não encontrado em $VENV_PYTHON. Pulando migrações."
fi

# 4. Sincronizar alterações com o Git e GitHub Pages
echo "[4/5] Sincronizando com repositório Git..."
if [ -d "$SGME_DIR/.git" ]; then
    git add frontend/ docs/ backend/ scripts/ .github/ .gitignore atualizar_sgme.sh 2>/dev/null || git add .
    if ! git diff --staged --quiet; then
        COMMIT_MSG="update: atualização do sistema SGME em $(date '+%d/%m/%Y %H:%M')"
        git commit -m "$COMMIT_MSG"
        echo "      Commit realizado: $COMMIT_MSG"
        if git remote | grep -q "origin"; then
            echo "      Enviando para o GitHub (branch main)..."
            git push origin main || echo "      Aviso: Falha ao enviar para o GitHub (verifique a conexão ou chave SSH)."
        fi
    else
        echo "      Nenhuma alteração pendente para commit no Git."
    fi
else
    echo "      Diretório .git não encontrado. Pulando sincronização Git."
fi

# 5. Reiniciar serviços do sistema
echo "[5/5] Reiniciando serviços do SGME..."
if command -v systemctl &>/dev/null; then
    # Reiniciar backend Flask
    if systemctl is-enabled sgme-backend.service &>/dev/null || systemctl is-active sgme-backend.service &>/dev/null; then
        sudo systemctl restart sgme-backend.service
        echo "      -> sgme-backend.service: REINICIADO"
    fi

    # Reiniciar Nginx
    if systemctl is-enabled nginx &>/dev/null || systemctl is-active nginx &>/dev/null; then
        sudo systemctl reload nginx 2>/dev/null || sudo systemctl restart nginx
        echo "      -> nginx.service: REINICIADO / RECARREGADO"
    fi

    # Reiniciar túnel Cloudflare
    if systemctl is-enabled sgme-tunnel.service &>/dev/null || systemctl is-active sgme-tunnel.service &>/dev/null; then
        sudo systemctl restart sgme-tunnel.service
        echo "      -> sgme-tunnel.service: REINICIADO"
    fi

    echo ""
    echo "Status dos Serviços:"
    echo " - Backend Flask:      $(systemctl is-active sgme-backend.service 2>/dev/null || echo 'desconhecido')"
    echo " - Servidor Nginx:     $(systemctl is-active nginx 2>/dev/null || echo 'desconhecido')"
    echo " - Túnel Cloudflare:   $(systemctl is-active sgme-tunnel.service 2>/dev/null || echo 'desconhecido')"
fi

echo ""
echo "=========================================================="
echo "    Atualização do SGME concluída com sucesso!"
echo "=========================================================="
