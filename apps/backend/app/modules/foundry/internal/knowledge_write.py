"""Criar e apagar base de conhecimento — via SDK oficial.

MÁXIMA MAIOR: `create_or_update_knowledge_source` + `create_or_update_knowledge_base` fazem o
trabalho, e `AzureBlobKnowledgeSource` já resolve chunking, embedding e indexação. O que
escrevemos é: subir os arquivos, montar os dois objetos na forma que ESTE repositório já usa
(copiada de `modules/knowledge/internal/ingest.py`, que é o caminho testado em produção aqui), e
apagar na ordem certa.

TRÊS DECISÕES QUE NÃO SÃO ÓBVIAS:

**A ordem de apagar importa.** Base antes de fonte. A base REFERENCIA a fonte; apagar a fonte
primeiro deixa a base apontando para nada — e uma base nesse estado responde erro em vez de
"não sei", que é pior porque parece defeito do agente.

**Um container por base, não um por tenant.** Cada base recebe seu próprio container no
storage. Compartilhar um container faria a fonte de uma base indexar os arquivos da outra, já
que `AzureBlobKnowledgeSource` indexa o container inteiro. O isolamento não é preferência de
organização — é o que impede uma base de responder com o conteúdo da vizinha.

**Nenhum segredo trafega.** A fonte lê o blob por `ResourceId=`, que instrui o Search a usar a
identidade gerenciada dele. É o mesmo mecanismo do ingest, e o motivo é a RULE #2: nunca chave
de conta no caminho.
"""

from __future__ import annotations

import contextlib
import os
import re
from typing import Any

from app.modules.foundry.internal.audited import audited
from app.modules.foundry.internal.names import qualify
from app.modules.tenancy.public import tenant_config

_API_VERSION = os.environ.get("SEARCH_API_VERSION", "2026-05-01-preview")

# Teto por arquivo e por lote. Não é politica de produto — é o que impede um upload de derrubar o
# processo por memória, já que o conteúdo é lido inteiro para subir.
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_FILES = 200

# Extensões que o blob source extrai texto de forma confiável. Recusar antes de subir é melhor
# que indexar um binário e devolver lixo como citação.
ALLOWED_SUFFIXES = {
    ".md", ".txt", ".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm", ".json", ".csv",
}


class UploadRejected(ValueError):
    """Arquivo que não vamos subir, com o motivo."""


def _index_client():
    from azure.identity import DefaultAzureCredential
    from azure.search.documents.indexes import SearchIndexClient

    return SearchIndexClient(
        endpoint=tenant_config().azure_search_endpoint,
        credential=DefaultAzureCredential(),
        api_version=_API_VERSION,
    )


def _blob_service():
    from azure.identity import DefaultAzureCredential
    from azure.storage.blob import BlobServiceClient

    account = tenant_config().azure_storage_account
    return BlobServiceClient(
        account_url=f"https://{account}.blob.core.windows.net",
        credential=DefaultAzureCredential(),
    )


def _container_for(qualified_name: str) -> str:
    """O container desta base.

    Regra do Azure Storage: 3–63 caracteres, minúsculas, números e hífens, sem hífen duplo nem
    nas pontas. O nome do recurso já foi validado, mas o alfabeto do storage é mais estreito que
    o do Search — então normaliza aqui em vez de confiar que os dois coincidem.
    """
    slug = re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9-]", "-", qualified_name.lower())).strip("-")
    return f"kb-{slug}"[:63].rstrip("-")


def _safe_blob_name(filename: str) -> str:
    """O nome do blob, sem caminho.

    `../` num nome de arquivo enviado pelo cliente é travessia de diretório: o storage trata
    barras como hierarquia, então um nome como `../outra-base/doc.md` escreveria fora do
    container previsto. Só a última parte sobrevive, e ela é higienizada.
    """
    base = os.path.basename(filename.replace("\\", "/")).strip()
    base = re.sub(r"[^\w.\- ]", "_", base)
    if not base or base.startswith("."):
        raise UploadRejected(f"Nome de arquivo inválido: {filename!r}")
    return base


def check_upload(filename: str, size: int) -> str:
    """Valida um arquivo antes de ler o conteúdo; devolve o nome de blob seguro."""
    name = _safe_blob_name(filename)
    suffix = os.path.splitext(name)[1].lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise UploadRejected(
            f"{name}: extensão {suffix or '(nenhuma)'} não é suportada. "
            f"Aceitas: {', '.join(sorted(ALLOWED_SUFFIXES))}."
        )
    if size > MAX_FILE_BYTES:
        raise UploadRejected(f"{name}: passa de {MAX_FILE_BYTES // (1024 * 1024)} MB.")
    return name


def ensure_container(qualified_name: str) -> str:
    """Garante que o container desta base existe, e devolve o nome dele.

    ORDEM QUE O SERVIÇO IMPÕE, e que só a chamada real revelou: a knowledge source é validada no
    momento em que é criada. Se o container ainda não existe, o Search responde

        Unable to retrieve blob container for account '<conta>' using your managed identity

    — mensagem que soa como problema de permissão e manda procurar no lugar errado. Então o
    container nasce ANTES da fonte, não no primeiro upload.
    """
    service = _blob_service()
    try:
        container = _container_for(qualified_name)
        with contextlib.suppress(Exception):  # já existe é o caso normal
            service.get_container_client(container).create_container()
        return container
    finally:
        with contextlib.suppress(Exception):
            service.close()


@audited("knowledge", "update")
def upload_files(name: str, files: list[tuple[str, bytes]]) -> dict:
    """Sobe arquivos para o container desta base, criando o container se preciso.

    Devolve o que subiu, para a resposta poder dizer nome por nome — "3 arquivos enviados" sem a
    lista esconde qual falhou quando um falha.
    """
    if len(files) > MAX_FILES:
        raise UploadRejected(f"Máximo de {MAX_FILES} arquivos por envio (recebidos {len(files)}).")

    qualified = qualify(name)
    container = ensure_container(qualified)
    service = _blob_service()
    try:
        cc = service.get_container_client(container)
        written = []
        for filename, data in files:
            blob = check_upload(filename, len(data))
            cc.upload_blob(name=blob, data=data, overwrite=True)
            written.append({"name": blob, "bytes": len(data)})
        return {"container": container, "files": written}
    finally:
        with contextlib.suppress(Exception):
            service.close()


@audited("knowledge", "create")
def create_knowledge(name: str, description: str = "", answer_instructions: str = "") -> dict:
    """Cria (ou atualiza) a fonte e a base desta base de conhecimento.

    Fonte primeiro, base depois — a base referencia a fonte, então criar na ordem inversa
    falharia na referência. `create_or_update` é idempotente de propósito: chamar duas vezes com
    o mesmo nome atualiza, e é o que faz "salvar de novo" funcionar sem erro.
    """
    from azure.search.documents.indexes.models import (
        AzureBlobKnowledgeSource,
        AzureBlobKnowledgeSourceParameters,
        AzureOpenAIVectorizerParameters,
        KnowledgeBase,
        KnowledgeBaseAzureOpenAIModel,
        KnowledgeRetrievalLowReasoningEffort,
        KnowledgeSourceAzureOpenAIVectorizer,
        KnowledgeSourceIngestionParameters,
        KnowledgeSourceReference,
    )

    qualified = qualify(name)
    source_name = f"{qualified}-ks"
    # Antes da fonte: o Search valida o container no momento da criação (ver `ensure_container`).
    container = ensure_container(qualified)
    cfg = tenant_config()
    storage_id = cfg.azure_storage_resource_id

    client = _index_client()
    try:
        source = AzureBlobKnowledgeSource(
            name=source_name,
            description=description or f"Fonte da base {name}.",
            azure_blob_parameters=AzureBlobKnowledgeSourceParameters(
                # ResourceId= manda o Search ler pela identidade gerenciada dele (sem chave).
                connection_string=f"ResourceId={storage_id};",
                container_name=container,
                ingestion_parameters=KnowledgeSourceIngestionParameters(
                    embedding_model=KnowledgeSourceAzureOpenAIVectorizer(
                        azure_open_ai_parameters=AzureOpenAIVectorizerParameters(
                            resource_url=cfg.azure_ai_openai_endpoint,
                            deployment_name=cfg.foundry_embedding_model,
                            model_name=cfg.foundry_embedding_model,
                        )
                    ),
                ),
            ),
        )
        client.create_or_update_knowledge_source(source)

        base = KnowledgeBase(
            name=qualified,
            description=description or f"Base {name}.",
            knowledge_sources=[KnowledgeSourceReference(name=source_name)],
            models=[
                KnowledgeBaseAzureOpenAIModel(
                    azure_open_ai_parameters=AzureOpenAIVectorizerParameters(
                        resource_url=cfg.azure_ai_openai_endpoint,
                        deployment_name=cfg.foundry_model,
                        model_name=cfg.foundry_model,
                    )
                )
            ],
            output_mode="answerSynthesis",
            # O default carrega a regra que é POLICY neste produto (regra 4 do CLAUDE.md): citar
            # a fonte ou declinar. Uma base criada sem isso responderia sem citação, e o gate de
            # eval reprovaria o agente por um default que o usuário nunca escolheu.
            answer_instructions=answer_instructions
            or (
                "Responda apenas a partir dos documentos recuperados. Cite o documento de origem "
                "de cada afirmação. Se a resposta não estiver na base, diga que não sabe."
            ),
            retrieval_reasoning_effort=KnowledgeRetrievalLowReasoningEffort(),
        )
        client.create_or_update_knowledge_base(base)
        return {"name": qualified, "source": source_name, "container": container}
    finally:
        with contextlib.suppress(Exception):
            client.close()


@audited("knowledge", "delete")
def delete_knowledge(name: str, *, delete_container: bool = False) -> dict:
    """Apaga a base e depois a fonte. A ordem é o ponto.

    A base referencia a fonte: apagar a fonte primeiro deixa a base apontando para nada, e uma
    base nesse estado responde erro em vez de "não sei" — parece defeito do agente.

    O container NÃO é apagado por default. Apagar índice é reversível (reindexar); apagar os
    documentos originais não é. Quem quiser os arquivos fora pede explicitamente.
    """
    qualified = qualify(name)
    source_name = f"{qualified}-ks"
    done: dict[str, Any] = {"name": qualified, "base": False, "source": False, "container": None}

    client = _index_client()
    try:
        with contextlib.suppress(Exception):
            client.delete_knowledge_base(qualified)
            done["base"] = True
        with contextlib.suppress(Exception):
            client.delete_knowledge_source(source_name)
            done["source"] = True
    finally:
        with contextlib.suppress(Exception):
            client.close()

    if delete_container:
        service = _blob_service()
        try:
            with contextlib.suppress(Exception):
                service.delete_container(_container_for(qualified))
                done["container"] = _container_for(qualified)
        finally:
            with contextlib.suppress(Exception):
                service.close()
    return done
