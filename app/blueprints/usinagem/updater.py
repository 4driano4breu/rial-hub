"""
ATUALIZADOR DE DASHBOARDS — USINAGEM CBUQ
==========================================
Como usar:
  1. Abra a planilha no Google Sheets
  2. File → Download → CSV (.csv)
  3. Salve o arquivo CSV nesta mesma pasta (Usinagem)
  4. Execute: python atualizar_dashboards.py nome_do_arquivo.csv

O script atualiza automaticamente os 3 dashboards:
  - Dashboard AEGEA.html          (apenas contrato AEGEA com 30t CAP)
  - dashboard_aguas_guariroba.html (TDC + CB Térmico + RIAL)
  - Dashboard Geral.html          (todos os registros)

Configurações ajustáveis abaixo:
"""

import csv
import sys
import os
import re
from datetime import datetime

# ─── CONFIGURAÇÕES ────────────────────────────────────────────────────────────
CAP_AEGEA = 30          # toneladas de CAP fornecidas pela AEGEA
CAP_COMP  = 0.051       # composição: 5,1% de CAP no CBUQ
CAP_GUARIROBA = 63.93   # NF 71123 (31,36t) + NF 71136 (32,57t) = 63,93t — 25 e 28/04/2026

# Índices das colunas no CSV (detectados automaticamente pelo cabeçalho)
# Formato "Base_Notas - Notas.csv": ID, Data Salvamento, Modo, Data Operação,
#   Ticket Inicial, Ticket Final, Regiões, Total Caminhões,
#   Ticket(8), Data(9), Placa(10), Motorista(11), Operador(12),
#   Entrada(13), Saída(14), Tara(15), Peso(16), Região(17)
COL_DATA    = 9
COL_NOTA    = 8
COL_PLACA   = 10
COL_MOT     = 11
COL_SAIDA   = 13
COL_CHEGADA = 14
COL_BRUTO   = 15
COL_LIQ     = 16
COL_REGIAO  = 17

# Arquivos de saída (relativos ao hub)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
import os as _os
_HUB_ROOT = _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
ARQ_AEGEA     = _os.path.join(_HUB_ROOT, "static", "ferramentas", "usinagem", "aegea.html")
ARQ_GUARIROBA = _os.path.join(_HUB_ROOT, "static", "ferramentas", "usinagem", "guariroba.html")
ARQ_GERAL     = _os.path.join(_HUB_ROOT, "static", "ferramentas", "usinagem", "geral.html")
# ──────────────────────────────────────────────────────────────────────────────


def limpar_peso(val):
    """Converte string de peso para float, trata vírgula e erros."""
    if not val:
        return None
    val = val.strip().replace(',', '.')
    try:
        return float(val)
    except ValueError:
        return None


def parse_data(val):
    """Converte DD/MM/YYYY para objeto date (para ordenação)."""
    try:
        return datetime.strptime(val.strip(), "%d/%m/%Y")
    except:
        return datetime.min


def classificar(regiao):
    """Retorna 'AEGEA', 'GUARIROBA' ou 'GERAL'."""
    r = (regiao or '').upper()
    if 'GUARIROBA' in r or 'AGUAS GUARIROBA' in r:
        return 'GUARIROBA'
    if 'AEGEA' in r:
        return 'AEGEA'
    return 'GERAL'


def sub_guariroba(regiao):
    """TDC, CB ou RIAL."""
    r = (regiao or '').upper()
    if 'RIAL' in r:
        return 'RIAL'
    if 'CB' in r or 'TÉRMICO' in r or 'TERMICO' in r:
        return 'CB'
    return 'TDC'


def detectar_delimitador(caminho):
    """Detecta se o CSV usa vírgula ou ponto-e-vírgula."""
    with open(caminho, encoding='utf-8-sig', errors='replace') as f:
        primeira = f.readline()
    return ';' if primeira.count(';') > primeira.count(',') else ','


def detectar_colunas(cabecalho):
    """
    Tenta mapear colunas pelo nome do cabeçalho.
    Retorna dicionário {nome_interno: índice} ou None se não conseguir.
    """
    mapa_nomes = {
        'DATA':    ['data', 'dt', 'date'],
        'NOTA':    ['nota', 'nf', 'numero', 'número', 'ticket', 'num'],
        'PLACA':   ['placa', 'veiculo', 'veículo', 'placa do veiculo'],
        'MOT':     ['motorista', 'mot', 'condutor', 'driver'],
        'SAIDA':   ['saida', 'saída', 'hora saida', 'hora saída', 'h saida'],
        'CHEGADA': ['chegada', 'hora chegada', 'h chegada', 'retorno'],
        'BRUTO':   ['peso bruto', 'bruto', 'pb', 'gross'],
        'LIQ':     ['peso liq', 'peso líq', 'liquido', 'líquido', 'liq', 'líq', 'net', 'peso net'],
        'REGIAO':  ['regiao', 'região', 'destino', 'local', 'obra', 'contrato'],
    }
    cols = {}
    for i, h in enumerate(cabecalho):
        h_lower = h.strip().lower()
        for campo, opcoes in mapa_nomes.items():
            if campo not in cols and any(o in h_lower for o in opcoes):
                cols[campo] = i
    return cols if len(cols) >= 7 else None


def ler_csv(caminho):
    """Lê o CSV, detecta delimitador e colunas automaticamente."""
    global COL_DATA, COL_NOTA, COL_PLACA, COL_MOT, COL_SAIDA, COL_CHEGADA, COL_BRUTO, COL_LIQ, COL_REGIAO

    delim = detectar_delimitador(caminho)
    linhas = []
    cabecalho = None

    for enc in ['utf-8-sig', 'latin-1', 'cp1252']:
        try:
            with open(caminho, newline='', encoding=enc) as f:
                reader = csv.reader(f, delimiter=delim)
                rows = list(reader)
            break
        except UnicodeDecodeError:
            continue

    if not rows:
        return []

    cabecalho = rows[0]
    print(f"   Delimitador: '{delim}' | Encoding detectado | Colunas: {len(cabecalho)}")
    print(f"   Cabeçalho: {cabecalho[:9]}")

    # Tenta detectar colunas pelo nome
    cols_detectadas = detectar_colunas(cabecalho)
    if cols_detectadas and len(cols_detectadas) >= 7:
        COL_DATA    = cols_detectadas.get('DATA',    COL_DATA)
        COL_NOTA    = cols_detectadas.get('NOTA',    COL_NOTA)
        COL_PLACA   = cols_detectadas.get('PLACA',   COL_PLACA)
        COL_MOT     = cols_detectadas.get('MOT',     COL_MOT)
        COL_SAIDA   = cols_detectadas.get('SAIDA',   COL_SAIDA)
        COL_CHEGADA = cols_detectadas.get('CHEGADA', COL_CHEGADA)
        COL_BRUTO   = cols_detectadas.get('BRUTO',   COL_BRUTO)
        COL_LIQ     = cols_detectadas.get('LIQ',     COL_LIQ)
        COL_REGIAO  = cols_detectadas.get('REGIAO',  COL_REGIAO)
        print(f"   Colunas mapeadas automaticamente ✓")
    else:
        print(f"   Usando índices padrão (DATA=0, NOTA=1, ..., REGIAO=8)")

    max_col = max(COL_DATA, COL_NOTA, COL_PLACA, COL_MOT, COL_SAIDA, COL_CHEGADA, COL_BRUTO, COL_LIQ, COL_REGIAO)

    for row in rows[1:]:
        if len(row) <= max_col:
            continue  # linha com colunas insuficientes
        nota = (row[COL_NOTA] or '').strip().replace('.', '').replace(',', '')
        if not nota.isdigit():
            continue  # pula linhas sem nota válida (ex: cabeçalho repetido, totais)
        linhas.append(row)

    return linhas


def deduplicar(linhas):
    """Mantém apenas 1 linha por nota (a com mais campos preenchidos)."""
    mapa = {}
    for row in linhas:
        nota = row[COL_NOTA].strip()
        preenchidos = sum(1 for c in row if c.strip())
        if nota not in mapa or preenchidos > mapa[nota][1]:
            mapa[nota] = (row, preenchidos)
    return [v[0] for v in mapa.values()]


def ordenar_desc(linhas):
    """Ordena do mais recente para o mais antigo (depois por nota desc)."""
    return sorted(linhas,
                  key=lambda r: (parse_data(r[COL_DATA]), int(r[COL_NOTA]) if r[COL_NOTA].isdigit() else 0),
                  reverse=True)


def row_to_js(row):
    """Converte linha para string JS array."""
    campos = [
        row[COL_DATA].strip(),
        row[COL_NOTA].strip(),
        row[COL_PLACA].strip(),
        row[COL_MOT].strip(),
        row[COL_SAIDA].strip() if len(row) > COL_SAIDA else '',
        row[COL_CHEGADA].strip() if len(row) > COL_CHEGADA else '',
        row[COL_BRUTO].strip().replace(',', '.') if len(row) > COL_BRUTO else '',
        row[COL_LIQ].strip().replace(',', '.') if len(row) > COL_LIQ else '',
        row[COL_REGIAO].strip() if len(row) > COL_REGIAO else '',
    ]
    # Escape aspas simples
    campos_esc = [c.replace('"', '\\"') for c in campos]
    return '["' + '","'.join(campos_esc) + '"]'


def rows_to_js_array(linhas):
    return ',\n'.join(row_to_js(r) for r in linhas)


def substituir_array(html, marcador_inicio, marcador_fim, novo_conteudo):
    """Substitui o conteúdo entre marcador_inicio e marcador_fim no HTML."""
    idx_ini = html.find(marcador_inicio)
    if idx_ini == -1:
        raise ValueError(f"Marcador não encontrado: {marcador_inicio!r}")
    idx_ini += len(marcador_inicio)
    idx_fim = html.find(marcador_fim, idx_ini)
    if idx_fim == -1:
        raise ValueError(f"Marcador de fim não encontrado: {marcador_fim!r}")
    return html[:idx_ini] + '\n' + novo_conteudo + '\n' + html[idx_fim:]


def atualizar_aegea(linhas_aegea):
    if not os.path.exists(ARQ_AEGEA):
        print(f"  ⚠️  Arquivo não encontrado: {ARQ_AEGEA}")
        return
    with open(ARQ_AEGEA, 'r', encoding='utf-8') as f:
        html = f.read()

    novo_js = rows_to_js_array(linhas_aegea)
    html = substituir_array(html, 'const AEGEA_ROWS = [', '];', novo_js)

    # Atualiza CAP_TOTAL se necessário
    meta = CAP_AEGEA / CAP_COMP
    html = re.sub(
        r'const CAP_TOTAL=\d+(?:\.\d+)?',
        f'const CAP_TOTAL={CAP_AEGEA}',
        html
    )

    with open(ARQ_AEGEA, 'w', encoding='utf-8') as f:
        f.write(html)
    total = sum(float(r[COL_LIQ]) for r in linhas_aegea if limpar_peso(r[COL_LIQ]))
    pct = (total / meta * 100)
    print(f"  ✅ Dashboard AEGEA → {len(linhas_aegea)} registros | {total:.2f}t | {pct:.1f}% da meta ({meta:.0f}t)")


def atualizar_guariroba(linhas_guariroba):
    if not os.path.exists(ARQ_GUARIROBA):
        print(f"  ⚠️  Arquivo não encontrado: {ARQ_GUARIROBA}")
        return
    with open(ARQ_GUARIROBA, 'r', encoding='utf-8') as f:
        html = f.read()

    novo_js = rows_to_js_array(linhas_guariroba)
    html = substituir_array(html, 'const ROWS = [', '];', novo_js)

    # Atualiza CAP_GUARIROBA
    if CAP_GUARIROBA is not None:
        html = re.sub(
            r'const CAP_FORNECIDO = null;',
            f'const CAP_FORNECIDO = {CAP_GUARIROBA};',
            html
        )
        print(f"  ℹ️  CAP Guariroba configurado: {CAP_GUARIROBA}t")

    with open(ARQ_GUARIROBA, 'w', encoding='utf-8') as f:
        f.write(html)

    total = sum(float(r[COL_LIQ]) for r in linhas_guariroba if limpar_peso(r[COL_LIQ]))
    cap_est = total * CAP_COMP
    tdc = sum(float(r[COL_LIQ]) for r in linhas_guariroba if sub_guariroba(r[COL_REGIAO])=='TDC' and limpar_peso(r[COL_LIQ]))
    cb  = sum(float(r[COL_LIQ]) for r in linhas_guariroba if sub_guariroba(r[COL_REGIAO])=='CB'  and limpar_peso(r[COL_LIQ]))
    rial= sum(float(r[COL_LIQ]) for r in linhas_guariroba if sub_guariroba(r[COL_REGIAO])=='RIAL'and limpar_peso(r[COL_LIQ]))
    print(f"  ✅ Dashboard Águas Guariroba → {len(linhas_guariroba)} registros | {total:.2f}t total")
    print(f"       TDC: {tdc:.2f}t  |  CB Térmico: {cb:.2f}t  |  RIAL: {rial:.2f}t")
    print(f"       CAP estimado consumido: {cap_est:.2f}t (5,1%)")
    if CAP_GUARIROBA is None:
        print(f"       ⚠️  Aguardando CAP — atualize CAP_GUARIROBA no topo do script quando receber")


def atualizar_geral(todas_linhas):
    if not os.path.exists(ARQ_GERAL):
        print(f"  ⚠️  Arquivo não encontrado: {ARQ_GERAL}")
        return
    with open(ARQ_GERAL, 'r', encoding='utf-8') as f:
        html = f.read()

    novo_js = rows_to_js_array(todas_linhas)
    html = substituir_array(html, 'const ROWS = [', '];', novo_js)

    with open(ARQ_GERAL, 'w', encoding='utf-8') as f:
        f.write(html)

    total = sum(float(r[COL_LIQ]) for r in todas_linhas if limpar_peso(r[COL_LIQ]))
    print(f"  ✅ Dashboard Geral → {len(todas_linhas)} registros | {total:.2f}t total")


# ─── MAIN ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    if len(sys.argv) < 2:
        # Tenta encontrar o CSV automaticamente na pasta
        csvs = [f for f in os.listdir(SCRIPT_DIR) if f.lower().endswith('.csv')]
        if len(csvs) == 1:
            caminho_csv = os.path.join(SCRIPT_DIR, csvs[0])
            print(f"CSV encontrado automaticamente: {csvs[0]}")
        elif len(csvs) > 1:
            print("Mais de um CSV encontrado. Especifique qual usar:")
            print(f"  python atualizar_dashboards.py <arquivo.csv>")
            print(f"  Arquivos: {', '.join(csvs)}")
            sys.exit(1)
        else:
            print("Uso: python atualizar_dashboards.py <arquivo.csv>")
            print()
            print("Onde obter o CSV:")
            print("  1. Abra a planilha no Google Sheets")
            print("  2. File → Download → Comma Separated Values (.csv)")
            print("  3. Salve nesta pasta e rode o script novamente")
            sys.exit(1)
    else:
        caminho_csv = sys.argv[1]
        if not os.path.isabs(caminho_csv):
            caminho_csv = os.path.join(SCRIPT_DIR, caminho_csv)

    if not os.path.exists(caminho_csv):
        print(f"❌ Arquivo não encontrado: {caminho_csv}")
        sys.exit(1)

    print(f"\n{'='*55}")
    print("  ATUALIZADOR DE DASHBOARDS — USINAGEM CBUQ")
    print(f"{'='*55}")
    print(f"  CSV: {os.path.basename(caminho_csv)}")
    print()

    # 1. Ler e deduplicar
    print("📂 Lendo dados...")
    linhas_raw = ler_csv(caminho_csv)
    linhas = deduplicar(linhas_raw)
    print(f"   {len(linhas_raw)} linhas brutas → {len(linhas)} após deduplicação")

    # 2. Separar por tipo (mais recente primeiro)
    aegea     = ordenar_desc([r for r in linhas if classificar(r[COL_REGIAO]) == 'AEGEA'])
    guariroba = ordenar_desc([r for r in linhas if classificar(r[COL_REGIAO]) == 'GUARIROBA'])
    todas     = ordenar_desc(linhas)

    print(f"   AEGEA: {len(aegea)} | Águas Guariroba: {len(guariroba)} | Geral: {len(todas)}")
    print()

    # 3. Atualizar dashboards
    print("🔄 Atualizando dashboards...\n")
    atualizar_aegea(aegea)
    print()
    atualizar_guariroba(guariroba)
    print()
    atualizar_geral(todas)

    print()
    print(f"{'='*55}")
    print("  ✅ Todos os dashboards atualizados com sucesso!")
    print(f"{'='*55}\n")
