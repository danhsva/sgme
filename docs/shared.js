/**
 * SGME - Núcleo Compartilhado Frontend
 * Arquivo: shared.js
 */

let servidorBaseUrl = "";
if (typeof window !== 'undefined' && window.location.hostname && !['localhost', '127.0.0.1'].includes(window.location.hostname) && !window.location.hostname.endsWith('.local')) {
    if (window.SGME_CONFIG && window.SGME_CONFIG.API_URL) {
        servidorBaseUrl = window.SGME_CONFIG.API_URL.replace(/\/+$/, '');
    }
}
let usuarioLogado = null;

// Lista oficial dos 184 municípios cearenses em caixa alta
const MUNICIPIOS_CE = [
    "ABAIARA","ACARAPE","ACARAÚ","ACOPIARA","AIUABA","ALCÂNTARAS","ALTANEIRA","ALTO SANTO","AMONTADA",
    "ANTONINA DO NORTE","APUIARÉS","AQUIRAZ","ARACATI","ARACOIABA","ARARENDÁ","ARARIPE","ARATUBA","ARNEIROZ",
    "ASSARÉ","AURORA","BAIXIO","BANABUIÚ","BARBALHA","BARREIRA","BARRO","BARROQUINHA","BATURITÉ","BEBERIBE",
    "BELA CRUZ","BOA VIAGEM","BREJO SANTO","CAMOCIM","CAMPOS SALES","CANINDÉ","CAPISTRANO","CARIDADE","CARIRÉ",
    "CARIRIAÇU","CARIÚS","CARNAUBAL","CASCAVEL","CATARINA","CATUNDA","CAUCAIA","CEDRO","CHAVAL","CHORÓ",
    "CHOROVOZINHO","COREAÚ","CRATEÚS","CRATO","CROATÁ","CRUZ","DEPUTADO IRAPUAN PINHEIRO","ERERÊ","EUSÉBIO",
    "FARIAS BRITO","FORQUILHA","FORTALEZA","FORTIM","FRECHEIRINHA","GENERAL SAMPAIO","GRAÇA","GRANJA",
    "GRANJEIRO","GROAÍRAS","GUAIÚBA","GUARACIABA DO NORTE","GUARAMIRANGA","HIDROLÂNDIA","HORIZONTE","IBARETAMA",
    "IBIAPINA","IBICUITINGA","ICAPUÍ","ICÓ","IGUATU","INDEPENDÊNCIA","IPAPORANGA","IPAUMIRIM","IPU","IPUEIRAS",
    "IRACEMA","IRAUÇUBA","ITAIÇABA","ITAITINGA","ITAPAJÉ","ITAPIPOCA","ITAPIÚNA","ITAREMA","ITATIRA","JAGUARETAMA",
    "JAGUARIBARA","JAGUARIBE","JAGUARUANA","JARDIM","JATI","JIJOCA DE JERICOACOARA","JUAZEIRO DO NORTE","JUCÁS",
    "LAVRAS DA MANGABEIRA","LIMOEIRO DO NORTE","MADALENA","MARACANAÚ","MARANGUAPE","MARCO","MARTINÓPOLE","MASSAPÊ",
    "MAURITI","MERUOCA","MILAGRES","MILHÃ","MIRAÍMA","MISSÃO VELHA","MOMBAÇA","MONSENHOR TABOSA","MORADA NOVA",
    "MORAÚJO","MORRINHOS","MUCAMBO","MULUNGU","NOVA OLINDA","NOVA RUSSAS","NOVO ORIENTE","OCARA","ORÓS","PACAJUS",
    "PACATUBA","PACOTI","PACUJÁ","PALHANO","PALMÁCIA","PARACURU","PARAIPABA","PARAMBU","PARAMOTI","PEDRA BRANCA",
    "PENAFORTE","PENTECOSTE","PEREIRO","PINDORETAMA","PIQUET CARNEIRO","PIRES FERREIRA","PORANGA","PORTEIRAS",
    "POTENGI","POTIRETAMA","QUITERIANÓPOLIS","QUIXADÁ","QUIXELÔ","QUIXERAMOBIM","QUIXERÉ","REDENÇÃO","RERIUTABA",
    "RUSSAS","SABOEIRO","SALITRE","SANTA QUITÉRIA","SANTANA DO ACARAÚ","SANTANA DO CARIRI","SÃO BENEDITO",
    "SÃO GONÇALO DO AMARANTE","SÃO JOÃO DO JAGUARIBE","SÃO LUÍS DO CURU","SENADOR POMPEU","SENADOR SÁ","SOBRAL",
    "SOLONÓPOLE","TABULEIRO DO NORTE","TAMBORIL","TARRAFAS","TAUÁ","TEJUÇUOCA","TIANGUÁ","TRAIRI","TURURU",
    "UBAJARA","UMARI","UMIRIM","URUBURETAMA","URUOCA","VARJOTA","VÁRZEA ALEGRE","VIÇOSA DO CEARÁ"
];

// Sanitização estrita contra XSS
function esc(str) {
    return str ? String(str).replace(/[&<>'"]/g, m => ({ '&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;' }[m])) : '';
}

// Formatação oficial do identificador da O.S.: XXXX.MM.AAAA (ex: 0017.09.2026)
function formatarNumOS(id, timestamp, comPrefixo = false) {
    if (!id) return '';
    let d = timestamp ? new Date(timestamp) : new Date();
    if (isNaN(d.getTime())) d = new Date();
    const seq = String(id).padStart(4, '0');
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const aaaa = d.getFullYear();
    const codigo = `${seq}.${mm}.${aaaa}`;
    return comPrefixo ? `OS_${codigo}` : codigo;
}


// Formatação amigável de data e hora
function dataFormatada(timestamp) {
    if (!timestamp) return '-';
    return new Date(timestamp).toLocaleString('pt-BR');
}

// Utilitários de interface
function fecharModal(id) {
    const el = document.getElementById(id);
    if (el) el.classList.add('hidden');
}

function fazerLogout() {
    localStorage.removeItem('os_usuario_logado');
    sessionStorage.clear();
    window.location.href = 'index.html';
}

function getApiUrl(ep) {
    return `${servidorBaseUrl}${ep}`;
}

// Inicialização central de segurança de sessão
async function inicializarCore(perfilEsperado) {
    const raw = localStorage.getItem('os_usuario_logado');
    if (!raw) { 
        window.location.href = 'index.html'; 
        return null; 
    }
    
    usuarioLogado = JSON.parse(raw);
    if (!usuarioLogado || !usuarioLogado.token || (perfilEsperado && usuarioLogado.perfil !== perfilEsperado)) {
        window.location.href = 'index.html';
        return null;
    }

    const nomeDisp = document.getElementById('usuarioNomeDisplay');
    if (nomeDisp) nomeDisp.textContent = esc(usuarioLogado.nome);

    return usuarioLogado;
}

// Cliente HTTP com Bearer Token e suporte automático a JSON e FormData
async function apiFetch(endpoint, options = {}) {
    if (!options.headers) options.headers = {};
    if (usuarioLogado && usuarioLogado.token) {
        options.headers['Authorization'] = `Bearer ${usuarioLogado.token}`;
    }
    
    if (!(options.body instanceof FormData) && !options.headers['Content-Type']) {
        options.headers['Content-Type'] = 'application/json';
    }

    const res = await fetch(getApiUrl(endpoint), options);
    if (res.status === 401) {
        alert("Sessão expirada. Faça login novamente.");
        fazerLogout();
        throw new Error("401 Unauthorized");
    }
    return res;
}

// Emissão e download direto do PDF no padrão oficial OS_XXXX.MM.AAAA.pdf
async function imprimirOSPdf(os_id, data_abertura = null) {
    if (!usuarioLogado || !usuarioLogado.token) {
        alert("Usuário não autenticado.");
        return;
    }

    try {
        // 1. Baixa o binário do PDF via AJAX seguro com o token no header
        const res = await apiFetch(`/api/os/${os_id}/pdf`);
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.erro || "Falha ao gerar o documento PDF.");
        }

        // 2. Recupera o nome oficial enviado pelo backend (ex: OS_0017.09.2026.pdf) ou gera pelo formatador
        let nomeArquivo = res.headers.get('X-Filename');
        if (!nomeArquivo) {
            nomeArquivo = `${formatarNumOS(os_id, data_abertura, true)}.pdf`;
        }

        // 3. Converte a resposta em um Blob local do navegador
        const blob = await res.blob();
        const blobUrl = window.URL.createObjectURL(blob);

        // 4. Dispara o download com o nome padronizado
        const link = document.createElement('a');
        link.href = blobUrl;
        link.download = nomeArquivo;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

        // 5. Libera a memória alocada
        setTimeout(() => window.URL.revokeObjectURL(blobUrl), 30000);

    } catch (err) {
        alert("Erro ao obter PDF: " + err.message);
    }
}

// ---- Fotos: reduz no próprio aparelho ANTES do envio -----------
// Foto de 8 MB vira ~300 KB (lado maior 1600 px, JPEG 80%). PDF e qualquer falha: devolve o arquivo original.
async function otimizarImagemCliente(arquivo, ladoMax = 1600, qualidade = 0.8) {
    try {
        if (!arquivo || !/^image\//i.test(arquivo.type || '')) return arquivo;
        let imagem;
        if (window.createImageBitmap) {
            try { imagem = await createImageBitmap(arquivo, { imageOrientation: 'from-image' }); }
            catch (e) { imagem = await createImageBitmap(arquivo); }
        } else {
            imagem = await new Promise((ok, erro) => {
                const url = URL.createObjectURL(arquivo);
                const el = new Image();
                el.onload = () => { URL.revokeObjectURL(url); ok(el); };
                el.onerror = () => { URL.revokeObjectURL(url); erro(new Error('imagem ilegível')); };
                el.src = url;
            });
        }
        const larg = imagem.width, alt = imagem.height;
        const escala = Math.min(1, ladoMax / Math.max(larg, alt));
        const w = Math.max(1, Math.round(larg * escala)), h = Math.max(1, Math.round(alt * escala));
        const tela = document.createElement('canvas');
        tela.width = w; tela.height = h;
        const ctx = tela.getContext('2d');
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, w, h);
        ctx.drawImage(imagem, 0, 0, w, h);
        if (imagem.close) imagem.close();
        const blob = await new Promise(ok => tela.toBlob(ok, 'image/jpeg', qualidade));
        if (!blob || (blob.size >= arquivo.size && /jpe?g/i.test(arquivo.type))) return arquivo;
        const base = (arquivo.name || 'foto').replace(/\.[^.]+$/, '');
        return new File([blob], base + '.jpg', { type: 'image/jpeg' });
    } catch (e) {
        return arquivo;   // em qualquer problema, envia o original (o servidor também otimiza)
    }
}

// ---- Anexos (folha assinada) -------------------------------------------------
// Busca o arquivo com o token no header e exibe SEM abrir nova aba. Mostra aviso de carregamento e erro se falhar.
function avisoAnexo(texto) {
    let el = document.getElementById('avisoAnexo');
    if (!texto) { if (el) el.remove(); return; }
    if (!el) {
        el = document.createElement('div');
        el.id = 'avisoAnexo';
        el.style.cssText = 'position:fixed;top:14px;left:50%;transform:translateX(-50%);z-index:100001;background:#0f172a;color:#fff;padding:12px 18px;border-radius:8px;font:bold 14px sans-serif;box-shadow:0 4px 14px rgba(0,0,0,.35);';
        document.body.appendChild(el);
    }
    el.textContent = texto;
}

async function abrirAnexo(nomeArquivo) {
    const ctl = new AbortController();
    const limite = setTimeout(() => ctl.abort(), 90000);
    avisoAnexo('⏳ Carregando anexo...');
    try {
        const res = await apiFetch('/api/uploads/' + encodeURIComponent(nomeArquivo), { signal: ctl.signal });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.erro || ('Servidor respondeu HTTP ' + res.status));
        }
        const tipo = (res.headers.get('Content-Type') || '').toLowerCase();
        const total = parseInt(res.headers.get('Content-Length') || '0', 10);
        let blob;
        if (res.body && res.body.getReader) {
            const leitor = res.body.getReader();
            const partes = [];
            let recebido = 0;
            for (;;) {
                const { done, value } = await leitor.read();
                if (done) break;
                partes.push(value);
                recebido += value.length;
                avisoAnexo('⏳ Carregando anexo... ' + (total ? Math.min(99, Math.round(recebido * 100 / total)) + '%' : Math.round(recebido / 1024) + ' KB'));
            }
            blob = new Blob(partes, { type: tipo });
        } else {
            blob = await res.blob();
        }
        const blobUrl = window.URL.createObjectURL(blob);
        const movel = /Android|iPhone|iPad|iPod|Mobi/i.test(navigator.userAgent);

        if (tipo.startsWith('image/') || (tipo.startsWith('application/pdf') && !movel)) {
            mostrarVisualizadorAnexo(blobUrl, nomeArquivo, tipo);
        } else {
            baixarBlob(blobUrl, nomeArquivo);
            setTimeout(() => window.URL.revokeObjectURL(blobUrl), 30000);
        }
    } catch (err) {
        const msg = err.name === 'AbortError' ? 'Tempo esgotado (90 s). Verifique a conexão e tente novamente.' : err.message;
        alert('Erro ao abrir anexo: ' + msg);
    } finally {
        clearTimeout(limite);
        avisoAnexo(null);
    }
}

function baixarBlob(blobUrl, nomeArquivo) {
    const link = document.createElement('a');
    link.href = blobUrl;
    link.download = nomeArquivo;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

function mostrarVisualizadorAnexo(blobUrl, nomeArquivo, tipo) {
    const antigo = document.getElementById('visualizadorAnexo');
    if (antigo) antigo.remove();

    const fundo = document.createElement('div');
    fundo.id = 'visualizadorAnexo';
    fundo.style.cssText = 'position:fixed;inset:0;z-index:100000;background:rgba(0,0,0,.9);display:flex;flex-direction:column;';

    const barra = document.createElement('div');
    barra.style.cssText = 'display:flex;gap:10px;justify-content:flex-end;align-items:center;padding:10px 14px;flex:0 0 auto;';
    const dica = document.createElement('span');
    dica.style.cssText = 'color:#cbd5e1;font:12px sans-serif;margin-right:auto;';
    dica.textContent = tipo.startsWith('image/') ? 'Toque na imagem para ampliar/reduzir' : '';
    const estiloBtn = 'border:0;border-radius:6px;padding:9px 14px;font:bold 13px sans-serif;cursor:pointer;text-decoration:none;';
    const baixar = document.createElement('button');
    baixar.type = 'button';
    baixar.textContent = '⬇ Baixar';
    baixar.style.cssText = estiloBtn + 'background:#10b981;color:#fff;';
    baixar.onclick = () => baixarBlob(blobUrl, nomeArquivo);
    const fechar = document.createElement('button');
    fechar.type = 'button';
    fechar.textContent = '✕ Fechar';
    fechar.style.cssText = estiloBtn + 'background:#e2e8f0;color:#0f172a;';
    barra.append(dica, baixar, fechar);

    const area = document.createElement('div');
    area.style.cssText = 'flex:1 1 auto;overflow:auto;display:flex;padding:0 10px 10px;min-height:0;';

    if (tipo.startsWith('image/')) {
        const img = document.createElement('img');
        img.src = blobUrl;
        img.alt = 'Folha assinada';
        const ajustada = 'max-width:100%;max-height:100%;margin:auto;object-fit:contain;cursor:zoom-in;background:#fff;';
        const ampliada = 'max-width:none;margin:0 auto auto;cursor:zoom-out;background:#fff;';
        img.style.cssText = ajustada;
        let zoom = false;
        img.onclick = () => { zoom = !zoom; img.style.cssText = zoom ? ampliada : ajustada; };
        area.appendChild(img);
    } else {
        const quadro = document.createElement('iframe');
        quadro.src = blobUrl;
        quadro.style.cssText = 'flex:1;border:0;background:#fff;';
        area.appendChild(quadro);
    }

    const encerrar = () => {
        document.removeEventListener('keydown', aoTeclar);
        fundo.remove();
        window.URL.revokeObjectURL(blobUrl);
    };
    const aoTeclar = (e) => { if (e.key === 'Escape') encerrar(); };
    fechar.onclick = encerrar;
    document.addEventListener('keydown', aoTeclar);

    fundo.append(barra, area);
    document.body.appendChild(fundo);
}

// SGME 5.0 - utilitários para O.S. de instalação/substituição
function rotuloTipoOS(tipo) {
    return tipo === 'instalacao' ? 'INSTALAÇÃO' : (tipo === 'substituicao' ? 'SUBSTITUIÇÃO' : 'MANUTENÇÃO');
}
function seloTipoOS(tipo) {
    const cor = tipo === 'instalacao' ? '#059669' : (tipo === 'substituicao' ? '#7c3aed' : '#2563eb');
    return `<span class="badge" style="background:${cor};color:#fff;margin-right:4px;">${rotuloTipoOS(tipo)}</span>`;
}
function descricaoEquipamentoOS(os) {
    const marca = os.marca ? `${esc(os.marca)} ` : '';
    return `${marca}${esc(os.tipo_equipamento || '')} ${esc(os.capacidade || '')} (Tombo: ${esc(os.tombo || 'S/T')})`;
}
function linksAnexosOS(os) {
    const isInst = ['instalacao', 'substituicao'].includes(os.tipo_os);
    const rotuloConclusao = isInst ? '📄 O.S. Assinada & Relatório Fotográfico (PDF)' : '📄 Folha de O.S. Assinada';
    const itens = [
        [rotuloConclusao, os.arquivo_conclusao],
        ['Foto da evaporadora', os.foto_evaporadora],
        ['Foto da condensadora', os.foto_condensadora],
        ['Foto da tubulação aparente', os.foto_tubulacao],
        ['Foto do dreno aparente', os.foto_dreno]
    ].filter(x => x[1]);
    return itens.map(([r,n]) => `<a href="#" onclick="event.preventDefault();abrirAnexo('${esc(n)}');return false;" style="background:#10b981;color:#fff;padding:7px 10px;border-radius:6px;text-decoration:none;font-weight:bold;font-size:12px;display:inline-block;margin:3px;">📎 ${r}</a>`).join('');
}
async function enviarArquivoSGME(arquivo, rotulo) {
    if (!arquivo) throw new Error(`${rotulo}: selecione um arquivo.`);
    const fd = new FormData(); fd.append('file', await otimizarImagemCliente(arquivo));
    const r = await apiFetch('/api/upload', { method:'POST', body:fd });
    const d = await r.json(); if (!r.ok) throw new Error(`${rotulo}: ${d.erro || 'falha no envio'}`);
    return d.arquivo;
}

// SGME 6.0 - Utilitários de Manutenção Preventiva (PMOC)
function rotuloPeriodicidade(p) {
    const mapa = { 'M': 'Mensal', 'T': 'Trimestral', 'S': 'Semestral', 'A': 'Anual' };
    return mapa[(p || 'M').toUpperCase()] || 'Mensal';
}

function seloPeriodicidade(p) {
    const rotulo = rotuloPeriodicidade(p);
    const cores = { 'M': '#0284c7', 'T': '#7c3aed', 'S': '#d97706', 'A': '#dc2626' };
    const cor = cores[(p || 'M').toUpperCase()] || '#0284c7';
    return `<span class="badge" style="background:${cor};color:#fff;margin-right:4px;">${rotulo}</span>`;
}

function formatarNumPMOC(id, mes, ano) {
    if (!id) return '';
    const seq = String(id).padStart(4, '0');
    const mm = String(mes || 1).padStart(2, '0');
    const aaaa = ano || new Date().getFullYear();
    return `PMOC_${seq}.${mm}.${aaaa}`;
}

function seloStatusPMOC(status) {
    const mapa = {
        'pendente': { rotulo: 'Pendente', cor: '#f59e0b', fundo: '#fef3c7', texto: '#92400e' },
        'em_execucao': { rotulo: 'Em Execução', cor: '#2563eb', fundo: '#dbeafe', texto: '#1e40af' },
        'em_analise': { rotulo: 'Concluída', cor: '#10b981', fundo: '#d1fae5', texto: '#065f46' },
        'concluida': { rotulo: 'Concluída', cor: '#10b981', fundo: '#d1fae5', texto: '#065f46' },
        'reprovada': { rotulo: 'REPROVADO', cor: '#dc2626', fundo: '#fee2e2', texto: '#991b1b' },
        'reprovado': { rotulo: 'REPROVADO', cor: '#dc2626', fundo: '#fee2e2', texto: '#991b1b' },
        'cancelada': { rotulo: 'Cancelada', cor: '#64748b', fundo: '#f1f5f9', texto: '#334155' }
    };
    const s = mapa[(status || 'pendente').toLowerCase()] || { rotulo: (status || '').toUpperCase(), cor: '#64748b', fundo: '#f1f5f9', texto: '#334155' };
    return `<span class="badge" style="background:${s.fundo};color:${s.texto};border:1px solid ${s.cor};font-weight:700;">${s.rotulo}</span>`;
}

async function imprimirPMOCPdf(pmoc_id, mes = null, ano = null) {
    if (!usuarioLogado || !usuarioLogado.token) {
        alert("Usuário não autenticado.");
        return;
    }
    try {
        const res = await apiFetch(`/api/pmoc/manutencoes/${pmoc_id}/pdf`);
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.erro || "Falha ao gerar o documento PDF do PMOC.");
        }
        let nomeArquivo = res.headers.get('X-Filename');
        if (!nomeArquivo) {
            nomeArquivo = `${formatarNumPMOC(pmoc_id, mes, ano)}.pdf`;
        }
        const blob = await res.blob();
        const blobUrl = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = blobUrl;
        link.download = nomeArquivo;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        setTimeout(() => window.URL.revokeObjectURL(blobUrl), 30000);
    } catch (err) {
        alert("Erro ao obter PDF do PMOC: " + err.message);
    }
}

// ================= COMPONENTE VISUAL DO CALENDÁRIO ANUAL DO PMOC =================
let _pmocCalCache = null;
let _pmocCalFiltros = { ano: new Date().getFullYear(), comarca: '', busca: '', periodicidade: '', visao: 'matriz' };

const NOMES_MESES_ABREV = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"];

function badgeCicloPMOC(per, status = 'planejado', manutId = null) {
    if (!per) return '<span style="color:#cbd5e1;font-weight:bold;">—</span>';
    const mapaEstilos = {
        'A': { fundo: '#f3e8ff', texto: '#6b21a8', borda: '#c084fc', titulo: 'Anual' },
        'S': { fundo: '#ffedd5', texto: '#9a3412', borda: '#fdba74', titulo: 'Semestral' },
        'T': { fundo: '#ccfbf1', texto: '#115e59', borda: '#5eead4', titulo: 'Trimestral' },
        'M': { fundo: '#e0f2fe', texto: '#0369a1', borda: '#7dd3fc', titulo: 'Mensal' }
    };
    const c = mapaEstilos[per] || mapaEstilos['M'];
    if (status === 'reprovado' || status === 'reprovada') {
        return `<span class="badge" title="${c.titulo} (REPROVADO PELA FISCALIZAÇÃO)" style="background:#fee2e2;color:#991b1b;border:2px solid #dc2626;font-weight:800;font-size:11px;padding:3px 6px;cursor:pointer;">${per} <span style="font-size:10px;">❌</span></span>`;
    }
    const bordaEstilo = (status === 'planejado') ? `2px dashed ${c.borda}` : `2px solid ${c.borda}`;
    let icon = '';
    if (status === 'concluido') icon = ' <span style="font-size:10px;">?</span>';
    else if (status === 'gerado') icon = ' <span style="font-size:10px;">?</span>';

    return `<span class="badge" title="${c.titulo} (${status})" style="background:${c.fundo};color:${c.texto};border:${bordaEstilo};font-weight:800;font-size:11px;padding:3px 6px;cursor:pointer;">${per}${icon}</span>`;
}

async function renderizarPainelCalendarioPMOC(containerEl, podeGerar = false) {
    if (!containerEl) return;
    containerEl.innerHTML = `<div style="text-align:center;padding:30px;color:#64748b;">Carregando Janela Móvel do PMOC (24 Meses)...</div>`;

    try {
        const res = await apiFetch(`/api/pmoc/calendario?modo=janela`);
        _pmocCalCache = await res.json();
    } catch (err) {
        containerEl.innerHTML = `<div style="color:red;padding:20px;text-align:center;">Erro ao carregar o plano preventivo do PMOC: ${esc(err.message)}</div>`;
        return;
    }

    desenharEstruturaCalendarioPMOC(containerEl, podeGerar);
}

function desenharEstruturaCalendarioPMOC(containerEl, podeGerar = false) {
    if (!_pmocCalCache) return;
    const cal = _pmocCalCache;
    const gat = cal.gatilho_proximo || {};
    const janela = cal.janela || [];
    const mesInicio = janela.length ? janela[0].rotulo_completo : '-';
    const mesFim = janela.length ? janela[janela.length - 1].rotulo_completo : '-';

    // Comarcas presentes no plano
    const comarcasSet = new Set();
    (cal.equipamentos || []).forEach(e => { if (e.comarca) comarcasSet.add(e.comarca); });
    const comarcas = Array.from(comarcasSet).sort();

    let htmlBotoesAcao = `
        <button class="btn-sm btn-success" onclick="abrirModalRelatorioCicloPMOC()" style="font-weight:bold;">📊 Relatório de Ciclo (Meses Anteriores)</button>
    `;
    if (podeGerar) {
        htmlBotoesAcao += `
            <button class="btn-sm btn-info" onclick="executarRotinaPmocAutomaticaManual()">⚡ Disparar Rotina Automática</button>
        `;
    }

    containerEl.innerHTML = `
        <!-- CARD DE APRESENTAÇÃO DO PLANO: JANELA MÓVEL 24 MESES -->
        <div style="background:linear-gradient(135deg, #1e293b 0%, #0f172a 100%);color:#fff;border-radius:10px;padding:16px 20px;margin-bottom:15px;box-shadow:0 4px 15px rgba(0,0,0,0.15);">
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;">
                <div>
                    <h4 style="margin:0 0 5px 0;display:flex;align-items:center;gap:8px;color:#38bdf8;">
                        <span>📅</span> Plano de Manutenção Preventiva — Janela Móvel Contínua (Contrato por Prazo Indeterminado)
                    </h4>
                    <p style="margin:0;font-size:12px;color:#cbd5e1;line-height:1.4;">
                        <strong>Janela Deslizante de 24 Meses:</strong> Apresenta continuamente os <strong>12 meses anteriores</strong> (executados/histórico), o <strong>mês atual</strong> e os <strong>12 meses subsequentes</strong> (a executar). À medida que o tempo avança, novos ciclos entram no horizonte e os mais antigos são preservados no histórico sem qualquer limitação de tempo.<br>
                        <strong>PMOC Individualizado:</strong> Cada equipamento possui sua própria Ordem de Serviço e documento individual de manutenção preventiva.
                    </p>
                </div>
                <div style="background:rgba(255,255,255,0.1);padding:10px 14px;border-radius:8px;text-align:right;border:1px solid rgba(255,255,255,0.15);">
                    <div style="font-size:11px;color:#94a3b8;">Mês Atual em Execução: <strong style="color:#facc15;font-size:13px;">${cal.mes_atual || '-'}</strong></div>
                    <div style="font-size:11px;color:#cbd5e1;margin-top:2px;">Próxima Abertura Automática: <strong>${gat.proximo_mes || '-'}</strong> (Gatilho: ${gat.data_gatilho ? gat.data_gatilho.split('-').reverse().join('/') : '-'})</div>
                </div>
            </div>
        </div>

        <!-- BARRA DE FILTROS E CONTROLES -->
        <div style="background:#f8fafc;padding:14px;border-radius:8px;border:1px solid var(--border);margin-bottom:15px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;">
            <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
                <div>
                    <span class="badge" style="background:#0284c7;color:#fff;font-weight:bold;padding:6px 10px;font-size:12px;border-radius:6px;display:inline-block;">
                        🗓️ Janela: ${mesInicio} até ${mesFim} (${janela.length} Meses)
                    </span>
                </div>
                <div>
                    <select id="pmocCalComarca" onchange="filtrarCalendarioPMOC('comarca', this.value)" style="padding:6px 10px;font-size:12px;background:#fff;border-radius:6px;border:1px solid var(--border);margin:0;">
                        <option value="">Todas as Comarcas (${comarcas.length})</option>
                        ${comarcas.map(c => `<option value="${esc(c)}" ${_pmocCalFiltros.comarca === c ? 'selected' : ''}>${esc(c)}</option>`).join('')}
                    </select>
                </div>
                <div>
                    <select id="pmocCalCiclo" onchange="filtrarCalendarioPMOC('periodicidade', this.value)" style="padding:6px 10px;font-size:12px;background:#fff;border-radius:6px;border:1px solid var(--border);margin:0;">
                        <option value="">Todos os Ciclos</option>
                        <option value="A" ${_pmocCalFiltros.periodicidade === 'A' ? 'selected' : ''}>A - Anual (1x/ano)</option>
                        <option value="S" ${_pmocCalFiltros.periodicidade === 'S' ? 'selected' : ''}>S - Semestral (1x/ano)</option>
                        <option value="T" ${_pmocCalFiltros.periodicidade === 'T' ? 'selected' : ''}>T - Trimestral (2x/ano)</option>
                        <option value="M" ${_pmocCalFiltros.periodicidade === 'M' ? 'selected' : ''}>M - Mensal (8x/ano)</option>
                    </select>
                </div>
                <div>
                    <input type="text" id="pmocCalBusca" placeholder="Tombo, Sala, Marca..." value="${esc(_pmocCalFiltros.busca)}" oninput="filtrarCalendarioPMOC('busca', this.value)" style="padding:6px 10px;font-size:12px;margin:0;width:170px;">
                </div>
            </div>

            <!-- ALTERNÂNCIA DE VISÃO & AÇÕES -->
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
                <div style="display:flex;border:1px solid var(--border);border-radius:6px;overflow:hidden;">
                    <button class="btn-sm" onclick="mudarVisaoCalendarioPMOC('matriz')" style="margin:0;border-radius:0;background:${_pmocCalFiltros.visao === 'matriz' ? 'var(--primary-dark)' : '#fff'};color:${_pmocCalFiltros.visao === 'matriz' ? '#fff' : '#475569'};">📋 Por Equipamento</button>
                    <button class="btn-sm" onclick="mudarVisaoCalendarioPMOC('comarca')" style="margin:0;border-radius:0;background:${_pmocCalFiltros.visao === 'comarca' ? 'var(--primary-dark)' : '#fff'};color:${_pmocCalFiltros.visao === 'comarca' ? '#fff' : '#475569'};">🏛️ Consolidado por Comarca</button>
                </div>
                ${htmlBotoesAcao}
            </div>
        </div>

        <!-- LEGENDA DE CICLOS E CORES DA JANELA -->
        <div style="display:flex;gap:15px;align-items:center;margin-bottom:12px;flex-wrap:wrap;font-size:12px;background:#fff;padding:10px 14px;border-radius:6px;border:1px solid var(--border);">
            <span style="font-weight:bold;color:#475569;">Legenda de Ciclos:</span>
            <span>${badgeCicloPMOC('A')} Anual</span>
            <span>${badgeCicloPMOC('S')} Semestral</span>
            <span>${badgeCicloPMOC('T')} Trimestral</span>
            <span>${badgeCicloPMOC('M')} Mensal</span>
            <span style="border-left:1px solid #cbd5e1;padding-left:10px;color:#0284c7;font-weight:bold;">Coluna Azul: Mês Atual</span>
            <span style="color:#64748b;">Esquerda: 12 Meses Anteriores (Histórico)</span>
            <span style="color:#10b981;">Direita: 12 Meses Subsequentes (A Executar)</span>
        </div>

        <!-- ÁREA DE EXIBIÇÃO DO PLANO -->
        <div id="boxConteudoCalendarioPMOC" style="overflow-x:auto;"></div>
    `;

    renderizarConteudoVisaoCalendarioPMOC();
}

function renderizarConteudoVisaoCalendarioPMOC() {
    const box = document.getElementById('boxConteudoCalendarioPMOC');
    if (!box || !_pmocCalCache) return;

    if (_pmocCalFiltros.visao === 'comarca') {
        desenharVisaoConsolidadaComarca(box);
    } else {
        desenharVisaoMatrizEquipamentos(box);
    }
}

function desenharVisaoMatrizEquipamentos(box) {
    const cal = _pmocCalCache;
    const janela = cal.janela || [];
    let equipamentos = cal.equipamentos || [];

    // Filtros
    if (_pmocCalFiltros.comarca) {
        equipamentos = equipamentos.filter(e => e.comarca === _pmocCalFiltros.comarca);
    }
    if (_pmocCalFiltros.busca) {
        const b = _pmocCalFiltros.busca.toLowerCase();
        equipamentos = equipamentos.filter(e => 
            (e.tombo||'').toLowerCase().includes(b) ||
            (e.sala||'').toLowerCase().includes(b) ||
            (e.predio||'').toLowerCase().includes(b) ||
            (e.marca||'').toLowerCase().includes(b) ||
            (e.comarca||'').toLowerCase().includes(b)
        );
    }
    if (_pmocCalFiltros.periodicidade) {
        const p = _pmocCalFiltros.periodicidade;
        equipamentos = equipamentos.filter(e => {
            return Object.values(e.meses || {}).some(m => m.periodicidade === p);
        });
    }

    if (!equipamentos.length) {
        box.innerHTML = `<div style="text-align:center;padding:30px;color:#64748b;background:#fff;border-radius:8px;border:1px solid var(--border);">Nenhum equipamento encontrado com os filtros selecionados.</div>`;
        return;
    }

    // Cabeçalhos das 25 colunas
    const thMeses = janela.map(j => {
        if (j.tipo === 'atual') {
            return `<th style="text-align:center;padding:6px 2px;min-width:44px;background:#0284c7;color:#fff;border-top:3px solid #facc15;border-bottom:3px solid #facc15;" title="Mês Atual (${j.rotulo_completo})">
                <span style="font-size:11px;font-weight:bold;">${j.rotulo}</span><br>
                <span style="font-size:8px;background:#facc15;color:#0f172a;border-radius:2px;padding:0 2px;font-weight:800;">ATUAL</span>
            </th>`;
        } else if (j.tipo === 'passado') {
            return `<th style="text-align:center;padding:6px 2px;min-width:38px;background:#f1f5f9;color:#64748b;" title="Histórico Executado (${j.rotulo_completo})">
                <span style="font-size:11px;">${j.rotulo}</span>
            </th>`;
        } else {
            return `<th style="text-align:center;padding:6px 2px;min-width:38px;background:#f8fafc;color:#1e293b;" title="A Executar (${j.rotulo_completo})">
                <span style="font-size:11px;">${j.rotulo}</span>
            </th>`;
        }
    }).join('');

    let linhasHtml = '';
    equipamentos.forEach(eq => {
        let celulasMeses = '';
        janela.forEach(j => {
            const mInfo = (eq.meses || {})[j.chave];
            const badge = (mInfo && mInfo.periodicidade)
                ? badgeCicloPMOC(mInfo.periodicidade, mInfo.status, mInfo.manutencao_id)
                : '<span style="color:#cbd5e1;font-weight:bold;">—</span>';
            if (j.tipo === 'atual') {
                celulasMeses += `<td style="text-align:center;padding:5px 2px;background:#f0f9ff;border-left:1px solid #bae6fd;border-right:1px solid #bae6fd;">${badge}</td>`;
            } else {
                celulasMeses += `<td style="text-align:center;padding:5px 2px;">${badge}</td>`;
            }
        });

        linhasHtml += `
            <tr style="border-bottom:1px solid var(--border);">
                <td style="padding:8px 6px;white-space:nowrap;"><strong>${esc(eq.tombo)}</strong><br><small style="color:#64748b;">${esc(eq.tipo_equipamento || 'AC')}</small></td>
                <td style="padding:8px 6px;white-space:nowrap;"><strong>${esc(eq.comarca)}</strong></td>
                <td style="padding:8px 6px;"><small>${esc(eq.predio)}<br>${esc(eq.sala)}</small></td>
                <td style="padding:8px 6px;white-space:nowrap;"><small>${esc(eq.marca)} ${esc(eq.capacidade || '')}</small></td>
                ${celulasMeses}
            </tr>
        `;
    });

    box.innerHTML = `
        <table style="width:100%;border-collapse:collapse;background:#fff;font-size:12px;">
            <thead>
                <tr style="background:#f1f5f9;color:#334155;border-bottom:2px solid var(--border);">
                    <th style="padding:8px 6px;min-width:110px;">Tombo / Tipo</th>
                    <th style="padding:8px 6px;min-width:100px;">Comarca</th>
                    <th style="padding:8px 6px;min-width:120px;">Local</th>
                    <th style="padding:8px 6px;min-width:110px;">Marca / Cap.</th>
                    ${thMeses}
                </tr>
            </thead>
            <tbody>${linhasHtml}</tbody>
        </table>
        <div style="font-size:11px;color:#64748b;margin-top:8px;text-align:right;">Exibindo ${equipamentos.length} de ${cal.total_equipamentos} equipamentos na Janela Móvel de 24 Meses.</div>
    `;
}

function desenharVisaoConsolidadaComarca(box) {
    const cal = _pmocCalCache;
    const janela = cal.janela || [];
    const resumo = cal.resumo_comarcas || {};
    const comarcas = Object.keys(resumo).sort();

    if (!comarcas.length) {
        box.innerHTML = `<div style="text-align:center;padding:30px;color:#64748b;background:#fff;border-radius:8px;">Sem dados de comarcas na janela móvel.</div>`;
        return;
    }

    const thMeses = janela.map(j => {
        if (j.tipo === 'atual') {
            return `<th style="text-align:center;padding:6px 2px;min-width:44px;background:#0284c7;color:#fff;border-top:3px solid #facc15;border-bottom:3px solid #facc15;" title="Mês Atual (${j.rotulo_completo})">
                <span style="font-size:11px;font-weight:bold;">${j.rotulo}</span><br>
                <span style="font-size:8px;background:#facc15;color:#0f172a;border-radius:2px;padding:0 2px;font-weight:800;">ATUAL</span>
            </th>`;
        } else if (j.tipo === 'passado') {
            return `<th style="text-align:center;padding:6px 2px;min-width:38px;background:#f1f5f9;color:#64748b;" title="Histórico Executado (${j.rotulo_completo})">
                <span style="font-size:11px;">${j.rotulo}</span>
            </th>`;
        } else {
            return `<th style="text-align:center;padding:6px 2px;min-width:38px;background:#f8fafc;color:#1e293b;" title="A Executar (${j.rotulo_completo})">
                <span style="font-size:11px;">${j.rotulo}</span>
            </th>`;
        }
    }).join('');

    let linhasHtml = '';
    comarcas.forEach(com => {
        if (_pmocCalFiltros.comarca && com !== _pmocCalFiltros.comarca) return;

        let colunasMeses = '';
        let totalComarcaMesAtual = 0;
        janela.forEach(j => {
            const mData = (resumo[com] || {})[j.chave] || { A: 0, S: 0, T: 0, M: 0, total: 0 };
            if (j.tipo === 'atual') totalComarcaMesAtual = mData.total;
            const bg = j.tipo === 'atual' ? 'background:#f0f9ff;border-left:1px solid #bae6fd;border-right:1px solid #bae6fd;' : '';
            colunasMeses += `
                <td style="text-align:center;padding:6px 2px;font-size:10px;line-height:1.2;${bg}">
                    ${mData.A ? `<span style="color:#6b21a8;font-weight:bold;">${mData.A}A</span> ` : ''}
                    ${mData.S ? `<span style="color:#9a3412;font-weight:bold;">${mData.S}S</span> ` : ''}
                    ${mData.T ? `<span style="color:#115e59;font-weight:bold;">${mData.T}T</span> ` : ''}
                    ${mData.M ? `<span style="color:#0369a1;">${mData.M}M</span>` : ''}
                    <div style="color:#94a3b8;font-size:9px;">(${mData.total})</div>
                </td>
            `;
        });

        linhasHtml += `
            <tr style="border-bottom:1px solid var(--border);">
                <td style="padding:10px;font-weight:bold;">${esc(com)}</td>
                <td style="text-align:center;padding:10px;font-weight:bold;color:var(--primary-dark);">${totalComarcaMesAtual}</td>
                ${colunasMeses}
            </tr>
        `;
    });

    box.innerHTML = `
        <table style="width:100%;border-collapse:collapse;background:#fff;font-size:12px;">
            <thead>
                <tr style="background:#f1f5f9;color:#334155;border-bottom:2px solid var(--border);">
                    <th style="padding:10px;min-width:130px;">Comarca</th>
                    <th style="text-align:center;padding:10px;min-width:70px;">Máquinas</th>
                    ${thMeses}
                </tr>
            </thead>
            <tbody>${linhasHtml}</tbody>
        </table>
        <div style="font-size:11px;color:#64748b;margin-top:8px;">Distribuição do rodízio equilibrada na Janela Móvel de 24 Meses: cada comarca atende proporcionalmente seus ciclos sem sobrecarga.</div>
    `;
}

function filtrarCalendarioPMOC(campo, valor) {
    _pmocCalFiltros[campo] = valor;
    renderizarConteudoVisaoCalendarioPMOC();
}

function mudarVisaoCalendarioPMOC(visao) {
    _pmocCalFiltros.visao = visao;
    desenharEstruturaCalendarioPMOC(document.getElementById('painelCalendarioPMOCContainer'), true);
}

async function executarRotinaPmocAutomaticaManual() {
    if (!confirm("Deseja executar a rotina automática agora? Ela verificará as ordens aglutinadas do mês atual e do próximo mês (se faltar 5 dias ou menos).")) return;
    try {
        const res = await (await apiFetch('/api/pmoc/rotina-automatica', { method: 'POST' })).json();
        alert(`Rotina executada com sucesso!\n${(res.mensagens || []).join('\n')}`);
        renderizarPainelCalendarioPMOC(document.getElementById('painelCalendarioPMOCContainer'), true);
    } catch (e) {
        alert("Erro ao disparar rotina: " + e.message);
    }
}

async function limparTestesPmocManual() {
    if (!confirm("ATENÇÃO: Deseja limpar os chamados de teste do banco de dados e resetar o PMOC para o cronograma oficial aglutinado?")) return;
    try {
        const res = await (await apiFetch('/api/pmoc/limpar-testes', { method: 'POST' })).json();
        alert(res.mensagem || "Limpeza de testes concluída!");
        await apiFetch('/api/pmoc/rotina-automatica', { method: 'POST' });
        renderizarPainelCalendarioPMOC(document.getElementById('painelCalendarioPMOCContainer'), true);
    } catch (e) {
        alert("Erro ao limpar testes: " + e.message);
    }
}

/* ==========================================================================
   MODAIS E FUNÇÕES DE HISTÓRICO DE EQUIPAMENTOS (CORRETIVAS E PREVENTIVAS)
   ========================================================================== */

function garantirModaisHistoricoEquipamento() {
    if (document.getElementById('modalHistoricoCorretivasEq')) return;

    const divModais = document.createElement('div');
    divModais.innerHTML = `
        <!-- MODAL HISTÓRICO CORRETIVAS -->
        <div id="modalHistoricoCorretivasEq" class="modal-overlay hidden">
            <div class="modal-box" style="max-width: 900px;">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px;border-bottom:1px solid var(--border);padding-bottom:10px;">
                    <div>
                        <h3 id="histCorretivasTitulo" style="margin:0 0 4px 0;color:var(--primary-dark);">🛠️ Histórico de O.S. Corretivas</h3>
                        <div id="histCorretivasSub" style="font-size:12px;color:#475569;"></div>
                    </div>
                    <button class="btn-danger btn-sm" onclick="fecharModal('modalHistoricoCorretivasEq')" style="padding:4px 8px;">✕</button>
                </div>

                <div id="histCorretivasAcoesTop" style="margin-bottom:14px;display:flex;justify-content:flex-end;align-items:center;">
                    <!-- Botão "+ Abrir O.S. Corretiva" injetado dinamicamente -->
                </div>

                <div style="overflow-x:auto;max-height:360px;border:1px solid var(--border);border-radius:6px;">
                    <table style="width:100%;border-collapse:collapse;margin:0;font-size:12px;">
                        <thead style="background:#f1f5f9;position:sticky;top:0;z-index:2;">
                            <tr>
                                <th style="padding:8px;">O.S. / Data</th>
                                <th style="padding:8px;">Tipo / Relato da Falha</th>
                                <th style="padding:8px;">Solicitante</th>
                                <th style="padding:8px;text-align:center;">Status</th>
                                <th style="padding:8px;text-align:center;">Ações</th>
                            </tr>
                        </thead>
                        <tbody id="tabelaHistoricoCorretivasCorpo"></tbody>
                    </table>
                </div>

                <div style="margin-top:14px;text-align:right;">
                    <button class="btn btn-secondary" onclick="fecharModal('modalHistoricoCorretivasEq')">Fechar</button>
                </div>
            </div>
        </div>

        <!-- MODAL HISTÓRICO PREVENTIVAS (PMOC) -->
        <div id="modalHistoricoPreventivasEq" class="modal-overlay hidden">
            <div class="modal-box" style="max-width: 920px;">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px;border-bottom:1px solid var(--border);padding-bottom:10px;">
                    <div>
                        <h3 id="histPreventivasTitulo" style="margin:0 0 4px 0;color:#0369a1;">📅 Histórico de Manutenções Preventivas (PMOC)</h3>
                        <div id="histPreventivasSub" style="font-size:12px;color:#475569;"></div>
                    </div>
                    <button class="btn-danger btn-sm" onclick="fecharModal('modalHistoricoPreventivasEq')" style="padding:4px 8px;">✕</button>
                </div>

                <div style="overflow-x:auto;max-height:360px;border:1px solid var(--border);border-radius:6px;">
                    <table style="width:100%;border-collapse:collapse;margin:0;font-size:12px;">
                        <thead style="background:#f1f5f9;position:sticky;top:0;z-index:2;">
                            <tr>
                                <th style="padding:8px;">PMOC / Competência</th>
                                <th style="padding:8px;text-align:center;">Periodicidade</th>
                                <th style="padding:8px;">Medições Elétricas / Térmicas</th>
                                <th style="padding:8px;">Técnico</th>
                                <th style="padding:8px;text-align:center;">Status</th>
                                <th style="padding:8px;text-align:center;">Ações</th>
                            </tr>
                        </thead>
                        <tbody id="tabelaHistoricoPreventivasCorpo"></tbody>
                    </table>
                </div>

                <div style="margin-top:14px;text-align:right;">
                    <button class="btn btn-secondary" onclick="fecharModal('modalHistoricoPreventivasEq')">Fechar</button>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(divModais);
}

function abrirNovaOSParaEquipamentoAtual(eqId) {
    const eq = (window.equipamentosCache || []).find(e => e.id == eqId);
    if (!eq) return;
    if (eq.ativo !== 1) {
        alert("Este equipamento está inativo e não pode receber novas Ordens de Serviço.");
        return;
    }
    fecharModal('modalHistoricoCorretivasEq');
    const nome = `${eq.tipo_equipamento} ${eq.capacidade || ''} (Tombo: ${eq.tombo || 'S/T'})`;
    const local = `${eq.comarca} - ${eq.predio} / ${eq.sala}`;
    if (typeof abrirModalNovaOSAvulsaPeloEq === 'function') {
        abrirModalNovaOSAvulsaPeloEq(eq.id, nome, local);
    } else {
        alert("Função de abertura de O.S. não disponível nesta tela.");
    }
}

async function abrirHistoricoCorretivasEq(eq_id) {
    garantirModaisHistoricoEquipamento();
    const modal = document.getElementById('modalHistoricoCorretivasEq');
    modal.classList.remove('hidden');

    const lblTitulo = document.getElementById('histCorretivasTitulo');
    const lblSub = document.getElementById('histCorretivasSub');
    const boxBotaoAbrir = document.getElementById('histCorretivasAcoesTop');
    const tbody = document.getElementById('tabelaHistoricoCorretivasCorpo');

    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:15px;">Carregando histórico de O.S. corretivas...</td></tr>';

    let eq = (window.equipamentosCache || []).find(e => e.id == eq_id);
    if (!eq) {
        try {
            const resp = await (await apiFetch(`/api/equipamentos`)).json();
            window.equipamentosCache = resp;
            eq = resp.find(e => e.id == eq_id);
        } catch (e) {}
    }

    if (eq) {
        lblTitulo.textContent = `Histórico de O.S. Corretivas — Tombo: ${eq.tombo || 'S/T'}`;
        const stHtml = eq.ativo === 1
            ? `<span class="badge" style="background:#10b981;color:#fff;">ATIVO</span>`
            : `<span class="badge" style="background:#ef4444;color:#fff;">INATIVO</span>`;
        lblSub.innerHTML = `<strong>${esc(eq.tipo_equipamento)} ${esc(eq.capacidade || '')}</strong> | Marca: ${esc(eq.marca || '-')} | Local: ${esc(eq.comarca)} - ${esc(eq.predio)} / ${esc(eq.sala)} | Status: ${stHtml}`;

        if (eq.ativo === 1) {
            boxBotaoAbrir.innerHTML = `
                <button class="btn btn-success" onclick="abrirNovaOSParaEquipamentoAtual(${eq.id})" style="display:inline-flex;align-items:center;gap:6px;font-weight:bold;box-shadow:0 2px 6px rgba(16,185,129,0.3);padding:8px 16px;">
                    ➕ Abrir O.S. Corretiva
                </button>
            `;
        } else {
            boxBotaoAbrir.innerHTML = `
                <div style="background:#fee2e2;color:#991b1b;border:1px solid #f87171;padding:6px 12px;border-radius:6px;font-size:12px;font-weight:bold;">
                    ⚠️ Equipamento Inativo — Bloqueado para abertura de novas O.S. (Reative-o para abrir chamados)
                </div>
            `;
        }
    }

    try {
        const chamados = await (await apiFetch(`/api/equipamentos/${eq_id}/os`)).json();
        if (!chamados || chamados.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:20px;color:#64748b;">Nenhuma Ordem de Serviço registrada para este equipamento.</td></tr>';
            return;
        }

        let html = '';
        chamados.forEach(os => {
            let cor = '#3b82f6';
            if (os.status === 'concluida') cor = '#10b981';
            if (os.status === 'cancelada') cor = '#ef4444';
            if (os.status === 'em_execucao') cor = '#f59e0b';
            if (os.status === 'aguardando_peca') cor = '#8b5cf6';
            if (os.status === 'aprovada') cor = '#0ea5e9';
            if (os.status === 'em_analise') cor = '#4f46e5';

            const btnAnexo = os.arquivo_conclusao
                ? `<a href="#" onclick="event.preventDefault(); abrirAnexo('${esc(os.arquivo_conclusao)}'); return false;" class="btn-sm btn-success" style="text-decoration:none;display:inline-block;margin-left:4px;">📎 Anexo</a>`
                : '';

            const btnDetalhes = (typeof abrirDetalhesOS === 'function')
                ? `<button class="btn-sm btn-secondary" onclick="fecharModal('modalHistoricoCorretivasEq'); abrirDetalhesOS(${os.id});">Detalhes</button>`
                : '';

            html += `
                <tr>
                    <td><strong>${formatarNumOS(os.id, os.data_abertura)}</strong><br><small style="color:#64748b;">${dataFormatada(os.data_abertura)}</small></td>
                    <td>${seloTipoOS(os.tipo_os)}<br><small style="color:#334155;">${esc(os.descricao_falha)}</small></td>
                    <td><small>${esc(os.nome_solicitante || '-')}</small></td>
                    <td style="text-align:center;"><span class="badge" style="background:${cor};color:white;">${os.status.replace('_', ' ').toUpperCase()}</span></td>
                    <td style="text-align:center;white-space:nowrap;">
                        ${btnDetalhes}
                        <button class="btn-sm btn-info" onclick="imprimirOSPdf(${os.id}, ${os.data_abertura})">🖨️ PDF</button>
                        ${btnAnexo}
                    </td>
                </tr>
            `;
        });
        tbody.innerHTML = html;
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;padding:15px;color:red;">Erro ao buscar histórico de corretivas: ${esc(err.message)}</td></tr>`;
    }
}

async function abrirHistoricoPreventivasEq(eq_id) {
    garantirModaisHistoricoEquipamento();
    const modal = document.getElementById('modalHistoricoPreventivasEq');
    modal.classList.remove('hidden');

    const lblTitulo = document.getElementById('histPreventivasTitulo');
    const lblSub = document.getElementById('histPreventivasSub');
    const tbody = document.getElementById('tabelaHistoricoPreventivasCorpo');

    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:15px;">Carregando histórico de preventivas PMOC...</td></tr>';

    let eq = (window.equipamentosCache || []).find(e => e.id == eq_id);
    if (!eq) {
        try {
            const resp = await (await apiFetch(`/api/equipamentos`)).json();
            window.equipamentosCache = resp;
            eq = resp.find(e => e.id == eq_id);
        } catch (e) {}
    }

    if (eq) {
        lblTitulo.textContent = `Histórico de Preventivas (PMOC) — Tombo: ${eq.tombo || 'S/T'}`;
        const stHtml = eq.ativo === 1
            ? `<span class="badge" style="background:#10b981;color:#fff;">ATIVO NO PLANO</span>`
            : `<span class="badge" style="background:#ef4444;color:#fff;">INATIVO</span>`;
        lblSub.innerHTML = `<strong>${esc(eq.tipo_equipamento)} ${esc(eq.capacidade || '')}</strong> | Marca: ${esc(eq.marca || '-')} | Local: ${esc(eq.comarca)} - ${esc(eq.predio)} / ${esc(eq.sala)} | Status: ${stHtml}`;
    }

    try {
        const preventivas = await (await apiFetch(`/api/equipamentos/${eq_id}/pmoc`)).json();
        if (!preventivas || preventivas.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:20px;color:#64748b;">Nenhuma manutenção preventiva registrada para este equipamento.</td></tr>';
            return;
        }

        let html = '';
        preventivas.forEach(p => {
            const cod = formatarNumPMOC(p.id, p.mes_competencia, p.ano_competencia);
            const btnFolha = p.arquivo_folha_assinada
                ? `<a href="#" onclick="event.preventDefault();abrirAnexo('${esc(p.arquivo_folha_assinada)}');return false;" class="btn-sm btn-success" style="text-decoration:none;display:inline-block;margin-left:3px;">📎 Folha</a>`
                : '';
            const med = (p.tensao_medida || p.corrente_medida)
                ? `${esc(p.tensao_medida || '-')}V / ${esc(p.corrente_medida || '-')}A`
                : '-';
            const temp = (p.temperatura_insuflamento || p.temperatura_retorno)
                ? `Ins: ${esc(p.temperatura_insuflamento || '-')}°C | Ret: ${esc(p.temperatura_retorno || '-')}°C`
                : '-';

            const btnValidar = (typeof abrirValidarPMOC === 'function')
                ? `<button class="btn-sm btn-secondary" onclick="fecharModal('modalHistoricoPreventivasEq'); abrirValidarPMOC(${p.id});">Detalhes</button>`
                : '';

            html += `
                <tr>
                    <td><strong>${cod}</strong><br><small style="color:#64748b;">${String(p.mes_competencia).padStart(2,'0')}/${p.ano_competencia}</small></td>
                    <td style="text-align:center;">${seloPeriodicidade(p.periodicidade)}</td>
                    <td><small>${med}<br><span style="color:#64748b;">${temp}</span></small></td>
                    <td><small>${esc(p.nome_executante || 'Não atribuído')}</small></td>
                    <td style="text-align:center;">${seloStatusPMOC(p.item_status || p.status)}</td>
                    <td style="text-align:center;white-space:nowrap;">
                        ${btnValidar}
                        <button class="btn-sm btn-info" onclick="imprimirPMOCPdf(${p.id}, ${p.mes_competencia}, ${p.ano_competencia})">🖨️ PDF</button>
                        ${btnFolha}
                    </td>
                </tr>
            `;
        });
        tbody.innerHTML = html;
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:15px;color:red;">Erro ao buscar histórico de preventivas: ${esc(err.message)}</td></tr>`;
    }
}



/* ==========================================================================
   RELATÓRIO DE FECHAMENTO DE CICLO MENSAL DO PMOC (POR COMARCA EM LISTA)
   ========================================================================== */

let _relatorioCicloContratosCache = [];

function garantirModalRelatorioCicloPMOC() {
    if (document.getElementById('modalRelatorioCicloPMOC')) return;

    const div = document.createElement('div');
    div.innerHTML = `
        <div id="modalRelatorioCicloPMOC" class="modal-overlay hidden">
            <div class="modal-box" style="max-width: 1050px; width: 96%;">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px;border-bottom:1px solid var(--border);padding-bottom:10px;">
                    <div>
                        <h3 style="margin:0 0 4px 0;color:var(--primary-dark);">📊 Relatório de Fechamento de Ciclo Mensal (PMOC)</h3>
                        <div style="font-size:12px;color:#475569;">
                            Relação de todos os equipamentos do contrato, separados por comarca, apontando a manutenção realizada (<strong>M, T, S, A</strong>) ou <strong>"Não Realizada"</strong>.
                        </div>
                    </div>
                    <button class="btn-danger btn-sm" onclick="fecharModal('modalRelatorioCicloPMOC')" style="padding:4px 8px;">✕</button>
                </div>

                <!-- BARRA DE SELEÇÃO DE CONTRATO E MÊS/ANO DO CICLO -->
                <div style="background:#f8fafc;padding:12px 15px;border-radius:8px;border:1px solid var(--border);margin-bottom:14px;display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap;justify-content:space-between;">
                    <div style="display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap;">
                        <div>
                            <label style="font-size:11px;font-weight:bold;margin-bottom:3px;display:block;">Contrato:</label>
                            <select id="relCicloContratoSelect" onchange="carregarVisualizacaoRelatorioCicloPMOC()" style="margin:0;padding:7px 10px;font-size:12px;min-width:260px;background:#fff;"></select>
                        </div>
                        <div>
                            <label style="font-size:11px;font-weight:bold;margin-bottom:3px;display:block;">Mês / Ano do Ciclo (Meses Anteriores):</label>
                            <select id="relCicloCompetenciaSelect" onchange="carregarVisualizacaoRelatorioCicloPMOC()" style="margin:0;padding:7px 10px;font-size:12px;min-width:210px;background:#fff;"></select>
                        </div>
                        <button type="button" class="btn btn-primary" onclick="carregarVisualizacaoRelatorioCicloPMOC()" style="padding:7px 14px;font-size:12px;">
                            🔍 Atualizar Consulta
                        </button>
                    </div>
                    <div>
                        <button type="button" class="btn btn-info" onclick="imprimirRelatorioCicloPMOCPdf()" style="padding:8px 16px;font-size:12px;font-weight:bold;display:inline-flex;align-items:center;gap:6px;">
                            🖨️ Emitir Relatório em PDF
                        </button>
                    </div>
                </div>

                <!-- RESUMO DO CICLO -->
                <div id="relCicloResumoBox" style="margin-bottom:14px;"></div>

                <!-- LISTAGEM POR COMARCA -->
                <div id="relCicloConteudoBox" style="max-height:430px;overflow-y:auto;border:1px solid var(--border);border-radius:8px;padding:10px;background:#fff;">
                    <div style="text-align:center;padding:25px;color:#64748b;">Carregando relatório...</div>
                </div>

                <div style="margin-top:14px;text-align:right;">
                    <button class="btn btn-secondary" onclick="fecharModal('modalRelatorioCicloPMOC')">Fechar</button>
                </div>
            </div>
        </div>
    `;
    document.body.appendChild(div);
}

async function abrirModalRelatorioCicloPMOC() {
    garantirModalRelatorioCicloPMOC();
    const modal = document.getElementById('modalRelatorioCicloPMOC');
    modal.classList.remove('hidden');

    // Popular contratos
    const selContrato = document.getElementById('relCicloContratoSelect');
    try {
        const resCt = await apiFetch('/api/contratos');
        if (resCt.ok) {
            _relatorioCicloContratosCache = await resCt.json();
        }
    } catch (e) {}

    let htmlCt = `<option value="">Todos os Contratos Vinculados</option>`;
    (_relatorioCicloContratosCache || []).forEach(c => {
        htmlCt += `<option value="${c.id}">${esc(c.numero_contrato)} - ${esc(c.nome_empresa)}</option>`;
    });
    selContrato.innerHTML = htmlCt;

    // Popular os 12 meses anteriores + mês atual
    const selComp = document.getElementById('relCicloCompetenciaSelect');
    const hoje = new Date();
    const anoAtual = hoje.getFullYear();
    const mesAtual = hoje.getMonth() + 1;
    const nomesMeses = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro'];

    let htmlComp = '';
    for (let offset = -1; offset >= -12; offset--) {
        const totalM = (anoAtual * 12) + (mesAtual - 1) + offset;
        const a = Math.floor(totalM / 12);
        const m = (totalM % 12) + 1;
        const val = `${a}-${String(m).padStart(2, '0')}`;
        const label = `${String(m).padStart(2, '0')}/${a} — ${nomesMeses[m - 1]} / ${a} (Ciclo Encerrado)`;
        htmlComp += `<option value="${val}" ${offset === -1 ? 'selected' : ''}>${label}</option>`;
    }
    // Adicionar também opção do mês atual no final para consulta parcial
    htmlComp += `<option value="${anoAtual}-${String(mesAtual).padStart(2, '0')}">${String(mesAtual).padStart(2, '0')}/${anoAtual} — ${nomesMeses[mesAtual - 1]} / ${anoAtual} (Ciclo Atual em Andamento)</option>`;
    selComp.innerHTML = htmlComp;

    await carregarVisualizacaoRelatorioCicloPMOC();
}

async function carregarVisualizacaoRelatorioCicloPMOC() {
    const selContrato = document.getElementById('relCicloContratoSelect');
    const selComp = document.getElementById('relCicloCompetenciaSelect');
    const boxResumo = document.getElementById('relCicloResumoBox');
    const boxConteudo = document.getElementById('relCicloConteudoBox');

    if (!selComp || !boxConteudo) return;
    const [anoStr, mesStr] = (selComp.value || '2026-09').split('-');
    const contratoId = selContrato ? selContrato.value : '';

    boxConteudo.innerHTML = `<div style="text-align:center;padding:30px;color:#64748b;">Gerando relatório consolidado por comarca para ${mesStr}/${anoStr}...</div>`;

    try {
        let url = `/api/pmoc/relatorio-ciclo?ano=${encodeURIComponent(anoStr)}&mes=${encodeURIComponent(mesStr)}`;
        if (contratoId) url += `&contrato_id=${encodeURIComponent(contratoId)}`;

        const res = await apiFetch(url);
        const data = await res.json();
        if (!res.ok) {
            boxConteudo.innerHTML = `<div style="color:red;text-align:center;padding:20px;">${esc(data.erro || 'Erro ao carregar relatório.')}</div>`;
            return;
        }

        const r = data.resumo || {};
        boxResumo.innerHTML = `
            <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(145px, 1fr));gap:10px;">
                <div style="background:#f1f5f9;padding:10px 12px;border-radius:6px;border-left:4px solid #0284c7;">
                    <div style="font-size:11px;color:#64748b;">Total de Equipamentos</div>
                    <div style="font-size:18px;font-weight:bold;color:#0f172a;">${r.total_equipamentos || 0}</div>
                </div>
                <div style="background:#ecfdf5;padding:10px 12px;border-radius:6px;border-left:4px solid #10b981;">
                    <div style="font-size:11px;color:#065f46;">Preventivas Concluídas</div>
                    <div style="font-size:18px;font-weight:bold;color:#047857;">${r.total_realizadas || 0} <span style="font-size:12px;font-weight:normal;">(${r.percentual_execucao || 0}%)</span></div>
                </div>
                <div style="background:#eff6ff;padding:10px 12px;border-radius:6px;border-left:4px solid #3b82f6;">
                    <div style="font-size:11px;color:#1e40af;">Por Tipo de Manutenção</div>
                    <div style="font-size:12px;font-weight:bold;color:#1e3a8a;margin-top:3px;">
                        M: ${r.M || 0} | T: ${r.T || 0} | S: ${r.S || 0} | A: ${r.A || 0}
                    </div>
                </div>
                <div style="background:#fef2f2;padding:10px 12px;border-radius:6px;border-left:4px solid #dc2626;">
                    <div style="font-size:11px;color:#991b1b;font-weight:bold;">Reprovadas (Avaliação)</div>
                    <div style="font-size:18px;font-weight:bold;color:#dc2626;">${r.reprovadas || 0}</div>
                </div>
                <div style="background:#fff7ed;padding:10px 12px;border-radius:6px;border-left:4px solid #f97316;">
                    <div style="font-size:11px;color:#9a3412;">Não Realizadas</div>
                    <div style="font-size:18px;font-weight:bold;color:#c2410c;">${r.nao_realizadas || 0}</div>
                </div>
            </div>
        `;

        const comarcas = data.comarcas || [];
        if (!comarcas.length) {
            boxConteudo.innerHTML = `<div style="text-align:center;padding:25px;color:#64748b;">Nenhum equipamento encontrado para este contrato.</div>`;
            return;
        }

        let html = '';
        comarcas.forEach(bloco => {
            html += `
                <div style="margin-bottom:18px;border:1px solid var(--border);border-radius:6px;overflow:hidden;">
                    <div style="background:#1e293b;color:#fff;padding:8px 12px;display:flex;justify-content:space-between;align-items:center;font-size:13px;font-weight:bold;">
                        <span>🏛️ COMARCA: ${esc(bloco.comarca)}</span>
                        <span style="font-size:11px;color:#cbd5e1;">
                            Total: <strong style="color:#fff;">${bloco.total}</strong> |
                            Concluídas: <strong style="color:#4ade80;">${bloco.realizadas}</strong> |
                            Reprovadas: <strong style="color:#f87171;">${bloco.reprovadas || 0}</strong> |
                            Não Realizadas: <strong style="color:#fbbf24;">${bloco.nao_realizadas}</strong>
                        </span>
                    </div>
                    <table style="width:100%;border-collapse:collapse;margin:0;font-size:11px;">
                        <thead>
                            <tr style="background:#f1f5f9;color:#334155;border-bottom:1px solid var(--border);">
                                <th style="padding:6px;width:40px;text-align:center;">Nº</th>
                                <th style="padding:6px;width:90px;">Tombo</th>
                                <th style="padding:6px;">Prédio / Local</th>
                                <th style="padding:6px;">Equipamento / Marca / Cap.</th>
                                <th style="padding:6px;width:110px;">Contrato</th>
                                <th style="padding:6px;width:95px;text-align:center;">O.S. PMOC</th>
                                <th style="padding:6px;width:85px;text-align:center;">Data Exec.</th>
                                <th style="padding:6px;width:140px;text-align:center;">Manutenção / Status</th>
                            </tr>
                        </thead>
                        <tbody>
            `;

            (bloco.equipamentos || []).forEach((eq, idx) => {
                let badgeManut = '';
                if (eq.reprovada || eq.manutencao_apontada === 'REPROVADO') {
                    const just = eq.justificativa_fiscal ? `<div style="font-size:9px;color:#991b1b;margin-top:2px;">${esc(eq.justificativa_fiscal)}</div>` : '';
                    badgeManut = `<span class="badge" style="background:#dc2626;color:#fff;border:1px solid #991b1b;font-weight:bold;padding:3px 8px;">❌ REPROVADO</span>${just}`;
                } else if (eq.realizada) {
                    badgeManut = `${badgeCicloPMOC(eq.manutencao_apontada, 'concluido')} <strong style="color:#047857;font-size:11px;margin-left:3px;">(${esc(eq.manutencao_apontada)})</strong>`;
                } else {
                    badgeManut = `<span class="badge" style="background:#fee2e2;color:#b91c1c;border:1px solid #f87171;font-weight:bold;padding:3px 8px;">Não Realizada</span>`;
                }

                html += `
                    <tr style="border-bottom:1px solid #f1f5f9;">
                        <td style="padding:6px;text-align:center;color:#64748b;">${idx + 1}</td>
                        <td style="padding:6px;"><strong>${esc(eq.tombo)}</strong></td>
                        <td style="padding:6px;">${esc(eq.predio)} / ${esc(eq.sala)}</td>
                        <td style="padding:6px;">${esc(eq.tipo_equipamento)} ${esc(eq.capacidade || '')} <small style="color:#64748b;">(${esc(eq.marca)})</small></td>
                        <td style="padding:6px;font-size:10px;">${esc(eq.numero_contrato)}</td>
                        <td style="padding:6px;text-align:center;font-weight:bold;">${esc(eq.num_pmoc)}</td>
                        <td style="padding:6px;text-align:center;">${esc(eq.data_execucao_fmt)}</td>
                        <td style="padding:6px;text-align:center;">${badgeManut}</td>
                    </tr>
                `;
            });

            html += `</tbody></table></div>`;
        });

        boxConteudo.innerHTML = html;
    } catch (err) {
        boxConteudo.innerHTML = `<div style="color:red;text-align:center;padding:20px;">Erro ao carregar relatório: ${esc(err.message)}</div>`;
    }
}

async function imprimirRelatorioCicloPMOCPdf() {
    const selContrato = document.getElementById('relCicloContratoSelect');
    const selComp = document.getElementById('relCicloCompetenciaSelect');
    if (!selComp) return;

    const [anoStr, mesStr] = (selComp.value || '2026-09').split('-');
    const contratoId = selContrato ? selContrato.value : '';

    try {
        let ep = `/api/pmoc/relatorio-ciclo/pdf?ano=${encodeURIComponent(anoStr)}&mes=${encodeURIComponent(mesStr)}`;
        if (contratoId) ep += `&contrato_id=${encodeURIComponent(contratoId)}`;

        const res = await apiFetch(ep);
        if (!res.ok) {
            const err = await res.json();
            alert(err.erro || "Falha ao gerar o PDF do relatório de ciclo.");
            return;
        }
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.target = '_blank';
        a.download = `Relatorio_Ciclo_PMOC_${mesStr}_${anoStr}.pdf`;
        document.body.appendChild(a);
        a.click();
        setTimeout(() => {
            window.URL.revokeObjectURL(url);
            a.remove();
        }, 5000);
    } catch (e) {
        alert("Erro ao emitir PDF do relatório: " + e.message);
    }
}
