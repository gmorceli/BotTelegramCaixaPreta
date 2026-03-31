import asyncio
import anthropic
from bot.config import Config

SYSTEM_PROMPT_TEMPLATE = """Você é Caixa Preta, assistente de memória do projeto "{project_name}".

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
- Máximo de 500 palavras por resposta"""

SUMMARY_PROMPT_TEMPLATE = """Analise as mensagens abaixo do grupo "{project_name}" e gere um resumo estruturado.

## Formato do resumo:
**Decisões tomadas:**
- [liste decisões identificadas]

**Pendências mencionadas:**
- [liste tarefas ou ações pendentes com responsável se mencionado]

**Tópicos discutidos:**
- [liste os principais assuntos abordados]

**Pontos de atenção:**
- [qualquer conflito, dúvida não resolvida ou urgência]

Se alguma seção não tiver conteúdo, omita-a.

---
MENSAGENS:
{formatted_messages}"""

CONTEXT_PROMPT_TEMPLATE = """Com base no histórico de mensagens e registros do projeto "{project_name}", responda a pergunta do membro da equipe.

HISTÓRICO DE MENSAGENS RECENTES:
{formatted_messages}

DECISÕES REGISTRADAS:
{formatted_decisions}

PENDÊNCIAS ATUAIS:
{formatted_tasks}

PERGUNTA:
{user_question}

Responda de forma direta, citando fontes (quem disse, quando) quando possível."""


class ClaudeService:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=Config.ANTHROPIC_API_KEY)
        self.model = Config.CLAUDE_MODEL

    async def _call(self, system: str, user_message: str) -> str:
        response = await asyncio.to_thread(
            self.client.messages.create,
            model=self.model,
            max_tokens=2048,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text

    async def generate_summary(
        self, project_name: str, formatted_messages: str, system_prompt: str | None = None
    ) -> str:
        system = system_prompt or SYSTEM_PROMPT_TEMPLATE.format(project_name=project_name)
        user_msg = SUMMARY_PROMPT_TEMPLATE.format(
            project_name=project_name, formatted_messages=formatted_messages
        )
        return await self._call(system, user_msg)

    async def answer_context(
        self,
        project_name: str,
        formatted_messages: str,
        formatted_decisions: str,
        formatted_tasks: str,
        user_question: str,
        system_prompt: str | None = None,
    ) -> str:
        system = system_prompt or SYSTEM_PROMPT_TEMPLATE.format(project_name=project_name)
        user_msg = CONTEXT_PROMPT_TEMPLATE.format(
            project_name=project_name,
            formatted_messages=formatted_messages,
            formatted_decisions=formatted_decisions,
            formatted_tasks=formatted_tasks,
            user_question=user_question,
        )
        return await self._call(system, user_msg)
