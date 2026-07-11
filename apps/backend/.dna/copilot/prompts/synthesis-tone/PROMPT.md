---
name: synthesis-tone
description: Coach-Overlay synthesis tone by meeting_type — appended to the synthesis base at call time
variables:
- presentation
- technical
- sales
- interview
tags:
- copilot
- synthesis
- tone
---
{{#presentation}} Tom de negócio: foque benefícios e arquitetura de alto nível.{{/presentation}}{{#technical}} Tom técnico: pode citar detalhes de implementação.{{/technical}}{{#sales}} Tom comercial: foque valor, segurança e escalabilidade.{{/sales}}{{#interview}} Tom conceitual: foque trade-offs e o porquê das decisões.{{/interview}}
