"""
Migração única: importa recebimentos.json para o banco de dados.
Uso: python scripts/importar_recebimentos.py <caminho_do_json> [org_id]
"""
import json
import sys
from datetime import date

sys.path.insert(0, '.')
from app import create_app
from app.extensions import db
from app.models import FaturamentoNota

def main():
    json_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Users\Adriano Abreu\Desktop\recebimentos.json'
    org_id    = int(sys.argv[2]) if len(sys.argv) > 2 else None

    with open(json_path, encoding='utf-8') as f:
        dados = json.load(f)

    app = create_app()
    with app.app_context():
        if org_id is None:
            from app.models import Organization
            orgs = Organization.query.all()
            if len(orgs) == 1:
                org_id = orgs[0].id
                print(f"Usando org_id={org_id} ({orgs[0].name})")
            else:
                print("Mais de uma organização no banco. Informe o org_id como segundo argumento.")
                print("Organizações disponíveis:")
                for o in orgs:
                    print(f"  id={o.id}  nome={o.name}")
                sys.exit(1)

        atualizadas = ignoradas = nao_encontradas = 0

        for nr_str, info in dados.items():
            nr = int(nr_str)
            nota = FaturamentoNota.query.filter_by(org_id=org_id, nr=nr, excluido=False).first()
            if nota is None:
                print(f"  ⚠️  NF {nr} não encontrada no banco")
                nao_encontradas += 1
                continue

            recebido = bool(info.get('recebido', False))
            data_str = (info.get('dataRecebimento') or '').strip()
            data_rec = date.fromisoformat(data_str) if data_str else None

            nota.recebido        = recebido
            nota.data_recebimento = data_rec
            atualizadas += 1

        db.session.commit()
        print(f"\n✅ {atualizadas} nota(s) atualizadas")
        if nao_encontradas:
            print(f"⚠️  {nao_encontradas} nota(s) não encontradas no banco (serão importadas quando o XML for enviado)")

if __name__ == '__main__':
    main()
