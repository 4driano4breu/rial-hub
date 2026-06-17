# OBRIA — Roadmap de Desenvolvimento
> Plataforma SaaS de gestão operacional para empreiteiras de infraestrutura

**Versão:** 1.0  
**Data:** Junho 2026  
**Status:** Planejamento  
**Tenant #1:** RIAL Construtora (contrato 037/2021 AGESUL)

---

## Visão do Produto

**OBRIA** é uma plataforma SaaS vertical para empreiteiras de infraestrutura que automatiza as tarefas administrativas de maior custo operacional: geração de notas de medição, controle de faturamento NFS-e, rastreamento de insumos (CBUQ/CAP), inspeção viária via OCR+GPS e ferramentas de cálculo de obra.

**Tagline:** *"Do canteiro ao financeiro — automação para quem constrói o Brasil."*

**Problema que resolve:** Empreiteiras de médio porte gerenciam contratos bilionários com planilhas Excel, Word e e-mail. Cada nota de medição, cada NF-e, cada laudo de inspeção é feito manualmente. OBRIA elimina esse atrito.

---

## Nomenclatura das Ferramentas (Tom: Técnico/Descritivo)

### Módulos do Sistema (fixos, toda organização tem acesso conforme plano)

| Nome Atual | Nome OBRIA | URL |
|---|---|---|
| Faz Tudo 3000 | **Registro de Produção Diária** | `/ferramentas/producao` |
| Le Doc | **Preenchimento de Documentos** | `/ferramentas/documentos` |
| Dashboard Abastecimento | **Controle de Combustível** | `/ferramentas/combustivel` |
| Notas 037 (standalone) | **Notas de Medição (offline)** | `/ferramentas/notas` |
| Notas (blueprint) | **Gerador de Notas de Medição** | `/notas` |
| Faturamento | **Gestão de Notas Fiscais** | `/faturamento` |
| Usinagem | **Gestão de Insumos** | `/insumos` |
| Viário | **Inspeção Viária** | `/viario` |
| *(novo)* | **Coleta de Campo** | `/formularios` |

### Painéis — Módulo Genérico de Dashboards

**Conceito:** Dashboards não são mais vinculados a um módulo específico por nome. Toda organização tem uma seção **Painéis** (`/paineis`) que exibe os dashboards que ela configurou — com os nomes, cores e dados que fazem sentido para o seu contexto.

```
/paineis/                    ← galeria de painéis da organização
/paineis/{slug}              ← painel individual (ex: /paineis/acompanhamento-aegea)
/paineis/novo                ← ADMIN: criar novo painel
/paineis/{slug}/configurar   ← ADMIN: editar painel
```

**Para a RIAL, os painéis configurados seriam:**

| Slug | Nome do Painel | Fonte de Dados |
|---|---|---|
| `acompanhamento-aegea` | Acompanhamento AEGEA | Módulo Gestão de Insumos (filtro: AEGEA) |
| `medicao-guariroba` | Medição Águas Guariroba | Módulo Gestão de Insumos (filtro: GUARIROBA) |
| `controle-cbuq` | Controle Geral CBUQ | Módulo Gestão de Insumos (todos) |
| `notas-fiscais` | Acompanhamento de Faturamento | Módulo Gestão de Notas Fiscais |

**Para outra empresa (ex: construtora de pontes), os painéis seriam diferentes:**

| Slug | Nome do Painel | Fonte de Dados |
|---|---|---|
| `consumo-aco` | Consumo de Aço | Módulo Gestão de Insumos |
| `contratos-ativos` | Contratos Ativos | Módulo Gestão de Notas Fiscais |

**Modelo no banco:**
```python
class Painel(db.Model):
    id, org_id, slug, nome, descricao
    modulo_fonte  # 'insumos' | 'faturamento' | 'viario' | 'producao'
    filtros       # JSON: {"tipo": "AEGEA", "contrato": "..."} — filtra dados do módulo
    config_visual # JSON: {"cor": "#003366", "icone": "📊", "ordem": 1}
    ativo, criado_em, atualizado_em
```

**Regra:** A plataforma não sabe o que é "AEGEA" ou "Guariroba". Ela sabe que há dados de insumos com campo `regiao`. O admin da organização cria um painel, escolhe o módulo-fonte e define os filtros. O nome é livre.

---

## Situação Atual (Baseline)

O RIAL Hub é um Flask monolítico funcional rodando localmente com:

| Módulo | Status | Limitação para Nuvem |
|---|---|---|
| Notas de Medição | ✅ Funcional | Arquivos .docx gerados em memória (ok) |
| Faturamento NFS-e | ✅ Funcional | XLSX gravado em disco (`instance/`) |
| Usinagem CBUQ | ✅ Funcional | Dados injetados em HTML estático (disco) |
| Ferramentas (4x) | ✅ Funcional | 100% client-side (ok) |
| Viário OCR/GPS | ⚠️ Desativado | Depende de Tesseract local |
| **Auth/Usuários** | ❌ Não existe | Crítico para deploy |
| **Multi-tenant** | ❌ Não existe | Necessário para SaaS |
| **Banco de Dados** | ❌ Não existe | Filesystem → cloud storage |

**Problema central para deploy:** O app escreve dados no sistema de arquivos local (Excel, HTML, timestamps), o que é incompatível com containers efêmeros em qualquer PaaS.

---

## Decisões de Arquitetura

### Stack de Produção

```
┌─────────────────────────────────────────────────────────┐
│                      OBRIA Cloud                        │
│                                                         │
│  Browser ──► Railway (Flask + Gunicorn)                 │
│                    │                                    │
│              ┌─────┴──────┐                             │
│              │            │                             │
│         PostgreSQL    Cloudflare R2                     │
│         (Railway)     (arquivos .xlsx,                  │
│         tenants,       .docx, .csv)                     │
│         usuários,                                       │
│         registros      Google Sheets API                │
│              │         (fonte de dados                  │
│              └─────────  Usinagem/Viário)               │
└─────────────────────────────────────────────────────────┘
```

### Princípios

1. **Multi-tenant por design** — Todo modelo no banco carrega `organization_id`. A RIAL é `org_id=1`. Novos clientes ganham IDs incrementais.
2. **Filesystem zero** — Nenhum dado de usuário toca o disco do servidor. Tudo vai para PostgreSQL ou R2.
3. **Config por tenant** — Alíquotas, valores de CAP, regiões, contratos são parâmetros no banco, não constantes no código.
4. **Secrets via variáveis de ambiente** — `SECRET_KEY`, `DATABASE_URL`, `R2_*`, `GOOGLE_*` nunca no código.
5. **LGPD** — Dados de terceiros (NFS-e, planilhas de funcionários) são armazenados apenas enquanto necessários, com direito a exclusão.

### Modelo de Dados Central

```
Organization (tenant)
├── id, slug, name, plan
├── settings (JSON) ← alíquotas, CAP, regiões por contrato
└── Users
    ├── id, email, password_hash, role
    └── role: ADMIN | OPERACIONAL | FINANCEIRO | VIEWER

Modules por org:
├── MedicaoRecord (nota, período, cidades, docx_url)
├── FaturamentoNota (nr, emissao, contrato, municipio, valores...)
├── UsinagemRegistro (ticket, data, placa, motorista, peso, regiao)
├── VIarioInspecao (rodovia, km_ini, km_fim, fotos_url[], relatorio_url)
├── FormularioTemplate (slug, nome, campos JSON)        ← Coleta de Campo
└── FormularioResposta (template_id, dados JSON, lat/lon)
```

---

## Fases de Desenvolvimento

---

### FASE 0 — Fundação Cloud
**Duração:** 2–3 semanas  
**Objetivo:** Infraestrutura que suporta todas as fases seguintes  
**Resultado entregável:** App rodando em `obria.app` com login

#### 0.1 — Autenticação e Multi-tenancy

- Adicionar `flask-login`, `bcrypt`, `flask-wtf` ao `requirements.txt`
- Criar modelos SQLAlchemy: `Organization`, `User`, `Role`
- Telas: `/login`, `/logout`, `/register` (invite-only inicialmente)
- Middleware: `@login_required` + `@require_role(...)` em todas as rotas
- Seed: criar organização RIAL + usuário admin no primeiro boot

**Segurança:**
- Senhas: bcrypt com `rounds=12`
- Session: `SECRET_KEY` via env var, `SESSION_COOKIE_SECURE=True`
- CSRF: Flask-WTF em todos os formulários POST
- Rate limiting: Flask-Limiter em `/login` (10 tentativas/hora por IP)

#### 0.2 — Banco de Dados PostgreSQL

- Adicionar `flask-sqlalchemy`, `flask-migrate`, `psycopg2-binary`
- Criar `migrations/` via Alembic (Flask-Migrate)
- `DATABASE_URL` via variável de ambiente (Railway provê automaticamente)
- Migrar `core/timestamps.py` → tabela `ModuleSync(org_id, module, updated_at)`

#### 0.3 — Object Storage (Cloudflare R2)

- Conta R2 gratuita: 10 GB armazenamento, 1M operações/mês — suficiente
- Biblioteca: `boto3` (R2 é S3-compatible)
- Criar `core/storage.py`: `upload_file(key, bytes) → url`, `download_file(key) → bytes`
- Usar para: `.docx` gerados, `.xlsx` do Faturamento, relatórios do Viário

#### 0.4 — Deploy Railway

- `Procfile`: `web: gunicorn -w 2 -b 0.0.0.0:$PORT "app:create_app()"`
- `requirements.txt` adicionar: `gunicorn`
- Variáveis de ambiente no Railway: `SECRET_KEY`, `DATABASE_URL`, `R2_*`
- Domínio customizado: `obria.app` (ou subdomínio Railway inicialmente)
- GitHub Actions: deploy automático a cada push em `main`

#### 0.5 — Segurança Base

- `HTTPS` obrigatório (Railway provê SSL automático)
- Headers de segurança via `flask-talisman`: `CSP`, `HSTS`, `X-Frame-Options`
- Upload validation: checar magic bytes (não só extensão) em todos os endpoints de upload
- `.gitignore`: garantir que `.env`, `instance/`, `uploads/` nunca entram no repo

---

### FASE 1 — Módulos Existentes em Nuvem
**Duração:** 3–4 semanas  
**Objetivo:** Todos os módulos funcionando em produção sem filesystem local  
**Resultado entregável:** RIAL usando OBRIA na nuvem para o trabalho diário

#### 1.1 — Módulo Usinagem: Google Sheets → Banco

**Problema atual:** CSV exportado manualmente → upload → regex injection em HTML estático.

**Nova arquitetura:**
```
Google Sheets (planilha de viagens)
    ↓ Google Sheets API (service account)
    ↓ /usinagem/sincronizar (POST ou cron job)
    ↓ UsinagemRegistro no PostgreSQL
    ↓ /usinagem/geral|aegea|guariroba (GET)
    ↓ Render dinâmico via Jinja2 (sem HTML estático injetado)
```

- Criar `app/services/sheets.py`: `ler_planilha(spreadsheet_id, range) → list[dict]`
- Configuração por tenant: `spreadsheet_id`, `aba`, mapeamento de colunas (em `organization.settings`)
- Remover `updater.py` (regex injection) — substituído por queries SQL
- Dashboards renderizados dinamicamente (dados via API JSON → JS no browser)
- Botão "Sincronizar Agora" + indicador de última sincronização

**Segurança Google Sheets:**
- Service account JSON via variável de ambiente (`GOOGLE_CREDENTIALS_JSON`)
- Compartilhamento: apenas leitura da planilha para a service account
- Credenciais nunca no código ou no repositório

#### 1.2 — Módulo Faturamento: XLSX em R2

**Problema atual:** `Faturamento 2026.xlsx` em `instance/` (perde com restart).

**Nova arquitetura:**
- Ao fazer upload do XLSX inicial → salva em R2 (`faturamento/{org_id}/master.xlsx`)
- Ao processar XML → baixa XLSX do R2 → modifica em memória → sobe de volta ao R2
- `regenerar_dashboard()` → remove lógica de HTML injection → dados servidos via API JSON
- Dashboard HTML vira template Jinja2 com dados dinâmicos

#### 1.3 — Módulo Notas: Sem Mudança Funcional

- Lógica de `core/extractor.py` e `core/generator.py` já funciona em memória ✅
- Único ajuste: salvar `.docx` gerados no R2 com URL temporária (24h) para download
- Registrar `MedicaoRecord` no banco (histórico de notas geradas por org)

#### 1.4 — Registro de Produção Diária (ex-Faz Tudo 3000): Google Sheets → Banco

**Problema atual:** Salva em Google Sheets via Apps Script URL no `localStorage`. Troca de dispositivo = configuração perdida. Sem histórico auditável.

**Análise do código:** O tool já faz `POST` com JSON estruturado para uma URL configurável:
```javascript
// Payload atual (já estruturado, só precisa trocar o destino)
{
  action: 'salvar',
  payload: {
    modo: 'tb' | 'qm',
    data: 'dd/mm/yyyy',
    ticketInicio: 1001,
    ticketFim: 1008,
    regioes: ['ANHANDUIZINHO', ...],
    totalCaminhoes: 8,
    registros: [{ placa, motorista, entrada, saida, tara, peso, regiao }, ...]
  }
}
```

**Nova arquitetura:**
```
Tool HTML (browser)
    ↓ POST /api/producao/salvar  (substitui URL do Apps Script)
    ↓ Blueprint: ferramentas/producao
    ↓ Salva em PostgreSQL (multi-tenant por org_id)
    ↓ Retorna: { ok: true, id: 1234 }
```

**Modelos no banco:**
```python
class OperacaoProducao(db.Model):
    id, org_id, modo (TB/QM), data, ticket_inicio, ticket_fim
    total_caminhoes, criado_por, criado_em

class RegistroProducao(db.Model):
    id, operacao_id, placa, motorista
    entrada, saida, tara, peso, regiao

class BuracoProducao(db.Model):  # dimensões de TB/QM
    id, operacao_id, larg_original, comp_original
    larg_ajustado, comp_ajustado, massa_calculada
```

**Mudanças no HTML** (`static/ferramentas/faz_tudo/medicao_pavimentacao_v6.0.html`):
- Trocar `apiUrl` hardcoded por `/api/producao/salvar` (sem configuração manual)
- Remover lógica de `localStorage` para URL do Apps Script
- Adicionar header `X-CSRFToken` na requisição (Flask-WTF)
- Histórico: buscar via `GET /api/producao/historico?de=&ate=` ao abrir tab Histórico

**Novo endpoint Flask** (`app/blueprints/ferramentas/routes.py`):
```python
@ferramentas_bp.route("/api/producao/salvar", methods=["POST"])
@login_required
def producao_salvar():
    # Valida, cria OperacaoProducao + RegistroProducao[]
    # Retorna JSON { ok: True, id: operacao.id }

@ferramentas_bp.route("/api/producao/historico")
@login_required
def producao_historico():
    # Filtra por org_id, data range, retorna JSON
```

**Ferramentas sem mudança por ora:**
- `Preenchimento de Documentos` (Le Doc): localStorage para config de campos é aceitável
- `Notas de Medição (offline)`: versão standalone do blueprint já existente
- `Controle de Combustível`: dados hardcoded — fase futura quando houver input de abastecimento

#### 1.5 — Parametrização por Tenant

Mover de `core/config.py` (constantes hardcoded) para banco:

```python
# Antes (hardcoded)
ALIQUOTAS = {"pav": 0.10, "canteiro": 0.35, ...}
CAP_AEGEA = 30

# Depois (por tenant)
org.settings = {
  "aliquotas": {"pav": 0.10, "canteiro": 0.35, ...},
  "usinagem": {
    "cap_aegea": 30,
    "cap_guariroba": 63.93,
    "composicao_cap": 0.051
  },
  "contratos": [{"nome": "037/2021", "orgao": "AGESUL", ...}]
}
```

---

### FASE 2 — Produto SaaS
**Duração:** 4–6 semanas  
**Objetivo:** Infraestrutura para onboarding de novos clientes  
**Resultado entregável:** 2–3 clientes piloto além da RIAL

#### 2.1 — Painel de Administração

- `/admin` (acesso: `role=SUPERADMIN`)
- Gerenciar organizações: criar, editar plano, ver uso
- Gerenciar usuários por org: convidar, remover, alterar cargo
- Logs de auditoria: quem fez o quê, quando (tabela `AuditLog`)

#### 2.2 — Sistema de Convite

- Admin da org convida por e-mail → link tokenizado (expira em 48h)
- Novo usuário define senha no primeiro acesso
- Roles disponíveis: `ADMIN`, `FINANCEIRO`, `OPERACIONAL`, `VIEWER`

**Permissões por módulo:**

| Role | Notas | Faturamento | Usinagem | Viário | Config |
|---|---|---|---|---|---|
| ADMIN | ✅ | ✅ | ✅ | ✅ | ✅ |
| FINANCEIRO | ✅ | ✅ | 👁️ | ❌ | ❌ |
| OPERACIONAL | ❌ | ❌ | ✅ | ✅ | ❌ |
| VIEWER | 👁️ | 👁️ | 👁️ | 👁️ | ❌ |

#### 2.3 — Onboarding de Novo Cliente

- Wizard de configuração inicial (3 passos):
  1. Dados da empresa (CNPJ, nome, responsável)
  2. Configuração do contrato (alíquotas, CAP, regiões)
  3. Conexão Google Sheets (colar ID da planilha + tutorial)
- Tenant isolado imediatamente após wizard

#### 2.4 — Landing Page Pública

- `obria.app` — página de apresentação do produto
- Seções: Problema, Solução, Módulos, Preços, Contato
- CTA: "Solicitar demonstração" (formulário → e-mail / WhatsApp)
- Não requer banco — pode ser HTML estático no Cloudflare Pages

#### 2.5 — Modelo de Preços (Sugestão Inicial)

| Plano | Usuários | Módulos | Preço |
|---|---|---|---|
| **Starter** | 3 | Usinagem + Ferramentas | R$ 197/mês |
| **Pro** | 10 | Todos (exceto Viário) | R$ 397/mês |
| **Enterprise** | Ilimitado | Todos + Viário + Config | R$ 797/mês |

*(Revisar após feedback dos clientes piloto)*

#### 2.6 — Coleta de Campo (PWA Mobile)

**Objetivo:** Substituir o Google Forms por formulários mobile configuráveis onde os dados ficam no OBRIA.

**Motivação:** O Google Forms obriga a ter conta Google, os dados ficam no Google Sheets (fora do controle da empresa), não integra com os Painéis do OBRIA e não funciona offline. A Coleta de Campo resolve todos esses pontos.

**Conceito central:**

```
Admin (OBRIA web) → define template (campos, tipos, validações)
                          ↓
            URL: /f/{org_slug}/{form_slug}
            QR Code: impresso no caminhão / canteiro
                          ↓
Worker (celular) → abre URL → preenche → envia → dado no PostgreSQL
                          ↓
Admin (OBRIA web) → vê respostas em tabela → exporta Excel → cruza com Painéis
```

**Rotas:**

```
/formularios/                       ← admin: galeria de templates
/formularios/novo                   ← admin: criar template (drag-and-drop)
/formularios/{slug}/editar          ← admin: editar campos
/formularios/{slug}/respostas       ← admin: tabela de respostas + export Excel
/formularios/{slug}/qrcode          ← admin: gerar QR code para impressão
/f/{org_slug}/{form_slug}           ← mobile: preencher (público ou autenticado)
/f/{org_slug}/{form_slug}/obrigado  ← mobile: confirmação de envio
```

**Tipos de campo suportados:**

| Tipo | Input HTML | Observação |
|------|-----------|------------|
| `text` | `<input type="text">` | Texto livre |
| `number` | `<input type="number">` | Com validação min/max |
| `select` | `<select>` | Opções definidas pelo admin |
| `multiselect` | `<select multiple>` | Múltipla seleção |
| `date` | `<input type="date">` | Picker nativo mobile |
| `time` | `<input type="time">` | Picker nativo mobile |
| `photo` | `<input type="file" capture="camera">` | Câmera do celular, salva no R2 |
| `gps` | `navigator.geolocation` | Auto-preenche lat/lon |
| `boolean` | `<input type="checkbox">` | Sim/Não |

**Definição de um campo (JSON dentro de `campos`):**

```python
{
    "id": "placa",           # identificador único, vira chave no JSON de resposta
    "tipo": "text",
    "label": "Placa do Veículo",
    "placeholder": "ABC-1234",
    "ajuda": "Placa do caminhão que abasteceu",
    "obrigatorio": True,
    "opcoes": [],            # somente para select/multiselect
    "validacao": {}          # {"min": 0, "max": 999} para number
}
```

**Modelos no banco:**

```python
class FormularioTemplate(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    org_id        = db.Column(db.Integer, db.ForeignKey("organization.id"), nullable=False)
    slug          = db.Column(db.String(80), nullable=False)
    nome          = db.Column(db.String(120), nullable=False)
    descricao     = db.Column(db.String(255))
    campos        = db.Column(db.JSON, nullable=False)  # lista de CampoDefinicao
    aceita_anonimo = db.Column(db.Boolean, default=True)  # True = sem login
    ativo         = db.Column(db.Boolean, default=True)
    criado_em     = db.Column(db.DateTime, default=datetime.utcnow)

class FormularioResposta(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    org_id        = db.Column(db.Integer, db.ForeignKey("organization.id"), nullable=False)
    template_id   = db.Column(db.Integer, db.ForeignKey("formulario_template.id"), nullable=False)
    dados         = db.Column(db.JSON, nullable=False)  # {campo_id: valor, ...}
    enviado_por   = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    latitude      = db.Column(db.Float, nullable=True)
    longitude     = db.Column(db.Float, nullable=True)
    dispositivo   = db.Column(db.String(200))  # user-agent
    criado_em     = db.Column(db.DateTime, default=datetime.utcnow)
```

**PWA — Suporte Offline (diferencial vs Google Forms):**

```
Service Worker (sw.js):
├── Cache da página do formulário (instala ao abrir)
├── IndexedDB: armazena respostas enviadas com sinal ruim
├── Background Sync: enfileira POST /f/.../responder
└── Ao reconectar: drena fila automaticamente

Resultado: formulário funciona no canteiro sem internet.
          Os dados chegam assim que o sinal volta.
```

Arquivos a criar:
- `static/formularios/sw.js` — Service Worker
- `static/formularios/manifest.json` — "Adicionar à tela inicial"
- `templates/formularios/form_mobile.html` — UI mobile-first (sem extends base.html, standalone)

**UI Mobile — princípios de design:**

- Fundo escuro (`#0f172a`), sem barra de navegação do OBRIA
- Campos com `padding: 14px`, `font-size: 16px` (evita zoom automático no iOS)
- Botão "Enviar" fixo no bottom: `position: fixed; bottom: 0`
- Indicador de modo offline: banner laranja no topo quando sem conexão
- Após envio: tela de confirmação com "Registrar outro" em 1 clique

**Exemplo de uso (RIAL — substituir planilha de abastecimento):**

Template "Abastecimento Diário" com campos:
```
data (date, obrigatório)
placa (text, obrigatório)
motorista (select: lista de motoristas, obrigatório)
km_atual (number, obrigatório)
litros (number, min:0, max:500)
posto (text)
observacao (text, opcional)
foto_hodometro (photo, opcional)
```

QR code colado no painel do caminhão → motorista escaneia → preenche em 30 segundos.

**Integração com Painéis:**

Admin pode criar um Painel com `modulo_fonte: 'formularios'` + `filtros: {"template_slug": "abastecimento-diario"}` para visualizar as respostas como dashboard com KPIs, gráficos e exportação Excel — usando a mesma infraestrutura de Painéis.

---

### FASE 3 — Módulo Viário
**Duração:** 4–6 semanas  
**Dependência:** Fase 1 concluída, servidor com suporte a Tesseract  
**Objetivo:** Diferencial competitivo — nenhum concorrente tem isso

#### 3.1 — Ativação do Blueprint

- Registrar `viario_bp` em `app/__init__.py`
- Adicionar `pytesseract`, `Pillow`, `numpy`, `pandas` ao `requirements.txt`
- Tesseract em produção: instalar via `nixpacks.toml` no Railway

#### 3.2 — Pipeline OCR + GPS (Cloud)

**Problema atual:** Processa fotos localmente, output em arquivos locais.

**Nova arquitetura:**
```
Usuário faz upload de fotos (batch) via browser
    ↓ R2: armazena fotos originais
    ↓ Pipeline assíncrono (Celery + Redis, ou Railway Jobs)
    ↓ Tesseract: extrai KM, data, hora de cada foto
    ↓ OpenRouteService API: calcula distâncias entre pontos GPS
    ↓ PostgreSQL: salva VIarioInspecao com resultados
    ↓ Gera relatório Excel → salva no R2 → notifica usuário
```

#### 3.3 — Dashboard de Inspeção

- Mapa interativo (Leaflet.js) com as rodovias configuradas
- Linha do tempo de inspeções por rodovia
- Exportação de relatório em Excel/PDF

---

### FASE 4 — Automação e Inteligência
**Duração:** Contínua (pós Fase 2)  
**Objetivo:** Reduzir ainda mais o trabalho manual

#### 4.1 — Sincronização Automática (Cron)
- Usinagem: sincronizar Google Sheets automaticamente a cada 6h
- Faturamento: importar NFS-e via integração com prefeitura (SOAP/REST, onde disponível)

#### 4.2 — Alertas e Notificações
- E-mail/WhatsApp: "Meta AEGEA atingiu 80% — revisar contrato"
- "Nenhuma atualização de Usinagem há 5 dias"
- "Prazo de medição se aproxima" (configurável por contrato)

#### 4.3 — Análise com IA
- Sumarização de relatórios de inspeção viária via LLM
- Detecção de anomalias em dados de pesagem (tickets duplicados suspeitos)
- Assistente de preenchimento de notas de medição

---

## Cronograma Resumido

```
Jun 2026   Jul 2026    Ago 2026    Set 2026    Out 2026    Nov 2026    Dez 2026
│          │           │           │           │           │           │
├─ FASE 0 ─┤
│ Auth, DB │
│ R2, CI/CD│
│ Deploy   │
│          ├── FASE 1 ────────────┤
│          │ Usinagem → Sheets    │
│          │ Faturamento → R2     │
│          │ Parametrização       │
│          │ Produção → DB        │
│          │                      ├── FASE 2 ──────────────────────────┤
│          │                      │ Admin panel                        │
│          │                      │ Convites/RBAC                      │
│          │                      │ Onboarding                         │
│          │                      │ Landing page                       │
│          │                      │ Coleta de Campo (PWA)              │
│          │                      │                    ├─ FASE 3 ──────┤
│          │                      │                    │ Viário OCR    │
│          │                      │                    │ GPS + Mapa    │
```

---

## Stack Técnica Final

```
Backend:     Flask 3.x + SQLAlchemy + Flask-Migrate + Flask-Login
Database:    PostgreSQL 16 (Railway)
Storage:     Cloudflare R2 (S3-compatible, 10GB free)
Auth:        Flask-Login + bcrypt + Flask-WTF (CSRF)
Security:    flask-talisman (headers) + Flask-Limiter (rate limit)
Sheets:      google-api-python-client + google-auth
Deploy:      Railway (PaaS) + Gunicorn
CI/CD:       GitHub Actions → auto-deploy em push para main
Frontend:    Jinja2 + CSS variables (dark theme existente) + Chart.js
Mobile:      PWA (Service Worker + IndexedDB + Background Sync) — Fase 2.6
Maps:        Leaflet.js (Fase 3)
Async:       Railway Jobs / Celery + Redis (Fase 3+)
```

---

## Checklist de Segurança (OWASP Top 10)

- [ ] **A01 Broken Access Control** — `@login_required` + `@require_org_access` em todas as rotas
- [ ] **A02 Cryptographic Failures** — HTTPS obrigatório, bcrypt para senhas, secrets em env vars
- [ ] **A03 Injection** — SQLAlchemy ORM (sem SQL raw), Jinja2 auto-escape
- [ ] **A04 Insecure Design** — Tenant isolation por `org_id` em todas as queries
- [ ] **A05 Security Misconfiguration** — `DEBUG=False` em prod, headers via flask-talisman
- [ ] **A06 Vulnerable Components** — `pip-audit` no CI/CD, `requirements.txt` com versões mínimas
- [ ] **A07 Auth Failures** — Rate limiting em `/login`, tokens de convite com expiração
- [ ] **A08 Software Integrity** — GitHub Actions com pinned actions, deploy via git
- [ ] **A09 Logging Failures** — `AuditLog` table para ações sensíveis
- [ ] **A10 SSRF** — Validar URLs de webhook (Fase futura), whitelist de domínios Google API

---

## Próximos Passos Imediatos (Fase 0)

1. **Criar branch `feat/auth-multitenant`** no `dev/rial-hub`
2. **Instalar dependências base:** `flask-sqlalchemy flask-migrate flask-login flask-wtf flask-talisman flask-limiter bcrypt gunicorn psycopg2-binary`
3. **Criar modelos:** `Organization`, `User` com `role` enum
4. **Configurar Railway:** projeto novo + PostgreSQL plugin + variáveis de ambiente
5. **Escrever `Procfile`** e testar deploy
6. **Migrar `core/timestamps.py`** para tabela `ModuleSync`
7. **Adicionar `@login_required`** em todas as blueprints existentes

---

## Onde Salvar Este Documento

Após aprovação, salvar em:
```
C:\Users\Pichau\dev\rial-hub\docs\ROADMAP.md
```
E commitar no repositório para referência da equipe.
