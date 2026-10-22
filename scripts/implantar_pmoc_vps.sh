#!/usr/bin/env bash
# SGME - Script de Implantação do Módulo PMOC (v3.1.0) na Oracle VPS
set -Eeuo pipefail
umask 027

SERVICE="${SERVICE:-sgme}"
APP_DIR="${APP_DIR:-/opt/sgme/app}"
DB_PATH="${DB_PATH:-/var/lib/sgme/sistema.db}"
BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/sgme}"
STAMP="$(date +%Y%m%d_%H%M%S)"
BKP_DIR="$BACKUP_ROOT/pre_deploy_pmoc_$STAMP"
TMP_DIR="$(mktemp -d /tmp/sgme-deploy-pmoc.XXXXXX)"

say() { printf '[SGME-PMOC-DEPLOY] %s\n' "$*"; }
die() { printf '[SGME-PMOC-DEPLOY] ERRO: %s\n' "$*" >&2; exit 1; }

cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

[[ ${EUID:-$(id -u)} -eq 0 ]] || die "Execute este script com sudo."
command -v python3 >/dev/null 2>&1 || die "python3 nao encontrado."
command -v systemctl >/dev/null 2>&1 || die "systemctl nao encontrado."

say "1. Descompactando pacote de deploy..."
[[ -f /home/opc/deploy_pmoc.tar.gz ]] || die "Arquivo /home/opc/deploy_pmoc.tar.gz nao encontrado."
tar -xzf /home/opc/deploy_pmoc.tar.gz -C "$TMP_DIR"

say "2. Validando integridade prévia do banco SQLite..."
INTEGRIDADE=$(python3 - "$DB_PATH" <<'PY'
import sqlite3, sys
with sqlite3.connect(sys.argv[1]) as conn:
    res = conn.execute("PRAGMA integrity_check").fetchone()[0]
    print(res)
PY
)
[[ "$INTEGRIDADE" == "ok" ]] || die "Banco com integridade violada: $INTEGRIDADE"
say "Integridade pré-deploy: OK"

say "3. Criando backup consistente completo em $BKP_DIR..."
mkdir -p "$BKP_DIR/app"
python3 - "$DB_PATH" "$BKP_DIR/sistema.db" <<'PY'
import sqlite3, sys
src, dst = sys.argv[1:3]
with sqlite3.connect(f"file:{src}?mode=ro", uri=True) as s:
    with sqlite3.connect(dst) as d:
        s.backup(d)
PY
cp -a "$APP_DIR"/. "$BKP_DIR/app/"
say "Backup concluído com sucesso."

say "4. Parando o serviço $SERVICE temporariamente para migração..."
systemctl stop "$SERVICE"

say "5. Atualizando arquivos do Backend e Frontend..."
cp -a "$TMP_DIR"/backend/*.py "$APP_DIR/backend/"
cp -a "$TMP_DIR"/frontend/* "$APP_DIR/frontend/"
cp -a "$TMP_DIR"/backup_sgme.sh /opt/sgme/
cp -a "$TMP_DIR"/checagem_funcional_completa_sgme.sh /opt/sgme/
chmod +x /opt/sgme/*.sh

say "6. Executando migração de banco PMOC..."
sudo -u sgme SGME_DADOS=/var/lib/sgme /opt/sgme/venv/bin/python "$APP_DIR/backend/migrar_pmoc.py"

say "7. Verificando integridade do banco pós-migração..."
POS_INTEGRIDADE=$(python3 - "$DB_PATH" <<'PY'
import sqlite3, sys
with sqlite3.connect(sys.argv[1]) as conn:
    res = conn.execute("PRAGMA integrity_check").fetchone()[0]
    print(res)
PY
)
[[ "$POS_INTEGRIDADE" == "ok" ]] || die "Banco violado apos migracao: $POS_INTEGRIDADE"
say "Integridade pós-migração: OK"

say "8. Ajustando permissões e propriedades de segurança (SELinux)..."
chown -R sgme:sgme /opt/sgme/app /var/lib/sgme
chmod 755 /opt/sgme/app
chmod 750 /opt/sgme/app/backend
chmod 755 /opt/sgme/app/frontend
chmod 644 /opt/sgme/app/frontend/*
chmod 640 "$DB_PATH"
restorecon -Rv /opt/sgme/app/frontend >/dev/null 2>&1 || true

say "9. Reiniciando o serviço $SERVICE..."
systemctl start "$SERVICE"
sleep 2

say "10. Validando funcionamento dos serviços e endpoints..."
systemctl is-active --quiet "$SERVICE" || die "O servico $SERVICE nao esta ativo!"
say "Serviço $SERVICE ativo e em execução."

HEALTH_RES=$(curl -s http://127.0.0.1:5001/)
say "Health check (5001): $HEALTH_RES"
echo "$HEALTH_RES" | grep -q "3.1.0_pmoc_preventivas" || die "Versao inesperada no backend: $HEALTH_RES"

NGINX_RES=$(curl -s http://127.0.0.1/servidor.json)
echo "$NGINX_RES" | grep -q '"url"' || die "Nginx servidor.json indisponivel"
say "Nginx /servidor.json: OK ($NGINX_RES)"

HTML_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1/)
[[ "$HTML_CODE" == "200" ]] || die "Nginx HTTP root retornou $HTML_CODE"
say "Nginx /: HTTP 200 OK"

rm -f /home/opc/deploy_pmoc.tar.gz
say "=========================================================="
say " IMPLANTAÇÃO PMOC CONCLUÍDA COM SUCESSO NA ORACLE VPS!"
say " Versão Ativa: 3.1.0_pmoc_preventivas"
say "=========================================================="
