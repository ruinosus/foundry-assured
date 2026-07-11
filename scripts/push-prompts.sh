#!/usr/bin/env bash
# Publish the runtime DNA prompt scope to production (ADR-014, production leg).
#
# Uploads apps/backend/.dna/ to the `assured-prompts` Azure Files share (mounted
# read-only in the backend container app at /mnt/dna, selected via DNA_BASE_DIR)
# and restarts the backend revision so the new prompts compose at boot.
#
# The prod prompt loop — no image build, no `azd deploy`:
#
#   $EDITOR apps/backend/.dna/helpdesk/agents/cockpit.yaml
#   dna eval run helpdesk-prompts --scope helpdesk   # the content gate (CI runs it too)
#   ./scripts/push-prompts.sh                        # upload + revision restart
#
# Restart is the refresh unit (ADR-014): prompts compose at import and agents
# are built at boot — there is deliberately NO hot reload. A backend scaled to
# zero needs no restart at all: the next cold start reads the fresh share.
#
# Honest caveats:
# - `az storage file upload-batch` overwrites but never DELETES: removing or
#   renaming a scope file needs `az storage file delete-batch` (or wiping the
#   share) before the upload — see --mirror.
# - --mirror empties the share first. A cold start during the wipe→upload
#   window boots on the baked-in fallback (scope absent) or fails loudly on a
#   half-uploaded scope and is retried by ACA; the terminal restart settles it.
#
# Reads everything from the azd env (bicep outputs) — run after `azd up`.
set -euo pipefail
cd "$(dirname "$0")/.."

MIRROR=0
RESTART=1
for arg in "$@"; do
  case "$arg" in
    --mirror) MIRROR=1 ;;
    --no-restart) RESTART=0 ;;
    *) echo "usage: $0 [--mirror] [--no-restart]" >&2; exit 2 ;;
  esac
done

VALUES="$(azd env get-values 2>/dev/null)" || { echo "✗ no azd env — run 'azd up' (or 'azd env select') first" >&2; exit 1; }
val() { echo "$VALUES" | sed -n "s/^$1=\"\(.*\)\"\$/\1/p" | head -1; }

SA="$(val AZURE_STORAGE_ACCOUNT)"
SHARE="$(val AZURE_PROMPTS_FILE_SHARE)"
[ -z "$SHARE" ] && SHARE="assured-prompts" # env provisioned before the output existed
RG="rg-$(val AZURE_ENV_NAME)"
[ -z "$SA" ] && { echo "✗ AZURE_STORAGE_ACCOUNT missing from the azd env — provision first" >&2; exit 1; }

# Azure Files access is account-key (the same auth the ACA storage link uses).
KEY="$(az storage account keys list -n "$SA" -g "$RG" --query '[0].value' -o tsv)"

if [ "$MIRROR" = 1 ]; then
  echo "▸ mirroring: emptying share '$SHARE' first (removed/renamed files die here)"
  az storage file delete-batch --account-name "$SA" --account-key "$KEY" --source "$SHARE" >/dev/null
fi

echo "▸ uploading apps/backend/.dna → $SA/$SHARE"
az storage file upload-batch --account-name "$SA" --account-key "$KEY" \
  --destination "$SHARE" --source apps/backend/.dna --no-progress >/dev/null
echo "  ✓ scope uploaded"

if [ "$RESTART" = 1 ]; then
  APP="$(az containerapp list -g "$RG" --query "[?tags.\"azd-service-name\"=='backend'].name | [0]" -o tsv)"
  [ -z "$APP" ] && { echo "✗ backend container app not found in $RG" >&2; exit 1; }
  REV="$(az containerapp revision list -n "$APP" -g "$RG" --query '[0].name' -o tsv)"
  if az containerapp revision restart -n "$APP" -g "$RG" --revision "$REV" >/dev/null 2>&1; then
    echo "  ✓ restarted revision $REV — new prompts compose at boot"
  else
    # scale-to-zero: no running replica to restart; the next cold start reads the share.
    echo "  · could not restart $REV (scaled to zero?) — the next cold start picks the prompts up"
  fi
else
  echo "  · restart skipped (--no-restart) — prompts apply on the next backend boot"
fi
