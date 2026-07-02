#!/usr/bin/env bash
# Build the Azure Managed Application marketplace package.
#
# Produces:
#   mainTemplate.json   — ARM JSON compiled from managedApp.bicep (the required
#                         root deployment template for a Managed Application).
#   managed-app.zip      — the marketplace artifact: mainTemplate.json +
#                         createUiDefinition.json zipped flat (-j, no dir paths),
#                         as required by Partner Center.
#
# Prereqs: Azure CLI with the Bicep extension (`az bicep version`), and `zip`.
# Publishing the resulting zip to a Partner Center offer is infra-gated — see
# docs/D-PACKAGING-RUNBOOK.md.

set -euo pipefail

cd "$(dirname "$0")"

echo "==> Compiling managedApp.bicep -> mainTemplate.json"
az bicep build --file managedApp.bicep --outfile mainTemplate.json

echo "==> Packaging managed-app.zip (mainTemplate.json + createUiDefinition.json)"
rm -f managed-app.zip
zip -j managed-app.zip mainTemplate.json createUiDefinition.json

echo "==> Done. Artifact: $(pwd)/managed-app.zip"
