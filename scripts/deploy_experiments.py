#!/usr/bin/env python3
"""Apply generated benchmark manifests to a Kubernetes / OpenShift cluster.

Walks ``generated/i*-o*/`` directories in order and applies each manifest
file with ``oc apply`` (or ``kubectl apply`` if ``oc`` is not on PATH).
Verifies the namespace and the ``hf-token-secret`` exist before deploying.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List


class ExperimentDeployer:
    def __init__(self, manifests_dir: Path, namespace: str):
        self.manifests_dir = manifests_dir
        self.namespace = namespace
        self.cli = "oc" if shutil.which("oc") else "kubectl"

        if not self.manifests_dir.exists():
            sys.exit(
                f"Manifests directory not found: {self.manifests_dir}\n"
                "Run scripts/generate_manifests.py first."
            )
        print(f"Using cluster CLI: {self.cli}")

    def _run(self, args: List[str], check: bool = True) -> subprocess.CompletedProcess:
        cmd = [self.cli, *args]
        print(f"  $ {' '.join(cmd)}")
        return subprocess.run(cmd, capture_output=True, text=True, check=check)

    def verify_namespace(self) -> None:
        try:
            self._run(["get", "namespace", self.namespace])
        except subprocess.CalledProcessError:
            sys.exit(
                f"Namespace '{self.namespace}' not found. "
                f"Apply cluster/00-namespace.yaml first."
            )

    def verify_secret(self, secret_name: str = "hf-token-secret") -> None:
        try:
            self._run(["get", "secret", secret_name, "-n", self.namespace])
        except subprocess.CalledProcessError:
            sys.exit(
                f"Secret '{secret_name}' not found in namespace '{self.namespace}'.\n"
                "Copy cluster/03-hf-secret.yaml.example, fill in your token, then apply it."
            )

    def find_combinations(self) -> List[Path]:
        return sorted(d for d in self.manifests_dir.iterdir() if d.is_dir() and d.name.startswith("i"))

    def deploy_combination(self, combo_dir: Path) -> bool:
        print(f"\nDeploying {combo_dir.name}")
        ok = True
        for manifest in sorted(combo_dir.glob("*.yaml")):
            try:
                self._run(["apply", "-f", str(manifest), "-n", self.namespace])
            except subprocess.CalledProcessError as e:
                print(f"  failed: {manifest.name}\n{e.stderr}", file=sys.stderr)
                ok = False
        return ok

    def show_status(self) -> None:
        print("\nDeployments:")
        self._run(["get", "deployments", "-l", "experiment=vllm-sweep", "-n", self.namespace], check=False)
        print("\nJobs:")
        self._run(["get", "jobs", "-l", "experiment=vllm-sweep", "-n", self.namespace], check=False)
        print("\nPods:")
        self._run(["get", "pods", "-l", "experiment=vllm-sweep", "-n", self.namespace], check=False)

    def deploy_all(self) -> None:
        self.verify_namespace()
        self.verify_secret()

        combos = self.find_combinations()
        if not combos:
            sys.exit(f"No combinations found in {self.manifests_dir}")

        print(f"Found {len(combos)} combinations")
        success = sum(1 for c in combos if self.deploy_combination(c))
        print(f"\n{success}/{len(combos)} combinations applied successfully")

        self.show_status()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifests-dir", type=Path, default=Path("generated"))
    p.add_argument("--namespace", default="vllm-test")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    ExperimentDeployer(args.manifests_dir, args.namespace).deploy_all()


if __name__ == "__main__":
    main()
