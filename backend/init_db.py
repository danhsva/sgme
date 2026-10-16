import os
import sys
import sqlite3
from werkzeug.security import generate_password_hash

DB_DIR = os.environ.get('SGME_DADOS', '/var/lib/sgme' if os.path.exists('/var/lib/sgme') else os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'dados')))
DB_PATH = os.path.join(DB_DIR, 'sistema.db')
UPLOADS_DIR = os.path.join(DB_DIR, 'uploads')

os.makedirs(DB_DIR, exist_ok=True)
os.makedirs(UPLOADS_DIR, exist_ok=True)

# PROTEÇÃO: este script APAGA o banco existente. Só roda sobre um banco existente com --force.
if os.path.exists(DB_PATH):
    if '--force' not in sys.argv:
        print('ERRO: ' + DB_PATH + ' já existe. Este script apaga todos os dados.')
        print('Se for isso mesmo que deseja: python init_db.py --force')
        sys.exit(1)
    os.remove(DB_PATH)

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Diretrizes de integridade e alta concorrência SQLite
cursor.execute('PRAGMA journal_mode=WAL;')
cursor.execute('PRAGMA foreign_keys=ON;')

# 1. Contratos
cursor.execute('''
CREATE TABLE contratos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero_contrato TEXT NOT NULL UNIQUE,
    nome_empresa TEXT NOT NULL,
    cnpj TEXT,
    ativo INTEGER DEFAULT 1
);
''')

# 2. Usuários
cursor.execute('''
CREATE TABLE usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    login TEXT NOT NULL UNIQUE,
    senha_hash TEXT NOT NULL,
    perfil TEXT NOT NULL CHECK(perfil IN ('administrador','fiscal','contratada','executante','solicitante')),
    primeiro_acesso INTEGER DEFAULT 1,
    ativo INTEGER DEFAULT 1
);
''')

# 3. Associação N:N (Múltiplos Contratos por Usuário)
cursor.execute('''
CREATE TABLE usuario_contratos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL,
    contrato_id INTEGER NOT NULL,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (contrato_id) REFERENCES contratos(id) ON DELETE CASCADE,
    UNIQUE(usuario_id, contrato_id)
);
''')
cursor.execute('CREATE INDEX idx_uc_usuario ON usuario_contratos(usuario_id);')
cursor.execute('CREATE INDEX idx_uc_contrato ON usuario_contratos(contrato_id);')

# 4. Equipamentos (1:N estrito com Contratos)
cursor.execute('''
CREATE TABLE equipamentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    comarca TEXT NOT NULL,
    predio TEXT NOT NULL,
    sala TEXT NOT NULL,
    tipo_equipamento TEXT NOT NULL,
    capacidade TEXT,
    marca TEXT,
    tombo TEXT DEFAULT 'S/T',
    contrato_id INTEGER,
    status_equipamento TEXT DEFAULT 'ATIVO',
    ativo INTEGER DEFAULT 1,
    FOREIGN KEY (contrato_id) REFERENCES contratos(id)
);
''')

# 5. Ordens de Serviço (Workflow Completo com Validação Fiscal)
cursor.execute('''
CREATE TABLE ordens_servico (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    equipamento_id INTEGER,
    solicitante_id INTEGER NOT NULL,
    fiscal_id INTEGER,
    executante_id INTEGER,
    descricao_falha TEXT NOT NULL,
    data_abertura INTEGER NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('aberta','aprovada','em_analise','aguardando_peca','em_execucao','concluida','cancelada')),
    prioridade TEXT DEFAULT 'media',
    data_conclusao INTEGER,
    arquivo_conclusao TEXT,
    tipo_os TEXT NOT NULL DEFAULT 'manutencao' CHECK(tipo_os IN ('manutencao','instalacao','substituicao')),
    contrato_id INTEGER,
    FOREIGN KEY (equipamento_id) REFERENCES equipamentos(id),
    FOREIGN KEY (solicitante_id) REFERENCES usuarios(id),
    FOREIGN KEY (fiscal_id) REFERENCES usuarios(id),
    FOREIGN KEY (executante_id) REFERENCES usuarios(id),
    FOREIGN KEY (contrato_id) REFERENCES contratos(id)
);
''')

# 5.1 Dados exclusivos da instalação/substituição
cursor.execute('''
CREATE TABLE os_instalacao (
    os_id INTEGER PRIMARY KEY, marca TEXT NOT NULL, tipo_equipamento TEXT NOT NULL, capacidade TEXT,
    comarca TEXT NOT NULL, predio TEXT NOT NULL, sala TEXT NOT NULL, tombo TEXT,
    foto_evaporadora TEXT, foto_condensadora TEXT, equipamento_novo_id INTEGER,
    FOREIGN KEY (os_id) REFERENCES ordens_servico(id) ON DELETE CASCADE,
    FOREIGN KEY (equipamento_novo_id) REFERENCES equipamentos(id)
);
''')
cursor.execute('CREATE INDEX idx_os_contrato ON ordens_servico(contrato_id);')
cursor.execute('CREATE INDEX idx_os_tipo ON ordens_servico(tipo_os);')

# 6. Histórico
cursor.execute('''
CREATE TABLE historico_os (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    os_id INTEGER NOT NULL,
    usuario_id INTEGER NOT NULL,
    data_registro INTEGER NOT NULL,
    acao TEXT NOT NULL,
    observacao TEXT,
    FOREIGN KEY (os_id) REFERENCES ordens_servico(id),
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
);
''')

# 7. Ciclos e Manutenções Preventivas (PMOC)
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
    status TEXT NOT NULL DEFAULT 'pendente' CHECK(status IN ('pendente','em_execucao','em_analise','concluida','cancelada')),
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

cursor.execute('''
CREATE TABLE IF NOT EXISTS pmoc_calendario_anual (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    equipamento_id INTEGER NOT NULL,
    contrato_id INTEGER NOT NULL,
    comarca TEXT NOT NULL,
    ano INTEGER NOT NULL,
    mes INTEGER NOT NULL,
    periodicidade TEXT NOT NULL CHECK(periodicidade IN ('M','T','S','A')),
    status TEXT NOT NULL DEFAULT 'planejado' CHECK(status IN ('planejado','gerado','concluido')),
    manutencao_id INTEGER,
    criado_em INTEGER NOT NULL,
    FOREIGN KEY (equipamento_id) REFERENCES equipamentos(id),
    FOREIGN KEY (contrato_id) REFERENCES contratos(id),
    FOREIGN KEY (manutencao_id) REFERENCES pmoc_manutencoes(id) ON DELETE SET NULL,
    UNIQUE(equipamento_id, ano, mes)
);
''')

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

# Criar Usuário Administrador Inicial do SGME
senha_admin_hash = generate_password_hash("admin")
cursor.execute('''
INSERT INTO usuarios (nome, login, senha_hash, perfil, primeiro_acesso, ativo)
VALUES ('ADMINISTRADOR SGME', 'admin', ?, 'administrador', 1, 1);
''', (senha_admin_hash,))

conn.commit()
conn.close()

print("==================================================")
print(" BANCO OFICIAL CRIADO COM SUCESSO!")
print(f" Local: {DB_PATH}")
print(" Credenciais Iniciais: login: admin | senha: admin (troca obrigatória no 1º acesso)")
print("==================================================")