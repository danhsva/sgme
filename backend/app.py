import os
import sqlite3
import time
import io
import secrets
import threading
import uuid

try:
    from PIL import Image, ImageOps   # pip install pillow (opcional: sem ele as fotos são gravadas como enviadas)
    Image.MAX_IMAGE_PIXELS = 40_000_000
except ImportError:
    Image = None
from datetime import datetime, date
from html import escape as html_esc
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_cors import CORS
import jwt
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# Dependências leves do ReportLab (< 8 MB RAM)
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

app = Flask(__name__)
# CORS: Na Oracle VPS com Nginx o acesso é de mesma origem.
# Para restringir origens específicas: export SGME_CORS_ORIGINS="https://meudominio.com"
CORS_ORIGINS = [o.strip() for o in os.environ.get('SGME_CORS_ORIGINS', '*').split(',') if o.strip()]
CORS(app, resources={r"/api/*": {"origins": CORS_ORIGINS}})

from pmoc_catalogo import obter_checklist_padrao, determinar_categoria
from pmoc_planejamento import (
    obter_calendario_anual, gerar_calendario_anual,
    gerar_ordens_mes_automatico, verificar_e_executar_rotina_automatica,
    limpar_chamados_teste, obter_plano_preventiva_janela_movel,
    sincronizar_calendario_equipamento, obter_dados_relatorio_ciclo_pmoc
)
from relatorio_fotografico_pdf import gerar_pdf_conclusao_instalacao

# Configurações Oficiais SGME (Oracle VPS)
def _obter_dados_dir():
    if 'SGME_DADOS' in os.environ:
        return os.environ['SGME_DADOS']
    padrao = '/var/lib/sgme'
    if os.path.exists(padrao):
        return padrao
    local = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'dados'))
    if os.path.exists(local):
        return local
    return padrao

DADOS_DIR = _obter_dados_dir()
DB_PATH = os.path.join(DADOS_DIR, 'sistema.db')
UPLOAD_FOLDER = os.path.join(DADOS_DIR, 'uploads')


def carregar_secret_key():
    """Chave JWT: variável de ambiente SGME_SECRET_KEY (>= 32 chars) ou arquivo dados/.secret_key
    (gerado aleatoriamente na primeira execução, permissão 600). Nunca mais fica fixa no código."""
    env = os.environ.get('SGME_SECRET_KEY', '')
    if len(env) >= 32:
        return env
    caminho = os.path.join(os.path.dirname(DB_PATH), '.secret_key')
    try:
        with open(caminho, encoding='utf-8') as fh:
            chave = fh.read().strip()
            if len(chave) >= 32:
                return chave
    except FileNotFoundError:
        pass
    chave = secrets.token_hex(32)
    fd = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as fh:
        fh.write(chave)
    return chave


SECRET_KEY = carregar_secret_key()
PERFIS_VALIDOS = ['administrador', 'fiscal', 'contratada', 'executante', 'solicitante']
MIN_SENHA = 8
SENHAS_FRACAS = {'admin', 'admin123', '12345678', '123456789', '1234567890', 'password', 'senha123', 'senha1234', 'qwerty123'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['MAX_CONTENT_LENGTH'] = 15 * 1024 * 1024

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row 
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    return conn

# ================= MIDDLEWARES DE SEGURANÇA =================
def erro_interno(e, mensagem='Erro interno do servidor.'):
    """Nunca devolve detalhes da exceção ao cliente; o traceback vai para o journal (journalctl -u sgme-backend)."""
    if isinstance(e, KeyError):
        return jsonify({'erro': f'Campo obrigatório ausente: {e.args[0]}'}), 400
    app.logger.exception('Erro não tratado em %s %s', request.method, request.path)
    return jsonify({'erro': mensagem}), 500


def pode_acessar_os(conn, usuario, os_info):
    """Mesma regra de visibilidade de GET /api/os/<id>, reutilizada para os anexos."""
    perfil, uid = usuario['perfil'], usuario['id']
    if perfil == 'administrador':
        return True
    if perfil == 'solicitante':
        return os_info['solicitante_id'] == uid
    if perfil == 'executante':
        return os_info['executante_id'] == uid
    if perfil in ('fiscal', 'contratada'):
        if perfil == 'contratada' and os_info['status'] == 'aberta':
            return False
        return conn.execute("SELECT 1 FROM usuario_contratos WHERE usuario_id = ? AND contrato_id = ?",
                            (uid, os_info['contrato_id'])).fetchone() is not None
    return False


def pode_acessar_pmoc(conn, usuario, pmoc_info):
    """Regra de visibilidade para manutenções preventivas (PMOC) e seus anexos."""
    perfil, uid = usuario['perfil'], usuario['id']
    if perfil == 'administrador':
        return True
    if perfil == 'executante':
        return pmoc_info['executante_id'] == uid or conn.execute(
            "SELECT 1 FROM usuario_contratos WHERE usuario_id = ? AND contrato_id = ?",
            (uid, pmoc_info['contrato_id'])).fetchone() is not None
    if perfil in ('fiscal', 'contratada'):
        return conn.execute("SELECT 1 FROM usuario_contratos WHERE usuario_id = ? AND contrato_id = ?",
                            (uid, pmoc_info['contrato_id'])).fetchone() is not None
    if perfil == 'solicitante':
        return True
    return False


# ---- Limitador de tentativas de login (em memória; 1 processo, ~KBs de RAM) ----
_FALHAS = {}
_FALHAS_LOCK = threading.Lock()
LIMITES_LOGIN = {'u': 8, 'i': 30}   # falhas por login / por IP dentro da janela
BLOQUEIO_SEGUNDOS = 300


def ip_cliente():
    return (request.headers.get('CF-Connecting-IP')
            or request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
            or request.remote_addr or '?')


def tempo_bloqueio(chave):
    with _FALHAS_LOCK:
        reg = _FALHAS.get(chave)
        if reg and reg['ate'] > time.time():
            return int(reg['ate'] - time.time())
        return 0


def registrar_falha(chave):
    agora = time.time()
    with _FALHAS_LOCK:
        if len(_FALHAS) > 2000:
            for k in [k for k, r in _FALHAS.items() if r['ate'] < agora and agora - r['ultimo'] > BLOQUEIO_SEGUNDOS]:
                del _FALHAS[k]
            if len(_FALHAS) > 10000:
                _FALHAS.clear()
        reg = _FALHAS.setdefault(chave, {'n': 0, 'ultimo': agora, 'ate': 0})
        if agora - reg['ultimo'] > BLOQUEIO_SEGUNDOS:
            reg['n'] = 0
        reg['n'] += 1
        reg['ultimo'] = agora
        if reg['n'] >= LIMITES_LOGIN[chave[0]]:
            reg['ate'] = agora + BLOQUEIO_SEGUNDOS
            reg['n'] = 0


def limpar_falhas(chave):
    with _FALHAS_LOCK:
        _FALHAS.pop(chave, None)


def valida_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # Token SOMENTE no header Authorization (o ?token= na URL vazava em logs e histórico).
        partes = request.headers.get('Authorization', '').split()
        token = partes[1] if len(partes) == 2 and partes[0].lower() == 'bearer' else None

        if not token:
            return jsonify({'erro': 'Token ausente. Faça login novamente.'}), 401
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return jsonify({'erro': 'Sessão expirada. Faça login novamente.'}), 401
        except Exception:
            return jsonify({'erro': 'Token inválido.'}), 401

        # O banco é a fonte da verdade: usuário inativado/rebaixado perde acesso na hora, sem esperar o token expirar.
        conn = get_db_connection()
        try:
            u = conn.execute("SELECT id, nome, perfil, ativo, primeiro_acesso FROM usuarios WHERE id = ?",
                             (payload.get('id'),)).fetchone()
        finally:
            conn.close()
        if not u or u['ativo'] == 0:
            return jsonify({'erro': 'Usuário inativo ou inexistente. Faça login novamente.'}), 401
        if u['primeiro_acesso'] == 1 and request.endpoint != 'trocar_senha':
            return jsonify({'erro': 'Defina uma nova senha antes de continuar.'}), 403

        usuario_atual = {'id': u['id'], 'nome': u['nome'], 'perfil': u['perfil']}
        return f(usuario_atual, *args, **kwargs)
    return decorated


def exige_admin(f):
    @wraps(f)
    def decorated(usuario_atual, *args, **kwargs):
        if usuario_atual.get('perfil') != 'administrador':
            return jsonify({'erro': 'Acesso negado. Requer privilégios de Administrador.'}), 403
        return f(usuario_atual, *args, **kwargs)
    return decorated

# ================= HEALTHCHECK =================
@app.route('/', methods=['GET'])
def health_check(): 
    return jsonify({
        "status": "online", 
        "sigla": "SGME",
        "sistema": "SGME - Sistema de Gestão de Manutenção de Equipamentos", 
        "versao": "3.1.0_pmoc_preventivas"
    }), 200

# ================= AUTENTICAÇÃO E SENHA =================
@app.route('/api/login', methods=['POST'])
def login():
    try:
        dados = request.get_json(silent=True) or {}
        login_input = str(dados.get('login', '')).strip().lower()
        senha = str(dados.get('senha', ''))

        chave_u, chave_i = ('u', login_input), ('i', ip_cliente())
        espera = max(tempo_bloqueio(chave_u), tempo_bloqueio(chave_i))
        if espera:
            return jsonify({'erro': f'Muitas tentativas de acesso. Tente novamente em {(espera + 59) // 60} min.'}), 429

        conn = get_db_connection()
        user = conn.execute("SELECT * FROM usuarios WHERE login = ?", (login_input,)).fetchone()

        if user and check_password_hash(user['senha_hash'], senha):
            if user['ativo'] == 0:
                conn.close()
                return jsonify({"erro": "Usuário inativo. Contate o administrador."}), 403

            limpar_falhas(chave_u)

            # Senha provisória (igual ao login) ou padrão de fábrica ('admin') => troca obrigatória, também no servidor.
            forcar_troca = user['primeiro_acesso'] == 1 or senha == 'admin' or senha.lower() == login_input
            if forcar_troca and user['primeiro_acesso'] != 1:
                conn.execute("UPDATE usuarios SET primeiro_acesso = 1 WHERE id = ?", (user['id'],))
                conn.commit()

            contratos_user = conn.execute('''
                SELECT c.id, c.numero_contrato, c.nome_empresa 
                FROM contratos c
                JOIN usuario_contratos uc ON c.id = uc.contrato_id
                WHERE uc.usuario_id = ? AND c.ativo = 1
                ORDER BY c.numero_contrato
            ''', (user['id'],)).fetchall()
            conn.close()

            agora = int(time.time())
            token = jwt.encode({
                'id': user['id'],
                'nome': user['nome'],
                'perfil': user['perfil'],
                'iat': agora,
                'exp': agora + (12 * 3600)
            }, SECRET_KEY, algorithm="HS256")

            return jsonify({
                "token": token,
                "id": user['id'],
                "nome": user['nome'],
                "perfil": user['perfil'],
                "contratos": [dict(c) for c in contratos_user],
                "primeiro_acesso": 1 if forcar_troca else 0
            }), 200

        conn.close()
        registrar_falha(chave_u)
        registrar_falha(chave_i)
        return jsonify({"erro": "Credenciais inválidas."}), 401
    except Exception as e:
        return erro_interno(e)

@app.route('/api/trocar-senha', methods=['POST'])
@valida_token
def trocar_senha(usuario_atual):
    try:
        dados = request.get_json(silent=True) or {}
        nova_senha = str(dados.get('nova_senha', '')).strip()
        if len(nova_senha) < MIN_SENHA:
            return jsonify({"erro": f"A nova senha deve possuir no mínimo {MIN_SENHA} caracteres."}), 400

        conn = get_db_connection()
        user = conn.execute("SELECT login FROM usuarios WHERE id = ?", (usuario_atual['id'],)).fetchone()
        if nova_senha.lower() == user['login'] or nova_senha.lower() in SENHAS_FRACAS:
            conn.close()
            return jsonify({"erro": "Escolha uma senha diferente do seu login e menos previsível."}), 400

        novo_hash = generate_password_hash(nova_senha)
        conn.execute("UPDATE usuarios SET senha_hash = ?, primeiro_acesso = 0 WHERE id = ?", (novo_hash, usuario_atual['id']))
        conn.commit()
        conn.close()
        return jsonify({"mensagem": "Senha atualizada com sucesso!"}), 200
    except Exception as e:
        return erro_interno(e)

# ================= GESTÃO DE CONTRATOS =================
@app.route('/api/contratos', methods=['GET', 'POST'])
@valida_token
def gerenciar_contratos(usuario_atual):
    try:
        conn = get_db_connection()
        perfil = usuario_atual['perfil']
        uid = usuario_atual['id']

        if request.method == 'GET':
            if perfil == 'administrador':
                contratos = conn.execute("SELECT * FROM contratos ORDER BY numero_contrato").fetchall()
            elif perfil in ['fiscal', 'contratada', 'executante']:
                contratos = conn.execute('''
                    SELECT c.* FROM contratos c
                    JOIN usuario_contratos uc ON c.id = uc.contrato_id
                    WHERE uc.usuario_id = ? AND c.ativo = 1
                    ORDER BY c.numero_contrato
                ''', (uid,)).fetchall()
            else:
                contratos = []

            conn.close()
            return jsonify([dict(c) for c in contratos]), 200
        
        if request.method == 'POST':
            if perfil != 'administrador': 
                conn.close()
                return jsonify({'erro': 'Acesso negado.'}), 403
            d = request.get_json() or {}
            conn.execute("INSERT INTO contratos (numero_contrato, nome_empresa, cnpj, ativo) VALUES (?, ?, ?, 1)", 
                         (d['numero_contrato'].strip().upper(), d['nome_empresa'].strip().upper(), d.get('cnpj', '').strip()))
            conn.commit()
            conn.close()
            return jsonify({"mensagem": "Contrato criado!"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"erro": "Já existe um contrato com este número."}), 400
    except Exception as e: 
        return erro_interno(e)

@app.route('/api/contratos/<int:c_id>', methods=['PUT'])
@valida_token
@exige_admin
def atualizar_contrato(usuario_atual, c_id):
    try:
        d = request.get_json() or {}
        conn = get_db_connection()
        conn.execute("UPDATE contratos SET numero_contrato=?, nome_empresa=?, cnpj=?, ativo=? WHERE id=?", 
                     (d['numero_contrato'].strip().upper(), d['nome_empresa'].strip().upper(), d.get('cnpj', '').strip(), d.get('ativo', 1), c_id))
        conn.commit()
        conn.close()
        return jsonify({"mensagem": "Contrato atualizado!"}), 200
    except sqlite3.IntegrityError:
        return jsonify({"erro": "Já existe um contrato com este número."}), 400
    except Exception as e: 
        return erro_interno(e)

# ================= GESTÃO DE USUÁRIOS =================
@app.route('/api/usuarios', methods=['GET', 'POST'])
@valida_token
def gerenciar_usuarios(usuario_atual):
    try:
        conn = get_db_connection()
        perfil = usuario_atual['perfil']
        uid = usuario_atual['id']

        if request.method == 'GET':
            if perfil == 'administrador':
                query = '''
                    SELECT u.id, u.nome, u.login, u.perfil, u.ativo, 
                           GROUP_CONCAT(c.numero_contrato, ', ') as contrato_nome,
                           GROUP_CONCAT(c.id, ',') as contratos_ids
                    FROM usuarios u 
                    LEFT JOIN usuario_contratos uc ON u.id = uc.usuario_id 
                    LEFT JOIN contratos c ON uc.contrato_id = c.id 
                    GROUP BY u.id 
                    ORDER BY u.nome
                '''
                users = conn.execute(query).fetchall()
            elif perfil == 'fiscal':
                query = '''
                    SELECT DISTINCT u.id, u.nome, u.login, u.perfil, u.ativo,
                           GROUP_CONCAT(c.numero_contrato, ', ') as contrato_nome,
                           GROUP_CONCAT(c.id, ',') as contratos_ids
                    FROM usuarios u
                    JOIN usuario_contratos uc ON u.id = uc.usuario_id
                    JOIN contratos c ON uc.contrato_id = c.id
                    WHERE uc.contrato_id IN (SELECT contrato_id FROM usuario_contratos WHERE usuario_id = ?)
                    GROUP BY u.id
                    ORDER BY u.nome
                '''
                users = conn.execute(query, (uid,)).fetchall()
            elif perfil == 'contratada':
                query = '''
                    SELECT DISTINCT u.id, u.nome, u.login, u.perfil, u.ativo,
                           GROUP_CONCAT(c.numero_contrato, ', ') as contrato_nome
                    FROM usuarios u
                    JOIN usuario_contratos uc ON u.id = uc.usuario_id
                    JOIN contratos c ON uc.contrato_id = c.id
                    WHERE u.perfil = 'executante' AND u.ativo = 1
                      AND uc.contrato_id IN (SELECT contrato_id FROM usuario_contratos WHERE usuario_id = ?)
                    GROUP BY u.id
                    ORDER BY u.nome
                '''
                users = conn.execute(query, (uid,)).fetchall()
            else:
                conn.close()
                return jsonify({'erro': 'Acesso negado.'}), 403

            conn.close()
            return jsonify([dict(u) for u in users]), 200
            
        if request.method == 'POST':
            if perfil not in ['administrador', 'fiscal']: 
                conn.close()
                return jsonify({'erro': 'Acesso negado.'}), 403
            
            d = request.get_json() or {}
            contratos_ids = d.get('contratos_ids') or []
            if not contratos_ids and d.get('contrato_id'):
                contratos_ids = [d.get('contrato_id')]

            if perfil == 'fiscal':
                if d.get('perfil') not in ['executante', 'contratada']: 
                    conn.close()
                    return jsonify({'erro': 'Você só pode cadastrar Executantes ou Contratadas.'}), 403
                for cid in contratos_ids:
                    pertence = conn.execute("SELECT 1 FROM usuario_contratos WHERE usuario_id = ? AND contrato_id = ?", (uid, cid)).fetchone()
                    if not pertence:
                        conn.close()
                        return jsonify({'erro': f'Contrato #{cid} não autorizado para o seu usuário.'}), 403
            
            if d.get('perfil') not in PERFIS_VALIDOS:
                conn.close()
                return jsonify({'erro': 'Perfil inválido.'}), 400

            senha_hash = generate_password_hash(d['login'].strip().lower())
            cursor = conn.cursor()
            cursor.execute("INSERT INTO usuarios (nome, login, senha_hash, perfil, primeiro_acesso, ativo) VALUES (?, ?, ?, ?, 1, 1)", 
                           (d['nome'].strip().upper(), d['login'].strip().lower(), senha_hash, d['perfil']))
            novo_uid = cursor.lastrowid

            for cid in contratos_ids:
                if cid:
                    cursor.execute("INSERT OR IGNORE INTO usuario_contratos (usuario_id, contrato_id) VALUES (?, ?)", (novo_uid, int(cid)))

            conn.commit()
            conn.close()
            return jsonify({"mensagem": "Usuário criado com sucesso!"}), 201
    except sqlite3.IntegrityError: 
        return jsonify({"erro": "Este login já está cadastrado."}), 400
    except Exception as e: 
        return erro_interno(e)

@app.route('/api/usuarios/<int:user_id>', methods=['PUT'])
@valida_token
def atualizar_usuario(usuario_atual, user_id):
    try:
        perfil = usuario_atual['perfil']
        uid = usuario_atual['id']

        if perfil not in ['administrador', 'fiscal']: 
            return jsonify({'erro': 'Acesso negado.'}), 403

        d = request.get_json() or {}
        if user_id == uid and d.get('ativo') == 0: 
            return jsonify({'erro': 'Você não pode inativar o seu próprio perfil.'}), 400
        if d.get('perfil') not in PERFIS_VALIDOS:
            return jsonify({'erro': 'Perfil inválido.'}), 400
        if user_id == uid and d.get('perfil') != perfil:
            return jsonify({'erro': 'Você não pode alterar o seu próprio perfil de acesso.'}), 400
        if perfil == 'fiscal' and d.get('perfil') not in ['executante', 'contratada']:
            return jsonify({'erro': 'O Fiscal só pode manter usuários com perfil Executante ou Contratada.'}), 403
        
        conn = get_db_connection()

        if perfil == 'fiscal':
            alvo = conn.execute('''
                SELECT u.id, u.perfil 
                FROM usuarios u
                JOIN usuario_contratos uc ON u.id = uc.usuario_id
                WHERE u.id = ? AND uc.contrato_id IN (SELECT contrato_id FROM usuario_contratos WHERE usuario_id = ?)
            ''', (user_id, uid)).fetchone()
            
            if not alvo:
                conn.close()
                return jsonify({'erro': 'Usuário não pertence à sua equipe/contratos.'}), 403
            if alvo['perfil'] not in ['executante', 'contratada']:
                conn.close()
                return jsonify({'erro': 'Permissão insuficiente para alterar este perfil.'}), 403

        conn.execute('UPDATE usuarios SET nome=?, login=?, perfil=?, ativo=? WHERE id=?', 
                     (d['nome'].strip().upper(), d['login'].strip().lower(), d['perfil'], d.get('ativo', 1), user_id))
        
        if 'contratos_ids' in d or 'contrato_id' in d:
            novos_contratos = d.get('contratos_ids') or []
            if not novos_contratos and d.get('contrato_id'):
                novos_contratos = [d.get('contrato_id')]

            if perfil == 'administrador':
                conn.execute('DELETE FROM usuario_contratos WHERE usuario_id = ?', (user_id,))
                for cid in novos_contratos:
                    if cid: conn.execute('INSERT OR IGNORE INTO usuario_contratos (usuario_id, contrato_id) VALUES (?, ?)', (user_id, int(cid)))
            elif perfil == 'fiscal':
                conn.execute('DELETE FROM usuario_contratos WHERE usuario_id = ? AND contrato_id IN (SELECT contrato_id FROM usuario_contratos WHERE usuario_id = ?)', (user_id, uid))
                for cid in novos_contratos:
                    pertence = conn.execute("SELECT 1 FROM usuario_contratos WHERE usuario_id = ? AND contrato_id = ?", (uid, cid)).fetchone()
                    if pertence:
                        conn.execute('INSERT OR IGNORE INTO usuario_contratos (usuario_id, contrato_id) VALUES (?, ?)', (user_id, int(cid)))

        conn.commit()
        conn.close()
        return jsonify({"mensagem": "Usuário atualizado com sucesso!"}), 200
    except sqlite3.IntegrityError: 
        return jsonify({"erro": "Este login já está em uso."}), 400
    except Exception as e: 
        return erro_interno(e)

@app.route('/api/usuarios/<int:user_id>/resetar-senha', methods=['POST'])
@valida_token
@exige_admin
def resetar_senha_usuario(usuario_atual, user_id):
    try:
        conn = get_db_connection()
        user = conn.execute("SELECT login FROM usuarios WHERE id = ?", (user_id,)).fetchone()
        if not user:
            conn.close()
            return jsonify({'erro': 'Usuário não encontrado.'}), 404
            
        nova_senha_hash = generate_password_hash(user['login'])
        conn.execute("UPDATE usuarios SET senha_hash = ?, primeiro_acesso = 1 WHERE id = ?", (nova_senha_hash, user_id))
        conn.commit()
        conn.close()
        return jsonify({"mensagem": f"Senha resetada com sucesso! A nova senha provisória é: {user['login']}"}), 200
    except Exception as e: 
        return erro_interno(e)

# ================= GESTÃO DE EQUIPAMENTOS =================
@app.route('/api/equipamentos', methods=['GET', 'POST'])
@valida_token
def gerenciar_equipamentos(usuario_atual):
    try:
        conn = get_db_connection()
        perfil = usuario_atual['perfil']
        uid = usuario_atual['id']

        if request.method == 'GET':
            if perfil == 'executante':
                conn.close()
                return jsonify([]), 200
                
            query = '''
                SELECT e.*, c.numero_contrato as contrato_nome, 
                (SELECT COUNT(id) FROM ordens_servico WHERE equipamento_id = e.id AND status NOT IN ('concluida', 'cancelada')) as tem_os_ativa
                FROM equipamentos e LEFT JOIN contratos c ON e.contrato_id = c.id 
            '''
            params = []

            if perfil in ['fiscal', 'contratada']:
                query += " WHERE e.contrato_id IN (SELECT contrato_id FROM usuario_contratos WHERE usuario_id = ?) "
                params.append(uid)
                
            query += " ORDER BY e.comarca, e.predio, e.sala "
            eqs = conn.execute(query, params).fetchall()
            conn.close()
            return jsonify([dict(e) for e in eqs]), 200
            
        if request.method == 'POST':
            if perfil not in ['administrador', 'fiscal']: 
                conn.close()
                return jsonify({'erro': 'Acesso negado.'}), 403
            
            d = request.get_json() or {}
            contrato_id = d.get('contrato_id')

            if perfil == 'fiscal':
                if not contrato_id:
                    conn.close()
                    return jsonify({'erro': 'Selecione um contrato para vincular ao equipamento.'}), 400
                pertence = conn.execute("SELECT 1 FROM usuario_contratos WHERE usuario_id = ? AND contrato_id = ?", (uid, contrato_id)).fetchone()
                if not pertence:
                    conn.close()
                    return jsonify({'erro': 'Contrato não autorizado para o seu perfil.'}), 403
            
            conn.execute('''INSERT INTO equipamentos (comarca, predio, sala, tipo_equipamento, capacidade, marca, tombo, contrato_id, status_equipamento, ativo) 
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'ATIVO', 1)''', 
                         (d['comarca'].strip().upper(), d['predio'].strip().upper(), d['sala'].strip().upper(), 
                          d['tipo_equipamento'].strip().upper(), d.get('capacidade', '').strip().upper(), 
                          d.get('marca', '').strip().upper(), d.get('tombo', 'S/T').strip().upper() or 'S/T', contrato_id))
            conn.commit()
            conn.close()
            return jsonify({"mensagem": "Equipamento cadastrado com sucesso!"}), 201
    except Exception as e: 
        return erro_interno(e)

@app.route('/api/equipamentos/<int:eq_id>', methods=['PUT'])
@valida_token
def atualizar_equipamento(usuario_atual, eq_id):
    try:
        perfil = usuario_atual['perfil']
        uid = usuario_atual['id']

        if perfil not in ['administrador', 'fiscal']: 
            return jsonify({'erro': 'Acesso negado.'}), 403
        
        d = request.get_json() or {}
        conn = get_db_connection()
        contrato_id = d.get('contrato_id')

        if perfil == 'fiscal':
            eq = conn.execute('''
                SELECT id, contrato_id FROM equipamentos 
                WHERE id = ? AND contrato_id IN (SELECT contrato_id FROM usuario_contratos WHERE usuario_id = ?)
            ''', (eq_id, uid)).fetchone()
            if not eq:
                conn.close()
                return jsonify({'erro': 'Equipamento não pertence a nenhum contrato seu.'}), 403
            
            if contrato_id:
                valido = conn.execute("SELECT 1 FROM usuario_contratos WHERE usuario_id = ? AND contrato_id = ?", (uid, contrato_id)).fetchone()
                if not valido:
                    conn.close()
                    return jsonify({'erro': 'Novo contrato escolhido não está autorizado para você.'}), 403
            else:
                contrato_id = eq['contrato_id']
            
        novo_ativo = int(d.get('ativo', 1))
        novo_status_eq = 'ATIVO' if novo_ativo == 1 else 'INATIVO'

        # Se inativado, retira o equipamento do plano de manutenção (remove previsões futuras não executadas)
        if novo_ativo == 0:
            conn.execute('''
                DELETE FROM pmoc_calendario_anual 
                WHERE equipamento_id = ? AND status = 'planejado' AND (manutencao_id IS NULL OR manutencao_id IN (SELECT id FROM pmoc_manutencoes WHERE status = 'pendente'))
            ''', (eq_id,))
            conn.execute('''
                DELETE FROM pmoc_manutencao_equipamentos 
                WHERE equipamento_id = ? AND manutencao_id IN (SELECT id FROM pmoc_manutencoes WHERE status = 'pendente')
            ''', (eq_id,))

        conn.execute('''UPDATE equipamentos SET comarca=?, predio=?, sala=?, tipo_equipamento=?, capacidade=?, marca=?, tombo=?, contrato_id=?, status_equipamento=?, ativo=? WHERE id=?''', 
                     (d['comarca'].strip().upper(), d['predio'].strip().upper(), d['sala'].strip().upper(), 
                      d['tipo_equipamento'].strip().upper(), d.get('capacidade', '').strip().upper(), 
                      d.get('marca', '').strip().upper(), d.get('tombo', 'S/T').strip().upper() or 'S/T', 
                      contrato_id, novo_status_eq, novo_ativo, eq_id))
        if novo_ativo == 1:
            sincronizar_calendario_equipamento(eq_id, conn)
        conn.commit()
        conn.close()
        return jsonify({"mensagem": "Equipamento atualizado com sucesso!"}), 200
    except Exception as e: 
        return erro_interno(e)

@app.route('/api/equipamentos/<int:eq_id>/os', methods=['GET'])
@valida_token
def historico_os_equipamento(usuario_atual, eq_id):
    try:
        conn = get_db_connection()
        perfil = usuario_atual['perfil']
        uid = usuario_atual['id']

        eq = conn.execute("SELECT id, contrato_id FROM equipamentos WHERE id = ?", (eq_id,)).fetchone()
        if not eq:
            conn.close()
            return jsonify({'erro': 'Equipamento não encontrado.'}), 404

        if perfil in ['fiscal', 'contratada']:
            tem_acesso = conn.execute("SELECT 1 FROM usuario_contratos WHERE usuario_id = ? AND contrato_id = ?", (uid, eq['contrato_id'])).fetchone()
            if not tem_acesso:
                conn.close()
                return jsonify({'erro': 'Acesso negado a este equipamento.'}), 403

        query = '''
            SELECT os.*, 
                   COALESCE(oi.tipo_equipamento, eq.tipo_equipamento) AS tipo_equipamento, 
                   COALESCE(oi.capacidade, eq.capacidade) AS capacidade, 
                   COALESCE(oi.comarca, eq.comarca) AS comarca, 
                   COALESCE(oi.predio, eq.predio) AS predio, 
                   COALESCE(oi.sala, eq.sala) AS sala, 
                   COALESCE(oi.marca, eq.marca) AS marca,
                   COALESCE(oi.tombo, eq.tombo) AS tombo,
                   oi.foto_evaporadora, oi.foto_condensadora, oi.foto_tubulacao, oi.foto_dreno, oi.arquivo_os_assinada_original, oi.equipamento_novo_id,
                   u.nome as nome_solicitante 
            FROM ordens_servico os 
            LEFT JOIN equipamentos eq ON os.equipamento_id = eq.id
            LEFT JOIN os_instalacao oi ON oi.os_id = os.id 
            JOIN usuarios u ON os.solicitante_id = u.id 
            WHERE (os.equipamento_id = ? OR oi.equipamento_novo_id = ?)
        '''
        params = [eq_id, eq_id]

        if perfil == 'contratada':
            query += " AND os.status != 'aberta'"

        query += " ORDER BY os.data_abertura DESC"
        chamados = conn.execute(query, params).fetchall()
        conn.close()
        return jsonify([dict(c) for c in chamados]), 200
    except Exception as e: 
        return erro_interno(e)

# ================= GESTÃO DE ORDENS DE SERVIÇO =================
TRANSICOES_OS = {
    'aberta':          {'aprovada', 'cancelada'},
    'aprovada':        {'em_execucao', 'aguardando_peca', 'em_analise', 'cancelada'},
    'em_execucao':     {'em_execucao', 'aguardando_peca', 'em_analise', 'cancelada'},
    'aguardando_peca': {'em_execucao', 'aguardando_peca', 'em_analise', 'cancelada'},
    'em_analise':      {'concluida', 'em_execucao', 'cancelada'},
    'concluida':       set(),
    'cancelada':       set(),
}

@app.route('/api/os', methods=['GET', 'POST'])
@valida_token
def gerenciar_os(usuario_atual):
    try:
        conn = get_db_connection()
        perfil = usuario_atual['perfil']
        uid = usuario_atual['id']

        if request.method == 'POST':
            dados = request.get_json() or {}
            eq_id = dados.get('equipamento_id')
            descricao = dados.get('descricao_falha', '').strip().upper()

            if not eq_id or not descricao:
                conn.close()
                return jsonify({'erro': 'Equipamento e descrição da falha são obrigatórios.'}), 400

            eq = conn.execute("SELECT id, ativo, contrato_id FROM equipamentos WHERE id = ?", (eq_id,)).fetchone()
            if not eq or eq['ativo'] != 1:
                conn.close()
                return jsonify({'erro': 'Equipamento inválido ou inativo.'}), 400

            ts = int(time.time() * 1000)

            if perfil in ['fiscal', 'administrador']:
                status_inicial = 'aprovada'
                fiscal_id = uid if perfil == 'fiscal' else None
                acao_hist = "ABERTURA E APROVAÇÃO"
                obs_hist = "ORDEM DE SERVIÇO REGISTRADA E APROVADA PELO FISCAL/ADMINISTRADOR."
            else:
                status_inicial = 'aberta'
                fiscal_id = None
                acao_hist = "ABERTURA"
                obs_hist = "ORDEM DE SERVIÇO REGISTRADA PELO SOLICITANTE."

            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO ordens_servico (equipamento_id, solicitante_id, fiscal_id, descricao_falha, data_abertura, status, prioridade, contrato_id) 
                VALUES (?, ?, ?, ?, ?, ?, 'media', ?)
            """, (eq_id, uid, fiscal_id, descricao, ts, status_inicial, eq['contrato_id']))
            
            os_id = cursor.lastrowid
            cursor.execute("INSERT INTO historico_os (os_id, usuario_id, data_registro, acao, observacao) VALUES (?, ?, ?, ?, ?)", 
                           (os_id, uid, ts, acao_hist, obs_hist))
            conn.commit()
            conn.close()
            return jsonify({"mensagem": "O.S. Aberta com sucesso!", "os_id": os_id, "status": status_inicial}), 201
            
        if request.method == 'GET':
            query = '''
                SELECT os.*, 
                       COALESCE(oi.tipo_equipamento, eq.tipo_equipamento) AS tipo_equipamento, 
                       COALESCE(oi.capacidade, eq.capacidade) AS capacidade, 
                       COALESCE(oi.comarca, eq.comarca) AS comarca, 
                       COALESCE(oi.predio, eq.predio) AS predio, 
                       COALESCE(oi.sala, eq.sala) AS sala, 
                       COALESCE(oi.tombo, eq.tombo) AS tombo,
                       COALESCE(os.contrato_id, eq.contrato_id) AS contrato_id, 
                       COALESCE(oi.marca, eq.marca) AS marca, 
                       oi.foto_evaporadora, oi.foto_condensadora, oi.foto_tubulacao, oi.foto_dreno, oi.arquivo_os_assinada_original, oi.equipamento_novo_id,
                       u.nome as nome_solicitante, c.numero_contrato as contrato_nome
                FROM ordens_servico os 
                LEFT JOIN equipamentos eq ON os.equipamento_id = eq.id
                LEFT JOIN os_instalacao oi ON oi.os_id = os.id 
                JOIN usuarios u ON os.solicitante_id = u.id 
                LEFT JOIN contratos c ON COALESCE(os.contrato_id, eq.contrato_id) = c.id
            '''
            params = []

            if perfil == 'solicitante':
                query += " WHERE os.solicitante_id = ?"
                params.append(uid)
            elif perfil == 'fiscal':
                query += " WHERE COALESCE(os.contrato_id, eq.contrato_id) IN (SELECT contrato_id FROM usuario_contratos WHERE usuario_id = ?)"
                params.append(uid)
            elif perfil == 'contratada':
                query += " WHERE COALESCE(os.contrato_id, eq.contrato_id) IN (SELECT contrato_id FROM usuario_contratos WHERE usuario_id = ?) AND os.status != 'aberta'"
                params.append(uid)
            elif perfil == 'executante':
                query += " WHERE os.executante_id = ? AND os.status NOT IN ('em_analise', 'concluida', 'cancelada')"
                params.append(uid)
            elif perfil != 'administrador':
                conn.close()
                return jsonify({'erro': 'Perfil não autorizado.'}), 403
                
            query += " ORDER BY os.data_abertura DESC"
            chamados = conn.execute(query, params).fetchall()
            conn.close()
            return jsonify([dict(c) for c in chamados]), 200
    except Exception as e: 
        return erro_interno(e)

@app.route('/api/os/<int:os_id>', methods=['GET'])
@valida_token
def obter_detalhes_os(usuario_atual, os_id):
    try:
        conn = get_db_connection()
        perfil = usuario_atual['perfil']
        uid = usuario_atual['id']

        os_info = conn.execute('''
            SELECT os.*, COALESCE(oi.tipo_equipamento,eq.tipo_equipamento) AS tipo_equipamento, COALESCE(oi.capacidade,eq.capacidade) AS capacidade, COALESCE(oi.comarca,eq.comarca) AS comarca, COALESCE(oi.predio,eq.predio) AS predio, COALESCE(oi.sala,eq.sala) AS sala, COALESCE(oi.tombo,eq.tombo) AS tombo, COALESCE(os.contrato_id,eq.contrato_id) AS contrato_id, COALESCE(oi.marca,eq.marca) AS marca, oi.foto_evaporadora, oi.foto_condensadora, oi.foto_tubulacao, oi.foto_dreno, oi.arquivo_os_assinada_original, oi.equipamento_novo_id,
                   u.nome as nome_solicitante, ex.nome as nome_executante, c.numero_contrato as contrato_nome
            FROM ordens_servico os 
            LEFT JOIN equipamentos eq ON os.equipamento_id = eq.id
            LEFT JOIN os_instalacao oi ON oi.os_id = os.id 
            JOIN usuarios u ON os.solicitante_id = u.id 
            LEFT JOIN usuarios ex ON os.executante_id = ex.id
            LEFT JOIN contratos c ON COALESCE(os.contrato_id, eq.contrato_id) = c.id
            WHERE os.id = ?
        ''', (os_id,)).fetchone()
        
        if not os_info: 
            conn.close()
            return jsonify({"erro": "OS não encontrada."}), 404

        if perfil == 'solicitante' and os_info['solicitante_id'] != uid:
            conn.close()
            return jsonify({'erro': 'Acesso negado a este chamado.'}), 403
        elif perfil == 'fiscal':
            tem_contrato = conn.execute("SELECT 1 FROM usuario_contratos WHERE usuario_id = ? AND contrato_id = ?", (uid, os_info['contrato_id'])).fetchone()
            if not tem_contrato:
                conn.close()
                return jsonify({'erro': 'Chamado não pertence aos seus contratos.'}), 403
        elif perfil == 'contratada':
            tem_contrato = conn.execute("SELECT 1 FROM usuario_contratos WHERE usuario_id = ? AND contrato_id = ?", (uid, os_info['contrato_id'])).fetchone()
            if not tem_contrato or os_info['status'] == 'aberta':
                conn.close()
                return jsonify({'erro': 'Chamado inacessível para sua empresa.'}), 403
        elif perfil == 'executante' and os_info['executante_id'] != uid:
            conn.close()
            return jsonify({'erro': 'Esta O.S. não está designada para o seu usuário.'}), 403

        historico = conn.execute('''
            SELECT h.*, u.nome as nome_usuario 
            FROM historico_os h JOIN usuarios u ON h.usuario_id = u.id 
            WHERE h.os_id = ? ORDER BY h.data_registro DESC
        ''', (os_id,)).fetchall()
        conn.close()
        
        return jsonify({"os": dict(os_info), "historico": [dict(h) for h in historico]}), 200
    except Exception as e: 
        return erro_interno(e)

@app.route('/api/os/instalacao', methods=['POST'])
@valida_token
def criar_os_instalacao(usuario_atual):
    if usuario_atual['perfil'] != 'fiscal':
        return jsonify({'erro':'Somente o fiscal pode abrir O.S. de instalação/substituição.'}), 403
    d=request.get_json(silent=True) or {}; uid=usuario_atual['id']; sub=bool(d.get('substituicao'))
    obrig=['marca','tipo_equipamento','comarca','predio','sala']
    if any(not str(d.get(k,'')).strip() for k in obrig): return jsonify({'erro':'Marca, modelo, comarca, prédio e local são obrigatórios.'}),400
    conn=get_db_connection()
    try:
        eq_id=d.get('equipamento_substituido_id') if sub else None
        if sub:
            eq=conn.execute("SELECT * FROM equipamentos WHERE id=? AND ativo=1",(eq_id,)).fetchone()
            if not eq: return jsonify({'erro':'Equipamento a substituir inválido ou inativo.'}),400
            contrato_id=eq['contrato_id']
            ativa=conn.execute("SELECT 1 FROM ordens_servico WHERE equipamento_id=? AND status NOT IN ('concluida','cancelada')",(eq_id,)).fetchone()
            if ativa: return jsonify({'erro':'O equipamento possui O.S. em andamento.'}),409
        else: contrato_id=d.get('contrato_id')
        if not contrato_id or not conn.execute("SELECT 1 FROM usuario_contratos WHERE usuario_id=? AND contrato_id=?",(uid,contrato_id)).fetchone():
            return jsonify({'erro':'Contrato não autorizado para o fiscal.'}),403
        tipo='substituicao' if sub else 'instalacao'; ts=int(time.time()*1000)
        desc=('SUBSTITUIÇÃO' if sub else 'INSTALAÇÃO')+' DE EQUIPAMENTO '+str(d['marca']).strip().upper()+' '+str(d['tipo_equipamento']).strip().upper()
        obs=str(d.get('observacao','')).strip().upper()
        cur=conn.cursor(); cur.execute("INSERT INTO ordens_servico(equipamento_id,solicitante_id,fiscal_id,descricao_falha,data_abertura,status,prioridade,tipo_os,contrato_id) VALUES(?,?,?,?,?,'aprovada','media',?,?)",(eq_id,uid,uid,desc,ts,tipo,contrato_id)); oid=cur.lastrowid
        cur.execute("INSERT INTO os_instalacao(os_id,marca,tipo_equipamento,capacidade,comarca,predio,sala,tombo) VALUES(?,?,?,?,?,?,?,?)",(oid,str(d['marca']).strip().upper(),str(d['tipo_equipamento']).strip().upper(),str(d.get('capacidade','')).strip().upper(),str(d['comarca']).strip().upper(),str(d['predio']).strip().upper(),str(d['sala']).strip().upper(),str(d.get('tombo','')).strip().upper() or None))
        cur.execute("INSERT INTO historico_os(os_id,usuario_id,data_registro,acao,observacao) VALUES(?,?,?,?,?)",(oid,uid,ts,'ABERTURA_E_APROVACAO_'+tipo.upper(),obs or desc)); conn.commit()
        return jsonify({'mensagem':'O.S. de instalação criada.','os_id':oid,'status':'aprovada','tipo_os':tipo}),201
    except Exception as e: conn.rollback(); return erro_interno(e)
    finally: conn.close()

@app.route('/api/os/<int:os_id>/status', methods=['PUT'])
@valida_token
def atualizar_status_os(usuario_atual, os_id):
    try:
        dados = request.get_json() or {}
        status_novo = dados.get('status')
        observacao = dados.get('observacao', '').strip().upper()
        executante_id = dados.get('executante_id')
        arquivo_conclusao = dados.get('arquivo_conclusao')
        tombo_novo = str(dados.get('tombo','')).strip().upper()
        foto_evaporadora = dados.get('foto_evaporadora')
        foto_condensadora = dados.get('foto_condensadora')
        foto_tubulacao = dados.get('foto_tubulacao')
        foto_dreno = dados.get('foto_dreno')
        
        perfil = usuario_atual['perfil']
        uid = usuario_atual['id']

        if perfil == 'solicitante': 
            return jsonify({'erro': 'Solicitantes não possuem permissão para tramitar O.S.'}), 403

        conn = get_db_connection()
        conn.execute('BEGIN IMMEDIATE')  # serializa decisões concorrentes sobre a mesma O.S.
        os_info = conn.execute('''
            SELECT os.*, COALESCE(os.contrato_id,eq.contrato_id) AS contrato_id, 
                   oi.tombo, oi.foto_evaporadora, oi.foto_condensadora, oi.foto_tubulacao, oi.foto_dreno, 
                   oi.arquivo_os_assinada_original, oi.equipamento_novo_id,
                   COALESCE(oi.tipo_equipamento,eq.tipo_equipamento) AS tipo_equipamento,
                   COALESCE(oi.capacidade,eq.capacidade) AS capacidade,
                   COALESCE(oi.comarca,eq.comarca) AS comarca,
                   COALESCE(oi.predio,eq.predio) AS predio,
                   COALESCE(oi.sala,eq.sala) AS sala,
                   COALESCE(oi.marca,eq.marca) AS marca,
                   c.numero_contrato AS contrato_nome
            FROM ordens_servico os 
            LEFT JOIN equipamentos eq ON os.equipamento_id = eq.id
            LEFT JOIN os_instalacao oi ON oi.os_id = os.id 
            LEFT JOIN contratos c ON COALESCE(os.contrato_id, eq.contrato_id) = c.id
            WHERE os.id = ?
        ''', (os_id,)).fetchone()

        if not os_info:
            conn.close()
            return jsonify({'erro': 'Ordem de Serviço inexistente.'}), 404

        # TRAVA DE CUSTÓDIA FISCAL
        if perfil in ['contratada', 'executante'] and os_info['status'] in ['em_analise', 'concluida', 'cancelada']:
            conn.close()
            return jsonify({'erro': 'Esta O.S. está em validação fiscal ou já encerrada. Nenhuma alteração é permitida até manifestação do Fiscal.'}), 403

        # MÁQUINA DE ESTADOS: só transições previstas no fluxo de governança são aceitas
        status_atual = os_info['status']
        if status_novo not in TRANSICOES_OS:
            conn.close()
            return jsonify({'erro': 'Status informado é inválido.'}), 400
        if status_novo not in TRANSICOES_OS[status_atual]:
            conn.close()
            return jsonify({'erro': f'Transição não permitida: a O.S. está "{status_atual}" e não pode ir para "{status_novo}".'}), 409
        if perfil == 'fiscal' and status_novo == 'em_execucao' and not executante_id and status_atual != 'em_analise':
            conn.close()
            return jsonify({'erro': 'O Fiscal só devolve para retrabalho O.S. que estejam em análise.'}), 409

        # RBAC MULTI-CONTRATOS
        if perfil == 'fiscal':
            tem_contrato = conn.execute("SELECT 1 FROM usuario_contratos WHERE usuario_id = ? AND contrato_id = ?", (uid, os_info['contrato_id'])).fetchone()
            if not tem_contrato:
                conn.close()
                return jsonify({'erro': 'O.S. não pertence a nenhum dos seus contratos.'}), 403
            
            if status_novo not in ['aprovada', 'concluida', 'em_execucao', 'cancelada']:
                conn.close()
                return jsonify({'erro': 'Decisão inválida para o perfil Fiscal.'}), 400

            if status_novo in ['em_execucao', 'cancelada'] and not observacao:
                conn.close()
                return jsonify({'erro': 'A justificativa é obrigatória para devolver ou cancelar a O.S.'}), 400

        elif perfil == 'contratada':
            tem_contrato = conn.execute("SELECT 1 FROM usuario_contratos WHERE usuario_id = ? AND contrato_id = ?", (uid, os_info['contrato_id'])).fetchone()
            if not tem_contrato:
                conn.close()
                return jsonify({'erro': 'O.S. não pertence a nenhum contrato da sua empresa.'}), 403
            if os_info['status'] == 'aberta':
                conn.close()
                return jsonify({'erro': 'Aguarde aprovação prévia do Fiscal.'}), 403
            
            if status_novo not in ['em_execucao', 'aguardando_peca', 'em_analise']:
                conn.close()
                return jsonify({'erro': 'Opção inválida. A finalização do serviço deve ser enviada para validação fiscal.'}), 403

        elif perfil == 'executante':
            if os_info['executante_id'] != uid:
                conn.close()
                return jsonify({'erro': 'Você só pode responder por O.S. designadas a você.'}), 403
            
            if status_novo not in ['aguardando_peca', 'em_analise']:
                conn.close()
                return jsonify({'erro': 'Opção de apontamento inválida. Finalize enviando para validação fiscal.'}), 400

        if os_info['tipo_os'] in ('instalacao','substituicao') and status_novo in ('em_analise','concluida'):
            tombo_final = tombo_novo or (os_info['tombo'] or '')
            fe = foto_evaporadora or os_info['foto_evaporadora']
            fc = foto_condensadora or os_info['foto_condensadora']
            ft = foto_tubulacao or os_info['foto_tubulacao']
            fd = foto_dreno or os_info['foto_dreno']
            arq_os = arquivo_conclusao or os_info['arquivo_os_assinada_original'] or os_info['arquivo_conclusao']
            
            if not tombo_final or tombo_final == 'S/T' or not arq_os or not fe or not fc or not ft or not fd:
                conn.close()
                return jsonify({'erro':'Tombo, 4 fotos obrigatórias (evaporadora, condensadora, tubulação e dreno) e folha de O.S. assinada são obrigatórios.'}), 400
                
            for nome in [x for x in (arquivo_conclusao, fe, fc, ft, fd) if x]:
                if secure_filename(nome) != nome or not os.path.isfile(os.path.join(UPLOAD_FOLDER, nome)):
                    conn.close()
                    return jsonify({'erro':'Anexo de instalação inválido ou inexistente.'}), 400
                    
            dup = conn.execute("SELECT 1 FROM equipamentos WHERE ativo=1 AND UPPER(tombo)=? AND id IS NOT ?",(tombo_final, os_info['equipamento_id'])).fetchone()
            if dup:
                conn.close()
                return jsonify({'erro':'Já existe equipamento ativo com este tombo.'}), 409
                
            arq_original = arquivo_conclusao if arquivo_conclusao else (os_info['arquivo_os_assinada_original'] or arq_os)
            precisa_gerar_pdf = bool(arquivo_conclusao or foto_evaporadora or foto_condensadora or foto_tubulacao or foto_dreno or not os_info['arquivo_conclusao'])
            
            if precisa_gerar_pdf:
                pdf_unificado_nome = f"os_{os_id}_conclusao_completa_{int(time.time())}.pdf"
                pdf_unificado_path = os.path.join(UPLOAD_FOLDER, pdf_unificado_nome)
                dados_relatorio = {
                    'id': os_info['id'],
                    'data_conclusao_str': time.strftime('%d/%m/%Y'),
                    'contrato_str': os_info['contrato_nome'] or (f"Contrato #{os_info['contrato_id']}" if os_info['contrato_id'] else '-'),
                    'comarca': os_info['comarca'] or '-',
                    'predio': os_info['predio'] or '-',
                    'sala': os_info['sala'] or '-',
                    'tipo_equipamento': os_info['tipo_equipamento'] or '',
                    'capacidade': os_info['capacidade'] or '',
                    'marca': os_info['marca'] or '',
                    'tombo': tombo_final
                }
                fotos_dict = {
                    'evaporadora': os.path.join(UPLOAD_FOLDER, fe),
                    'condensadora': os.path.join(UPLOAD_FOLDER, fc),
                    'tubulacao': os.path.join(UPLOAD_FOLDER, ft),
                    'dreno': os.path.join(UPLOAD_FOLDER, fd)
                }
                caminho_os_assinada = os.path.join(UPLOAD_FOLDER, arq_original)
                try:
                    gerar_pdf_conclusao_instalacao(dados_relatorio, caminho_os_assinada, fotos_dict, pdf_unificado_path)
                    arquivo_conclusao = pdf_unificado_nome
                except Exception as e_pdf:
                    print(f"[ERRO-GERAR-PDF-CONCLUSAO] {e_pdf}")
                    if not arquivo_conclusao:
                        arquivo_conclusao = arq_original

            conn.execute('''
                UPDATE os_instalacao 
                SET tombo=?, 
                    foto_evaporadora=COALESCE(?,foto_evaporadora), 
                    foto_condensadora=COALESCE(?,foto_condensadora),
                    foto_tubulacao=COALESCE(?,foto_tubulacao),
                    foto_dreno=COALESCE(?,foto_dreno),
                    arquivo_os_assinada_original=?
                WHERE os_id=?
            ''', (tombo_final, foto_evaporadora, foto_condensadora, foto_tubulacao, foto_dreno, arq_original, os_id))
        if status_novo == 'em_analise' and perfil in ['contratada', 'executante']:
            if not arquivo_conclusao and not os_info['arquivo_conclusao']:
                conn.close()
                return jsonify({'erro': 'O anexo da folha de O.S. assinada é obrigatório.'}), 400

        if arquivo_conclusao:
            if (not isinstance(arquivo_conclusao, str) or secure_filename(arquivo_conclusao) != arquivo_conclusao
                    or not os.path.isfile(os.path.join(UPLOAD_FOLDER, arquivo_conclusao))):
                conn.close()
                return jsonify({'erro': 'Anexo inválido ou inexistente.'}), 400
            if conn.execute("SELECT 1 FROM ordens_servico WHERE arquivo_conclusao = ? AND id != ?", (arquivo_conclusao, os_id)).fetchone():
                conn.close()
                return jsonify({'erro': 'Este anexo já está vinculado a outra O.S.'}), 400

        ts = int(time.time() * 1000)
        acao_hist = f"STATUS_{status_novo.upper()}"

        if status_novo == 'em_execucao' and executante_id:
            tecnico_check = conn.execute('''
                SELECT u.id, u.nome FROM usuarios u
                JOIN usuario_contratos uc ON u.id = uc.usuario_id
                WHERE u.id = ? AND u.perfil = 'executante' AND uc.contrato_id = ? AND u.ativo = 1
            ''', (executante_id, os_info['contrato_id'])).fetchone()
            
            if not tecnico_check and perfil != 'administrador':
                conn.close()
                return jsonify({'erro': 'Técnico executante inválido ou inativo para este contrato específico.'}), 400

            nome_tecnico = tecnico_check['nome'] if tecnico_check else 'TÉCNICO'
            acao_hist = f"DELEGADA: {nome_tecnico}"
            conn.execute("UPDATE ordens_servico SET status = ?, executante_id = ? WHERE id = ?", (status_novo, executante_id, os_id))

        elif status_novo == 'em_execucao' and perfil == 'fiscal':
            acao_hist = "DEVOLVIDA_PARA_COMPLEMENTACAO"
            conn.execute("UPDATE ordens_servico SET status = ? WHERE id = ?", (status_novo, os_id))

        elif status_novo == 'aprovada' and perfil == 'fiscal':
            acao_hist = "APROVADA_PELO_FISCAL"
            conn.execute("UPDATE ordens_servico SET status = ?, fiscal_id = ? WHERE id = ?", (status_novo, uid, os_id))
        elif status_novo == 'em_analise':
            acao_hist = "ENVIADA_PARA_VALIDACAO_FISCAL"
            conn.execute("UPDATE ordens_servico SET status = ?, arquivo_conclusao = COALESCE(?, arquivo_conclusao) WHERE id = ?", 
                         (status_novo, arquivo_conclusao, os_id))

        elif status_novo == 'concluida' and os_info['tipo_os'] in ('instalacao','substituicao'):
            if perfil != 'fiscal': conn.close(); return jsonify({'erro':'Somente o fiscal homologa instalações.'}),403
            inst=conn.execute('SELECT * FROM os_instalacao WHERE os_id=?',(os_id,)).fetchone()
            if inst['equipamento_novo_id']: conn.close(); return jsonify({'erro':'Instalação já homologada.'}),409
            
            # Verificar se o tombo já existe no sistema (reativação com histórico preservado)
            tombo_limpo = (inst['tombo'] or '').strip()
            eq_existente = None
            if tombo_limpo and tombo_limpo.upper() != 'S/T':
                eq_existente = conn.execute(
                    "SELECT id FROM equipamentos WHERE UPPER(TRIM(tombo)) = ? ORDER BY id DESC LIMIT 1",
                    (tombo_limpo.upper(),)
                ).fetchone()
            
            if eq_existente:
                novo_id = eq_existente['id']
                conn.execute('''
                    UPDATE equipamentos 
                    SET comarca=?, predio=?, sala=?, tipo_equipamento=?, capacidade=?, marca=?, tombo=?, contrato_id=?, status_equipamento='ATIVO', ativo=1 
                    WHERE id=?
                ''', (inst['comarca'].strip().upper(), inst['predio'].strip().upper(), inst['sala'].strip().upper(),
                      inst['tipo_equipamento'].strip().upper(), (inst['capacidade'] or '').strip().upper(),
                      (inst['marca'] or '').strip().upper(), tombo_limpo.upper(), os_info['contrato_id'], novo_id))
            else:
                cur=conn.execute(
                    "INSERT INTO equipamentos(comarca,predio,sala,tipo_equipamento,capacidade,marca,tombo,contrato_id,status_equipamento,ativo) VALUES(?,?,?,?,?,?,?,?,'ATIVO',1)",
                    (inst['comarca'].strip().upper(), inst['predio'].strip().upper(), inst['sala'].strip().upper(),
                     inst['tipo_equipamento'].strip().upper(), (inst['capacidade'] or '').strip().upper(),
                     (inst['marca'] or '').strip().upper(), (tombo_limpo.upper() if tombo_limpo else 'S/T'), os_info['contrato_id'])
                )
                novo_id=cur.lastrowid
            
            sincronizar_calendario_equipamento(novo_id, conn)
            conn.execute('UPDATE os_instalacao SET equipamento_novo_id=? WHERE os_id=?',(novo_id,os_id))
            if os_info['tipo_os']=='substituicao':
                conn.execute("UPDATE equipamentos SET ativo=0,status_equipamento='SUBSTITUIDO' WHERE id=?",(os_info['equipamento_id'],))
                acao_hist='SUBSTITUICAO_HOMOLOGADA'
            else:
                conn.execute("UPDATE ordens_servico SET equipamento_id=? WHERE id=?",(novo_id,os_id))
                acao_hist='INSTALACAO_HOMOLOGADA'
            conn.execute("UPDATE ordens_servico SET status='concluida',data_conclusao=? WHERE id=?",(ts,os_id))
        elif status_novo == 'concluida':
            acao_hist = "CONCLUIDA_E_HOMOLOGADA"
            conn.execute("UPDATE ordens_servico SET status = ?, data_conclusao = ?, arquivo_conclusao = COALESCE(?, arquivo_conclusao) WHERE id = ?", 
                         (status_novo, ts, arquivo_conclusao, os_id))
        else:
            conn.execute("UPDATE ordens_servico SET status = ? WHERE id = ?", (status_novo, os_id))

        conn.execute("INSERT INTO historico_os (os_id, usuario_id, data_registro, acao, observacao) VALUES (?, ?, ?, ?, ?)", 
                     (os_id, uid, ts, acao_hist, observacao))
        conn.commit()
        conn.close()
        return jsonify({"mensagem": "Status atualizado com sucesso!"}), 200
    except Exception as e: 
        return erro_interno(e)

# ================= EMISSÃO DE PDF OFICIAL SGME (XXXX.MM.AAAA) =================
@app.route('/api/os/<int:os_id>/pdf', methods=['GET'])
@valida_token
def gerar_pdf_os_endpoint(usuario_atual, os_id):
    try:
        conn = get_db_connection()
        perfil = usuario_atual['perfil']
        uid = usuario_atual['id']

        os_info = conn.execute('''
            SELECT os.*, COALESCE(oi.tipo_equipamento,eq.tipo_equipamento) AS tipo_equipamento, COALESCE(oi.capacidade,eq.capacidade) AS capacidade, COALESCE(oi.comarca,eq.comarca) AS comarca, COALESCE(oi.predio,eq.predio) AS predio, COALESCE(oi.sala,eq.sala) AS sala, COALESCE(oi.tombo,eq.tombo) AS tombo, COALESCE(os.contrato_id,eq.contrato_id) AS contrato_id, COALESCE(oi.marca,eq.marca) AS marca, oi.foto_evaporadora, oi.foto_condensadora, oi.foto_tubulacao, oi.foto_dreno, oi.arquivo_os_assinada_original, oi.equipamento_novo_id,
                   u.nome as nome_solicitante, ex.nome as nome_executante, c.numero_contrato as contrato_nome
            FROM ordens_servico os 
            LEFT JOIN equipamentos eq ON os.equipamento_id = eq.id
            LEFT JOIN os_instalacao oi ON oi.os_id = os.id 
            JOIN usuarios u ON os.solicitante_id = u.id 
            LEFT JOIN usuarios ex ON os.executante_id = ex.id
            LEFT JOIN contratos c ON COALESCE(os.contrato_id, eq.contrato_id) = c.id
            WHERE os.id = ?
        ''', (os_id,)).fetchone()
        
        if not os_info: 
            conn.close()
            return jsonify({"erro": "O.S. não encontrada."}), 404

        if perfil == 'solicitante' and os_info['solicitante_id'] != uid:
            conn.close()
            return jsonify({'erro': 'Acesso negado.'}), 403
        elif perfil in ['fiscal', 'contratada']:
            tem_contrato = conn.execute("SELECT 1 FROM usuario_contratos WHERE usuario_id = ? AND contrato_id = ?", (uid, os_info['contrato_id'])).fetchone()
            if not tem_contrato:
                conn.close()
                return jsonify({'erro': 'Acesso negado a este contrato.'}), 403
        elif perfil == 'executante' and os_info['executante_id'] != uid:
            conn.close()
            return jsonify({'erro': 'Acesso negado.'}), 403

        historico = conn.execute('''
            SELECT h.*, u.nome as nome_usuario 
            FROM historico_os h JOIN usuarios u ON h.usuario_id = u.id 
            WHERE h.os_id = ? ORDER BY h.data_registro ASC
        ''', (os_id,)).fetchall()
        conn.close()

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=12*2.83, rightMargin=12*2.83, topMargin=12*2.83, bottomMargin=12*2.83)
        styles = getSampleStyleSheet()

        style_title = ParagraphStyle('DocTitle', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, leading=12, alignment=1)
        style_sub = ParagraphStyle('DocSub', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8.5, leading=11, alignment=1)
        style_top_right = ParagraphStyle('TopRight', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, leading=12, alignment=2)
        style_hdr = ParagraphStyle('SecHeader', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=8, leading=10, alignment=1, textColor=colors.black)
        style_lbl = ParagraphStyle('ColLabel', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=7.5, leading=9, alignment=1)
        style_val = ParagraphStyle('ColVal', parent=styles['Normal'], fontName='Helvetica', fontSize=7.5, leading=9, alignment=1)
        style_hist = ParagraphStyle('HistTxt', parent=styles['Normal'], fontName='Helvetica', fontSize=7, leading=8.5)

        dt_abertura = datetime.fromtimestamp(os_info['data_abertura'] / 1000)
        seq_formatado = f"{int(os_info['id']):04d}"
        mes_formatado = dt_abertura.strftime('%m')
        ano_formatado = dt_abertura.strftime('%Y')
        num_os_fmt = f"{seq_formatado}.{mes_formatado}.{ano_formatado}"

        dt_inicio_fmt = dt_abertura.strftime('%d/%m/%Y')
        dt_concl_fmt = datetime.fromtimestamp(os_info['data_conclusao'] / 1000).strftime('%d/%m/%Y') if os_info['data_conclusao'] else '-'
        
        dt_aprov_fmt = '-'
        for h in historico:
            if 'APROVADA' in (h['acao'] or ''):
                dt_aprov_fmt = datetime.fromtimestamp(h['data_registro'] / 1000).strftime('%d/%m/%Y')
                break

        tipo_rotulo = {'manutencao':'Manutenção de Equipamento','instalacao':'Instalação de Equipamento','substituicao':'Substituição de Equipamento'}.get(os_info['tipo_os'],'Manutenção de Equipamento')
        marca_txt = (os_info['marca'] or '').strip()
        desc_completa = f"Ar-condicionado {marca_txt} {os_info['tipo_equipamento']} {os_info['capacidade'] or ''} {('tombo ' + os_info['tombo']) if os_info['tombo'] and os_info['tombo'] != 'S/T' else ''}. {os_info['descricao_falha']}".replace('  ',' ')

        elements = []

        elements.append(Paragraph(f"<b>{num_os_fmt}</b>", style_top_right))
        elements.append(Spacer(1, 4))

        data_tab1 = [
            [Paragraph("ESTADO DO CEARÁ - PODER JUDICIÁRIO", style_title), ""],
            [Paragraph("TRIBUNAL DE JUSTIÇA - GERÊNCIA DE MANUTENÇÃO E ZELADORIA", style_sub), ""],
            [Paragraph("Nº da OS", style_lbl), Paragraph(f"<b>{num_os_fmt}</b>", style_val)],
            [Paragraph("ATENDENTE", style_lbl), Paragraph(html_esc(os_info['nome_solicitante'] or '-'), style_val)],
            [Paragraph("MATRÍCULA DO ATENDENTE", style_lbl), Paragraph("-", style_val)],
            [Paragraph("LOCALIZAÇÃO", style_hdr), ""],
            [Paragraph("REQUISITANTE", style_lbl), Paragraph(html_esc(os_info['nome_solicitante'] or '-'), style_val)],
            [Paragraph("MATRÍCULA DO REQUISITANTE", style_lbl), Paragraph("-", style_val)],
            [Paragraph("TELEFONE / RAMAL CONTATO", style_lbl), Paragraph("0", style_val)],
            [Paragraph("LOTAÇÃO", style_lbl), Paragraph(html_esc(os_info['sala'] or '-'), style_val)],
            [Paragraph("MUNICÍPIO", style_lbl), Paragraph(html_esc(os_info['comarca'] or '-'), style_val)],
            [Paragraph("REGIÃO", style_lbl), Paragraph("Região I", style_val)],
            [Paragraph("PRÉDIO", style_lbl), Paragraph(html_esc(os_info['predio'] or '-'), style_val)],
            [Paragraph("LOCAL DE OCORRÊNCIA", style_lbl), Paragraph(html_esc(os_info['sala'] or '-'), style_val)],
            [Paragraph("TIPO DE SOLICITAÇÃO", style_lbl), Paragraph(tipo_rotulo, style_val)],
            [Paragraph("SERVIÇO", style_lbl), Paragraph("Climatização", style_val)],
            [Paragraph("CPA / TOMBO", style_lbl), Paragraph(f"<b>{html_esc(os_info['tombo'] or 'S/T')}</b>", style_val)],
            [Paragraph("PRIORIDADE", style_lbl), Paragraph("Não Emergencial", style_val)],
            [Paragraph("FORNECEDOR", style_lbl), Paragraph(html_esc(os_info['contrato_nome'] or '-'), style_val)],
            [Paragraph("DESCRIÇÃO", style_lbl), Paragraph(html_esc(desc_completa), style_val)],
            [Paragraph("DATA DE APROVAÇÃO", style_lbl), Paragraph(dt_aprov_fmt, style_val)],
            [Paragraph("DATA DE INÍCIO", style_lbl), Paragraph(dt_inicio_fmt, style_val)],
            [Paragraph("DATA DE CONCLUSÃO", style_lbl), Paragraph(dt_concl_fmt, style_val)]
        ]

        t1 = Table(data_tab1, colWidths=[65*2.83, 115*2.83])
        t1.setStyle(TableStyle([
            ('SPAN', (0, 0), (1, 0)),
            ('SPAN', (0, 1), (1, 1)),
            ('SPAN', (0, 5), (1, 5)),
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('BACKGROUND', (0, 5), (1, 5), colors.HexColor('#f1f5f9')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        elements.append(t1)

        hist_paragraphs = []
        for h in historico:
            dt_h = datetime.fromtimestamp(h['data_registro'] / 1000).strftime('%d/%m/%Y %H:%M')
            u_nome = html_esc(h['nome_usuario'] or '')
            u_acao = html_esc(h['acao'] or '')
            u_obs = html_esc(h['observacao'] or '')
            hist_paragraphs.append(Paragraph(f"<b>{dt_h} - {u_nome} ({u_acao}):</b> {u_obs}", style_hist))

        data_tab2 = [
            [Paragraph("DESCRIÇÃO DETALHADA", style_hdr)],
            [Paragraph(html_esc(desc_completa), style_val)],
            [Paragraph("HISTÓRICO DO CHAMADO", style_hdr)],
            [hist_paragraphs if hist_paragraphs else Paragraph("Nenhum histórico.", style_val)]
        ]

        t2 = Table(data_tab2, colWidths=[180*2.83])
        t2.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#f1f5f9')),
            ('BACKGROUND', (0, 2), (0, 2), colors.HexColor('#f1f5f9')),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        elements.append(t2)

        solic_nome = html_esc(os_info['nome_solicitante'] or '-')
        exec_nome = html_esc(os_info['nome_executante'] or 'NÃO DESIGNADO')
        
        data_tab3 = [
            [Paragraph("ATENDENTE", style_hdr), Paragraph("EXECUTOR / TÉCNICO", style_hdr)],
            [
                Paragraph(f"<b>Nome:</b> {solic_nome}<br/><br/><b>Assinatura:</b> ___________________________", style_val),
                Paragraph(f"<b>Nome:</b> {exec_nome}<br/><br/><b>Assinatura:</b> ___________________________", style_val)
            ]
        ]

        t3 = Table(data_tab3, colWidths=[90*2.83, 90*2.83])
        t3.setStyle(TableStyle([
            ('BOX', (0, 0), (-1, -1), 1, colors.black),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#f1f5f9')),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(t3)

        elements.append(Spacer(1, 6))
        elements.append(Paragraph(f"<b>Nº da OS: {num_os_fmt}</b>", style_top_right))

        doc.build(elements)
        buffer.seek(0)

        filename = f"OS_{num_os_fmt}.pdf"
        response = send_file(buffer, mimetype='application/pdf', as_attachment=False, download_name=filename)
        response.headers['X-Filename'] = filename
        response.headers['Access-Control-Expose-Headers'] = 'Content-Disposition, X-Filename'
        return response
    except Exception as e:
        return erro_interno(e, 'Falha ao gerar o PDF.')

# ================= GESTÃO DE PMOC / MANUTENÇÕES PREVENTIVAS =================
from pmoc_pdf import gerar_pdf_pmoc_buffer, gerar_pdf_relatorio_ciclo_buffer

@app.route('/api/pmoc/catalogo', methods=['GET'])
@valida_token
def obter_catalogo_pmoc(usuario_atual):
    try:
        tipo = request.args.get('tipo_equipamento', 'DOMESTICO')
        periodicidade = request.args.get('periodicidade', 'M')
        itens = obter_checklist_padrao(tipo, periodicidade)
        categoria = determinar_categoria(tipo)
        return jsonify({'categoria': categoria, 'periodicidade': periodicidade.upper(), 'itens': itens}), 200
    except Exception as e:
        return erro_interno(e)


@app.route('/api/pmoc/ciclos', methods=['GET'])
@valida_token
def listar_ciclos_pmoc(usuario_atual):
    try:
        conn = get_db_connection()
        perfil, uid = usuario_atual['perfil'], usuario_atual['id']

        query = '''
            SELECT c.*, ct.numero_contrato, ct.nome_empresa, u.nome AS criado_por_nome,
                   (SELECT COUNT(*) FROM pmoc_manutencoes WHERE ciclo_id = c.id) AS total_manutencoes,
                   (SELECT COUNT(*) FROM pmoc_manutencoes WHERE ciclo_id = c.id AND status = 'pendente') AS pendentes,
                   (SELECT COUNT(*) FROM pmoc_manutencoes WHERE ciclo_id = c.id AND status = 'em_execucao') AS em_execucao,
                   (SELECT COUNT(*) FROM pmoc_manutencoes WHERE ciclo_id = c.id AND status = 'em_analise') AS em_analise,
                   (SELECT COUNT(*) FROM pmoc_manutencoes WHERE ciclo_id = c.id AND status = 'concluida') AS concluidas,
                   (SELECT COUNT(*) FROM pmoc_manutencoes WHERE ciclo_id = c.id AND status = 'reprovada') AS reprovadas,
                   (SELECT COUNT(*) FROM pmoc_manutencoes WHERE ciclo_id = c.id AND status = 'cancelada') AS canceladas
            FROM pmoc_ciclos c
            JOIN contratos ct ON c.contrato_id = ct.id
            JOIN usuarios u ON c.criado_por = u.id
            WHERE 1=1
        '''
        params = []
        if perfil in ('fiscal', 'contratada', 'executante'):
            query += " AND c.contrato_id IN (SELECT contrato_id FROM usuario_contratos WHERE usuario_id = ?) "
            params.append(uid)
            if perfil == 'fiscal':
                query += " AND EXISTS (SELECT 1 FROM pmoc_manutencoes pm WHERE pm.ciclo_id = c.id AND pm.status IN ('concluida', 'reprovada')) "
        elif perfil != 'administrador':
            conn.close()
            return jsonify({'erro': 'Perfil não autorizado.'}), 403

        query += " ORDER BY c.ano DESC, c.mes DESC, c.id DESC "
        ciclos = conn.execute(query, params).fetchall()
        conn.close()
        return jsonify([dict(c) for c in ciclos]), 200
    except Exception as e:
        return erro_interno(e)


@app.route('/api/pmoc/ciclos', methods=['POST'])
@valida_token
def criar_ciclo_pmoc(usuario_atual):
    try:
        perfil, uid = usuario_atual['perfil'], usuario_atual['id']
        if perfil not in ('administrador', 'fiscal'):
            return jsonify({'erro': 'Apenas o Fiscal ou Administrador podem programar ciclos de PMOC.'}), 403

        dados = request.get_json(silent=True) or {}
        contrato_id = dados.get('contrato_id')
        ano = int(dados.get('ano') or datetime.now().year)
        mes = int(dados.get('mes') or datetime.now().month)
        periodicidade = str(dados.get('periodicidade', 'M')).strip().upper()
        descricao = dados.get('descricao', '').strip().upper()
        comarca_filtro = str(dados.get('comarca', '')).strip().upper()
        predio_filtro = str(dados.get('predio', '')).strip().upper()

        if not contrato_id or periodicidade not in ('M', 'T', 'S', 'A') or mes < 1 or mes > 12:
            return jsonify({'erro': 'Contrato, mês (1-12) e periodicidade válida (M, T, S, A) são obrigatórios.'}), 400

        conn = get_db_connection()
        if perfil == 'fiscal':
            pertence = conn.execute("SELECT 1 FROM usuario_contratos WHERE usuario_id = ? AND contrato_id = ?",
                                    (uid, contrato_id)).fetchone()
            if not pertence:
                conn.close()
                return jsonify({'erro': 'Contrato não autorizado para o seu perfil.'}), 403

        contrato = conn.execute("SELECT numero_contrato, nome_empresa FROM contratos WHERE id = ?", (contrato_id,)).fetchone()
        if not contrato:
            conn.close()
            return jsonify({'erro': 'Contrato inexistente.'}), 404

        rotulo_period = {'M': 'MENSAL', 'T': 'TRIMESTRAL', 'S': 'SEMESTRAL', 'A': 'ANUAL'}.get(periodicidade, 'MENSAL')
        if not descricao:
            descricao = f"PMOC {rotulo_period} - {mes:02d}/{ano} - {contrato['numero_contrato']}"

        ts = int(time.time() * 1000)

        ciclo = conn.execute("SELECT id FROM pmoc_ciclos WHERE contrato_id = ? AND ano = ? AND mes = ? AND periodicidade = ?",
                            (contrato_id, ano, mes, periodicidade)).fetchone()
        if ciclo:
            ciclo_id = ciclo['id']
        else:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO pmoc_ciclos (contrato_id, ano, mes, periodicidade, descricao, criado_em, criado_por, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'em_andamento')
            """, (contrato_id, ano, mes, periodicidade, descricao, ts, uid))
            ciclo_id = cur.lastrowid

        query_eq = "SELECT id, tipo_equipamento FROM equipamentos WHERE contrato_id = ? AND ativo = 1"
        params_eq = [contrato_id]
        if comarca_filtro:
            query_eq += " AND comarca = ?"
            params_eq.append(comarca_filtro)
        if predio_filtro:
            query_eq += " AND predio = ?"
            params_eq.append(predio_filtro)

        eqs = conn.execute(query_eq, params_eq).fetchall()
        if not eqs:
            conn.close()
            return jsonify({'erro': 'Nenhum equipamento ativo encontrado para os filtros informados.'}), 400

        novos_count = 0
        cur = conn.cursor()
        for eq in eqs:
            eq_id = eq['id']
            ja_existe = conn.execute("""
                SELECT 1 FROM pmoc_manutencoes 
                WHERE equipamento_id = ? AND ano_competencia = ? AND mes_competencia = ? AND periodicidade = ? AND status != 'cancelada'
            """, (eq_id, ano, mes, periodicidade)).fetchone()
            if not ja_existe:
                cur.execute("""
                    INSERT INTO pmoc_manutencoes (ciclo_id, contrato_id, equipamento_id, periodicidade, mes_competencia, ano_competencia, data_geracao, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'pendente')
                """, (ciclo_id, contrato_id, eq_id, periodicidade, mes, ano, ts))
                pmoc_id = cur.lastrowid
                cur.execute("INSERT INTO historico_pmoc (manutencao_id, usuario_id, data_registro, acao, observacao) VALUES (?, ?, ?, ?, ?)",
                            (pmoc_id, uid, ts, "CRIADA_NO_CICLO", f"PROGRAMAÇÃO PREVENTIVA GERADA NO CICLO {mes:02d}/{ano}"))
                novos_count += 1

        conn.commit()
        conn.close()
        return jsonify({
            'mensagem': f'Ciclo programado com sucesso! {novos_count} preventivas geradas.',
            'ciclo_id': ciclo_id,
            'novos_gerados': novos_count,
            'total_equipamentos_alvo': len(eqs)
        }), 201
    except Exception as e:
        return erro_interno(e)


@app.route('/api/pmoc/manutencoes', methods=['GET'])
@valida_token
def listar_manutencoes_pmoc(usuario_atual):
    try:
        conn = get_db_connection()
        perfil, uid = usuario_atual['perfil'], usuario_atual['id']

        query = '''
            SELECT p.*,
                   COALESCE(p.comarca, e.comarca) AS comarca,
                   e.predio, e.sala, e.tombo, e.tipo_equipamento, e.marca, e.capacidade,
                   c.numero_contrato, c.nome_empresa,
                   COALESCE(p.total_equipamentos, (SELECT COUNT(*) FROM pmoc_manutencao_equipamentos WHERE manutencao_id = p.id), 1) AS total_equipamentos,
                   ex.nome AS nome_executante, fi.nome AS nome_fiscal
            FROM pmoc_manutencoes p
            LEFT JOIN equipamentos e ON p.equipamento_id = e.id
            JOIN contratos c ON p.contrato_id = c.id
            LEFT JOIN usuarios ex ON p.executante_id = ex.id
            LEFT JOIN usuarios fi ON p.fiscal_id = fi.id
            WHERE 1=1
        '''
        params = []

        if perfil == 'fiscal':
            query += " AND p.contrato_id IN (SELECT contrato_id FROM usuario_contratos WHERE usuario_id = ?) "
            params.append(uid)
            # Não deve haver O.S. de PMOC pendente para o Fiscal: exibe apenas as concluídas (com comprovação) ou reprovadas na fiscalização
            query += " AND p.status IN ('concluida', 'reprovada') "
        elif perfil == 'contratada':
            query += " AND p.contrato_id IN (SELECT contrato_id FROM usuario_contratos WHERE usuario_id = ?) "
            params.append(uid)
        elif perfil == 'executante':
            query += " AND (p.executante_id = ? OR (p.executante_id IS NULL AND p.contrato_id IN (SELECT contrato_id FROM usuario_contratos WHERE usuario_id = ?))) "
            params.extend([uid, uid])
        elif perfil not in ('administrador', 'solicitante'):
            conn.close()
            return jsonify({'erro': 'Perfil não autorizado.'}), 403

        contrato_id = request.args.get('contrato_id')
        if contrato_id:
            query += " AND p.contrato_id = ?"
            params.append(int(contrato_id))

        ciclo_id = request.args.get('ciclo_id')
        if ciclo_id:
            if '/' in str(ciclo_id):
                partes = str(ciclo_id).split('/')
                if len(partes) == 2 and partes[0].isdigit() and partes[1].isdigit():
                    query += " AND p.mes_competencia = ? AND p.ano_competencia = ?"
                    params.extend([int(partes[0]), int(partes[1])])
            elif '-' in str(ciclo_id):
                partes = str(ciclo_id).split('-')
                if len(partes) == 2 and partes[0].isdigit() and partes[1].isdigit():
                    query += " AND p.ano_competencia = ? AND p.mes_competencia = ?"
                    params.extend([int(partes[0]), int(partes[1])])
            elif str(ciclo_id) in ('M', 'T', 'S', 'A'):
                query += " AND p.periodicidade = ?"
                params.append(str(ciclo_id))
            elif str(ciclo_id).isdigit():
                query += " AND p.ciclo_id = ?"
                params.append(int(ciclo_id))

        competencia = request.args.get('competencia')
        if competencia:
            if '/' in str(competencia):
                partes = str(competencia).split('/')
                if len(partes) == 2 and partes[0].isdigit() and partes[1].isdigit():
                    query += " AND p.mes_competencia = ? AND p.ano_competencia = ?"
                    params.extend([int(partes[0]), int(partes[1])])
            elif '-' in str(competencia):
                partes = str(competencia).split('-')
                if len(partes) == 2 and partes[0].isdigit() and partes[1].isdigit():
                    query += " AND p.ano_competencia = ? AND p.mes_competencia = ?"
                    params.extend([int(partes[0]), int(partes[1])])

        periodicidade_req = request.args.get('periodicidade')
        if periodicidade_req and periodicidade_req.strip().upper() in ('M', 'T', 'S', 'A'):
            query += " AND p.periodicidade = ?"
            params.append(periodicidade_req.strip().upper())

        status_req = request.args.get('status')
        if status_req:
            query += " AND p.status = ?"
            params.append(status_req)

        mes = request.args.get('mes')
        if mes and str(mes).isdigit():
            query += " AND p.mes_competencia = ?"
            params.append(int(mes))

        ano = request.args.get('ano')
        if ano and str(ano).isdigit():
            query += " AND p.ano_competencia = ?"
            params.append(int(ano))

        comarca = request.args.get('comarca')
        if comarca:
            query += " AND e.comarca = ?"
            params.append(comarca.strip().upper())

        predio = request.args.get('predio')
        if predio:
            query += " AND e.predio = ?"
            params.append(predio.strip().upper())

        equipamento_id = request.args.get('equipamento_id')
        if equipamento_id:
            query += " AND p.equipamento_id = ?"
            params.append(int(equipamento_id))

        query += " ORDER BY p.ano_competencia DESC, p.mes_competencia DESC, p.id DESC "
        manutencoes = conn.execute(query, params).fetchall()
        conn.close()
        return jsonify([dict(m) for m in manutencoes]), 200
    except Exception as e:
        return erro_interno(e)


@app.route('/api/pmoc/manutencoes/avulsa', methods=['POST'])
@valida_token
def criar_manutencao_avulsa(usuario_atual):
    try:
        perfil, uid = usuario_atual['perfil'], usuario_atual['id']
        if perfil not in ('administrador', 'fiscal', 'contratada'):
            return jsonify({'erro': 'Acesso negado.'}), 403

        dados = request.get_json(silent=True) or {}
        eq_id = dados.get('equipamento_id')
        periodicidade = str(dados.get('periodicidade', 'M')).strip().upper()
        mes = int(dados.get('mes_competencia') or datetime.now().month)
        ano = int(dados.get('ano_competencia') or datetime.now().year)
        obs = dados.get('observacoes', '').strip().upper()

        if not eq_id or periodicidade not in ('M', 'T', 'S', 'A'):
            return jsonify({'erro': 'Equipamento e periodicidade são obrigatórios.'}), 400

        conn = get_db_connection()
        eq = conn.execute("SELECT id, contrato_id, ativo FROM equipamentos WHERE id = ?", (eq_id,)).fetchone()
        if not eq or eq['ativo'] != 1:
            conn.close()
            return jsonify({'erro': 'Equipamento inválido ou inativo.'}), 400

        if perfil in ('fiscal', 'contratada'):
            pertence = conn.execute("SELECT 1 FROM usuario_contratos WHERE usuario_id = ? AND contrato_id = ?",
                                    (uid, eq['contrato_id'])).fetchone()
            if not pertence:
                conn.close()
                return jsonify({'erro': 'Equipamento não pertence aos seus contratos.'}), 403

        ts = int(time.time() * 1000)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO pmoc_manutencoes (ciclo_id, contrato_id, equipamento_id, periodicidade, mes_competencia, ano_competencia, data_geracao, status, observacoes_execucao)
            VALUES (NULL, ?, ?, ?, ?, ?, ?, 'pendente', ?)
        """, (eq['contrato_id'], eq_id, periodicidade, mes, ano, ts, obs or None))
        pmoc_id = cur.lastrowid

        cur.execute("INSERT INTO historico_pmoc (manutencao_id, usuario_id, data_registro, acao, observacao) VALUES (?, ?, ?, ?, ?)",
                    (pmoc_id, uid, ts, "CRIACAO_AVULSA", f"PREVENTIVA AVULSA CRIADA POR {usuario_atual['nome']}"))
        conn.commit()
        conn.close()
        return jsonify({'mensagem': 'Manutenção preventiva avulsa registrada!', 'pmoc_id': pmoc_id}), 201
    except Exception as e:
        return erro_interno(e)


@app.route('/api/pmoc/manutencoes/<int:pmoc_id>', methods=['GET'])
@valida_token
def obter_detalhes_pmoc(usuario_atual, pmoc_id):
    try:
        conn = get_db_connection()
        pmoc_info = conn.execute('''
            SELECT p.*,
                   e.comarca, e.predio, e.sala, e.tombo, e.tipo_equipamento, e.marca, e.capacidade,
                   c.numero_contrato, c.nome_empresa, c.cnpj AS cnpj_empresa,
                   ex.nome AS nome_executante, fi.nome AS nome_fiscal
            FROM pmoc_manutencoes p
            JOIN equipamentos e ON p.equipamento_id = e.id
            JOIN contratos c ON p.contrato_id = c.id
            LEFT JOIN usuarios ex ON p.executante_id = ex.id
            LEFT JOIN usuarios fi ON p.fiscal_id = fi.id
            WHERE p.id = ?
        ''', (pmoc_id,)).fetchone()

        if not pmoc_info:
            conn.close()
            return jsonify({'erro': 'Manutenção preventiva não encontrada.'}), 404

        if not pode_acessar_pmoc(conn, usuario_atual, pmoc_info):
            conn.close()
            return jsonify({'erro': 'Acesso negado a esta manutenção preventiva.'}), 403

        respostas = conn.execute('''
            SELECT item_codigo, item_descricao, grupo, status_item, observacao
            FROM pmoc_checklist_respostas
            WHERE manutencao_id = ?
            ORDER BY id ASC
        ''', (pmoc_id,)).fetchall()

        checklist = [dict(r) for r in respostas]
        if not checklist:
            padrao = obter_checklist_padrao(pmoc_info['tipo_equipamento'], pmoc_info['periodicidade'])
            checklist = [{
                'item_codigo': it['codigo'],
                'item_descricao': it['descricao'],
                'grupo': it['grupo'],
                'status_item': 'conforme',
                'observacao': ''
            } for it in padrao]

        # Buscar lista de equipamentos atendidos nesta ordem aglutinada
        eqs_rows = conn.execute('''
            SELECT e.id, e.tombo, e.comarca, e.predio, e.sala, e.tipo_equipamento, e.marca, e.capacidade,
                   pme.status_item, pme.tensao_medida, pme.corrente_medida, pme.temperatura_insuflamento, pme.temperatura_retorno, pme.observacao
            FROM pmoc_manutencao_equipamentos pme
            JOIN equipamentos e ON pme.equipamento_id = e.id
            WHERE pme.manutencao_id = ?
            ORDER BY e.predio, e.sala, e.tombo
        ''', (pmoc_id,)).fetchall()

        equipamentos_os = [dict(eq_r) for eq_r in eqs_rows]
        pmoc_info = dict(pmoc_info)
        if not equipamentos_os and pmoc_info.get('equipamento_id'):
            equipamentos_os = [{
                'id': pmoc_info['equipamento_id'],
                'tombo': pmoc_info['tombo'],
                'comarca': pmoc_info['comarca'],
                'predio': pmoc_info['predio'],
                'sala': pmoc_info['sala'],
                'tipo_equipamento': pmoc_info['tipo_equipamento'],
                'marca': pmoc_info['marca'],
                'capacidade': pmoc_info['capacidade'],
                'status_item': pmoc_info['status'],
                'tensao_medida': pmoc_info['tensao_medida'],
                'corrente_medida': pmoc_info['corrente_medida'],
                'temperatura_insuflamento': pmoc_info['temperatura_insuflamento'],
                'temperatura_retorno': pmoc_info['temperatura_retorno'],
                'observacao': pmoc_info['observacoes_execucao']
            }]

        historico = conn.execute('''
            SELECT h.*, u.nome AS nome_usuario
            FROM historico_pmoc h
            JOIN usuarios u ON h.usuario_id = u.id
            WHERE h.manutencao_id = ?
            ORDER BY h.data_registro ASC
        ''', (pmoc_id,)).fetchall()

        conn.close()
        return jsonify({
            'pmoc': dict(pmoc_info),
            'equipamentos': equipamentos_os,
            'checklist': checklist,
            'historico': [dict(h) for h in historico]
        }), 200
    except Exception as e:
        return erro_interno(e)


@app.route('/api/pmoc/manutencoes/<int:pmoc_id>/delegar', methods=['PUT'])
@valida_token
def delegar_pmoc(usuario_atual, pmoc_id):
    try:
        perfil, uid = usuario_atual['perfil'], usuario_atual['id']
        if perfil not in ('administrador', 'fiscal', 'contratada'):
            return jsonify({'erro': 'Acesso negado.'}), 403

        dados = request.get_json(silent=True) or {}
        executante_id = dados.get('executante_id')
        if not executante_id:
            return jsonify({'erro': 'Selecione o técnico executante.'}), 400

        conn = get_db_connection()
        pmoc_info = conn.execute("SELECT * FROM pmoc_manutencoes WHERE id = ?", (pmoc_id,)).fetchone()
        if not pmoc_info:
            conn.close()
            return jsonify({'erro': 'Preventiva não encontrada.'}), 404

        if perfil in ('fiscal', 'contratada'):
            pertence = conn.execute("SELECT 1 FROM usuario_contratos WHERE usuario_id = ? AND contrato_id = ?",
                                    (uid, pmoc_info['contrato_id'])).fetchone()
            if not pertence:
                conn.close()
                return jsonify({'erro': 'Contrato não autorizado.'}), 403

        tec = conn.execute('''
            SELECT u.id, u.nome FROM usuarios u
            JOIN usuario_contratos uc ON u.id = uc.usuario_id
            WHERE u.id = ? AND u.perfil = 'executante' AND uc.contrato_id = ? AND u.ativo = 1
        ''', (executante_id, pmoc_info['contrato_id'])).fetchone()
        if not tec and perfil != 'administrador':
            conn.close()
            return jsonify({'erro': 'Técnico inválido ou não vinculado ao contrato.'}), 400

        ts = int(time.time() * 1000)
        novo_status = 'em_execucao' if pmoc_info['status'] == 'pendente' else pmoc_info['status']
        conn.execute("UPDATE pmoc_manutencoes SET executante_id = ?, status = ? WHERE id = ?",
                     (executante_id, novo_status, pmoc_id))
        nome_tec = tec['nome'] if tec else 'TÉCNICO'
        conn.execute("INSERT INTO historico_pmoc (manutencao_id, usuario_id, data_registro, acao, observacao) VALUES (?, ?, ?, ?, ?)",
                     (pmoc_id, uid, ts, f"DELEGADA: {nome_tec}", f"DESIGNADA AO TÉCNICO {nome_tec}"))
        conn.commit()
        conn.close()
        return jsonify({'mensagem': f'Preventiva designada para {nome_tec}!'}), 200
    except Exception as e:
        return erro_interno(e)


@app.route('/api/pmoc/manutencoes/<int:pmoc_id>/atendimento', methods=['PUT'])
@valida_token
def registrar_atendimento_pmoc(usuario_atual, pmoc_id):
    try:
        perfil, uid = usuario_atual['perfil'], usuario_atual['id']
        if perfil not in ('administrador', 'fiscal', 'contratada', 'executante'):
            return jsonify({'erro': 'Acesso negado.'}), 403

        conn = get_db_connection()
        pmoc_info = conn.execute("SELECT * FROM pmoc_manutencoes WHERE id = ?", (pmoc_id,)).fetchone()
        if not pmoc_info:
            conn.close()
            return jsonify({'erro': 'Preventiva não encontrada.'}), 404

        if not pode_acessar_pmoc(conn, usuario_atual, pmoc_info):
            conn.close()
            return jsonify({'erro': 'Acesso não autorizado a esta manutenção.'}), 403

        if pmoc_info['status'] in ('concluida', 'reprovada', 'cancelada') and perfil in ('contratada', 'executante'):
            conn.close()
            return jsonify({'erro': 'Manutenção já encerrada ou avaliada. Nenhuma alteração permitida.'}), 403

        dados = request.get_json(silent=True) or {}
        tensao = str(dados.get('tensao_medida', '')).strip().upper()
        corrente = str(dados.get('corrente_medida', '')).strip().upper()
        temp_ins = str(dados.get('temperatura_insuflamento', '')).strip().upper()
        temp_ret = str(dados.get('temperatura_retorno', '')).strip().upper()
        obs = str(dados.get('observacoes_execucao', '')).strip().upper()
        arquivo_folha = dados.get('arquivo_folha_assinada')
        checklist = dados.get('checklist') or []

        if arquivo_folha:
            if secure_filename(arquivo_folha) != arquivo_folha or not os.path.isfile(os.path.join(UPLOAD_FOLDER, arquivo_folha)):
                conn.close()
                return jsonify({'erro': 'Anexo de comprovação inválido ou inexistente no servidor.'}), 400

        # Conclusão automática quando a contratada ou o executante inserir a comprovação ou solicitar conclusão
        concluir_os = bool(
            dados.get('enviar_validacao', False)
            or dados.get('concluir', False)
            or dados.get('status') == 'concluida'
            or arquivo_folha
        )

        comprovacao_efetiva = arquivo_folha or pmoc_info['arquivo_folha_assinada']
        tensao_efetiva = tensao or pmoc_info['tensao_medida']
        corrente_efetiva = corrente or pmoc_info['corrente_medida']

        if concluir_os:
            if not comprovacao_efetiva:
                conn.close()
                return jsonify({'erro': 'Para concluir a O.S. de preventiva, é obrigatório inserir a comprovação no sistema (foto ou PDF).'}), 400
            if not tensao_efetiva or not corrente_efetiva:
                conn.close()
                return jsonify({'erro': 'As medições de tensão (V) e corrente (A) são obrigatórias para concluir a preventiva.'}), 400

        ts = int(time.time() * 1000)
        novo_status = 'concluida' if concluir_os else 'em_execucao'

        conn.execute('''
            UPDATE pmoc_manutencoes SET
                executante_id = COALESCE(executante_id, ?),
                tensao_medida = COALESCE(?, tensao_medida),
                corrente_medida = COALESCE(?, corrente_medida),
                temperatura_insuflamento = COALESCE(?, temperatura_insuflamento),
                temperatura_retorno = COALESCE(?, temperatura_retorno),
                observacoes_execucao = COALESCE(?, observacoes_execucao),
                arquivo_folha_assinada = COALESCE(?, arquivo_folha_assinada),
                data_execucao = COALESCE(data_execucao, ?),
                status = ?
            WHERE id = ?
        ''', (uid, tensao or None, corrente or None, temp_ins or None, temp_ret or None,
              obs or None, arquivo_folha or None, ts, novo_status, pmoc_id))

        if concluir_os:
            conn.execute("UPDATE pmoc_calendario_anual SET status = 'concluido' WHERE manutencao_id = ?", (pmoc_id,))
            if pmoc_info['ciclo_id']:
                restantes = conn.execute('''
                    SELECT 1 FROM pmoc_manutencoes
                    WHERE ciclo_id = ? AND status NOT IN ('concluida', 'reprovada', 'cancelada')
                ''', (pmoc_info['ciclo_id'],)).fetchone()
                if not restantes:
                    conn.execute("UPDATE pmoc_ciclos SET status = 'concluido' WHERE id = ?", (pmoc_info['ciclo_id'],))

        for it in checklist:
            cod = str(it.get('codigo') or it.get('item_codigo') or '').strip()
            desc = str(it.get('descricao') or it.get('item_descricao') or '').strip()
            grp = str(it.get('grupo', 'Geral')).strip()
            st_item = str(it.get('status_item', 'conforme')).strip().lower()
            if st_item not in ('conforme', 'corrigido', 'nao_conforme', 'nao_se_aplica'):
                st_item = 'conforme'
            obs_item = str(it.get('observacao', '')).strip().upper()
            if cod:
                conn.execute('''
                    INSERT INTO pmoc_checklist_respostas (manutencao_id, item_codigo, item_descricao, grupo, status_item, observacao)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(manutencao_id, item_codigo) DO UPDATE SET
                        status_item = excluded.status_item,
                        observacao = excluded.observacao
                ''', (pmoc_id, cod, desc, grp, st_item, obs_item or None))

        acao = "CONCLUIDA_COM_COMPROVACAO" if concluir_os else "APONTAMENTO_SALVO"
        obs_padrao = f"O.S. Preventiva concluída automaticamente mediante inserção de comprovação por {usuario_atual.get('nome', perfil.upper())}." if concluir_os else "Checklist e medições atualizados."
        conn.execute("INSERT INTO historico_pmoc (manutencao_id, usuario_id, data_registro, acao, observacao) VALUES (?, ?, ?, ?, ?)",
                     (pmoc_id, uid, ts, acao, obs or obs_padrao))

        conn.commit()
        conn.close()
        msg = "O.S. de Manutenção Preventiva concluída automaticamente com comprovação registrada!" if concluir_os else "Andamento salvo com sucesso!"
        return jsonify({'mensagem': msg, 'status': novo_status}), 200
    except Exception as e:
        return erro_interno(e)


@app.route('/api/pmoc/manutencoes/<int:pmoc_id>/validacao', methods=['PUT'])
@valida_token
def validar_pmoc_fiscal(usuario_atual, pmoc_id):
    try:
        perfil, uid = usuario_atual['perfil'], usuario_atual['id']
        if perfil not in ('administrador', 'fiscal'):
            return jsonify({'erro': 'Apenas o Fiscal de Contrato ou Administrador pode registrar decisão de fiscalização.'}), 403

        conn = get_db_connection()
        pmoc_info = conn.execute("SELECT * FROM pmoc_manutencoes WHERE id = ?", (pmoc_id,)).fetchone()
        if not pmoc_info:
            conn.close()
            return jsonify({'erro': 'Preventiva não encontrada.'}), 404

        if perfil == 'fiscal':
            pertence = conn.execute("SELECT 1 FROM usuario_contratos WHERE usuario_id = ? AND contrato_id = ?",
                                    (uid, pmoc_info['contrato_id'])).fetchone()
            if not pertence:
                conn.close()
                return jsonify({'erro': 'Manutenção não pertence aos seus contratos.'}), 403

        dados = request.get_json(silent=True) or {}
        status_novo = str(dados.get('status') or '').strip().lower()
        justificativa = str(dados.get('justificativa', '')).strip().upper()

        if status_novo in ('reprovado', 'reprovada', 'em_execucao'):
            status_novo = 'reprovada'

        if status_novo not in ('reprovada', 'concluida', 'cancelada'):
            conn.close()
            return jsonify({'erro': 'Status de decisão inválido.'}), 400

        if status_novo in ('reprovada', 'cancelada') and not justificativa:
            conn.close()
            return jsonify({'erro': 'É obrigatório informar a falha identificada / justificativa para marcar como REPROVADO.'}), 400

        ts = int(time.time() * 1000)

        if status_novo == 'reprovada':
            conn.execute('''
                UPDATE pmoc_manutencoes SET
                    status = 'reprovada',
                    fiscal_id = ?,
                    data_homologacao = ?,
                    justificativa_fiscal = ?
                WHERE id = ?
            ''', (uid, ts, justificativa, pmoc_id))
            conn.execute("UPDATE pmoc_calendario_anual SET status = 'reprovado' WHERE manutencao_id = ?", (pmoc_id,))
            acao = "REPROVADO_PELO_FISCAL"
        elif status_novo == 'concluida':
            conn.execute('''
                UPDATE pmoc_manutencoes SET
                    status = 'concluida',
                    fiscal_id = ?,
                    data_homologacao = ?,
                    justificativa_fiscal = ?
                WHERE id = ?
            ''', (uid, ts, justificativa or "CONFERIDA / REGULAR PELA FISCALIZAÇÃO.", pmoc_id))
            conn.execute("UPDATE pmoc_calendario_anual SET status = 'concluido' WHERE manutencao_id = ?", (pmoc_id,))
            acao = "CONCLUIDA_REGULAR"
        else:
            conn.execute('''
                UPDATE pmoc_manutencoes SET
                    status = 'cancelada',
                    fiscal_id = ?,
                    justificativa_fiscal = ?
                WHERE id = ?
            ''', (uid, justificativa, pmoc_id))
            conn.execute("UPDATE pmoc_calendario_anual SET status = 'planejado', manutencao_id = NULL WHERE manutencao_id = ?", (pmoc_id,))
            acao = "CANCELADA_PELO_FISCAL"

        conn.execute("INSERT INTO historico_pmoc (manutencao_id, usuario_id, data_registro, acao, observacao) VALUES (?, ?, ?, ?, ?)",
                     (pmoc_id, uid, ts, acao, justificativa))

        conn.commit()
        conn.close()
        msg_dec = 'O.S. Preventiva marcada como REPROVADO para fins de avaliação e pagamento!' if status_novo == 'reprovada' else 'Decisão da fiscalização gravada com sucesso!'
        return jsonify({'mensagem': msg_dec, 'status': status_novo}), 200
    except Exception as e:
        return erro_interno(e)


@app.route('/api/pmoc/manutencoes/<int:pmoc_id>/pdf', methods=['GET'])
@valida_token
def gerar_pdf_pmoc_endpoint(usuario_atual, pmoc_id):
    try:
        conn = get_db_connection()
        pmoc_info = conn.execute('''
            SELECT p.*,
                   e.comarca, e.predio, e.sala, e.tombo, e.tipo_equipamento, e.marca, e.capacidade,
                   c.numero_contrato, c.nome_empresa, c.cnpj AS cnpj_empresa,
                   ex.nome AS nome_executante, fi.nome AS nome_fiscal
            FROM pmoc_manutencoes p
            JOIN equipamentos e ON p.equipamento_id = e.id
            JOIN contratos c ON p.contrato_id = c.id
            LEFT JOIN usuarios ex ON p.executante_id = ex.id
            LEFT JOIN usuarios fi ON p.fiscal_id = fi.id
            WHERE p.id = ?
        ''', (pmoc_id,)).fetchone()

        if not pmoc_info:
            conn.close()
            return jsonify({'erro': 'Preventiva não encontrada.'}), 404

        if not pode_acessar_pmoc(conn, usuario_atual, pmoc_info):
            conn.close()
            return jsonify({'erro': 'Acesso negado a este documento.'}), 403

        respostas = conn.execute('''
            SELECT item_codigo, item_descricao, grupo, status_item, observacao
            FROM pmoc_checklist_respostas
            WHERE manutencao_id = ?
            ORDER BY id ASC
        ''', (pmoc_id,)).fetchall()

        checklist = [dict(r) for r in respostas]
        if not checklist:
            padrao = obter_checklist_padrao(pmoc_info['tipo_equipamento'], pmoc_info['periodicidade'])
            checklist = [{
                'item_codigo': it['codigo'],
                'item_descricao': it['descricao'],
                'grupo': it['grupo'],
                'status_item': 'conforme',
                'observacao': ''
            } for it in padrao]

        historico = conn.execute('''
            SELECT h.*, u.nome AS nome_usuario
            FROM historico_pmoc h
            JOIN usuarios u ON h.usuario_id = u.id
            WHERE h.manutencao_id = ?
            ORDER BY h.data_registro ASC
        ''', (pmoc_id,)).fetchall()
        conn.close()

        conn_pdf = get_db_connection()
        eqs_pdf = conn_pdf.execute('''
            SELECT e.id, e.tombo, e.comarca, e.predio, e.sala, e.tipo_equipamento, e.marca, e.capacidade,
                   pme.status_item, pme.tensao_medida, pme.corrente_medida, pme.temperatura_insuflamento, pme.temperatura_retorno, pme.observacao
            FROM pmoc_manutencao_equipamentos pme
            JOIN equipamentos e ON pme.equipamento_id = e.id
            WHERE pme.manutencao_id = ?
            ORDER BY e.predio, e.sala, e.tombo
        ''', (pmoc_id,)).fetchall()
        lista_eqs_pdf = [dict(r) for r in eqs_pdf]
        conn_pdf.close()
        buffer, filename = gerar_pdf_pmoc_buffer(dict(pmoc_info), checklist, [dict(h) for h in historico], lista_equipamentos=lista_eqs_pdf)
        response = send_file(buffer, mimetype='application/pdf', as_attachment=False, download_name=filename)
        response.headers['X-Filename'] = filename
        response.headers['Access-Control-Expose-Headers'] = 'Content-Disposition, X-Filename'
        return response
    except Exception as e:
        return erro_interno(e, 'Falha ao gerar o documento oficial do PMOC.')


@app.route('/api/equipamentos/<int:eq_id>/pmoc', methods=['GET'])
@valida_token
def historico_pmoc_equipamento(usuario_atual, eq_id):
    try:
        conn = get_db_connection()
        perfil, uid = usuario_atual['perfil'], usuario_atual['id']

        eq = conn.execute("SELECT id, contrato_id FROM equipamentos WHERE id = ?", (eq_id,)).fetchone()
        if not eq:
            conn.close()
            return jsonify({'erro': 'Equipamento não encontrado.'}), 404

        if perfil in ('fiscal', 'contratada'):
            pertence = conn.execute("SELECT 1 FROM usuario_contratos WHERE usuario_id = ? AND contrato_id = ?",
                                    (uid, eq['contrato_id'])).fetchone()
            if not pertence:
                conn.close()
                return jsonify({'erro': 'Acesso negado a este equipamento.'}), 403

        preventivas = conn.execute('''
            SELECT p.*, c.numero_contrato, ex.nome AS nome_executante, fi.nome AS nome_fiscal,
                   COALESCE(pme.tensao_medida, p.tensao_medida) AS tensao_medida,
                   COALESCE(pme.corrente_medida, p.corrente_medida) AS corrente_medida,
                   COALESCE(pme.temperatura_insuflamento, p.temperatura_insuflamento) AS temperatura_insuflamento,
                   COALESCE(pme.temperatura_retorno, p.temperatura_retorno) AS temperatura_retorno,
                   COALESCE(pme.status_item, p.status) AS item_status
            FROM pmoc_manutencoes p
            JOIN contratos c ON p.contrato_id = c.id
            LEFT JOIN pmoc_manutencao_equipamentos pme ON pme.manutencao_id = p.id AND pme.equipamento_id = ?
            LEFT JOIN usuarios ex ON p.executante_id = ex.id
            LEFT JOIN usuarios fi ON p.fiscal_id = fi.id
            WHERE (p.equipamento_id = ?
               OR p.id IN (SELECT manutencao_id FROM pmoc_manutencao_equipamentos WHERE equipamento_id = ?)
               OR p.id IN (SELECT manutencao_id FROM pmoc_calendario_anual WHERE equipamento_id = ? AND manutencao_id IS NOT NULL))
              AND (? != 'fiscal' OR p.status IN ('concluida', 'reprovada'))
            ORDER BY p.ano_competencia DESC, p.mes_competencia DESC, p.id DESC
        ''', (eq_id, eq_id, eq_id, eq_id, perfil)).fetchall()
        conn.close()
        return jsonify([dict(p) for p in preventivas]), 200
    except Exception as e:
        return erro_interno(e)


# ================= CALENDÁRIO ANUAL E AUTOMAÇÃO DO PMOC =================
_ULTIMA_CHECAGEM_PMOC = 0

def _garantir_pmoc_em_dia():
    global _ULTIMA_CHECAGEM_PMOC
    agora = time.time()
    if agora - _ULTIMA_CHECAGEM_PMOC > 3600:  # Checagem a cada 1 hora no máximo
        _ULTIMA_CHECAGEM_PMOC = agora
        import threading
        def _job():
            try:
                verificar_e_executar_rotina_automatica()
            except Exception:
                pass
        threading.Thread(target=_job, daemon=True).start()


@app.route('/api/pmoc/calendario', methods=['GET'])
@valida_token
def obter_calendario_pmoc_rota(usuario_atual):
    try:
        _garantir_pmoc_em_dia()
        modo = request.args.get('modo', 'janela')
        comarca = request.args.get('comarca')
        eq_id = request.args.get('equipamento_id')
        eq_id = int(eq_id) if eq_id else None

        ano_param = request.args.get('ano')
        if modo == 'ano' and ano_param:
            ano = int(ano_param)
            dados = obter_calendario_anual(ano, comarca=comarca, equipamento_id=eq_id)
        else:
            dados = obter_plano_preventiva_janela_movel(comarca=comarca, equipamento_id=eq_id)

        return jsonify(dados), 200
    except Exception as e:
        return erro_interno(e)


@app.route('/api/pmoc/calendario/gerar', methods=['POST'])
@valida_token
def gerar_calendario_pmoc_rota(usuario_atual):
    try:
        if usuario_atual['perfil'] not in ('administrador', 'fiscal'):
            return jsonify({'erro': 'Apenas administradores e fiscais podem gerar o calendário.'}), 403
        dados_req = request.get_json(silent=True) or {}
        ano = int(dados_req.get('ano', date.today().year))
        forcar = bool(dados_req.get('forcar', False))
        res = gerar_calendario_anual(ano, forcar=forcar)
        return jsonify(res), 200
    except Exception as e:
        return erro_interno(e)


@app.route('/api/pmoc/gerar-mes', methods=['POST'])
@valida_token
def gerar_mes_pmoc_rota(usuario_atual):
    try:
        if usuario_atual['perfil'] not in ('administrador', 'fiscal'):
            return jsonify({'erro': 'Apenas administradores e fiscais podem gerar ordens do mês.'}), 403
        dados_req = request.get_json(silent=True) or {}
        ano = int(dados_req.get('ano', date.today().year))
        mes = int(dados_req.get('mes', date.today().month))
        res = gerar_ordens_mes_automatico(ano, mes, criado_por=usuario_atual['id'])
        return jsonify(res), 200
    except Exception as e:
        return erro_interno(e)


@app.route('/api/pmoc/rotina-automatica', methods=['POST'])
@valida_token
def executar_rotina_pmoc_rota(usuario_atual):
    try:
        if usuario_atual['perfil'] not in ('administrador', 'fiscal'):
            return jsonify({'erro': 'Apenas administradores e fiscais podem executar a rotina.'}), 403
        res = verificar_e_executar_rotina_automatica(criado_por=usuario_atual['id'])
        return jsonify(res), 200
    except Exception as e:
        return erro_interno(e)


@app.route('/api/pmoc/limpar-testes', methods=['POST'])
@valida_token
def limpar_testes_pmoc_rota(usuario_atual):
    try:
        if usuario_atual['perfil'] not in ('administrador', 'fiscal'):
            return jsonify({'erro': 'Apenas administradores e fiscais podem limpar chamados de teste.'}), 403
        res = limpar_chamados_teste()
        return jsonify(res), 200
    except Exception as e:
        return erro_interno(e)




@app.route('/api/pmoc/relatorio-ciclo', methods=['GET'])
@valida_token
def obter_relatorio_ciclo_pmoc_rota(usuario_atual):
    try:
        perfil, uid = usuario_atual['perfil'], usuario_atual['id']
        if perfil not in ('administrador', 'fiscal', 'contratada'):
            return jsonify({'erro': 'Apenas Fiscal, Contratada ou Administrador podem gerar o relatório de ciclo.'}), 403

        hoje = date.today()
        ano = int(request.args.get('ano', hoje.year))
        mes = int(request.args.get('mes', hoje.month))
        contrato_id = request.args.get('contrato_id')
        contrato_id = int(contrato_id) if contrato_id and str(contrato_id).isdigit() else None

        conn = get_db_connection()
        contratos_permitidos = None
        if perfil in ('fiscal', 'contratada'):
            rows_ct = conn.execute("SELECT contrato_id FROM usuario_contratos WHERE usuario_id = ?", (uid,)).fetchall()
            if rows_ct:
                contratos_permitidos = [r['contrato_id'] for r in rows_ct]
                if contrato_id and contrato_id not in contratos_permitidos:
                    conn.close()
                    return jsonify({'erro': 'Contrato não vinculado ao seu perfil.'}), 403

        dados = obter_dados_relatorio_ciclo_pmoc(
            ano=ano,
            mes=mes,
            contrato_id=contrato_id,
            contratos_permitidos=contratos_permitidos,
            db_conn=conn
        )
        conn.close()
        return jsonify(dados), 200
    except Exception as e:
        return erro_interno(e)


@app.route('/api/pmoc/relatorio-ciclo/pdf', methods=['GET'])
@valida_token
def gerar_pdf_relatorio_ciclo_pmoc_rota(usuario_atual):
    try:
        perfil, uid = usuario_atual['perfil'], usuario_atual['id']
        if perfil not in ('administrador', 'fiscal', 'contratada'):
            return jsonify({'erro': 'Apenas Fiscal, Contratada ou Administrador podem emitir o relatório de ciclo.'}), 403

        hoje = date.today()
        ano = int(request.args.get('ano', hoje.year))
        mes = int(request.args.get('mes', hoje.month))
        contrato_id = request.args.get('contrato_id')
        contrato_id = int(contrato_id) if contrato_id and str(contrato_id).isdigit() else None

        conn = get_db_connection()
        contratos_permitidos = None
        if perfil in ('fiscal', 'contratada'):
            rows_ct = conn.execute("SELECT contrato_id FROM usuario_contratos WHERE usuario_id = ?", (uid,)).fetchall()
            if rows_ct:
                contratos_permitidos = [r['contrato_id'] for r in rows_ct]
                if contrato_id and contrato_id not in contratos_permitidos:
                    conn.close()
                    return jsonify({'erro': 'Contrato não vinculado ao seu perfil.'}), 403

        dados = obter_dados_relatorio_ciclo_pmoc(
            ano=ano,
            mes=mes,
            contrato_id=contrato_id,
            contratos_permitidos=contratos_permitidos,
            db_conn=conn
        )
        conn.close()

        buffer, filename = gerar_pdf_relatorio_ciclo_buffer(dados)
        response = send_file(buffer, mimetype='application/pdf', as_attachment=False, download_name=filename)
        response.headers['X-Filename'] = filename
        response.headers['Access-Control-Expose-Headers'] = 'Content-Disposition, X-Filename'
        return response
    except Exception as e:
        return erro_interno(e, 'Falha ao gerar o PDF do relatório de ciclo.')


# ================= UPLOAD E DOWNLOAD DE ANEXOS =================
LADO_MAX_FOTO = 1600


def otimizar_imagem(arquivo_fs, destino):
    """Foto de celular (3-10 MB) -> ~300 KB: corrige a rotação, limita o lado maior, JPEG q80 e remove EXIF/GPS.
    Retorna True se gravou em 'destino'; False se a imagem não pôde ser decodificada."""
    try:
        arquivo_fs.stream.seek(0)
        img = Image.open(arquivo_fs.stream)
        if img.format == 'JPEG':
            img.draft('RGB', (LADO_MAX_FOTO, LADO_MAX_FOTO))   # decodifica já reduzido: pouca RAM no Pi
        img = ImageOps.exif_transpose(img)
        img.thumbnail((LADO_MAX_FOTO, LADO_MAX_FOTO))
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGBA')
            fundo = Image.new('RGB', img.size, (255, 255, 255))
            fundo.paste(img, mask=img.split()[-1])
            img = fundo
        else:
            img = img.convert('RGB')
        img.save(destino, 'JPEG', quality=80, optimize=True)
        return True
    except Exception:
        app.logger.exception('Falha ao otimizar imagem enviada')
        if os.path.exists(destino):
            os.remove(destino)
        return False


def detectar_tipo_arquivo(cabecalho):
    """Identifica o tipo real pelos primeiros bytes (não confia na extensão enviada)."""
    if cabecalho.startswith(b'%PDF'):
        return 'pdf'
    if cabecalho.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    if cabecalho.startswith(b'\xff\xd8\xff'):
        return 'jpg'
    return None


@app.route('/api/upload', methods=['POST'])
@valida_token
def upload_arquivo(usuario_atual):
    try:
        if usuario_atual['perfil'] == 'solicitante':
            return jsonify({'erro': 'Seu perfil não possui permissão para anexar arquivos.'}), 403
        if 'file' not in request.files:
            return jsonify({'erro': 'Nenhum arquivo enviado.'}), 400
        f = request.files['file']
        if f.filename == '':
            return jsonify({'erro': 'Nome de arquivo inválido.'}), 400

        cabecalho = f.stream.read(8)
        f.stream.seek(0)
        tipo = detectar_tipo_arquivo(cabecalho)
        if not tipo:
            return jsonify({'erro': 'Formato inválido. Apenas JPG, PNG ou PDF reais.'}), 400

        # Nome aleatório (128 bits): impossível de adivinhar, sem depender do nome enviado pelo cliente.
        if tipo in ('jpg', 'png') and Image is not None:
            nome_seguro = f"{uuid.uuid4().hex}.jpg"
            if not otimizar_imagem(f, os.path.join(UPLOAD_FOLDER, nome_seguro)):
                return jsonify({'erro': 'Imagem corrompida ou não suportada. Tire a foto novamente.'}), 400
        else:
            nome_seguro = f"{uuid.uuid4().hex}.{tipo}"
            f.save(os.path.join(UPLOAD_FOLDER, nome_seguro))
        return jsonify({'arquivo': nome_seguro}), 201
    except Exception as e:
        return erro_interno(e)


@app.route('/api/uploads/<path:filename>', methods=['GET'])
@valida_token
def baixar_anexo(usuario_atual, filename):
    try:
        nome_limpo = secure_filename(filename)
        if not nome_limpo or nome_limpo != filename:
            return jsonify({'erro': 'Arquivo não encontrado.'}), 404

        conn = get_db_connection()
        os_info = conn.execute('''
            SELECT os.id, os.solicitante_id, os.executante_id, os.status, COALESCE(os.contrato_id, eq.contrato_id) AS contrato_id
            FROM ordens_servico os LEFT JOIN equipamentos eq ON os.equipamento_id = eq.id
            LEFT JOIN os_instalacao oi ON oi.os_id = os.id
            WHERE os.arquivo_conclusao = ? OR oi.foto_evaporadora = ? OR oi.foto_condensadora = ? OR oi.foto_tubulacao = ? OR oi.foto_dreno = ? OR oi.arquivo_os_assinada_original = ?
        ''', (nome_limpo, nome_limpo, nome_limpo, nome_limpo, nome_limpo, nome_limpo)).fetchone()

        permitido = False
        if os_info is not None:
            permitido = pode_acessar_os(conn, usuario_atual, os_info)
        else:
            pmoc_info = conn.execute('''
                SELECT p.id, p.executante_id, p.status, p.contrato_id
                FROM pmoc_manutencoes p
                WHERE p.arquivo_folha_assinada = ?
            ''', (nome_limpo,)).fetchone()
            if pmoc_info is not None:
                permitido = pode_acessar_pmoc(conn, usuario_atual, pmoc_info)

        conn.close()

        # 404 (e não 403) para não revelar a existência de arquivos de outras O.S.
        if not permitido:
            return jsonify({'erro': 'Arquivo não encontrado.'}), 404

        resp = send_from_directory(UPLOAD_FOLDER, nome_limpo)
        resp.headers['Cache-Control'] = 'private, no-store'
        return resp
    except Exception as e:
        return erro_interno(e)


@app.after_request
def cabecalhos_seguranca(resp):
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['Referrer-Policy'] = 'no-referrer'
    return resp


# Disparo automático em segundo plano na inicialização
def _iniciar_worker_pmoc():
    import threading
    def _worker():
        try:
            time.sleep(2)
            verificar_e_executar_rotina_automatica()
        except Exception as ex:
            print("[SGME-PMOC-INICIAL] Aviso:", ex)
    t = threading.Thread(target=_worker, daemon=True)
    t.start()

_iniciar_worker_pmoc()


# Execução interna isolada na porta profissional 5001 (Loopback)
if __name__ == '__main__':
    try:
        from waitress import serve   # pip install waitress (puro Python, ~10 MB de RAM extra)
    except ImportError:
        serve = None
    if serve:
        serve(app, host='127.0.0.1', port=5001, threads=4, max_request_body_size=15 * 1024 * 1024)
    else:
        app.run(host='127.0.0.1', port=5001, threaded=True)