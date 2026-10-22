#!/usr/bin/env python3
import subprocess
import time
import re
import os
import sys

BASE_DIR = "/home/daniel/sgme"
CONFIG_JS = os.path.join(BASE_DIR, "frontend", "config.js")
DOCS_CONFIG_JS = os.path.join(BASE_DIR, "docs", "config.js")
CACHE_FILE = os.path.join(BASE_DIR, "dados", "current_tunnel_url.txt")

def obter_url_atual():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            return None
    return None

def atualizar_config_e_git(nova_url):
    print(f"[TUNNEL-SYNC] Atualizando frontend/config.js com nova URL: {nova_url}")
    with open(CONFIG_JS, "w", encoding="utf-8") as f:
        f.write(f'window.SGME_CONFIG = {{\n    API_URL: "{nova_url}"\n}};\n')
    if os.path.exists(os.path.dirname(DOCS_CONFIG_JS)):
        with open(DOCS_CONFIG_JS, "w", encoding="utf-8") as f:
            f.write(f'window.SGME_CONFIG = {{\n    API_URL: "{nova_url}"\n}};\n')
    
    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        f.write(nova_url)
    
    # Commit e push no git (se o git remote estiver configurado e autenticado)
    try:
        subprocess.run(["git", "-C", BASE_DIR, "add", "frontend/config.js", "docs/config.js"], check=True)
        # Verifica se há alteração antes de commitar
        diff = subprocess.run(["git", "-C", BASE_DIR, "diff", "--staged", "--quiet"])
        if diff.returncode != 0:
            msg = f"chore: atualizar Cloudflare Tunnel para {nova_url}"
            subprocess.run(["git", "-C", BASE_DIR, "commit", "-m", msg], check=True)
            push_res = subprocess.run(["git", "-C", BASE_DIR, "push", "origin", "main"], capture_output=True, text=True)
            if push_res.returncode == 0:
                print(f"[TUNNEL-SYNC] Push para o GitHub realizado com sucesso!")
            else:
                print(f"[TUNNEL-SYNC] Aviso no git push: {push_res.stderr.strip() or push_res.stdout.strip()}")
    except Exception as e:
        print(f"[TUNNEL-SYNC] Erro ao sincronizar com git: {e}")

def monitorar_tunel():
    url_anterior = obter_url_atual()
    print("[TUNNEL-SYNC] Iniciando monitoramento do Cloudflare Tunnel na porta 5001...")
    
    while True:
        try:
            proc = subprocess.Popen(
                ["cloudflared", "tunnel", "--url", "http://127.0.0.1:5001"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            url_capturada = None
            for line in iter(proc.stdout.readline, ''):
                if not line:
                    break
                # Procura por URLs do trycloudflare.com
                m = re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', line)
                if m:
                    nova_url = m.group(0)
                    if nova_url != url_capturada:
                        url_capturada = nova_url
                        print(f"[TUNNEL-SYNC] URL do Túnel detectada: {nova_url}")
                        if nova_url != url_anterior:
                            atualizar_config_e_git(nova_url)
                            url_anterior = nova_url
                
            proc.wait()
            print(f"[TUNNEL-SYNC] Processo cloudflared encerrou com código {proc.returncode}. Reiniciando em 5 segundos...")
            time.sleep(5)
        except Exception as err:
            print(f"[TUNNEL-SYNC] Erro no loop do túnel: {err}. Reiniciando em 5 segundos...")
            time.sleep(5)

if __name__ == "__main__":
    monitorar_tunel()
