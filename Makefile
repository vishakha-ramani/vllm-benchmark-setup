NAMESPACE ?= vllm-test
MODEL ?= Qwen/Qwen2.5-14B
MAX_MODEL_LEN ?= 16384
GENERATED_DIR ?= generated
RESULTS_DIR ?= results

.PHONY: help cluster generate deploy status extract clean-generated clean-cluster

help:
	@echo "Targets:"
	@echo "  cluster          Apply namespace, PVCs, and extractor pod"
	@echo "  secret           Apply your filled-in HF token secret (cluster/03-hf-secret.yaml)"
	@echo "  generate         Render manifests for the input/output token sweep"
	@echo "  deploy           Apply all generated manifests"
	@echo "  status           Show deployments / jobs / pods for the sweep"
	@echo "  extract          Copy benchmark results out of the PVC"
	@echo "  clean-generated  Remove $(GENERATED_DIR)/"
	@echo "  clean-cluster    Delete sweep deployments, services and jobs"

cluster:
	kubectl apply -f cluster/00-namespace.yaml
	kubectl apply -f cluster/01-models-cache-pvc.yaml
	kubectl apply -f cluster/02-results-pvc.yaml
	kubectl apply -f cluster/99-pvc-extractor.yaml

secret:
	kubectl apply -f cluster/03-hf-secret.yaml

generate:
	python3 scripts/generate_manifests.py \
		--model "$(MODEL)" \
		--max-model-len $(MAX_MODEL_LEN) \
		--namespace $(NAMESPACE) \
		--output-dir $(GENERATED_DIR)

deploy:
	python3 scripts/deploy_experiments.py \
		--manifests-dir $(GENERATED_DIR) \
		--namespace $(NAMESPACE)

status:
	kubectl get deployments,jobs,pods -l experiment=vllm-sweep -n $(NAMESPACE)

extract:
	bash scripts/extract_results.sh $(NAMESPACE) $(RESULTS_DIR)

clean-generated:
	rm -rf $(GENERATED_DIR)

clean-cluster:
	kubectl delete deployments,services,jobs -l experiment=vllm-sweep -n $(NAMESPACE)
