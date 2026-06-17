"""
Fix mojibake (double-UTF-8) nos arquivos HTML estaticos.
Execucao: python scripts/fix_encoding.py
"""
import os
import sys

# Pares: texto mojibake -> texto correto
# Gerados por: byte_utf8.decode('utf-8') quando o texto original
# foi lido como cp1252 antes de ser salvo.
PAIRS = [
    # Minusculas com acento
    ("Ã§", "ç"),  # Ã§ -> c cedilha
    ("Ã£", "ã"),  # Ã£ -> a tilde
    ("Ã¡", "á"),  # Ã¡ -> a agudo
    ("Ã©", "é"),  # Ã© -> e agudo
    ("Ã­", "í"),  # Ã­ -> i agudo
    ("Ã³", "ó"),  # Ã³ -> o agudo
    ("Ãº", "ú"),  # Ãº -> u agudo
    ("Ã¢", "â"),  # Ã¢ -> a circunflexo
    ("Ãª", "ê"),  # Ãª -> e circunflexo
    ("Ã´", "ô"),  # Ã´ -> o circunflexo
    ("Ã ", "à"),  # Ã  -> a grave
    ("Ãµ", "õ"),  # Ãµ -> o tilde
    ("Ã¼", "ü"),  # Ã¼ -> u trema
    ("Ã¶", "ö"),  # Ã¶ -> o trema
    ("Ã¤", "ä"),  # Ã¤ -> a trema
    ("Ã±", "ñ"),  # Ã± -> n tilde
    ("Ã¹", "ù"),  # Ã¹ -> u grave
    ("Ã«", "ë"),  # Ã« -> e trema
    ("Ã¯", "ï"),  # Ã¯ -> i trema
    ("Ã²", "ò"),  # Ã² -> o grave
    # Maiusculas com acento
    ("Ã‡", "Ç"),  # Ã‡ -> C cedilha
    ("Ã‚", "Â"),  # Ã‚ -> A circunflexo
    ("Ã", "Á"),  # Ã -> A agudo (fallback)
    ("Ã‰", "É"),  # Ã‰ -> E agudo
    ("Ã“", "Ó"),  # Ã" -> O agudo
    ("Ã", "À"),  # Ã€ -> A grave
    ("Ã•", "Õ"),  # Ã• -> O tilde
    ("Ã", "Ã"),  # Ã  -> A tilde (maiusc)
    # Pontuacao tipografica
    ("â€”", "—"),  # â€" -> em dash
    ("â€’", "‘"),  # â€˜ -> left single quote
    ("â€˜", "‘"),  # variante
    ("â€œ", "“"),  # â€œ -> left double quote
    ("â€˙", "–"),  # â€™/â€" -> en dash (variante)
    ("â€", "€"),        # â€ sozinho -> euro
    ("Â°", "°"),        # Â° -> grau
    ("Â·", "·"),        # Â· -> ponto medio
    ("Â»", "»"),        # Â» -> >>
    ("Â«", "«"),        # Â« -> <<
    ("Â½", "½"),        # Â½ -> 1/2
    ("Âº", "º"),        # Âº -> ordinal masc
    ("Âª", "ª"),        # Âª -> ordinal fem
    ("Â²", "²"),        # Â² -> superscript 2
    ("Â³", "³"),        # Â³ -> superscript 3
    ("Â ", " "),        # Â\xa0 -> nbsp
    ("Â±", "±"),        # Â± -> plusminus
    ("Âµ", "µ"),        # Âµ -> micro
    ("Â©", "©"),        # Â© -> copyright
    ("Â®", "®"),        # Â® -> registered
    ("Â§", "§"),        # Â§ -> secao
    ("â„¢", "™"),  # â„¢ -> trademark
]

FILES = [
    "static/ferramentas/notas/notas_037.html",
    "static/ferramentas/faturamento/dashboard.html",
    "static/ferramentas/usinagem/geral.html",
    "static/ferramentas/usinagem/aegea.html",
    "static/ferramentas/usinagem/guariroba.html",
    "static/ferramentas/abastecimento/Dashboard_Abastecimento.html",
]


def fix_file(path):
    if not os.path.exists(path):
        print(f"NOT FOUND: {path}")
        return

    with open(path, "rb") as f:
        raw = f.read()

    # Remove BOM se existir
    if raw[:3] == b"\xef\xbb\xbf":
        raw = raw[3:]

    text = raw.decode("utf-8", errors="replace")
    count = 0
    # Ordena por comprimento decrescente para evitar substituicoes parciais
    for bad, good in sorted(PAIRS, key=lambda p: -len(p[0])):
        n = text.count(bad)
        if n:
            text = text.replace(bad, good)
            count += n

    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)

    # Mostra preview
    idx = max(text.find("edio"), text.find("atur"), text.find("sina"))
    preview = text[max(0, idx - 5) : idx + 20].replace("\n", " ")
    print(f"FIXED {path}: {count} substituicoes | ...{preview}...")


if __name__ == "__main__":
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(base)
    for f in FILES:
        fix_file(f)
    print("Done.")
