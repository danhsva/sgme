"""
SGME - Catálogo Oficial de Atividades do PMOC (Plano de Manutenção, Operação e Controle)
Baseado no ANEXO 2 - Modelo Proposto do Tribunal de Justiça do Estado do Ceará (TJCE)

Periodicidades:
  M = Mensal
  T = Trimestral
  S = Semestral
  A = Anual
"""

# Periodicidades hierárquicas: quais periodicidades de itens se aplicam a um ciclo
PERIODICIDADES_APLICAVEIS = {
    'M': {'M'},
    'T': {'M', 'T'},
    'S': {'M', 'T', 'S'},
    'A': {'M', 'T', 'S', 'A'}
}

# 1. CONDICIONADORES DOMÉSTICOS ("Janela" / "Mini-Split" / Hi-Wall / Cassete / Piso Teto / Multi-Split / Cortina de Ar)
CATALOGO_DOMESTICO = [
    # 1 Ventiladores
    {"codigo": "1.1", "grupo": "Ventiladores", "descricao": "Verificar e corrigir limpeza (carcaça e rotor) e fixação do conjunto.", "periodicidade": "T"},
    {"codigo": "1.2", "grupo": "Ventiladores", "descricao": "Verificar e corrigir vibrações, ruídos anormais e aquecimento anormal dos mancais.", "periodicidade": "T"},
    {"codigo": "1.3", "grupo": "Ventiladores", "descricao": "Limpar sistema de drenagem.", "periodicidade": "T"},
    {"codigo": "1.4", "grupo": "Ventiladores", "descricao": "Verificar e corrigir o estado de amortecedores de vibração.", "periodicidade": "T"},

    # 2 Motores Elétricos
    {"codigo": "2.1", "grupo": "Motores Elétricos", "descricao": "Verificar e corrigir a fixação e a existência de sujeiras, danos e corrosão.", "periodicidade": "T"},
    {"codigo": "2.2", "grupo": "Motores Elétricos", "descricao": "Verificar e corrigir vibrações e ruídos anormais.", "periodicidade": "T"},

    # 3 Filtros Secos
    {"codigo": "3.1", "grupo": "Filtros Secos", "descricao": "Verificar e corrigir a existência de sujeira, danos e corrosão.", "periodicidade": "M"},
    {"codigo": "3.2", "grupo": "Filtros Secos", "descricao": "Verificar e corrigir frestas dos filtros.", "periodicidade": "M"},
    {"codigo": "3.3", "grupo": "Filtros Secos", "descricao": "Verificar e corrigir o ajuste da moldura do filtro na estrutura.", "periodicidade": "M"},
    {"codigo": "3.4", "grupo": "Filtros Secos", "descricao": "Limpar o elemento filtrante trocando se necessário.", "periodicidade": "M"},

    # 4 Gabinete
    {"codigo": "4.1", "grupo": "Gabinete", "descricao": "Verificar e corrigir a existência de sujeira.", "periodicidade": "M"},
    {"codigo": "4.2", "grupo": "Gabinete", "descricao": "Verificar e corrigir a existência de danos e corrosão.", "periodicidade": "T"},
    {"codigo": "4.3", "grupo": "Gabinete", "descricao": "Verificar e corrigir a vedação dos painéis de fechamento do gabinete.", "periodicidade": "T"},
    {"codigo": "4.5", "grupo": "Gabinete", "descricao": "Verificar e corrigir o estado de conservação do isolamento termo-acústico.", "periodicidade": "S"},

    # 5 Evaporadores
    {"codigo": "5.1", "grupo": "Evaporadores", "descricao": "Verificar e corrigir sujeiras, danos e corrosão na moldura da serpentina e na bandeja. Lavar a bandeja e serpentina com remoção de biofilme (lodo), sem uso de produtos desengraxantes e corrosivos.", "periodicidade": "T"},
    {"codigo": "5.2", "grupo": "Evaporadores", "descricao": "Verificar e corrigir a existência de agentes que prejudiquem a troca de calor.", "periodicidade": "M"},
    {"codigo": "5.3", "grupo": "Evaporadores", "descricao": "Limpar o aletado.", "periodicidade": "T"},
    {"codigo": "5.4", "grupo": "Evaporadores", "descricao": "Verificar e corrigir a operação de drenagem de água da bandeja.", "periodicidade": "T"},
    {"codigo": "5.5", "grupo": "Evaporadores", "descricao": "Verificar e corrigir a existência de vazamentos internos e externos.", "periodicidade": "T"},

    # 6 Condensadores
    {"codigo": "6.1", "grupo": "Condensadores", "descricao": "Verificar e corrigir a existência de agentes prejudiciais a troca térmica.", "periodicidade": "M"},
    {"codigo": "6.2", "grupo": "Condensadores", "descricao": "Limpar o aletado.", "periodicidade": "T"},
    {"codigo": "6.3", "grupo": "Condensadores", "descricao": "Verificar e corrigir o fluxo de ar.", "periodicidade": "T"},
    {"codigo": "6.4", "grupo": "Condensadores", "descricao": "Verificar e corrigir vazamentos internos e externos.", "periodicidade": "T"},

    # 7 Compressores
    {"codigo": "7.1", "grupo": "Compressores", "descricao": "Verificar e corrigir a existência de sujeiras, danos e corrosão.", "periodicidade": "T"},
    {"codigo": "7.2", "grupo": "Compressores", "descricao": "Verificar e corrigir a fixação e a existência de vibrações ou ruídos anormais.", "periodicidade": "T"},
    {"codigo": "7.3", "grupo": "Compressores", "descricao": "Verificar e corrigir o aterramento.", "periodicidade": "S"},
    {"codigo": "7.4", "grupo": "Compressores", "descricao": "Verificar e corrigir o funcionamento das válvulas de serviço.", "periodicidade": "T"},
    {"codigo": "7.5", "grupo": "Compressores", "descricao": "Verificar e corrigir o funcionamento dos dispositivos de segurança (pressostatos de alta, baixa, óleo).", "periodicidade": "S"},

    # 8 Circuito Refrigerante
    {"codigo": "8.1", "grupo": "Circuito Refrigerante", "descricao": "Verificar e corrigir a fixação, danos e a corrosão nas tubulações.", "periodicidade": "T"},
    {"codigo": "8.2", "grupo": "Circuito Refrigerante", "descricao": "Verificar e corrigir a existência de danos no isolamento térmico.", "periodicidade": "S"},
    {"codigo": "8.3", "grupo": "Circuito Refrigerante", "descricao": "Verificar e corrigir a existência de danos nos compensadores de vibração.", "periodicidade": "S"},
    {"codigo": "8.4", "grupo": "Circuito Refrigerante", "descricao": "Verificar e corrigir queda de pressão no filtro secador.", "periodicidade": "S"},
    {"codigo": "8.5", "grupo": "Circuito Refrigerante", "descricao": "Verificar e corrigir vazamento de gás.", "periodicidade": "T"},

    # 9 Painéis Elétricos e Eletrônicos
    {"codigo": "9.1", "grupo": "Painéis Elétricos e Eletrônicos", "descricao": "Verificar a instalação quanto as suas condições, existências de sujeiras, danos e corrosão.", "periodicidade": "T"},
    {"codigo": "9.2", "grupo": "Painéis Elétricos e Eletrônicos", "descricao": "Limpar os elementos e eliminar os pontos de corrosão.", "periodicidade": "T"},
    {"codigo": "9.3", "grupo": "Painéis Elétricos e Eletrônicos", "descricao": "Verificar e corrigir o funcionamento e fixação dos componentes eletromecânicos (fusíveis, botoeiras, lâmpadas de sinalização, contatos de contatoras, capacitores), terminais, conexões, cabos, barramentos, sistema de aterramento, reapertando.", "periodicidade": "S"},
    {"codigo": "9.4", "grupo": "Painéis Elétricos e Eletrônicos", "descricao": "Verificar e corrigir a atuação do sistema de partida e intertravamentos.", "periodicidade": "T"},
    {"codigo": "9.5", "grupo": "Painéis Elétricos e Eletrônicos", "descricao": "Verificar e corrigir, regulando os elementos de proteção (relês), operação e controle, conforme as condições de referências.", "periodicidade": "S"},
    {"codigo": "9.6", "grupo": "Painéis Elétricos e Eletrônicos", "descricao": "Verificar e corrigir o funcionamento dos alarmes visuais e sonoros, e operação no modo manual, automático e remoto.", "periodicidade": "S"},
    {"codigo": "9.7", "grupo": "Painéis Elétricos e Eletrônicos", "descricao": "Medir e registrar tensão.", "periodicidade": "M"},
    {"codigo": "9.8", "grupo": "Painéis Elétricos e Eletrônicos", "descricao": "Medir e registrar corrente.", "periodicidade": "M"}
]

# 2. CONDICIONADORES UNITÁRIOS ("Self" / "Splitão" / "Roof-Top")
CATALOGO_UNITARIO = [
    # 1 Ventiladores
    {"codigo": "1.1", "grupo": "Ventiladores", "descricao": "Verificar e corrigir limpeza (carcaça e rotor) e fixação do conjunto.", "periodicidade": "T"},
    {"codigo": "1.2", "grupo": "Ventiladores", "descricao": "Verificar e corrigir vibrações, ruídos anormais e aquecimento anormal dos mancais.", "periodicidade": "T"},
    {"codigo": "1.3", "grupo": "Ventiladores", "descricao": "Lubrificar mancais.", "periodicidade": "T"},
    {"codigo": "1.4", "grupo": "Ventiladores", "descricao": "Verificar e corrigir vazamentos nas junções flexíveis.", "periodicidade": "T"},
    {"codigo": "1.5", "grupo": "Ventiladores", "descricao": "Limpar sistema de drenagem.", "periodicidade": "A"},
    {"codigo": "1.6", "grupo": "Ventiladores", "descricao": "Verificar e corrigir o estado de amortecedores de vibração.", "periodicidade": "T"},
    {"codigo": "1.7", "grupo": "Ventiladores", "descricao": "Verificar e corrigir a operação dos controles de vazão.", "periodicidade": "T"},

    # 2 Motores Elétricos
    {"codigo": "2.1", "grupo": "Motores Elétricos", "descricao": "Verificar e corrigir a fixação e a existência de sujeiras, danos e corrosão.", "periodicidade": "T"},
    {"codigo": "2.2", "grupo": "Motores Elétricos", "descricao": "Verificar e corrigir o sentido de rotação.", "periodicidade": "T"},
    {"codigo": "2.3", "grupo": "Motores Elétricos", "descricao": "Verificar e corrigir vibrações e ruídos anormais.", "periodicidade": "T"},
    {"codigo": "2.4", "grupo": "Motores Elétricos", "descricao": "Lubrificar os mancais.", "periodicidade": "T"},
    {"codigo": "2.5", "grupo": "Motores Elétricos", "descricao": "Medir e registrar tensão entre fases.", "periodicidade": "T"},
    {"codigo": "2.6", "grupo": "Motores Elétricos", "descricao": "Medir e registrar corrente em cada fase.", "periodicidade": "T"},
    {"codigo": "2.7", "grupo": "Motores Elétricos", "descricao": "Medir e registrar a resistência de isolamento.", "periodicidade": "A"},

    # 3 Polias e Correias
    {"codigo": "3.1", "grupo": "Polias e Correias", "descricao": "Verificar e corrigir a existência de sujeiras, danos e desgastes.", "periodicidade": "T"},
    {"codigo": "3.2", "grupo": "Polias e Correias", "descricao": "Verificar a tensão e o alinhamento do conjunto.", "periodicidade": "T"},
    {"codigo": "3.3", "grupo": "Polias e Correias", "descricao": "Substituir o jogo de correias.", "periodicidade": "S"},
    {"codigo": "3.4", "grupo": "Polias e Correias", "descricao": "Verificar e corrigir a fixação das polias.", "periodicidade": "T"},

    # 4 Acoplamentos
    {"codigo": "4.1", "grupo": "Acoplamentos", "descricao": "Verificar e corrigir a fixação e a existência de sujeiras, danos e desgastes.", "periodicidade": "T"},
    {"codigo": "4.2", "grupo": "Acoplamentos", "descricao": "Verificar e corrigir alinhamento, vibrações e ruídos anormais.", "periodicidade": "T"},

    # 5 Filtros Secos
    {"codigo": "5.1", "grupo": "Filtros Secos", "descricao": "Verificar e corrigir a existência de sujeira, danos e corrosão.", "periodicidade": "M"},
    {"codigo": "5.2", "grupo": "Filtros Secos", "descricao": "Verificar e corrigir frestas dos filtros.", "periodicidade": "M"},
    {"codigo": "5.3", "grupo": "Filtros Secos", "descricao": "Medir e registrar o diferencial de pressão (não laváveis).", "periodicidade": "S"},
    {"codigo": "5.4", "grupo": "Filtros Secos", "descricao": "Verificar e corrigir o ajuste da moldura do filtro na estrutura.", "periodicidade": "T"},
    {"codigo": "5.5", "grupo": "Filtros Secos", "descricao": "Limpar o elemento filtrante trocando se necessário.", "periodicidade": "M"},

    # 6 Filtros Embebidos em Óleo
    {"codigo": "6.1", "grupo": "Filtros Embebidos em Óleo", "descricao": "Verificar e corrigir a existência de sujeira, danos e corrosão. Lavar o filtro com produto desengraxante e inodoro.", "periodicidade": "M"},
    {"codigo": "6.2", "grupo": "Filtros Embebidos em Óleo", "descricao": "Verificar e corrigir frestas dos filtros.", "periodicidade": "T"},
    {"codigo": "6.3", "grupo": "Filtros Embebidos em Óleo", "descricao": "Verificar e corrigir o ajuste da moldura do filtro na estrutura.", "periodicidade": "M"},
    {"codigo": "6.4", "grupo": "Filtros Embebidos em Óleo", "descricao": "Limpar o filtro.", "periodicidade": "M"},
    {"codigo": "6.5", "grupo": "Filtros Embebidos em Óleo", "descricao": "Aplicar óleo (inodoro) no elemento filtrante e escorrer, mantendo uma fina película de óleo.", "periodicidade": "T"},
    {"codigo": "6.6", "grupo": "Filtros Embebidos em Óleo", "descricao": "Substituir o elemento filtrante.", "periodicidade": "A"},

    # 7 Gabinete
    {"codigo": "7.1", "grupo": "Gabinete", "descricao": "Verificar e corrigir a existência de sujeira, danos e corrosão.", "periodicidade": "M"},
    {"codigo": "7.2", "grupo": "Gabinete", "descricao": "Verificar e corrigir a vedação dos painéis de fechamento do gabinete.", "periodicidade": "M"},
    {"codigo": "7.3", "grupo": "Gabinete", "descricao": "Verificar e corrigir o estado de conservação do isolamento termo-acústico.", "periodicidade": "T"},

    # 8 Evaporadores
    {"codigo": "8.1", "grupo": "Evaporadores", "descricao": "Verificar e corrigir a existência de sujeira, danos e corrosão na moldura da serpentina e na bandeja. Lavar a bandeja e serpentina com remoção de biofilme (lodo), sem uso de produtos desengraxantes e corrosivos.", "periodicidade": "T"},
    {"codigo": "8.2", "grupo": "Evaporadores", "descricao": "Verificar e corrigir a existência de agentes que prejudiquem a troca de calor.", "periodicidade": "T"},
    {"codigo": "8.3", "grupo": "Evaporadores", "descricao": "Limpar as superfícies do lado ar ou líquido refrigerante.", "periodicidade": "T"},
    {"codigo": "8.4", "grupo": "Evaporadores", "descricao": "Verificar e corrigir a vazão de ar, conforme projeto.", "periodicidade": "A"},
    {"codigo": "8.5", "grupo": "Evaporadores", "descricao": "Medir e registrar as temperaturas e pressões, na condição de plena vazão de ambos os fluidos nos pontos de entrada e saída.", "periodicidade": "A"},
    {"codigo": "8.6", "grupo": "Evaporadores", "descricao": "Verificar e corrigir o isolamento térmico do componente (inspeção visual).", "periodicidade": "T"},
    {"codigo": "8.7", "grupo": "Evaporadores", "descricao": "Medir e registrar o superaquecimento.", "periodicidade": "S"},
    {"codigo": "8.8", "grupo": "Evaporadores", "descricao": "Verificar e corrigir a operação de drenagem de água da bandeja.", "periodicidade": "M"},
    {"codigo": "8.9", "grupo": "Evaporadores", "descricao": "Verificar e corrigir a existência de vazamentos internos e externos.", "periodicidade": "T"},

    # 9 Condensadores
    {"codigo": "9.1", "grupo": "Condensadores", "descricao": "Verificar e corrigir a existência de agentes prejudiciais a troca térmica.", "periodicidade": "M"},
    {"codigo": "9.2", "grupo": "Condensadores", "descricao": "Limpar as superfícies de troca de calor (condens. água).", "periodicidade": "S"},
    {"codigo": "9.3", "grupo": "Condensadores", "descricao": "Limpar as superfícies de troca de calor (condens. ar).", "periodicidade": "T"},
    {"codigo": "9.4", "grupo": "Condensadores", "descricao": "Verificar e corrigir os fluxos dos fluidos.", "periodicidade": "T"},
    {"codigo": "9.5", "grupo": "Condensadores", "descricao": "Verificar e corrigir vazamentos internos e externos.", "periodicidade": "T"},
    {"codigo": "9.6", "grupo": "Condensadores", "descricao": "Limpar o sistema de drenagem.", "periodicidade": "T"},
    {"codigo": "9.7", "grupo": "Condensadores", "descricao": "Medir e registrar as temperaturas e as pressões na condição de plena vazão de ambos os fluidos nos pontos de entrada e saída.", "periodicidade": "A"},
    {"codigo": "9.8", "grupo": "Condensadores", "descricao": "Medir e registrar o sub-resfriamento do sistema.", "periodicidade": "S"},

    # 10 Compressores
    {"codigo": "10.1", "grupo": "Compressores", "descricao": "Verificar e corrigir a existência de sujeiras, danos e corrosão.", "periodicidade": "T"},
    {"codigo": "10.2", "grupo": "Compressores", "descricao": "Verificar e corrigir a fixação e a existência de vibrações ou ruídos anormais.", "periodicidade": "T"},
    {"codigo": "10.3", "grupo": "Compressores", "descricao": "Medir e registrar tensão entre fases.", "periodicidade": "T"},
    {"codigo": "10.4", "grupo": "Compressores", "descricao": "Medir e registrar corrente em cada fase.", "periodicidade": "T"},
    {"codigo": "10.5", "grupo": "Compressores", "descricao": "Medir e registrar a resistência de isolamento.", "periodicidade": "A"},
    {"codigo": "10.6", "grupo": "Compressores", "descricao": "Verificar e corrigir o aterramento.", "periodicidade": "S"},
    {"codigo": "10.7", "grupo": "Compressores", "descricao": "Medir e registrar a pressão de sucção junto ao compressor.", "periodicidade": "T"},
    {"codigo": "10.8", "grupo": "Compressores", "descricao": "Medir e registrar a temperatura de sucção junto ao compressor.", "periodicidade": "T"},
    {"codigo": "10.9", "grupo": "Compressores", "descricao": "Medir e registrar a pressão de descarga junto ao compressor.", "periodicidade": "T"},
    {"codigo": "10.10", "grupo": "Compressores", "descricao": "Medir e registrar a temperatura de descarga junto ao compressor.", "periodicidade": "T"},
    {"codigo": "10.11", "grupo": "Compressores", "descricao": "Verificar e corrigir o nível de óleo no visor.", "periodicidade": "T"},
    {"codigo": "10.12", "grupo": "Compressores", "descricao": "Verificar e corrigir o funcionamento dos dispositivos de segurança (pressostatos de alta, baixa, óleo).", "periodicidade": "S"},
    {"codigo": "10.13", "grupo": "Compressores", "descricao": "Medir e registrar a pressão diferencial do óleo.", "periodicidade": "A"},
    {"codigo": "10.14", "grupo": "Compressores", "descricao": "Verificar e corrigir o funcionamento da resistência de cárter.", "periodicidade": "S"},
    {"codigo": "10.15", "grupo": "Compressores", "descricao": "Verificar e corrigir o funcionamento das válvulas de serviço.", "periodicidade": "T"},
    {"codigo": "10.16", "grupo": "Compressores", "descricao": "Verificar e corrigir a existência de vazamentos.", "periodicidade": "T"},

    # 11 Circuito Refrigerante
    {"codigo": "11.1", "grupo": "Circuito Refrigerante", "descricao": "Verificar e corrigir a fixação e a existência de danos e corrosão de tubulações.", "periodicidade": "T"},
    {"codigo": "11.2", "grupo": "Circuito Refrigerante", "descricao": "Verificar e corrigir a existência de danos no isolamento térmico.", "periodicidade": "T"},
    {"codigo": "11.3", "grupo": "Circuito Refrigerante", "descricao": "Verificar e corrigir a existência de danos nos compensadores de vibração.", "periodicidade": "S"},
    {"codigo": "11.4", "grupo": "Circuito Refrigerante", "descricao": "Verificar e corrigir a existência de bolhas e umidade no visor de líquido.", "periodicidade": "T"},
    {"codigo": "11.5", "grupo": "Circuito Refrigerante", "descricao": "Verificar e corrigir queda de pressão no filtro secador.", "periodicidade": "T"},
    {"codigo": "11.6", "grupo": "Circuito Refrigerante", "descricao": "Verificar e corrigir vazamento de gás.", "periodicidade": "T"},
    {"codigo": "11.7", "grupo": "Circuito Refrigerante", "descricao": "Verificar e corrigir atuação da válvula solenóide.", "periodicidade": "S"},
    {"codigo": "11.8", "grupo": "Circuito Refrigerante", "descricao": "Verificar e corrigir fixação e isolamento do bulbo da válvula de expansão termostática.", "periodicidade": "S"},

    # 12 Painéis Elétricos e Eletrônicos
    {"codigo": "12.1", "grupo": "Painéis Elétricos e Eletrônicos", "descricao": "Verificar a instalação quanto as suas condições, existências de sujeiras, danos e corrosão.", "periodicidade": "T"},
    {"codigo": "12.2", "grupo": "Painéis Elétricos e Eletrônicos", "descricao": "Limpar os elementos e eliminar os pontos de corrosão.", "periodicidade": "T"},
    {"codigo": "12.3", "grupo": "Painéis Elétricos e Eletrônicos", "descricao": "Verificar e corrigir o funcionamento e fixação dos componentes eletromecânicos (fusíveis, botoeiras, lâmpadas de sinalização, contatos de contatoras, capacitores), terminais, conexões, cabos, barramentos, sistema de aterramento, reapertando.", "periodicidade": "S"},
    {"codigo": "12.4", "grupo": "Painéis Elétricos e Eletrônicos", "descricao": "Verificar e corrigir a atuação do sistema de partida e intertravamentos.", "periodicidade": "T"},
    {"codigo": "12.5", "grupo": "Painéis Elétricos e Eletrônicos", "descricao": "Verificar e corrigir, regulando os elementos de proteção (relés), operação e controle, conforme as condições de referências.", "periodicidade": "S"},
    {"codigo": "12.6", "grupo": "Painéis Elétricos e Eletrônicos", "descricao": "Verificar e corrigir o funcionamento dos alarmes visuais e sonoros, e operação no modo manual, automático e remoto.", "periodicidade": "S"}
]


def determinar_categoria(tipo_equipamento: str) -> str:
    """Mapeia o tipo de equipamento para a tabela correspondente do PMOC."""
    tipo = (tipo_equipamento or '').strip().upper()
    if tipo in ('SELF', 'SPLITÃO', 'SPLITAO', 'ROOF-TOP', 'ROOFTOP'):
        return 'UNITARIO'
    return 'DOMESTICO'


def obter_checklist_padrao(tipo_equipamento: str, periodicidade: str = 'M') -> list:
    """
    Retorna a lista de itens aplicáveis para o tipo de equipamento e ciclo (M, T, S, A).
    """
    cat = determinar_categoria(tipo_equipamento)
    catalogo = CATALOGO_UNITARIO if cat == 'UNITARIO' else CATALOGO_DOMESTICO
    per_val = (periodicidade or 'M').strip().upper()
    aplicaveis = PERIODICIDADES_APLICAVEIS.get(per_val, {'M'})

    resultado = []
    for item in catalogo:
        # Se a periodicidade do item está inclusa no ciclo acumulativo
        if item['periodicidade'] in aplicaveis:
            resultado.append({
                "codigo": item["codigo"],
                "grupo": item["grupo"],
                "descricao": item["descricao"],
                "periodicidade_minima": item["periodicidade"],
                "status_padrao": "conforme"
            })
    return resultado
