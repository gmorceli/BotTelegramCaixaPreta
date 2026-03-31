import logging
from datetime import date
from notion_client import Client
from bot.config import Config

logger = logging.getLogger(__name__)


class NotionService:
    def __init__(self):
        self.client = Client(auth=Config.NOTION_API_KEY)

    def create_project_database(self, project_name: str, chat_id: int, group_name: str) -> str:
        """Cria database para novo projeto. Retorna database_id.
        Salva chat_id e group_name na descrição da database para restauração."""
        properties = {
            "Name": {"title": {}},
            "Tipo": {
                "select": {
                    "options": [
                        {"name": "decisao", "color": "green"},
                        {"name": "pendencia", "color": "yellow"},
                        {"name": "resumo", "color": "blue"},
                    ]
                }
            },
            "Status": {
                "select": {
                    "options": [
                        {"name": "pendente", "color": "red"},
                        {"name": "em_andamento", "color": "yellow"},
                        {"name": "concluida", "color": "green"},
                    ]
                }
            },
            "Autor": {"rich_text": {}},
            "Responsavel": {"rich_text": {}},
            "Data": {"date": {}},
            "GrupoTelegram": {"rich_text": {}},
            "Contexto": {"rich_text": {}},
        }
        logger.info(f"Criando database Notion com properties: {list(properties.keys())}")
        response = self.client.databases.create(
            parent={"type": "page_id", "page_id": Config.NOTION_PARENT_PAGE_ID},
            title=[{"type": "text", "text": {"content": project_name}}],
            description=[{"type": "text", "text": {"content": f"chat_id={chat_id}|group_name={group_name}"}}],
            properties=properties,
        )
        created_props = list(response.get("properties", {}).keys())
        logger.info(f"Database criada com properties: {created_props}")
        return response["id"]

    def create_page(
        self,
        database_id: str,
        tipo: str,
        titulo: str,
        conteudo: str,
        autor: str,
        responsavel: str | None = None,
        status: str | None = None,
        contexto: str | None = None,
        grupo_telegram: str | None = None,
    ) -> str:
        """Cria page na database. Retorna page_id."""
        properties = {
            "Name": {"title": [{"text": {"content": titulo[:100]}}]},
            "Tipo": {"select": {"name": tipo}},
            "Autor": {"rich_text": [{"text": {"content": autor[:100]}}]},
            "Data": {"date": {"start": date.today().isoformat()}},
        }

        if responsavel:
            properties["Responsavel"] = {
                "rich_text": [{"text": {"content": responsavel[:100]}}]
            }
        if status:
            properties["Status"] = {"select": {"name": status}}
        if grupo_telegram:
            properties["GrupoTelegram"] = {
                "rich_text": [{"text": {"content": grupo_telegram[:100]}}]
            }

        # Conteúdo vai no body da page como bloco de texto
        children = self._text_to_blocks(conteudo)

        # Contexto como property (truncado a 2000 chars para Notion)
        if contexto:
            properties["Contexto"] = {
                "rich_text": [{"text": {"content": contexto[:2000]}}]
            }

        response = self.client.pages.create(
            parent={"database_id": database_id},
            properties=properties,
            children=children,
        )
        return response["id"]

    def update_page_status(self, page_id: str, status: str):
        """Atualiza status de uma pendência."""
        self.client.pages.update(
            page_id=page_id,
            properties={"Status": {"select": {"name": status}}},
        )

    def query_database(
        self, database_id: str, tipo: str | None = None, status: str | None = None
    ) -> list:
        """Consulta pages na database com filtros."""
        filters = []
        if tipo:
            filters.append({"property": "Tipo", "select": {"equals": tipo}})
        if status:
            filters.append({"property": "Status", "select": {"equals": status}})

        query_filter = None
        if len(filters) == 1:
            query_filter = filters[0]
        elif len(filters) > 1:
            query_filter = {"and": filters}

        kwargs = {"database_id": database_id}
        if query_filter:
            kwargs["filter"] = query_filter

        response = self.client.databases.query(**kwargs)
        return response.get("results", [])

    def get_all_project_databases(self) -> list[dict]:
        """Busca todas as databases filhas da page pai para restaurar configs.
        Retorna lista de dicts com chat_id, project_name, group_name, database_id."""
        projects = []
        try:
            response = self.client.search(
                filter={"property": "object", "value": "database"},
            )
            for db in response.get("results", []):
                # Verifica se é filha da page pai
                parent = db.get("parent", {})
                if parent.get("page_id", "").replace("-", "") != Config.NOTION_PARENT_PAGE_ID.replace("-", ""):
                    continue

                # Extrai info da descrição
                description_parts = db.get("description", [])
                desc_text = ""
                for part in description_parts:
                    desc_text += part.get("plain_text", "")

                if "chat_id=" not in desc_text:
                    continue

                # Parse: "chat_id=123|group_name=Grupo"
                info = {}
                for pair in desc_text.split("|"):
                    if "=" in pair:
                        key, value = pair.split("=", 1)
                        info[key.strip()] = value.strip()

                chat_id = info.get("chat_id")
                if not chat_id:
                    continue

                # Extrai nome do projeto do título da database
                title_parts = db.get("title", [])
                project_name = ""
                for part in title_parts:
                    project_name += part.get("plain_text", "")

                projects.append({
                    "chat_id": int(chat_id),
                    "project_name": project_name or "Projeto",
                    "group_name": info.get("group_name", project_name),
                    "database_id": db["id"],
                })

            logger.info(f"Encontrados {len(projects)} projetos no Notion para restaurar")
        except Exception as e:
            logger.error(f"Erro ao buscar databases no Notion: {e}")

        return projects

    @staticmethod
    def _text_to_blocks(text: str) -> list:
        """Converte texto em blocos Notion (paragraphs), respeitando limite de 2000 chars."""
        blocks = []
        # Divide em parágrafos
        paragraphs = text.split("\n\n") if "\n\n" in text else text.split("\n")
        for para in paragraphs:
            if not para.strip():
                continue
            # Notion limita rich_text a 2000 chars por bloco
            chunk = para[:2000]
            blocks.append(
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": chunk}}]
                    },
                }
            )
        return blocks
