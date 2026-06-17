"""
Corrige double-encoding (UTF-8 interpretado como cp1252 e re-salvo em UTF-8).
Funciona para acentos, pontuacao tipografica, setas e emojis.

Algoritmo:
  1. Le o arquivo como UTF-8 (obtem string com mojibake)
  2. Para cada char, converte de volta ao byte original:
     - char <= U+00FF  → byte = codepoint  (latin-1 direto)
     - char em cp1252  → byte = cp1252[char]
  3. Decodifica os bytes resultantes como UTF-8
  4. Salva o resultado como UTF-8 sem BOM

Execucao: python scripts/fix_encoding.py
"""
import os
import sys

# Mapa cp1252: chars acima de U+00FF -> byte
_CP1252_HIGH = {
    '€': 0x80,  # €
    '‚': 0x82,  # ‚
    'ƒ': 0x83,  # ƒ
    '„': 0x84,  # „
    '…': 0x85,  # …
    '†': 0x86,  # †
    '‡': 0x87,  # ‡
    'ˆ': 0x88,  # ˆ
    '‰': 0x89,  # ‰
    'Š': 0x8A,  # Š
    '‹': 0x8B,  # ‹
    'Œ': 0x8C,  # Œ
    'Ž': 0x8E,  # Ž
    '‘': 0x91,  # '
    '’': 0x92,  # '
    '“': 0x93,  # "
    '”': 0x94,  # "
    '•': 0x95,  # •
    '–': 0x96,  # –
    '—': 0x97,  # —
    '˜': 0x98,  # ˜
    '™': 0x99,  # ™
    'š': 0x9A,  # š
    '›': 0x9B,  # ›
    'œ': 0x9C,  # œ
    'ž': 0x9E,  # ž
    'Ÿ': 0x9F,  # Ÿ
}


def _encode_mojibake(text: str) -> bytes:
    """Converte string com mojibake de volta aos bytes UTF-8 originais."""
    buf = []
    for ch in text:
        cp = ord(ch)
        if cp <= 0xFF:
            buf.append(cp)
        elif ch in _CP1252_HIGH:
            buf.append(_CP1252_HIGH[ch])
        else:
            # Char genuinamente acima de cp1252 — nao e mojibake, preserva como UTF-8
            buf.extend(ch.encode('utf-8'))
    return bytes(buf)


FILES = [
    'static/ferramentas/notas/notas_037.html',
    'static/ferramentas/faturamento/dashboard.html',
    'static/ferramentas/usinagem/geral.html',
    'static/ferramentas/usinagem/aegea.html',
    'static/ferramentas/usinagem/guariroba.html',
    'static/ferramentas/abastecimento/Dashboard_Abastecimento.html',
    'static/ferramentas/faz_tudo/medicao_pavimentacao_v6.0.html',
    'static/ferramentas/le_doc/preenchimento.html',
]

# Padroes que so aparecem em double-encoding (mojibake cp1252->UTF-8)
_MOJIBAKE_PATTERNS = ['Ã§', 'Ã£', 'Ã¡', 'Ã©', 'â€"', 'â€™', 'Ã³', 'Ãº', 'Ã¢', 'â€œ']


def _is_mojibake(text: str) -> bool:
    return sum(text.count(p) for p in _MOJIBAKE_PATTERNS) >= 3


def fix_file(path: str) -> None:
    if not os.path.exists(path):
        print(f'NOT FOUND: {path}')
        return

    with open(path, 'rb') as f:
        raw = f.read()

    # Remove BOM
    if raw[:3] == b'\xef\xbb\xbf':
        raw = raw[3:]

    # Decodifica como UTF-8 (obtem string mojibake ou correta)
    mojibake = raw.decode('utf-8', errors='replace')

    if not _is_mojibake(mojibake):
        print(f'SKIP {path} (ja esta em UTF-8 correto)')
        return

    # Converte de volta ao UTF-8 correto
    try:
        original_bytes = _encode_mojibake(mojibake)
        correct = original_bytes.decode('utf-8', errors='replace')
    except Exception as e:
        print(f'ERRO em {path}: {e}')
        return

    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(correct)

    # Amostra do resultado
    import re
    title = re.search(r'<title>(.*?)</title>', correct)
    label = title.group(1) if title else correct[100:140].replace('\n', ' ')
    print(f'OK  {path}')
    print(f'    titulo: {label.encode("unicode_escape").decode()}')


if __name__ == '__main__':
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(base)
    for f in FILES:
        fix_file(f)
    print('\nDone.')
