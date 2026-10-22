#!/usr/bin/env python3
"""
SGME - Migração Segura e Idempotente do Módulo PMOC (Manutenções Preventivas)
Cria as tabelas e índices de PMOC preservando 100% dos dados existentes.
"""
import os
import sys
import sqlite3

def obter_caminho_db():
    if 'SGME_DADOS' in os.environ:
        return os.path.join(os.environ['SGME_DADOS'], 'sistema.db')
    if os.path.exists('/var/lib/sgme/sistema.db'):
        return '/var/lib/sgme/sistema.db'
    local = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'dados', 'sistema.db'))
    if os.path.exists(local):
        return local
    return '/var/lib/sgme/sistema.db'

def migrar(db_path=None):
    if not db_path:
        db_path = obter_caminho_db()
    
    print(f"[PMOC-MIGRACAO] Conectando ao banco em: {db_path}")
    if not os.path.exists(db_path):
        print(f"[PMOC-MIGRACAO] AVISO: Banco {db_path} ainda não existe. Criando diretório se necessário.")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA foreign_keys=ON;")

    # 1. Ciclos Periódicos de Preventivas (Mês/Ano/Periodicidade por Contrato)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS pmoc_ciclos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        contrato_id INTEGER NOT NULL,
        ano INTEGER NOT NULL,
        mes INTEGER NOT NULL,
        periodicidade TEXT NOT NULL CHECK(periodicidade IN ('M','T','S','A')),
        descricao TEXT,
        criado_em INTEGER NOT NULL,
        criado_por INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'em_andamento' CHECK(status IN ('em_andamento','concluido','cancelado')),
        FOREIGN KEY (contrato_id) REFERENCES contratos(id),
        FOREIGN KEY (criado_por) REFERENCES usuarios(id),
        UNIQUE(contrato_id, ano, mes, periodicidade)
    );
    ''')

    # 2. Manutenções Preventivas Individuais (Por Equipamento e Ciclo/Mês)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS pmoc_manutencoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ciclo_id INTEGER,
        contrato_id INTEGER NOT NULL,
        equipamento_id INTEGER NOT NULL,
        periodicidade TEXT NOT NULL CHECK(periodicidade IN ('M','T','S','A')),
        mes_competencia INTEGER NOT NULL,
        ano_competencia INTEGER NOT NULL,
        data_geracao INTEGER NOT NULL,
        data_execucao INTEGER,
        data_homologacao INTEGER,
        executante_id INTEGER,
        fiscal_id INTEGER,
        status TEXT NOT NULL DEFAULT 'pendente' CHECK(status IN ('pendente','em_execucao','em_analise','concluida','reprovada','cancelada')),
        tensao_medida TEXT,
        corrente_medida TEXT,
        temperatura_insuflamento TEXT,
        temperatura_retorno TEXT,
        arquivo_folha_assinada TEXT,
        observacoes_execucao TEXT,
        justificativa_fiscal TEXT,
        FOREIGN KEY (ciclo_id) REFERENCES pmoc_ciclos(id) ON DELETE CASCADE,
        FOREIGN KEY (contrato_id) REFERENCES contratos(id),
        FOREIGN KEY (equipamento_id) REFERENCES equipamentos(id),
        FOREIGN KEY (executante_id) REFERENCES usuarios(id),
        FOREIGN KEY (fiscal_id) REFERENCES usuarios(id)
    );
    ''')

    # 3. Checklist Detalhado das Atividades do PMOC (Item a Item)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS pmoc_checklist_respostas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        manutencao_id INTEGER NOT NULL,
        item_codigo TEXT NOT NULL,
        item_descricao TEXT NOT NULL,
        grupo TEXT NOT NULL,
        status_item TEXT NOT NULL CHECK(status_item IN ('conforme','corrigido','nao_conforme','nao_se_aplica')),
        observacao TEXT,
        FOREIGN KEY (manutencao_id) REFERENCES pmoc_manutencoes(id) ON DELETE CASCADE,
        UNIQUE(manutencao_id, item_codigo)
    );
    ''')

    # 4. Trilha de Auditoria e Histórico da Manutenção Preventiva
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS historico_pmoc (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        manutencao_id INTEGER NOT NULL,
        usuario_id INTEGER NOT NULL,
        data_registro INTEGER NOT NULL,
        acao TEXT NOT NULL,
        observacao TEXT,
        FOREIGN KEY (manutencao_id) REFERENCES pmoc_manutencoes(id) ON DELETE CASCADE,
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
    );
    ''')

    # 5. Calendário Anual e Rodízio Balanceado do PMOC
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS pmoc_calendario_anual (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        equipamento_id INTEGER NOT NULL,
        contrato_id INTEGER NOT NULL,
        comarca TEXT NOT NULL,
        ano INTEGER NOT NULL,
        mes INTEGER NOT NULL,
        periodicidade TEXT NOT NULL CHECK(periodicidade IN ('M','T','S','A')),
        status TEXT NOT NULL DEFAULT 'planejado' CHECK(status IN ('planejado','gerado','concluido','reprovado')),
        manutencao_id INTEGER,
        criado_em INTEGER NOT NULL,
        FOREIGN KEY (equipamento_id) REFERENCES equipamentos(id),
        FOREIGN KEY (contrato_id) REFERENCES contratos(id),
        FOREIGN KEY (manutencao_id) REFERENCES pmoc_manutencoes(id) ON DELETE SET NULL,
        UNIQUE(equipamento_id, ano, mes)
    );
    ''')

    # Índices de performance
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pmoc_ciclo ON pmoc_manutencoes(ciclo_id);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pmoc_contrato ON pmoc_manutencoes(contrato_id);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pmoc_equip ON pmoc_manutencoes(equipamento_id);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pmoc_status ON pmoc_manutencoes(status);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pmoc_comp ON pmoc_manutencoes(ano_competencia, mes_competencia);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pmoc_resp_m ON pmoc_checklist_respostas(manutencao_id);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pmoc_hist_m ON historico_pmoc(manutencao_id);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pmoc_cal_eq_ano ON pmoc_calendario_anual(equipamento_id, ano);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pmoc_cal_comarca ON pmoc_calendario_anual(comarca, ano, mes);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pmoc_cal_status ON pmoc_calendario_anual(status);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_pmoc_cal_manut ON pmoc_calendario_anual(manutencao_id);')

    # 6. Coluna data_instalacao e ajuste de cadência preventiva para recém-instalados
    cols_eq = {r[1] for r in cursor.execute("PRAGMA table_info(equipamentos)").fetchall()}
    if 'data_instalacao' not in cols_eq:
        print("[PMOC-MIGRACAO] Adicionando coluna data_instalacao na tabela equipamentos...")
        cursor.execute("ALTER TABLE equipamentos ADD COLUMN data_instalacao INTEGER;")

    cursor.execute("""
        UPDATE equipamentos 
        SET data_instalacao = (
            SELECT COALESCE(os.data_conclusao, os.data_abertura)
            FROM os_instalacao oi 
            JOIN ordens_servico os ON oi.os_id = os.id 
            WHERE oi.equipamento_novo_id = equipamentos.id
            ORDER BY os.id DESC LIMIT 1
        )
        WHERE data_instalacao IS NULL AND id IN (
            SELECT equipamento_novo_id FROM os_instalacao WHERE equipamento_novo_id IS NOT NULL
        );
    """)
    conn.commit()

    try:
        from pmoc_planejamento import sincronizar_calendario_equipamento
        eqs_instalados = cursor.execute("""
            SELECT id FROM equipamentos WHERE ativo = 1 AND data_instalacao IS NOT NULL
        """).fetchall()
        for eq_row in eqs_instalados:
            sincronizar_calendario_equipamento(eq_row[0], conn)
        print(f"[PMOC-MIGRACAO] Planejamento de {len(eqs_instalados)} equipamentos atualizado para regra de recém-instalado.")
    except Exception as e:
        print(f"[PMOC-MIGRACAO] Aviso ao sincronizar calendários: {e}")

    conn.commit()
    conn.close()
    print("[PMOC-MIGRACAO] Tabelas e índices criados com sucesso!")

if __name__ == '__main__':
    migrar()
