from datetime import date
from notion_client import Client
from bot.config import Config


class NotionService:
    def __init__(self):
        self.client = Client(auth=Config.NOTION_API_KEY)

    def create_project_database(self, project_name: str) -> str:
        """Cria database para novo projeto. Retorna database_id."""
        response = self.client.databases.create(
            parent={"type": "page_id", "page_id": Config.NOTION_PARENT_PAGE_ID},
            title=[{"type": "text", "text": {"content": project_name}}],
            properties={
                "Título": {"title": {}},
                "Tipo": {
                    "select": {
                        "options": [
                            {"name": "decisão", "color": "green"},
                            {"name": "pendência", "color": "yellow"},
                            {"name": "resumo", "color": "blue"},
                        ]
                    }
                },
                "Status": {
                    "select": {
                        "options": [
                            {"name": "pendente", "color": "red"},
                            {"name": "em_andamento", "color": "yellow"},
                            {"name": "concluída", "color": "green"},
                        ]
                    }
                },
                "Autor": {"rich_text": {}},
                "Responsável": {"rich_text": {}},
                "Data": {"date": {}},
                "Grupo Telegram": {"rich_text": {}},
                "Contexto": {"rich_text": {}},
            },
        )
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
            "Título": {"title": [{"text": {"content": titulo[:100]}}]},
            "Tipo": {"select": {"name": tipo}},
            "Autor": {"rich_text": [{"text": {"content": autor[:100]}}]},
            "Data": {"date": {"start": date.today().isoformat()}},
        }

        if responsavel:
            properties["Responsável"] = {
                "rich_text": [{"text": {"content": responsavel[:100]}}]
            }
        if status:
            properties["Status"] = {"select": {"name": status}}
        if grupo_telegram:
            properties["Grupo Telegram"] = {
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
