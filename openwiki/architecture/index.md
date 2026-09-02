# Files

- [Domain catalog, routing kinds, and frontend/backend parity](domain-catalog-and-routing.md) - How the product defines assistant domains once in the backend catalog, mounts live endpoints by kind, and mirrors the same domain ids and kinds into the frontend registry and navigation surfaces.
- [Repository Architecture Overview](overview.md) - Whole-repository map of Foundry Assured: applications, runtime seams, deployment modes, state owners, and the workflows that connect frontend, backend, hosted agents, infrastructure, and evaluation.
- [Runtime topology across backend, frontend, MCP, and infra](runtime-topology.md) - How the deployed system is split between the FastAPI backend monolith, the Next.js frontend, and the separate FastMCP server, and how shared catalogs and composition roots keep those surfaces aligned.
