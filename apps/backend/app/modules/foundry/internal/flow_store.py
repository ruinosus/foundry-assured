"""O fluxo do canvas, guardado no Foundry como Dataset versionado.

POR QUE DATASET, e não a superfície que o nome sugere. O SDK tem `WorkflowAgentDefinition`, com
um campo `workflow` que a docstring chama de "CSDL YAML definition" — parece a casa óbvia, e não
é. Duas descobertas, ambas empíricas:

  1. O serviço VALIDA esse campo e recusa YAML do Agent Framework (`invalid_payload: Invalid
     workflow definition`). O campo espera o formato do designer do portal, que é outro.
  2. Esse formato do portal **aposenta em 2026-12-01**, e a orientação da própria Microsoft é
     migrar para o Agent Framework — onde a definição vive junto da SUA aplicação, não dentro do
     Foundry. Escrever um tradutor para um formato sem schema publicado e com data de morte
     marcada seria trabalho jogado fora duas vezes.

O que sobrou depois disso: `client.datasets`. Um Dataset é recurso de projeto de primeira classe,
versionado, com upload por SAS temporário e leitura por credencial do serviço — exatamente o que
um arquivo de definição precisa, e sem fingir ser outra coisa. Uma skill também guardaria o
arquivo, mas quem abrisse o portal veria uma "skill" que não é skill.

O CICLO, verificado contra o serviço real antes de este arquivo existir:

    pending_upload(nome, versão)   →  container temporário + SAS de escrita
    upload do blob pelo SAS        →  o YAML sobe
    create_or_update(FileDataset)  →  a versão passa a existir no projeto
    get_credentials + download     →  volta byte a byte

Cada gravação é uma VERSÃO nova. Versões não se sobrescrevem, então o histórico do fluxo vem de
graça: dá para ver o que mudou e quando, e o portal mostra o mesmo que a tela.
"""

from __future__ import annotations

import contextlib

from app.modules.foundry.internal.names import qualify

#: O arquivo dentro do dataset. Nome fixo porque o dataset inteiro É um fluxo — não é uma pasta.
_ARQUIVO = "flow.yaml"


def _client():
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    from app.modules.tenancy.public import tenant_config

    return AIProjectClient(
        endpoint=tenant_config().foundry_project_endpoint,
        credential=DefaultAzureCredential(),
        allow_preview=True,
    )


def _latest_version(client, nome: str) -> str | None:
    """A maior versão existente, ou None se o dataset ainda não existe.

    Ordena por NÚMERO, não por texto: com dez versões, a ordem alfabética põe "10" antes de "9" e
    a tela passaria a mostrar um fluxo antigo sem nenhum erro aparecer.
    """
    numeros: list[int] = []
    with contextlib.suppress(Exception):
        for v in client.datasets.list_versions(nome):
            rotulo = getattr(v, "version", None)
            if rotulo is not None and str(rotulo).isdigit():
                numeros.append(int(rotulo))
    return str(max(numeros)) if numeros else None


def save_flow(name: str, yaml_text: str, *, description: str = "") -> dict:
    """Publica o YAML como uma nova versão do dataset. Devolve nome e versão gravados."""
    from azure.ai.projects.models import (
        FileDatasetVersion,
        PendingUploadRequest,
        PendingUploadType,
    )
    from azure.storage.blob import ContainerClient

    qualificado = qualify(name)
    client = _client()
    try:
        anterior = _latest_version(client, qualificado)
        versao = str(int(anterior) + 1) if anterior else "1"

        pendente = client.datasets.pending_upload(
            qualificado,
            versao,
            PendingUploadRequest(pending_upload_type=PendingUploadType.TEMPORARY_BLOB_REFERENCE),
        )
        referencia = pendente.blob_reference
        # O SAS vem SEPARADO do `blob_uri` — o `blob_uri` não carrega token, e usá-lo direto dá
        # `NoAuthenticationInformation`. A escrita é sempre pelo `credential.sas_uri`.
        ContainerClient.from_container_url(referencia.credential.sas_uri).upload_blob(
            _ARQUIVO, yaml_text.encode("utf-8"), overwrite=True
        )

        # `:443` explícito na URI que o serviço devolve; o `data_uri` registrado fica sem ele para
        # bater com o que o portal mostra.
        destino = str(referencia.blob_uri).replace(":443", "").rstrip("/") + f"/{_ARQUIVO}"
        client.datasets.create_or_update(
            qualificado,
            versao,
            FileDatasetVersion(data_uri=destino, description=description or None),
        )
        return {
            "name": qualificado,
            "version": versao,
            "bytes": len(yaml_text.encode("utf-8")),
        }
    finally:
        with contextlib.suppress(Exception):
            client.close()


def load_flow(name: str, version: str = "") -> str | None:
    """O YAML da versão pedida (ou da mais recente), ou None se não houver fluxo publicado.

    Ausência não é erro: um caso de uso que nunca foi editado no canvas simplesmente não tem
    dataset, e o chamador cai no fluxo que veio no repositório.
    """
    from azure.storage.blob import BlobClient

    qualificado = qualify(name)
    client = _client()
    try:
        alvo = version or _latest_version(client, qualificado)
        if not alvo:
            return None

        registro = client.datasets.get(qualificado, alvo)
        credencial = client.datasets.get_credentials(qualificado, alvo)
        sas = credencial.blob_reference.credential.sas_uri
        base, query = sas.split("?", 1)

        # O nome do blob sai do `data_uri` gravado, não de `_ARQUIVO`: se uma versão antiga tiver
        # sido escrita com outro nome, ela continua legível.
        caminho = str(getattr(registro, "data_uri", "") or "").split("?")[0]
        blob = caminho.rsplit("/", 1)[-1] or _ARQUIVO

        conteudo = (
            BlobClient.from_blob_url(f"{base.rstrip('/')}/{blob}?{query}")
            .download_blob()
            .readall()
        )
        return conteudo.decode("utf-8") or None
    except Exception:  # noqa: BLE001 — fluxo ausente ou ilegível cai no do repositório
        return None
    finally:
        with contextlib.suppress(Exception):
            client.close()
