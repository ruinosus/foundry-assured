# Hosted-agent container (built remotely by ACR — remoteBuild: true in azure.yaml).
# Mirrors the official agent-framework foundry-hosted-agents sample. Serves the
# Responses protocol on 8088 via ResponsesHostServer (started by main.py).
FROM python:3.12-slim

# ── Runtime .NET, para as expressões Power Fx dos workflows declarativos ────────────────────
#
# POR QUE UM RUNTIME .NET NUMA IMAGEM PYTHON. A linguagem declarativa de workflow do Agent
# Framework usa Power Fx nas expressões (`=Local.Triagem`), e o avaliador de Power Fx é .NET: o
# pacote `powerfx` traz as DLLs (Microsoft.PowerFx.Interpreter.dll) e as carrega por
# pythonnet/clr-loader, que exigem um runtime instalado. Sem ele as DLLs não sobem.
#
# E A FALHA É SILENCIOSA — foi assim que descobrimos. Um fluxo com expressão Power Fx num
# ambiente sem .NET NÃO dá erro: ele simplesmente nunca responde. O mesmo fluxo sem expressões
# executa inteiro. Ninguém investigaria o runtime .NET ao ver "o assistente não responde", e é
# por isso que esta camada existe aqui e não numa nota de instalação.
#
# `--runtime dotnet` instala só o runtime (não o SDK): o container executa DLLs prontas, não
# compila nada. `--channel 8.0` é a versão que o `powerfx` desta trava pede; subir de canal exige
# verificar que o clr-loader acompanha (ele tem patch próprio para maiores de dois dígitos).
ENV DOTNET_ROOT=/usr/share/dotnet
ENV PATH="${PATH}:${DOTNET_ROOT}"
# Telemetria da CLI desligada: o container não é ambiente de desenvolvimento, e o ping de
# primeira execução só adiciona latência ao cold start.
ENV DOTNET_CLI_TELEMETRY_OPTOUT=1
ENV DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1

RUN set -eux; \
    apt-get update; \
    # `libicu-dev` e não `libicu72`: o número da versão amarra à release do Debian, muda quando
    # a imagem base muda, e quebra o build com "Unable to locate package" — sem dizer por quê.
    # Aconteceu na primeira tentativa. O nome sem número resolve para o que a distro tiver.
    apt-get install -y --no-install-recommends curl ca-certificates libicu-dev; \
    curl -fsSL https://dot.net/v1/dotnet-install.sh -o /tmp/dotnet-install.sh; \
    chmod +x /tmp/dotnet-install.sh; \
    /tmp/dotnet-install.sh --channel 8.0 --runtime dotnet --install-dir "${DOTNET_ROOT}" --no-path; \
    rm -f /tmp/dotnet-install.sh; \
    apt-get purge -y --auto-remove curl; \
    rm -rf /var/lib/apt/lists/*; \
    # Falha o BUILD se o runtime não subiu — melhor que descobrir em produção, onde o sintoma
    # seria um agente mudo. `libicu` é dependência do .NET em Debian slim; sem ela o dotnet
    # instala e não roda.
    "${DOTNET_ROOT}/dotnet" --list-runtimes | grep -q "Microsoft.NETCore.App 8\."

WORKDIR /app

COPY . user_agent/
WORKDIR /app/user_agent

RUN if [ -f requirements.txt ]; then \
        pip install --no-cache-dir -r requirements.txt; \
    else \
        echo "No requirements.txt found"; \
    fi

EXPOSE 8088

CMD ["python", "main.py"]
