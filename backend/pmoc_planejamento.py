# -*- coding: utf-8 -*-
"""
SGME - Módulo de Planejamento, Janela Móvel de 24 Meses, Automação Individual do PMOC
e Relatório de Fechamento de Ciclo por Comarca.
"""
import os
import time
import datetime
import random
import sqlite3
from pmoc_catalogo import obter_checklist_padrao


def obter_caminho_db():
    if 'SGME_DADOS' in os.environ:
        return os.path.join(os.environ['SGME_DADOS'], 'sistema.db')
    if os.path.exists('/var/lib/sgme/sistema.db'):
        return '/var/lib/sgme/sistema.db'
    local = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'dados', 'sistema.db'))
    if os.path.exists(local):
        return local
    return '/var/lib/sgme/sistema.db'


def _obter_conexao(db_conn=None):
    if db_conn is not None:
        db_conn.row_factory = sqlite3.Row
        return db_conn, False
    conn = sqlite3.connect(obter_caminho_db())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn, True


def calcular_data_gatilho(ano: int, mes: int) -> datetime.date:
    """Calcula a data exata (5 dias antes do 1º dia do mês alvo)."""
    primeiro_dia = datetime.date(ano, mes, 1)
    return primeiro_dia - datetime.timedelta(days=5)


def obter_proximo_mes(ano: int, mes: int) -> tuple:
    """Retorna (ano, mes) do mês seguinte."""
    if mes == 12:
        return ano + 1, 1
    return ano, mes + 1


def rotulo_periodicidade(p: str) -> str:
    mapa = {'M': 'MENSAL', 'T': 'TRIMESTRAL', 'S': 'SEMESTRAL', 'A': 'ANUAL'}
    return mapa.get((p or '').upper(), 'MENSAL')


def obter_data_instalacao_equipamento(equipamento_id: int, cursor) -> tuple:
    """
    Retorna (ano_inst, mes_inst) do equipamento ou None se não identificado.
    """
    try:
        cols_eq = {r[1] for r in cursor.execute("PRAGMA table_info(equipamentos)").fetchall()}
        if 'data_instalacao' in cols_eq:
            r = cursor.execute("SELECT data_instalacao FROM equipamentos WHERE id = ?", (equipamento_id,)).fetchone()
            if r and r[0]:
                ts = r[0]
                if ts > 100_000_000_000:
                    ts = ts / 1000.0
                dt = datetime.date.fromtimestamp(ts)
                return (dt.year, dt.month)

        r_os = cursor.execute("""
            SELECT os.data_conclusao, os.data_abertura 
            FROM os_instalacao oi 
            JOIN ordens_servico os ON oi.os_id = os.id 
            WHERE oi.equipamento_novo_id = ? 
            ORDER BY os.id DESC LIMIT 1
        """, (equipamento_id,)).fetchone()
        if r_os:
            ts = r_os[0] or r_os[1]
            if ts:
                if ts > 100_000_000_000:
                    ts = ts / 1000.0
                dt = datetime.date.fromtimestamp(ts)
                return (dt.year, dt.month)
    except Exception as e:
        print(f"[PMOC-PLANEJAMENTO] Erro ao obter data de instalação: {e}")
    return None


def calcular_periodicidade_mes(ano: int, mes: int, data_inst: tuple = None, m0: int = 0) -> str:
    """
    Calcula a periodicidade (M, T, S, A) para um determinado mês/ano.
    
    Regra TJCE/SGME para Equipamento Novo/Recém-Instalado:
      No mês em que o equipamento for instalado (e anteriores), NÃO deve inseri-lo
      no cronograma de manutenções preventivas (retorna None).
      O cronograma de preventivas inicia SOMENTE no mês seguinte à instalação (Delta >= 1).
      As próximas manutenções preventivas são obrigatoriamente MENSAIS ('M'), pelo menos as 2 próximas (Delta = 1 e Delta = 2).
      
      Evolução temporal (Delta = (ano - ano_inst)*12 + (mes - mes_inst)):
        Delta <= 0 -> None (Sem preventiva no mês da instalação nem anteriores)
        Delta = 1  -> M (1ª preventiva subsequente: Mensal)
        Delta = 2  -> M (2ª preventiva subsequente: Mensal)
        Delta = 3  -> T (Trimestral - 3 meses de uso)
        Delta = 4  -> M
        Delta = 5  -> M
        Delta = 6  -> S (Semestral - 6 meses de uso)
        Delta = 7  -> M
        Delta = 8  -> M
        Delta = 9  -> T (Trimestral - 9 meses de uso)
        Delta = 10 -> M
        Delta = 11 -> M
        Delta = 12 -> A (Anual - 1 ano completo de operação)
        Delta > 12 -> Repete o ciclo regular de 12 meses
    """
    if data_inst:
        ano_inst, mes_inst = data_inst
        delta = (ano - ano_inst) * 12 + (mes - mes_inst)
        if delta <= 0:
            return None
        k = delta % 12
        if k in (3, 9):
            return 'T'
        elif k == 6:
            return 'S'
        elif k == 0:
            return 'A'
        else:
            return 'M'

    m_idx = mes - 1
    if m_idx == (m0 % 12):
        return 'A'
    elif m_idx == ((m0 + 6) % 12):
        return 'S'
    elif m_idx in (((m0 + 3) % 12), ((m0 + 9) % 12)):
        return 'T'
    else:
        return 'M'


def gerar_calendario_anual(ano: int, db_conn=None, forcar: bool = False) -> dict:
    """
    Gera o calendário de 12 meses para todos os equipamentos ativos no ano especificado.
    Cada equipamento cumpre no ano: 1x Anual, 1x Semestral, 2x Trimestral, 8x Mensal.
    """
    conn, deve_fechar = _obter_conexao(db_conn)
    try:
        cursor = conn.cursor()

        if not forcar:
            qtd_existente = cursor.execute(
                "SELECT COUNT(*) FROM pmoc_calendario_anual WHERE ano = ?", (ano,)
            ).fetchone()[0]
            if qtd_existente > 0:
                return {"status": "ja_existente", "ano": ano, "total_planejado": qtd_existente}

        if forcar:
            cursor.execute(
                "DELETE FROM pmoc_calendario_anual WHERE ano = ? AND (status = 'planejado' OR manutencao_id IS NULL)",
                (ano,)
            )

        equipamentos = cursor.execute("""
            SELECT e.id, e.contrato_id, e.comarca
            FROM equipamentos e
            WHERE e.ativo = 1
            ORDER BY e.comarca, e.id
        """).fetchall()

        if not equipamentos:
            return {"status": "sem_equipamentos", "ano": ano, "total_planejado": 0}

        por_comarca = {}
        for eq in equipamentos:
            com = (eq['comarca'] or 'OUTROS').strip().upper()
            por_comarca.setdefault(com, []).append(eq)

        agora = int(time.time())
        inseridos = 0

        for comarca, lista_eq in por_comarca.items():
            rnd = random.Random(f"{comarca}_{ano}")
            lista_embaralhada = list(lista_eq)
            rnd.shuffle(lista_embaralhada)

            for idx, eq in enumerate(lista_embaralhada):
                data_inst = obter_data_instalacao_equipamento(eq['id'], cursor)
                m0 = idx % 12
                for mes in range(1, 13):
                    periodicidade = calcular_periodicidade_mes(ano, mes, data_inst, m0)
                    if not periodicidade:
                        cursor.execute("""
                            DELETE FROM pmoc_calendario_anual 
                            WHERE equipamento_id = ? AND ano = ? AND mes = ? AND status = 'planejado' AND manutencao_id IS NULL
                        """, (eq['id'], ano, mes))
                        continue

                    cursor.execute("""
                        INSERT INTO pmoc_calendario_anual 
                        (equipamento_id, contrato_id, comarca, ano, mes, periodicidade, status, criado_em)
                        VALUES (?, ?, ?, ?, ?, ?, 'planejado', ?)
                        ON CONFLICT(equipamento_id, ano, mes) DO UPDATE SET
                            periodicidade = excluded.periodicidade
                            WHERE status = 'planejado' AND manutencao_id IS NULL
                    """, (eq['id'], eq['contrato_id'], comarca, ano, mes, periodicidade, agora))
                    inseridos += 1

        conn.commit()
        return {"status": "sucesso", "ano": ano, "total_planejado": inseridos}
    finally:
        if deve_fechar:
            conn.close()


def gerar_ordens_mes_automatico(ano: int, mes: int, db_conn=None, criado_por: int = 1) -> dict:
    """
    Gera as ordens de manutenção preventiva individuais (1 O.S. e 1 documento próprio
    para cada equipamento ativo) para o mês/ano especificado.
    """
    conn, deve_fechar = _obter_conexao(db_conn)
    try:
        cursor = conn.cursor()

        gerar_calendario_anual(ano, conn, forcar=False)

        itens_planejados = cursor.execute("""
            SELECT c.id AS cal_id, c.equipamento_id, c.contrato_id, c.comarca, c.periodicidade,
                   e.tipo_equipamento, ct.numero_contrato
            FROM pmoc_calendario_anual c
            JOIN equipamentos e ON e.id = c.equipamento_id
            JOIN contratos ct ON ct.id = c.contrato_id
            WHERE c.ano = ? AND c.mes = ? AND e.ativo = 1 AND (c.status = 'planejado' OR c.manutencao_id IS NULL)
        """, (ano, mes)).fetchall()

        if not itens_planejados:
            return {"status": "nada_a_gerar", "ano": ano, "mes": mes, "geradas": 0}

        ciclos_map = {}
        agora = int(time.time() * 1000)
        ordens_geradas = 0

        for item in itens_planejados:
            contrato_id = item['contrato_id']
            per = item['periodicidade']
            comarca = (item['comarca'] or 'OUTROS').strip().upper()
            chave_ciclo = (contrato_id, per)

            if chave_ciclo not in ciclos_map:
                ciclo_row = cursor.execute("""
                    SELECT id FROM pmoc_ciclos 
                    WHERE contrato_id = ? AND ano = ? AND mes = ? AND periodicidade = ?
                """, (contrato_id, ano, mes, per)).fetchone()

                if ciclo_row:
                    ciclos_map[chave_ciclo] = ciclo_row['id']
                else:
                    desc = f"PMOC {rotulo_periodicidade(per)} - {mes:02d}/{ano} - Contrato {item['numero_contrato']}"
                    cursor.execute("""
                        INSERT INTO pmoc_ciclos (contrato_id, ano, mes, periodicidade, descricao, criado_em, criado_por, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 'em_andamento')
                    """, (contrato_id, ano, mes, per, desc, agora, criado_por))
                    ciclos_map[chave_ciclo] = cursor.lastrowid

            ciclo_id = ciclos_map[chave_ciclo]

            # 1. Cria a Ordem de Serviço Preventiva Individual do Equipamento
            cursor.execute("""
                INSERT INTO pmoc_manutencoes (
                    ciclo_id, contrato_id, comarca, equipamento_id, periodicidade,
                    mes_competencia, ano_competencia, data_geracao, status, total_equipamentos
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pendente', 1)
            """, (ciclo_id, contrato_id, comarca, item['equipamento_id'], per, mes, ano, agora))
            manut_id = cursor.lastrowid

            # 2. Preenche o checklist técnico oficial padrão do Anexo 2 TJCE
            itens_checklist = obter_checklist_padrao(item['tipo_equipamento'], per)
            for chk in itens_checklist:
                cursor.execute("""
                    INSERT OR IGNORE INTO pmoc_checklist_respostas (
                        manutencao_id, item_codigo, item_descricao, grupo, status_item
                    ) VALUES (?, ?, ?, ?, 'conforme')
                """, (manut_id, chk['codigo'], chk['descricao'], chk['grupo']))

            # 3. Registra na trilha de auditoria
            cursor.execute("""
                INSERT INTO historico_pmoc (manutencao_id, usuario_id, data_registro, acao, observacao)
                VALUES (?, ?, ?, 'CRIACAO_AUTOMATICA', ?)
            """, (manut_id, criado_por, agora, f"Ordem PMOC Individual ({per}) gerada pelo cronograma ({mes:02d}/{ano})"))

            # 4. Atualiza o calendário anual apontando para a OS individual criada
            cursor.execute("""
                UPDATE pmoc_calendario_anual
                SET status = 'gerado', manutencao_id = ?
                WHERE id = ?
            """, (manut_id, item['cal_id']))

            ordens_geradas += 1

        conn.commit()
        return {"status": "sucesso", "ano": ano, "mes": mes, "geradas": ordens_geradas}
    finally:
        if deve_fechar:
            conn.close()


def verificar_e_executar_rotina_automatica(db_conn=None, hoje: datetime.date = None) -> dict:
    if hoje is None:
        hoje = datetime.date.today()

    ano_atual = hoje.year
    mes_atual = hoje.month

    conn, deve_fechar = _obter_conexao(db_conn)
    resultados = {
        "data_verificacao": str(hoje),
        "calendarios_verificados": [],
        "mes_atual": None,
        "proximo_mes": None,
        "mensagens": []
    }

    try:
        for a in (ano_atual - 1, ano_atual, ano_atual + 1):
            res_cal = gerar_calendario_anual(a, conn, forcar=False)
            resultados["calendarios_verificados"].append(res_cal)

        res_atual = gerar_ordens_mes_automatico(ano_atual, mes_atual, conn)
        resultados["mes_atual"] = res_atual
        if res_atual.get("geradas", 0) > 0:
            resultados["mensagens"].append(
                f"Geradas {res_atual['geradas']} ordens individuais referentes ao mês corrente ({mes_atual:02d}/{ano_atual})."
            )

        prox_ano, prox_mes = obter_proximo_mes(ano_atual, mes_atual)
        data_gatilho = calcular_data_gatilho(prox_ano, prox_mes)

        if hoje >= data_gatilho:
            res_prox = gerar_ordens_mes_automatico(prox_ano, prox_mes, conn)
            resultados["proximo_mes"] = res_prox
            if res_prox.get("geradas", 0) > 0:
                resultados["mensagens"].append(
                    f"Gatilho de 5 dias atingido ({data_gatilho}): geradas {res_prox['geradas']} ordens para {prox_mes:02d}/{prox_ano}."
                )
        else:
            dias_restantes = (data_gatilho - hoje).days
            resultados["proximo_mes"] = {
                "status": "aguardando_gatilho",
                "ano": prox_ano,
                "mes": prox_mes,
                "data_gatilho": str(data_gatilho),
                "dias_restantes": dias_restantes
            }
            resultados["mensagens"].append(
                f"Próximo ciclo ({prox_mes:02d}/{prox_ano}) programado para abrir automaticamente em {data_gatilho.strftime('%d/%m/%Y')} (faltam {dias_restantes} dias)."
            )

        return resultados
    finally:
        if deve_fechar:
            conn.close()


def obter_plano_preventiva_janela_movel(comarca: str = None, equipamento_id: int = None, db_conn=None) -> dict:
    """
    Retorna a apresentação oficial do plano de manutenção preventiva com base em uma janela
    móvel de 24 meses (12 anteriores já executados + mês atual + 12 subsequentes a executar).
    """
    hoje = datetime.date.today()
    ano_atual = hoje.year
    mes_atual = hoje.month

    meses_janela = []
    for offset in range(-12, 13):
        total_meses = (ano_atual * 12) + (mes_atual - 1) + offset
        a = total_meses // 12
        m = (total_meses % 12) + 1

        if offset < 0:
            tipo = "passado"
        elif offset == 0:
            tipo = "atual"
        else:
            tipo = "futuro"

        meses_janela.append({
            "ano": a,
            "mes": m,
            "chave": f"{a}-{m:02d}",
            "rotulo": f"{m:02d}/{str(a)[2:]}",
            "rotulo_completo": f"{m:02d}/{a}",
            "tipo": tipo,
            "offset": offset
        })

    conn, deve_fechar = _obter_conexao(db_conn)
    try:
        cursor = conn.cursor()

        anos_envolvidos = sorted(list(set(item["ano"] for item in meses_janela)))
        for a in anos_envolvidos:
            gerar_calendario_anual(a, conn, forcar=False)

        where_eq = ["e.ativo = 1"]
        params_eq = []
        if comarca:
            where_eq.append("UPPER(e.comarca) = ?")
            params_eq.append(comarca.strip().upper())
        if equipamento_id:
            where_eq.append("e.id = ?")
            params_eq.append(equipamento_id)

        sql_eq = f"""
            SELECT e.id, e.tombo, e.marca, e.capacidade, e.tipo_equipamento, e.comarca, e.predio, e.sala,
                   ct.numero_contrato, ct.nome_empresa
            FROM equipamentos e
            LEFT JOIN contratos ct ON ct.id = e.contrato_id
            WHERE {' AND '.join(where_eq)}
            ORDER BY e.comarca, e.predio, e.sala, e.tombo
        """
        equipamentos_rows = cursor.execute(sql_eq, params_eq).fetchall()

        condicoes_meses = " OR ".join(["(c.ano = ? AND c.mes = ?)" for _ in meses_janela])
        params_cal = []
        for item in meses_janela:
            params_cal.extend([item["ano"], item["mes"]])

        where_cal = [f"({condicoes_meses})"]
        if comarca:
            where_cal.append("UPPER(c.comarca) = ?")
            params_cal.append(comarca.strip().upper())
        if equipamento_id:
            where_cal.append("c.equipamento_id = ?")
            params_cal.append(equipamento_id)

        sql_cal = f"""
            SELECT c.id AS cal_id, c.equipamento_id, c.comarca, c.ano, c.mes, c.periodicidade,
                   c.status AS cal_status, c.manutencao_id,
                   m.status AS manut_status, u.nome AS executante_nome
            FROM pmoc_calendario_anual c
            LEFT JOIN pmoc_manutencoes m ON m.id = c.manutencao_id
            LEFT JOIN usuarios u ON u.id = m.executante_id
            WHERE {' AND '.join(where_cal)}
        """
        cal_rows = cursor.execute(sql_cal, params_cal).fetchall()

        cal_map = {}
        resumo_comarcas = {}

        for r in cal_rows:
            eq_id = r['equipamento_id']
            chave = f"{r['ano']}-{r['mes']:02d}"
            st_efetivo = 'concluido' if r['manut_status'] == 'concluida' else ('reprovado' if r['manut_status'] == 'reprovada' else r['cal_status'])
            cal_map[(eq_id, chave)] = {
                "cal_id": r['cal_id'],
                "periodicidade": r['periodicidade'],
                "status": st_efetivo,
                "manutencao_id": r['manutencao_id'],
                "manut_status": r['manut_status'],
                "executante_nome": r['executante_nome']
            }

            com = r['comarca'] or 'OUTROS'
            resumo_comarcas.setdefault(com, {})
            resumo_comarcas[com].setdefault(chave, {'M': 0, 'T': 0, 'S': 0, 'A': 0, 'total': 0})
            resumo_comarcas[com][chave][r['periodicidade']] += 1
            resumo_comarcas[com][chave]['total'] += 1

        equipamentos_lista = []
        for eq in equipamentos_rows:
            eq_id = eq['id']
            eq_meses = {}
            for item in meses_janela:
                chave = item["chave"]
                if (eq_id, chave) in cal_map:
                    eq_meses[chave] = cal_map[(eq_id, chave)]
                else:
                    eq_meses[chave] = None

            equipamentos_lista.append({
                "equipamento_id": eq_id,
                "tombo": eq['tombo'] or 'S/T',
                "marca": eq['marca'] or '',
                "capacidade": eq['capacidade'] or '',
                "tipo_equipamento": eq['tipo_equipamento'] or '',
                "comarca": eq['comarca'],
                "predio": eq['predio'],
                "sala": eq['sala'],
                "numero_contrato": eq['numero_contrato'],
                "empresa": eq['nome_empresa'],
                "meses": eq_meses
            })

        prox_ano, prox_mes = obter_proximo_mes(ano_atual, mes_atual)
        data_gatilho_prox = calcular_data_gatilho(prox_ano, prox_mes)

        return {
            "modo": "janela_movel",
            "janela": meses_janela,
            "mes_atual": f"{mes_atual:02d}/{ano_atual}",
            "total_equipamentos": len(equipamentos_lista),
            "equipamentos": equipamentos_lista,
            "resumo_comarcas": resumo_comarcas,
            "gatilho_proximo": {
                "proximo_mes": f"{prox_mes:02d}/{prox_ano}",
                "data_gatilho": str(data_gatilho_prox),
                "dias_restantes": max(0, (data_gatilho_prox - hoje).days),
                "gatilho_atingido": hoje >= data_gatilho_prox
            }
        }
    finally:
        if deve_fechar:
            conn.close()


def obter_calendario_anual(ano: int, comarca: str = None, equipamento_id: int = None, db_conn=None) -> dict:
    return obter_plano_preventiva_janela_movel(comarca=comarca, equipamento_id=equipamento_id, db_conn=db_conn)


def obter_dados_relatorio_ciclo_pmoc(ano: int, mes: int, contrato_id: int = None, contratos_permitidos: list = None, db_conn=None) -> dict:
    """
    Gera a estrutura de dados do Relatório de Fechamento de Ciclo Mensal:
      - Lista todos os equipamentos do contrato, separados por comarca.
      - Aponta por qual manutenção o equipamento passou (M, T, S, A) caso concluída.
      - Caso reprovada pelo fiscal (para avaliação de pagamento), aponta "REPROVADO".
      - Se não realizou a preventiva, aponta "Não Realizada".
    """
    conn, deve_fechar = _obter_conexao(db_conn)
    try:
        cursor = conn.cursor()

        where_eq = ["e.ativo = 1"]
        params = [ano, mes, ano, mes]

        if contrato_id:
            where_eq.append("e.contrato_id = ?")
            params.append(int(contrato_id))
        elif contratos_permitidos is not None:
            if not contratos_permitidos:
                return {
                    "ano": ano, "mes": mes, "contrato_descricao": "Nenhum contrato vinculado",
                    "resumo": {"total_equipamentos": 0, "total_realizadas": 0, "reprovadas": 0, "nao_realizadas": 0, "M": 0, "T": 0, "S": 0, "A": 0, "percentual_execucao": 0},
                    "comarcas": []
                }
            placeholders = ",".join(["?"] * len(contratos_permitidos))
            where_eq.append(f"e.contrato_id IN ({placeholders})")
            params.extend(contratos_permitidos)

        sql = f"""
            SELECT e.id AS equipamento_id, e.tombo, e.comarca, e.predio, e.sala,
                   e.tipo_equipamento, e.marca, e.capacidade, e.contrato_id,
                   ct.numero_contrato, ct.nome_empresa,
                   c.periodicidade AS cal_periodicidade, c.status AS cal_status,
                   m.id AS pmoc_id, m.periodicidade AS manut_periodicidade,
                   m.status AS manut_status, m.data_execucao,
                   m.tensao_medida, m.corrente_medida,
                   m.justificativa_fiscal, m.arquivo_folha_assinada,
                   u.nome AS nome_executante
            FROM equipamentos e
            LEFT JOIN contratos ct ON ct.id = e.contrato_id
            LEFT JOIN pmoc_calendario_anual c ON c.equipamento_id = e.id AND c.ano = ? AND c.mes = ?
            LEFT JOIN pmoc_manutencoes m ON m.equipamento_id = e.id AND m.ano_competencia = ? AND m.mes_competencia = ?
            LEFT JOIN usuarios u ON u.id = m.executante_id
            WHERE {' AND '.join(where_eq)}
            ORDER BY e.comarca ASC, e.predio ASC, e.sala ASC, e.tombo ASC
        """
        rows = cursor.execute(sql, params).fetchall()

        contrato_desc = "TODOS OS CONTRATOS"
        if contrato_id:
            ct_row = cursor.execute("SELECT numero_contrato, nome_empresa FROM contratos WHERE id = ?", (contrato_id,)).fetchone()
            if ct_row:
                contrato_desc = f"{ct_row['numero_contrato']} - {ct_row['nome_empresa']}"

        por_comarca = {}
        resumo = {
            "total_equipamentos": 0,
            "total_realizadas": 0,
            "reprovadas": 0,
            "nao_realizadas": 0,
            "M": 0, "T": 0, "S": 0, "A": 0,
            "percentual_execucao": 0.0
        }

        nomes_per = {'M': 'M (Mensal)', 'T': 'T (Trimestral)', 'S': 'S (Semestral)', 'A': 'A (Anual)'}

        for r in rows:
            com = (r['comarca'] or 'OUTROS').strip().upper()
            por_comarca.setdefault(com, [])

            st_manut = (r['manut_status'] or '').lower()
            per = (r['manut_periodicidade'] or r['cal_periodicidade'] or 'M').upper()
            realizada = (st_manut == 'concluida')
            reprovada = (st_manut == 'reprovada')

            resumo["total_equipamentos"] += 1
            if realizada:
                resumo["total_realizadas"] += 1
                if per in ('M', 'T', 'S', 'A'):
                    resumo[per] += 1
                apontamento_curto = per
                apontamento_completo = nomes_per.get(per, per)
            elif reprovada:
                resumo["reprovadas"] += 1
                apontamento_curto = "REPROVADO"
                apontamento_completo = "REPROVADO"
            else:
                resumo["nao_realizadas"] += 1
                apontamento_curto = "Não Realizada"
                apontamento_completo = "Não Realizada"

            dt_exec_fmt = '-'
            if r['data_execucao']:
                try:
                    dt_exec_fmt = datetime.datetime.fromtimestamp(r['data_execucao'] / 1000).strftime('%d/%m/%Y')
                except Exception:
                    dt_exec_fmt = '-'

            num_pmoc = f"{int(r['pmoc_id']):04d}.{int(mes):02d}.{int(ano)}" if r['pmoc_id'] else '-'

            por_comarca[com].append({
                "equipamento_id": r['equipamento_id'],
                "tombo": r['tombo'] or 'S/T',
                "comarca": com,
                "predio": r['predio'] or '-',
                "sala": r['sala'] or '-',
                "tipo_equipamento": r['tipo_equipamento'] or '-',
                "marca": r['marca'] or '-',
                "capacidade": r['capacidade'] or '',
                "contrato_id": r['contrato_id'],
                "numero_contrato": r['numero_contrato'] or '-',
                "nome_empresa": r['nome_empresa'] or '-',
                "pmoc_id": r['pmoc_id'],
                "num_pmoc": num_pmoc,
                "periodicidade_planejada": per,
                "realizada": realizada,
                "reprovada": reprovada,
                "manutencao_apontada": apontamento_curto,
                "manutencao_apontada_completa": apontamento_completo,
                "justificativa_fiscal": r['justificativa_fiscal'] or '',
                "data_execucao_fmt": dt_exec_fmt,
                "nome_executante": r['nome_executante'] or '-',
                "tensao_medida": r['tensao_medida'] or '-',
                "corrente_medida": r['corrente_medida'] or '-'
            })

        if resumo["total_equipamentos"] > 0:
            resumo["percentual_execucao"] = round((resumo["total_realizadas"] / resumo["total_equipamentos"]) * 100, 1)

        comarcas_lista = []
        for com in sorted(por_comarca.keys()):
            eqs = por_comarca[com]
            qtd_realizadas = sum(1 for item in eqs if item["realizada"])
            qtd_reprovadas = sum(1 for item in eqs if item.get("reprovada"))
            qtd_nao = len(eqs) - qtd_realizadas - qtd_reprovadas
            comarcas_lista.append({
                "comarca": com,
                "total": len(eqs),
                "realizadas": qtd_realizadas,
                "reprovadas": qtd_reprovadas,
                "nao_realizadas": qtd_nao,
                "equipamentos": eqs
            })

        return {
            "ano": ano,
            "mes": mes,
            "contrato_id": contrato_id,
            "contrato_descricao": contrato_desc,
            "resumo": resumo,
            "comarcas": comarcas_lista
        }
    finally:
        if deve_fechar:
            conn.close()


def sincronizar_calendario_equipamento(equipamento_id: int, db_conn=None, ano_instalacao: int = None, mes_instalacao: int = None):
    """
    Garante que um equipamento ativo (novo ou reativado) possua entradas planejadas
    no calendário anual para os meses futuros da janela móvel.
    Para equipamentos recém-instalados, NÃO insere preventiva no mês da instalação
    (somente a partir do mês seguinte), garantindo que as próximas manutenções sejam
    obrigatoriamente MENSAIS ('M'), pelo menos as 2 próximas.
    """
    conn, deve_fechar = _obter_conexao(db_conn)
    try:
        cursor = conn.cursor()
        eq = cursor.execute(
            "SELECT id, comarca, contrato_id, ativo FROM equipamentos WHERE id = ?",
            (equipamento_id,)
        ).fetchone()
        if not eq or eq['ativo'] != 1:
            return

        hoje = datetime.date.today()
        ano_atual = hoje.year
        mes_atual = hoje.month
        comarca = (eq['comarca'] or 'OUTROS').strip().upper()
        agora = int(time.time())

        data_inst = None
        if ano_instalacao and mes_instalacao:
            data_inst = (ano_instalacao, mes_instalacao)
        else:
            data_inst = obter_data_instalacao_equipamento(equipamento_id, cursor)

        if not data_inst:
            data_inst = (ano_atual, mes_atual)

        if data_inst:
            ano_inst, mes_inst = data_inst
            # No mês em que o equipamento for instalado (e anteriores), não deve inseri-lo no cronograma.
            # Limpa qualquer agendamento pendente/não executado do mês de instalação e anteriores.
            cursor.execute("""
                DELETE FROM pmoc_checklist_respostas 
                WHERE manutencao_id IN (
                    SELECT id FROM pmoc_manutencoes 
                    WHERE equipamento_id = ? AND (ano_competencia * 12 + mes_competencia) <= (? * 12 + ?) AND status = 'pendente' AND data_execucao IS NULL
                );
            """, (equipamento_id, ano_inst, mes_inst))

            cursor.execute("""
                DELETE FROM pmoc_manutencoes 
                WHERE equipamento_id = ? AND (ano_competencia * 12 + mes_competencia) <= (? * 12 + ?) AND status = 'pendente' AND data_execucao IS NULL;
            """, (equipamento_id, ano_inst, mes_inst))

            cursor.execute("""
                DELETE FROM pmoc_calendario_anual 
                WHERE equipamento_id = ? AND (ano * 12 + mes) <= (? * 12 + ?) AND (manutencao_id IS NULL OR status IN ('planejado', 'gerado'));
            """, (equipamento_id, ano_inst, mes_inst))

        for ano in (ano_atual, ano_atual + 1):
            m0 = (eq['id'] + ano) % 12
            for mes in range(1, 13):
                per = calcular_periodicidade_mes(ano, mes, data_inst, m0)
                if not per:
                    continue

                if not data_inst and (ano == ano_atual and mes < mes_atual):
                    continue

                existe = cursor.execute(
                    "SELECT id, status, manutencao_id FROM pmoc_calendario_anual WHERE equipamento_id = ? AND ano = ? AND mes = ?",
                    (equipamento_id, ano, mes)
                ).fetchone()

                if not existe:
                    cursor.execute("""
                        INSERT INTO pmoc_calendario_anual
                        (equipamento_id, contrato_id, comarca, ano, mes, periodicidade, status, criado_em)
                        VALUES (?, ?, ?, ?, ?, ?, 'planejado', ?)
                    """, (eq['id'], eq['contrato_id'], comarca, ano, mes, per, agora))
                elif existe['status'] == 'planejado' and not existe['manutencao_id']:
                    cursor.execute("""
                        UPDATE pmoc_calendario_anual
                        SET periodicidade = ?
                        WHERE id = ?
                    """, (per, existe['id']))

        conn.commit()
    finally:
        if deve_fechar:
            conn.close()


def limpar_chamados_teste(db_conn=None) -> dict:
    conn, deve_fechar = _obter_conexao(db_conn)
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM historico_pmoc;")
        cursor.execute("DELETE FROM pmoc_checklist_respostas;")
        cursor.execute("DELETE FROM pmoc_manutencao_equipamentos;")
        cursor.execute("DELETE FROM pmoc_manutencoes;")
        cursor.execute("DELETE FROM pmoc_ciclos;")
        cursor.execute("DELETE FROM pmoc_calendario_anual;")
        conn.commit()
        return {
            "status": "sucesso",
            "mensagem": "Tabelas do PMOC resetadas com sucesso."
        }
    finally:
        if deve_fechar:
            conn.close()
