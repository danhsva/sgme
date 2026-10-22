#!/usr/bin/env python3
import argparse, os, shutil, sqlite3, time
DADOS = os.environ.get('SGME_DADOS', '/var/lib/sgme' if os.path.exists('/var/lib/sgme') else os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'dados')))
DB = os.path.join(DADOS, 'sistema.db')

def cols(c, table): return {r[1] for r in c.execute(f'PRAGMA table_info({table})')}
def migrar(db=DB, backup=True):
    if not os.path.exists(db): raise FileNotFoundError(db)
    if backup:
        dst = db + '.antes_os_instalacao_' + time.strftime('%Y%m%d_%H%M%S')
        src = sqlite3.connect(db); out = sqlite3.connect(dst); src.backup(out); out.close(); src.close()
    c = sqlite3.connect(db, timeout=30)
    try:
        c.execute('PRAGMA foreign_keys=OFF')
        if 'tipo_os' not in cols(c, 'ordens_servico'):
            c.executescript('''
BEGIN IMMEDIATE;
ALTER TABLE ordens_servico RENAME TO ordens_servico_antiga;
CREATE TABLE ordens_servico (
 id INTEGER PRIMARY KEY AUTOINCREMENT, equipamento_id INTEGER, solicitante_id INTEGER NOT NULL,
 fiscal_id INTEGER, executante_id INTEGER, descricao_falha TEXT NOT NULL, data_abertura INTEGER NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('aberta','aprovada','em_analise','aguardando_peca','em_execucao','concluida','cancelada')),
 prioridade TEXT DEFAULT 'media', data_conclusao INTEGER, arquivo_conclusao TEXT,
 tipo_os TEXT NOT NULL DEFAULT 'manutencao' CHECK(tipo_os IN ('manutencao','instalacao','substituicao')),
 contrato_id INTEGER,
 FOREIGN KEY(equipamento_id) REFERENCES equipamentos(id), FOREIGN KEY(solicitante_id) REFERENCES usuarios(id),
 FOREIGN KEY(fiscal_id) REFERENCES usuarios(id), FOREIGN KEY(executante_id) REFERENCES usuarios(id),
 FOREIGN KEY(contrato_id) REFERENCES contratos(id));
INSERT INTO ordens_servico(id,equipamento_id,solicitante_id,fiscal_id,executante_id,descricao_falha,data_abertura,status,prioridade,data_conclusao,arquivo_conclusao,tipo_os,contrato_id)
 SELECT o.id,o.equipamento_id,o.solicitante_id,o.fiscal_id,o.executante_id,o.descricao_falha,o.data_abertura,o.status,o.prioridade,o.data_conclusao,o.arquivo_conclusao,'manutencao',e.contrato_id
 FROM ordens_servico_antiga o LEFT JOIN equipamentos e ON e.id=o.equipamento_id;

-- O ALTER TABLE acima faz o SQLite redirecionar a FK de historico_os
-- para ordens_servico_antiga. Recriamos a tabela para restaurar a FK correta.
ALTER TABLE historico_os RENAME TO historico_os_antigo;
CREATE TABLE historico_os (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 os_id INTEGER NOT NULL,
 usuario_id INTEGER NOT NULL,
 data_registro INTEGER NOT NULL,
 acao TEXT NOT NULL,
 observacao TEXT,
 FOREIGN KEY(os_id) REFERENCES ordens_servico(id),
 FOREIGN KEY(usuario_id) REFERENCES usuarios(id));
INSERT INTO historico_os(id,os_id,usuario_id,data_registro,acao,observacao)
 SELECT id,os_id,usuario_id,data_registro,acao,observacao
 FROM historico_os_antigo;
DROP TABLE historico_os_antigo;
DROP TABLE ordens_servico_antiga;
COMMIT;''')
        c.executescript('''
CREATE TABLE IF NOT EXISTS os_instalacao (
 os_id INTEGER PRIMARY KEY, marca TEXT NOT NULL, tipo_equipamento TEXT NOT NULL, capacidade TEXT,
 comarca TEXT NOT NULL, predio TEXT NOT NULL, sala TEXT NOT NULL, tombo TEXT,
 foto_evaporadora TEXT, foto_condensadora TEXT, foto_tubulacao TEXT, foto_dreno TEXT,
 arquivo_os_assinada_original TEXT, equipamento_novo_id INTEGER,
 FOREIGN KEY(os_id) REFERENCES ordens_servico(id) ON DELETE CASCADE,
 FOREIGN KEY(equipamento_novo_id) REFERENCES equipamentos(id));
CREATE INDEX IF NOT EXISTS idx_os_contrato ON ordens_servico(contrato_id);
CREATE INDEX IF NOT EXISTS idx_os_tipo ON ordens_servico(tipo_os);
''')
        cols_inst = cols(c, 'os_instalacao') if 'os_instalacao' in {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")} else set()
        if 'foto_tubulacao' not in cols_inst:
            c.execute('ALTER TABLE os_instalacao ADD COLUMN foto_tubulacao TEXT;')
        if 'foto_dreno' not in cols_inst:
            c.execute('ALTER TABLE os_instalacao ADD COLUMN foto_dreno TEXT;')
        if 'arquivo_os_assinada_original' not in cols_inst:
            c.execute('ALTER TABLE os_instalacao ADD COLUMN arquivo_os_assinada_original TEXT;')
        c.commit(); c.execute('PRAGMA foreign_keys=ON')
        integridade = c.execute('PRAGMA integrity_check').fetchone()[0]
        if integridade != 'ok':
            raise RuntimeError(f'Falha no integrity_check: {integridade}')
        falhas_fk = c.execute('PRAGMA foreign_key_check').fetchall()
        if falhas_fk:
            raise RuntimeError(f'Falhas de chave estrangeira: {falhas_fk[:20]}')
    finally: c.close()
    return True
if __name__ == '__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--sem-backup', action='store_true'); a=ap.parse_args()
    migrar(backup=not a.sem_backup); print('Migração de O.S. de instalação aplicada com sucesso.')
