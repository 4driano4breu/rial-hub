# Decisões Arquiteturais — RIAL Hub

DECISÃO: Blueprints por domínio de negócio
MOTIVO: Notas, Faturamento, Usinagem são independentes — cada um pode evoluir sem afetar os outros.
Adicionar uma nova ferramenta = criar nova pasta de Blueprint.
ALTERNATIVA DESCARTADA: Blueprint único "financeiro" — acoplaria rotas sem benefício.

---

DECISÃO: Camada core/ sem imports do Flask
MOTIVO: extractor.py e generator.py precisam ser testáveis com pytest puro, sem app context.
Também reutilizáveis pelos scripts CLI legados sem modificação.
ALTERNATIVA DESCARTADA: Lógica diretamente nos routes.py — duplicaria código entre blueprints.

---

DECISÃO: Ferramentas HTML puras servidas via send_from_directory
MOTIVO: Faz Tudo 3000, Le Doc e Abastecimento são 100% client-side. Reescrevê-las seria
trabalho sem ganho funcional. send_from_directory as serve sem tocar uma linha de JS.
ALTERNATIVA DESCARTADA: iframe embed — quebra scripts com window.location e CSP.

---

DECISÃO: Uploads deletados após processamento
MOTIVO: Planilhas AGESUL e XMLs NFS-e contêm dados contratuais sensíveis.
Sem autenticação na Fase 1, não persistir é a postura correta.
ALTERNATIVA DESCARTADA: Banco de arquivos + limpeza agendada — over-engineering para uso interno.

---

DECISÃO: Sistema Viário e Downloader excluídos da Fase 1
MOTIVO: Sistema Viário já é Flask autônomo com OCR + GPS API — integrar cria risco de regressão.
Downloader usa Telethon async incompatível com Flask síncrono e requer sessão OAuth com credenciais.
ALTERNATIVA: Rodar Sistema Viário em porta separada (:5001) e linkar via card no dashboard.

---

DECISÃO: requirements.txt com versão mínima (>=) sem pinning exato
MOTIVO: Ambiente local Windows, permite updates de segurança automáticos via pip.
Pinning exato (==) é necessário apenas para deploy em produção auditada.
