#!/usr/bin/env bash
# Copy guidellm benchmark results out of the in-cluster PVC.
#
# Usage:
#   scripts/extract_results.sh [namespace] [destination]
#
# Defaults to namespace=vllm-test, destination=./results.
# Requires a 'pvc-extractor' pod attached to the results PVC
# (see cluster/99-pvc-extractor.yaml).

set -euo pipefail

NAMESPACE="${1:-vllm-test}"
DEST="${2:-./results}"
POD="pvc-extractor"

if command -v oc >/dev/null 2>&1; then
  CLI=oc
else
  CLI=kubectl
fi

echo "Using $CLI"
echo "Namespace: $NAMESPACE"
echo "Destination: $DEST"

if ! "$CLI" get pod "$POD" -n "$NAMESPACE" >/dev/null 2>&1; then
  echo "Pod '$POD' not found in '$NAMESPACE'."
  echo "Apply cluster/99-pvc-extractor.yaml first."
  exit 1
fi

mkdir -p "$DEST"
"$CLI" cp "$NAMESPACE/$POD:/mnt/pvc" "$DEST"
echo "Copied PVC contents to $DEST"
