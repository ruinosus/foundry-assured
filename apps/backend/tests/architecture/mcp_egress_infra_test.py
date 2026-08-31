"""F03: o backend de discovery deve estar atrás do NSG de egress."""

from __future__ import annotations

import sys
from pathlib import Path

import app as _app

REPO_ROOT = Path(_app.__file__).resolve().parents[3]
BICEP_FILE = REPO_ROOT / "infra" / "containerapps.bicep"
REQUIRED_DENIALS = (
    "'10.0.0.0/8'",
    "'127.0.0.0/8'",
    "'169.254.0.0/16'",
    "'172.16.0.0/12'",
    "'192.168.0.0/16'",
    "'224.0.0.0/4'",
    "'240.0.0.0/4'",
    "'::1/128'",
    "'fc00::/7'",
    "'fe80::/10'",
    "'ff00::/8'",
)


def main() -> int:
    text = BICEP_FILE.read_text()
    requirements = {
        "NSG de discovery existe": "resource discoveryNsg 'Microsoft.Network/networkSecurityGroups@" in text,
        "regra de egress é deny": "name: 'deny-non-public-egress'" in text
        and "direction: 'Outbound'" in text
        and "access: 'Deny'" in text,
        "subnet referencia o NSG": "id: discoveryNsg.id" in text,
        "ambiente referencia a subnet": "infrastructureSubnetId: discoveryVnet.properties.subnets[0].id" in text,
        "backend usa ambiente protegido": "managedEnvironmentId: backendEnv.id" in text,
        "classes não públicas são negadas": all(prefix in text for prefix in REQUIRED_DENIALS),
    }
    failures = [name for name, passed in requirements.items() if not passed]
    for name, passed in requirements.items():
        print(f"  {'✓' if passed else '✗'} {name}")
    print(f"\n{'❌' if failures else '✅'} {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
