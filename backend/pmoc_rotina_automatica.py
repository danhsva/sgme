#!/usr/bin/env python3
"""
SGME - Rotina Autônoma Diária de Geração do PMOC
Este script é executado diariamente (via cron / systemd timer) para:
  1. Garantir que as ordens do mês atual estejam geradas.
  2. Verificar se faltam 5 dias para o início do próximo mês. Se sim, gera as ordens do próximo mês.
"""
import sys
import os

# Adiciona o diretório do backend ao sys.path se necessário
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from pmoc_planejamento import verificar_e_executar_rotina_automatica

def main():
    print("[SGME-PMOC-CRON] Iniciando verificação automática do cronograma...")
    res = verificar_e_executar_rotina_automatica()
    print(f"[SGME-PMOC-CRON] Data: {res['data_execucao']}")
    print(f"[SGME-PMOC-CRON] Mês Atual: {res['mes_atual']} (Geradas agora: {res['gerado_mes_atual']})")
    print(f"[SGME-PMOC-CRON] Próximo Mês: {res['proximo_mes']} (Gatilho: {res['data_gatilho_proximo']}, Atingido: {res['gatilho_atingido']}, Geradas: {res['gerado_proximo_mes']})")
    for msg in res['mensagens']:
        print(f"  -> {msg}")
    print("[SGME-PMOC-CRON] Concluído com sucesso.")

if __name__ == '__main__':
    main()
