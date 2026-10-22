#!/bin/bash
set -e

SGME_DIR="/home/daniel/sgme"
SCRIPT_NAME="$(basename "$0")"
VERSION="${SCRIPT_NAME%.sh}"
TAR_FILE="$SGME_DIR/${VERSION}.tar"
VENV_PYTHON="$SGME_DIR/backend/venv/bin/python"

echo "=========================================================="
echo "      SGME - Deploy de Atualização e Limpeza"
echo "      Versão do Pacote: $VERSION"
echo "=========================================================="
echo "Data/Hora: $(date '+%d/%m/%Y %H:%M:%S')"
echo "Diretório: $SGME_DIR"
echo ""

cd "$SGME_DIR"

# 1. Localizar e descompactar o arquivo .tar da versão
if [ ! -f "$TAR_FILE" ]; then
    ALT_TAR=$(ls -t "$SGME_DIR"/sgme*.tar 2>/dev/null | head -n 1 || true)
    if [ -n "$ALT_TAR" ] && [ -f "$ALT_TAR" ]; then
        echo "[1/6] Pacote alternativo detectado: $(basename "$ALT_TAR")"
        TAR_FILE="$ALT_TAR"
    fi
fi

if [ -f "$TAR_FILE" ]; then
    echo "[1/6] Preparando diretórios e extraindo $(basename "$TAR_FILE")..."
    # Garante permissão de escrita nos arquivos e pastas antes de descompactar
    chmod -R u+w "$SGME_DIR" 2>/dev/null || true
    
    # Extração segura: tenta tar nativo com sobrescrita; se falhar usa python tarfile
    if ! tar --overwrite --no-same-owner --warning=no-unknown-keyword --exclude="*.sh" -xf "$TAR_FILE" -C "$SGME_DIR" 2>/dev/null; then
        if ! tar --overwrite --exclude="*.sh" -xf "$TAR_FILE" -C "$SGME_DIR" 2>/dev/null; then
            python3 -c "import tarfile; [t.extract(m, '$SGME_DIR') for t in [tarfile.open('$TAR_FILE')] for m in t.getmembers() if not m.name.endswith('.sh')]"
        fi
    fi
    echo "      Arquivos atualizados com sucesso."
else
    echo "[1/6] Aviso: Nenhum arquivo .tar encontrado para extração em $SGME_DIR."
fi

# 2. Ajustar permissões de execução
echo "[2/6] Configurando permissões dos scripts..."
chmod +x "$SGME_DIR"/scripts/*.sh "$SGME_DIR"/scripts/*.py "$SGME_DIR"/backend/*.py "$SGME_DIR"/*.sh 2>/dev/null || true

# 3. Dependências e migrações do banco de dados (se houver venv)
echo "[3/6] Verificando dependências e aplicando migrações de banco de dados..."
if [ -f "$VENV_PYTHON" ]; then
    echo "      Garantindo biblioteca pypdf no venv..."
    $VENV_PYTHON -m pip install --quiet pypdf 2>/dev/null || true

    if [ -f "$SGME_DIR/backend/migrar_pmoc.py" ]; then
        $VENV_PYTHON "$SGME_DIR/backend/migrar_pmoc.py" || true
    fi
    if [ -f "$SGME_DIR/backend/migrar_os_instalacao.py" ]; then
        $VENV_PYTHON "$SGME_DIR/backend/migrar_os_instalacao.py" || true
    fi
else
    echo "      Ambiente virtual Python não encontrado em $VENV_PYTHON. Migrações puladas."
fi

# 4. Sincronizar com Git e atualizar o GitHub Pages
echo "[4/6] Sincronizando com repositório Git e GitHub Pages..."
if [ -d "$SGME_DIR/.git" ]; then
    git add frontend/ docs/ backend/ scripts/ .github/ .gitignore 2>/dev/null || git add .
    if ! git diff --staged --quiet; then
        COMMIT_MSG="release: $VERSION - cronograma PMOC iniciando no mês seguinte da instalação em $(date '+%d/%m/%Y %H:%M')"
        git commit -m "$COMMIT_MSG"
        echo "      Commit realizado: $COMMIT_MSG"
        if git remote | grep -q "origin"; then
            echo "      Enviando para o GitHub (branch main)..."
            git push origin main || echo "      Aviso: Falha ao enviar para o GitHub (verifique a conexão ou chave SSH)."
        fi
    else
        echo "      Repositório Git já está em dia."
    fi
fi

# 5. Limpeza de arquivos residuais e temporários
echo "[5/6] Executando limpeza de arquivos residuais..."

# Remove o arquivo .tar do deploy
if [ -f "$TAR_FILE" ]; then
    rm -f "$TAR_FILE"
    echo "      -> Removido arquivo de pacote: $(basename "$TAR_FILE")"
fi

# Remove arquivos .tar temporários residuais em /tmp ou no diretório
rm -f /tmp/sgme*.tar 2>/dev/null || true
rm -f "$SGME_DIR"/sgme*.tar 2>/dev/null || true

# Remove arquivos de backup e temporários
rm -f "$SGME_DIR"/*.bak "$SGME_DIR"/*.tmp "$SGME_DIR"/tunnel.log 2>/dev/null || true

# Remove caches de bytecode Python (__pycache__ e *.pyc) fora do venv
find "$SGME_DIR/backend" -name "__pycache__" -type d -not -path "*/venv/*" -exec rm -rf {} + 2>/dev/null || true
find "$SGME_DIR/backend" -name "*.pyc" -not -path "*/venv/*" -delete 2>/dev/null || true
echo "      -> Caches de bytecode Python limpos."

# Registra histórico de versão instalada
echo "$VERSION - Instalado em $(date '+%d/%m/%Y %H:%M:%S')" > "$SGME_DIR/VERSAO.txt"
mkdir -p "$SGME_DIR/historico_deploys"
cp -f "$SGME_DIR/$SCRIPT_NAME" "$SGME_DIR/historico_deploys/$SCRIPT_NAME" 2>/dev/null || true
echo "      -> Registro salvo em VERSAO.txt e histórico arquivado."

# 6. Reiniciar serviços do SGME
echo "[6/6] Reiniciando serviços do SGME..."
if command -v systemctl &>/dev/null; then
    if systemctl is-enabled sgme-backend.service &>/dev/null || systemctl is-active sgme-backend.service &>/dev/null; then
        sudo systemctl restart sgme-backend.service
        echo "      -> sgme-backend.service: REINICIADO"
    fi

    if systemctl is-enabled nginx &>/dev/null || systemctl is-active nginx &>/dev/null; then
        sudo systemctl reload nginx 2>/dev/null || sudo systemctl restart nginx
        echo "      -> nginx.service: RECARREGADO"
    fi

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
echo "    Versão $VERSION implantada com sucesso e resíduos limpos!"
echo "=========================================================="
