# vLLM Benchmark Setup

End-to-end scaffold for benchmarking a vLLM-served model with
[guidellm](https://github.com/vllm-project/guidellm) on Kubernetes /
OpenShift. Renders one vLLM deployment + one guidellm sweep job per
`(input_tokens, output_tokens)` pair in a configurable grid.

The default example targets **`Qwen/Qwen2.5-14B`** on a single GPU.

## What you get

```
.
├── cluster/      # one-time cluster prerequisites
├── templates/    # parameterized vLLM + guidellm manifests
├── scripts/      # generator, deployer, result extractor, csv→json
└── Makefile      # convenience wrappers
```

The default sweep is the 4×4 grid `{64, 256, 1024, 4096}` for prompt
tokens × output tokens — 16 deployments + 16 jobs. Each guidellm job
samples uniformly around the requested average using ±50% bounds (see
*Token sampling* below).

## Prerequisites

- A Kubernetes or OpenShift cluster with at least one node providing
  `nvidia.com/gpu`.
- `kubectl` or `oc` on PATH (the deploy script auto-detects).
- Python 3.9+ (stdlib only — no extra deps).
- A Hugging Face token with access to the model you intend to serve.

## Quick start (Qwen example)

### 1. One-time cluster setup

```sh
# Namespace, model-cache PVC, results PVC, extractor pod
make cluster

# HF token secret — copy the example, fill in your token, then apply
cp cluster/03-hf-secret.yaml.example cluster/03-hf-secret.yaml
$EDITOR cluster/03-hf-secret.yaml          # replace <your-huggingface-token>
make secret
```

`cluster/03-hf-secret.yaml` is gitignored — your filled-in token will
never be committed.

### 2. Generate manifests

```sh
make generate                              # uses Qwen/Qwen2.5-14B by default
# or override:
make generate MODEL=meta-llama/Llama-3.1-8B MAX_MODEL_LEN=131072
```

To narrow the grid for a smoke test, call the script directly:

```sh
python3 scripts/generate_manifests.py \
  --model Qwen/Qwen2.5-14B \
  --input-tokens 64 256 \
  --output-tokens 64 256
```

Output lands in `generated/i<input>-o<output>/{01-deployment, 02-service, 03-sweep-job}.yaml`.

### 3. Deploy

```sh
make deploy
```

The deployer verifies the namespace and HF secret exist, then applies
each combination's manifests in order. Pods will pull the vLLM image
and download model weights on first start (this can take several
minutes for a 14B model).

Watch progress:

```sh
make status
# or
kubectl get pods -l experiment=vllm-sweep -n vllm-test -w
```

### 4. Collect results

guidellm writes CSV / JSON / HTML output to the
`guidellm-results-pvc` PVC under `/results/sweep-i<i>-o<o>/`. The
`pvc-extractor` pod (applied by `make cluster`) keeps the volume
mounted so you can copy it out:

```sh
make extract                               # results land in ./results/
```

Convert any CSV to flat JSON for analysis:

```sh
python3 scripts/csv2json.py results/sweep-i1024-o1024/benchmarks.csv
```

### 5. Tear down

```sh
make clean-cluster                         # delete deployments/services/jobs
make clean-generated                       # remove generated/ locally
```

## Token sampling

We want prompt and output lengths to be **uniformly distributed** across
the configured range — not clustered around the mean — so each cell of
the input/output grid covers its space evenly.

### How guidellm samples

guidellm's synthetic dataset (`SyntheticTextItemsGenerator` in
`dataset/synthetic.py`) initializes both `prompt_tokens_sampler` and
`output_tokens_sampler` with `IntegerRangeSampler`:

```python
class IntegerRangeSampler:
    def __init__(self, average, variance, min_value, max_value, random_seed):
        self.average = average
        self.variance = variance
        self.min_value = min_value
        self.max_value = max_value
        self.rng = random.Random(random_seed)

    def __iter__(self):
        calc_min = self.min_value
        if calc_min is None:
            calc_min = max(
                1, self.average - 5 * self.variance if self.variance else self.average
            )
        calc_max = self.max_value
        if calc_max is None:
            calc_max = (
                self.average + 5 * self.variance if self.variance else self.average
            )

        while True:
            if calc_min == calc_max:
                yield calc_min
            elif not self.variance:
                yield self.rng.randint(calc_min, calc_max)         # uniform
            else:
                rand = self.rng.gauss(self.average, self.variance) # gaussian
                yield round(max(calc_min, min(calc_max, rand)))
```

The `variance` argument (i.e. `prompt_tokens_stdev` / `output_tokens_stdev`
in the guidellm data string) is what selects the distribution:

- **`variance` set** → `rng.gauss(average, variance)` — Gaussian, then
  clipped to `[min_value, max_value]`.
- **`variance` None or 0** → `rng.randint(calc_min, calc_max)` — uniform.

`generate_manifests.py` deliberately omits `prompt_tokens_stdev` /
`output_tokens_stdev`, so the sampler takes the uniform branch.

### Choosing min/max for a uniform target

For a uniform distribution the mean is the midpoint:

$$\mu = \frac{\text{min} + \text{max}}{2} \quad\Longrightarrow\quad \text{min} + \text{max} = 2\mu$$

So for an average of 64 tokens, any pair of bounds summing to 128 will
center the distribution there. The pair you pick determines how much
variability you get:

| Variability | Min | Max | Range (Max − Min + 1) |
| --- | --- | --- | --- |
| Low    | 60 | 68 | 9 tokens  |
| Medium | 48 | 80 | 33 tokens |
| High   | 32 | 96 | 65 tokens |

We pick **high variability** to cover the input/output space rather than
hover near the mean. `generate_manifests.py` implements this with
symmetric ±50% bounds around the requested average:

```
input_min  = avg // 2
input_max  = avg * 1.5    # same for output
```

For `avg = 64`, that yields `[32, 96]` — matching the "High" row above.

## Customizing

Common things you'll want to change:

| Knob | Where |
| --- | --- |
| Model id | `--model` flag, or `MODEL=...` to `make generate` |
| Max context length | `--max-model-len`, or `MAX_MODEL_LEN=...` |
| Sweep grid | `--input-tokens` / `--output-tokens` flags |
| Per-rate runtime | `--max-seconds` (default 600) |
| Sample count | `--samples` (default 10000) |
| Resource requests/limits, GPUs, image | edit `templates/deployment.yaml.template` |
| guidellm profile / outputs | edit `templates/sweep-job.yaml.template` |

The templates use plain `str.format` substitution — placeholders are
written as `{name}` and literal braces as `{{}}`.

## File reference

- `cluster/00-namespace.yaml` — `vllm-test` namespace.
- `cluster/01-models-cache-pvc.yaml` — 100Gi RWX PVC for HF model cache.
- `cluster/02-results-pvc.yaml` — 50Gi RWX PVC for guidellm output.
- `cluster/03-hf-secret.yaml.example` — placeholder; copy and fill in.
- `cluster/99-pvc-extractor.yaml` — utility pod to `kubectl cp` results out.
- `templates/deployment.yaml.template` — vLLM serving deployment.
- `templates/service.yaml.template` — ClusterIP fronting the deployment.
- `templates/sweep-job.yaml.template` — guidellm benchmark Job.
- `scripts/generate_manifests.py` — render templates for the sweep grid.
- `scripts/deploy_experiments.py` — apply manifests to the cluster.
- `scripts/extract_results.sh` — copy results PVC contents locally.
- `scripts/csv2json.py` — flatten guidellm multi-row CSV headers to JSON.
