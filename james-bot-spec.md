# James Bot — Telegram Bot de Memória de Projetos

## Visão Geral

Bot Telegram multi-grupo que funciona como memória inteligente de projetos. Um único bot atende N grupos, cada um com contexto isolado. Usa Claude Haiku como cérebro para resumos e buscas contextuais, e Notion como banco de dados persistente.

**Stack**: Python 3.11+ · python-telegram-bot · Anthropic SDK · Notion SDK · Railway (deploy)

---

## Arquitetura

```
Telegram Groups (N grupos)
       │
       ▼
  Bot Python (único processo)
       │
       ├── Router (identifica grupo pelo chat_id)
       │
       ├── Message Buffer (SQLite local)
       │      └── Armazena todas as mensagens por grupo
       │
       ├── Claude API (claude-haiku-4-5-20251001)
       │      └── Resumos, busca contextual, análise
       │
       └── Notion API
              └── Uma database por projeto
                    ├── Decisões
                    ├── Pendências
                    └── Resumos diários
```

---

## Estrutura do Projeto

```
james-bot/
├── bot/
│   ├── __init__.py
│   ├── main.py              # Entry point, inicializa bot e handlers
│   ├── config.py             # Carrega env vars e configurações
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── commands.py       # Handlers dos comandos /start, /setup, /resumo, etc.
│   │   ├── messages.py       # Handler passivo que captura todas as mensagens
│   │   └── callbacks.py      # Handlers de callback para botões inline
│   ├── services/
│   │   ├── __init__.py
│   │   ├── claude_service.py # Integração com Anthropic API
│   │   ├── notion_service.py # Integração com Notion API
│   │   └── summary_service.py# Lógica de resumos automáticos (scheduler)
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── database.py       # SQLite — buffer de mensagens e config de grupos
│   │   └── models.py         # Schemas das tabelas
│   └── utils/
│       ├── __init__.py
│       └── helpers.py        # Formatação, truncamento, parsing
├── .env.example              # Template de variáveis de ambiente
├── requirements.txt
├── Procfile                  # Para Railway
├── railway.toml              # Config Railway
└── README.md
```

---

## Variáveis de Ambiente (.env)

```env
# Telegram
TELEGRAM_BOT_TOKEN=           # Token do @BotFather

# Anthropic
ANTHROPIC_API_KEY=            # API key Anthropic
CLAUDE_MODEL=claude-haiku-4-5-20251001

# Notion
NOTION_API_KEY=               # Integration token do Notion
NOTION_PARENT_PAGE_ID=        # Page ID onde as databases dos projetos serão criadas

# Bot Config
ADMIN_USER_IDS=               # Telegram user IDs dos admins (comma-separated)
DAILY_SUMMARY_HOUR=18         # Hora do resumo diário (UTC-3 ajustar)
MESSAGE_BUFFER_LIMIT=500      # Máximo de mensagens no buffer antes de flush
```

---

## Banco de Dados Local (SQLite)

O SQLite serve como buffer rápido. Notion é a persistência de longo prazo.

### Tabela: `groups`

```sql
CREATE TABLE groups (
    chat_id INTEGER PRIMARY KEY,
    group_name TEXT NOT NULL,
    project_name TEXT NOT NULL,
    notion_database_id TEXT,          -- ID da database Notion deste projeto
    system_prompt TEXT,               -- System prompt customizado para o Claude
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT 1
);
```

### Tabela: `messages`

```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    username TEXT,
    display_name TEXT,
    message_text TEXT NOT NULL,
    message_type TEXT DEFAULT 'text',  -- text, photo, document, etc.
    reply_to_message_id INTEGER,
    telegram_message_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chat_id) REFERENCES groups(chat_id)
);
```

### Tabela: `decisions`

```sql
CREATE TABLE decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    decision_text TEXT NOT NULL,
    context TEXT,                      -- Mensagens anteriores que levaram à decisão
    notion_page_id TEXT,              -- ID da page criada no Notion
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chat_id) REFERENCES groups(chat_id)
);
```

### Tabela: `tasks`

```sql
CREATE TABLE tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    assigned_to TEXT,                  -- @username
    task_text TEXT NOT NULL,
    status TEXT DEFAULT 'pendente',    -- pendente, em_andamento, concluida
    notion_page_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    FOREIGN KEY (chat_id) REFERENCES groups(chat_id)
);
```

---

## Comandos do Bot

### `/setup`
**Quem pode usar**: Apenas ADMIN_USER_IDS
**Contexto**: Executado dentro do grupo a ser configurado
**Fluxo**:
1. Bot pergunta o nome do projeto (inline keyboard ou texto livre)
2. Bot cria uma database no Notion dentro da NOTION_PARENT_PAGE_ID com o schema:
   - Properties: `Tipo` (select: decisão/pendência/resumo), `Conteúdo` (rich_text), `Autor` (rich_text), `Status` (select: pendente/em_andamento/concluída — só para pendências), `Data` (date)
3. Bot salva chat_id + notion_database_id + project_name na tabela `groups`
4. Bot gera um system_prompt padrão: `"Você é o assistente do projeto {project_name}. Seu papel é ajudar a equipe a manter registro de decisões, pendências e contexto do projeto. Responda sempre em português brasileiro, de forma objetiva e direta."`
5. Bot confirma no grupo: "✅ Projeto **{name}** configurado! Database Notion criada. Use /help para ver os comandos."

### `/resumo`
**Quem pode usar**: Qualquer membro do grupo
**Fluxo**:
1. Busca as últimas 100 mensagens do grupo no SQLite (ou desde o último /resumo)
2. Envia para Claude com o system_prompt do grupo + instrução: "Gere um resumo objetivo das discussões. Destaque: decisões tomadas, pendências mencionadas, tópicos em aberto. Formato com bullet points. Máximo 500 palavras."
3. Posta o resumo no grupo
4. Salva o resumo no Notion com tipo "resumo"

### `/decisao [texto]`
**Quem pode usar**: Qualquer membro
**Fluxo**:
1. Captura o texto após o comando
2. Busca as 10 mensagens anteriores como contexto
3. Salva no SQLite (tabela decisions) e cria page no Notion
4. Confirma: "📌 Decisão registrada por @{username}: {texto}"

### `/pendencia [@usuario] [texto da tarefa]`
**Quem pode usar**: Qualquer membro
**Fluxo**:
1. Parseia @usuario e texto da tarefa
2. Se @usuario não for informado, atribui a quem enviou
3. Salva no SQLite (tabela tasks) e cria page no Notion com status "pendente"
4. Confirma: "📋 Pendência criada para @{usuario}: {texto}"

### `/pendencias`
**Quem pode usar**: Qualquer membro
**Fluxo**:
1. Busca todas as tasks pendentes e em_andamento do grupo
2. Lista formatada: "📋 **Pendências do projeto:**\n• {tarefa} → @{usuario} (status)\n..."

### `/feito [número ou texto da pendência]`
**Quem pode usar**: Qualquer membro
**Fluxo**:
1. Marca pendência como concluída no SQLite e atualiza no Notion
2. Confirma: "✅ Pendência concluída: {texto}"

### `/contexto [pergunta]`
**Quem pode usar**: Qualquer membro
**Fluxo**:
1. Busca mensagens relevantes no SQLite (últimas 200 ou busca por keywords)
2. Busca decisões e pendências do projeto
3. Envia tudo para Claude com a pergunta do usuário
4. Claude responde com base no histórico: "Com base nas discussões do projeto, {resposta}..."
5. Posta resposta no grupo (NÃO salva no Notion — é consulta efêmera)

### `/help`
Lista todos os comandos disponíveis com descrição breve.

### `/status`
**Quem pode usar**: Apenas ADMIN_USER_IDS
Mostra: nome do projeto, total de mensagens registradas, decisões, pendências abertas, último resumo.

---

## Captura Passiva de Mensagens

**Handler `messages.py`** — registra TODA mensagem de texto no grupo.

```python
# Pseudocódigo do handler
async def handle_message(update, context):
    # Ignora mensagens privadas (bot só opera em grupos)
    if update.effective_chat.type not in ['group', 'supergroup']:
        return

    chat_id = update.effective_chat.id

    # Verifica se o grupo está configurado
    group = db.get_group(chat_id)
    if not group:
        return  # Grupo não configurado, ignora silenciosamente

    # Salva no buffer SQLite
    db.save_message(
        chat_id=chat_id,
        user_id=update.effective_user.id,
        username=update.effective_user.username,
        display_name=update.effective_user.full_name,
        message_text=update.message.text,
        telegram_message_id=update.message.message_id,
        reply_to=update.message.reply_to_message.message_id if update.message.reply_to_message else None
    )
```

**Importante**: O bot precisa ter **privacidade de grupo desabilitada** no @BotFather (`/setprivacy` → Disable) para ler todas as mensagens, não só comandos.

---

## Resumo Automático Diário

Usar `APScheduler` para agendar um job que roda todo dia no horário configurado.

```python
# Pseudocódigo
async def daily_summary_job(context):
    groups = db.get_all_active_groups()
    for group in groups:
        messages = db.get_messages_since_last_summary(group.chat_id)
        if len(messages) < 5:
            continue  # Não gera resumo se teve pouca atividade

        summary = await claude_service.generate_summary(
            messages=messages,
            system_prompt=group.system_prompt
        )

        # Posta no grupo
        await context.bot.send_message(
            chat_id=group.chat_id,
            text=f"📊 **Resumo do dia** — {date.today().strftime('%d/%m/%Y')}\n\n{summary}",
            parse_mode='Markdown'
        )

        # Salva no Notion
        await notion_service.create_page(
            database_id=group.notion_database_id,
            tipo="resumo",
            conteudo=summary,
            autor="James Bot"
        )
```

---

## Claude Service — Configuração dos Prompts

### System Prompt Base (template, customizado por grupo)

```
Você é James, assistente de memória do projeto "{project_name}".

Seu papel:
- Manter o time organizado com resumos claros e objetivos
- Responder perguntas sobre o histórico do projeto com base nas mensagens registradas
- Identificar decisões, pendências e tópicos em aberto

Regras:
- Responda SEMPRE em português brasileiro
- Seja direto e objetivo, sem enrolação
- Quando citar uma informação, mencione quem disse e quando (se disponível)
- Se não tiver informação suficiente para responder, diga isso claramente
- Formate com bullet points para facilitar leitura em tela de celular
- Máximo de 500 palavras por resposta
```

### Prompt para /resumo

```
Analise as mensagens abaixo do grupo "{project_name}" e gere um resumo estruturado.

## Formato do resumo:
**🎯 Decisões tomadas:**
- [liste decisões identificadas]

**📋 Pendências mencionadas:**
- [liste tarefas ou ações pendentes com responsável se mencionado]

**💬 Tópicos discutidos:**
- [liste os principais assuntos abordados]

**⚠️ Pontos de atenção:**
- [qualquer conflito, dúvida não resolvida ou urgência]

Se alguma seção não tiver conteúdo, omita-a.

---
MENSAGENS:
{formatted_messages}
```

### Prompt para /contexto

```
Com base no histórico de mensagens e registros do projeto "{project_name}", responda a pergunta do membro da equipe.

HISTÓRICO DE MENSAGENS RECENTES:
{formatted_messages}

DECISÕES REGISTRADAS:
{formatted_decisions}

PENDÊNCIAS ATUAIS:
{formatted_tasks}

PERGUNTA:
{user_question}

Responda de forma direta, citando fontes (quem disse, quando) quando possível.
```

---

## Notion Service — Schema da Database

Ao executar `/setup`, criar database no Notion com estas properties:

```python
NOTION_DB_SCHEMA = {
    "Título": {"title": {}},
    "Tipo": {
        "select": {
            "options": [
                {"name": "decisão", "color": "green"},
                {"name": "pendência", "color": "yellow"},
                {"name": "resumo", "color": "blue"}
            ]
        }
    },
    "Status": {
        "select": {
            "options": [
                {"name": "pendente", "color": "red"},
                {"name": "em_andamento", "color": "yellow"},
                {"name": "concluída", "color": "green"}
            ]
        }
    },
    "Autor": {"rich_text": {}},
    "Responsável": {"rich_text": {}},
    "Data": {"date": {}},
    "Grupo Telegram": {"rich_text": {}},
    "Contexto": {"rich_text": {}}  # Mensagens que precederam a decisão
}
```

---

## Integração com Notion — Funções Necessárias

```python
class NotionService:
    async def create_project_database(self, parent_page_id: str, project_name: str) -> str:
        """Cria database para novo projeto. Retorna database_id."""

    async def create_page(self, database_id: str, tipo: str, titulo: str,
                          conteudo: str, autor: str, responsavel: str = None,
                          status: str = None, contexto: str = None) -> str:
        """Cria page na database. Retorna page_id."""

    async def update_page_status(self, page_id: str, status: str):
        """Atualiza status de uma pendência."""

    async def query_database(self, database_id: str, tipo: str = None,
                             status: str = None) -> list:
        """Consulta pages na database com filtros."""
```

---

## requirements.txt

```
python-telegram-bot[job-queue]==21.9
anthropic>=0.43.0
notion-client>=2.2.0
python-dotenv>=1.0.0
APScheduler>=3.10.0
aiosqlite>=0.20.0
```

---

## Deploy no Railway

### Procfile

```
worker: python -m bot.main
```

### railway.toml

```toml
[build]
builder = "nixpacks"

[deploy]
startCommand = "python -m bot.main"
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 3
```

### Notas de deploy:
- Railway suporta SQLite (os dados persistem no volume, mas **configurar volume persistente** no Railway para `/data`)
- Setar todas as env vars no dashboard do Railway
- O bot roda como **worker** (long-running process), NÃO como web service
- Railway free tier: 500h/mês — suficiente para rodar 24/7 com o bot idle a maior parte do tempo ($5/mês no plano Hobby garante uptime contínuo)

---

## Setup Inicial — Checklist para o Dev

1. [ ] Criar bot no @BotFather → obter TELEGRAM_BOT_TOKEN
2. [ ] Executar `/setprivacy` → Disable (para o bot ler todas as mensagens em grupo)
3. [ ] Criar Integration no Notion (https://www.notion.so/my-integrations) → obter NOTION_API_KEY
4. [ ] Criar page "Projetos James Bot" no Notion e compartilhar com a Integration → obter NOTION_PARENT_PAGE_ID
5. [ ] Obter ANTHROPIC_API_KEY em console.anthropic.com
6. [ ] Criar projeto no Railway, configurar env vars
7. [ ] Deploy e testar com um grupo de teste

---

## Extensões Futuras (não implementar agora)

- [ ] Busca semântica com embeddings (Chroma ou Pinecone) para /contexto mais preciso
- [ ] Integração com Google Drive (via MCP) para indexar documentos do projeto
- [ ] Comando /relatorio que gera PDF semanal do projeto
- [ ] Comando /config para admins ajustarem system_prompt e configurações sem tocar código
- [ ] Webhook para Notion → Telegram (notificar grupo quando alguém atualiza pendência direto no Notion)
- [ ] Multi-idioma (para projetos com parceiros internacionais)
