#!/usr/bin/env python3
"""Generate Kubernetes manifests for a vLLM input/output token sweep.

For each (input_tokens, output_tokens) pair in the configured grid this
script renders three manifests from the templates in ``templates/``:

  * ``01-deployment.yaml`` - vLLM serving deployment
  * ``02-service.yaml``    - ClusterIP service in front of the deployment
  * ``03-sweep-job.yaml``  - guidellm benchmark Job that drives the deployment

The min/max prompt and output token bounds are computed symmetrically around
the requested average so that guidellm samples uniformly (see README).
"""

import argparse
from pathlib import Path
from typing import Dict, List, Tuple


DEFAULT_MODEL = "Qwen/Qwen2.5-14B"
DEFAULT_MAX_MODEL_LEN = 16384
DEFAULT_NAMESPACE = "vllm-test"
DEFAULT_TOKEN_GRID = [64, 256, 1024, 4096]
DEFAULT_MAX_SECONDS = 600
DEFAULT_SAMPLES = 10000
DEFAULT_SEED = 42


class ManifestGenerator:
    def __init__(
        self,
        template_dir: Path,
        output_dir: Path,
        namespace: str,
        model: str,
        max_model_len: int,
        max_seconds: int,
        samples: int,
        seed: int,
    ):
        self.template_dir = template_dir
        self.output_dir = output_dir
        self.namespace = namespace
        self.model = model
        self.max_model_len = max_model_len
        self.max_seconds = max_seconds
        self.samples = samples
        self.seed = seed

    @staticmethod
    def token_range(avg: int) -> Tuple[int, int]:
        # Symmetric +/-50% range -> uniform sampling around the average.
        return avg // 2, int(avg * 1.5)

    def _load(self, name: str) -> str:
        return (self.template_dir / name).read_text()

    @staticmethod
    def _render(template: str, values: Dict) -> str:
        return template.format(**values)

    def _common_values(self, i: int, o: int) -> Dict:
        suffix = f"i{i}-o{o}"
        return {
            "name": f"vllm-{suffix}",
            "namespace": self.namespace,
            "app_label": f"vllm-{suffix}",
        }

    def deployment(self, i: int, o: int) -> str:
        values = self._common_values(i, o)
        values.update({
            "model": self.model,
            "max_model_len": self.max_model_len,
        })
        return self._render(self._load("deployment.yaml.template"), values)

    def service(self, i: int, o: int) -> str:
        return self._render(self._load("service.yaml.template"), self._common_values(i, o))

    def sweep_job(self, i: int, o: int) -> str:
        i_min, i_max = self.token_range(i)
        o_min, o_max = self.token_range(o)
        suffix = f"i{i}-o{o}"
        values = {
            "name": f"sweep-{suffix}",
            "namespace": self.namespace,
            "app_label": f"vllm-{suffix}",
            "vllm_service": f"http://vllm-{suffix}:8000",
            "input_tokens": i,
            "input_min": i_min,
            "input_max": i_max,
            "output_tokens": o,
            "output_min": o_min,
            "output_max": o_max,
            "output_file": f"sweep-{suffix}",
            "max_seconds": self.max_seconds,
            "samples": self.samples,
            "seed": self.seed,
        }
        return self._render(self._load("sweep-job.yaml.template"), values)

    def write_combination(self, i: int, o: int) -> None:
        combo_dir = self.output_dir / f"i{i}-o{o}"
        combo_dir.mkdir(parents=True, exist_ok=True)

        (combo_dir / "01-deployment.yaml").write_text(self.deployment(i, o))
        (combo_dir / "02-service.yaml").write_text(self.service(i, o))
        (combo_dir / "03-sweep-job.yaml").write_text(self.sweep_job(i, o))
        print(f"  generated {combo_dir}")

    def write_all(self, combinations: List[Tuple[int, int]]) -> None:
        print(f"Generating {len(combinations)} combinations into {self.output_dir}")
        for i, o in combinations:
            self.write_combination(i, o)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--template-dir", type=Path, default=Path(__file__).parent.parent / "templates")
    p.add_argument("--output-dir", type=Path, default=Path("generated"))
    p.add_argument("--namespace", default=DEFAULT_NAMESPACE)
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help=f"Hugging Face model id (default: {DEFAULT_MODEL})")
    p.add_argument("--max-model-len", type=int, default=DEFAULT_MAX_MODEL_LEN)
    p.add_argument("--max-seconds", type=int, default=DEFAULT_MAX_SECONDS,
                   help="guidellm max-seconds per rate point")
    p.add_argument("--samples", type=int, default=DEFAULT_SAMPLES)
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--input-tokens", type=int, nargs="+", default=DEFAULT_TOKEN_GRID)
    p.add_argument("--output-tokens", type=int, nargs="+", default=DEFAULT_TOKEN_GRID)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    combinations = [(i, o) for i in args.input_tokens for o in args.output_tokens]

    generator = ManifestGenerator(
        template_dir=args.template_dir,
        output_dir=args.output_dir,
        namespace=args.namespace,
        model=args.model,
        max_model_len=args.max_model_len,
        max_seconds=args.max_seconds,
        samples=args.samples,
        seed=args.seed,
    )
    generator.write_all(combinations)
    print(f"Done. Review manifests under {args.output_dir}/, then run scripts/deploy_experiments.py")


if __name__ == "__main__":
    main()
