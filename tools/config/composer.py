from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Protocol, cast

from tools.config.fragments import PolicyConfig
from tools.config.loader import load_policy_config
from tools.config.validator import validate_policy_config
from tools.infra.llm.client import LLMClient


def _load_attr(module_name: str, attr_name: str) -> object:
    module = import_module(module_name)
    return getattr(module, attr_name)


def _construct(
    module_name: str, class_name: str, *args: object, **kwargs: object
) -> object:
    klass = cast(type[object], _load_attr(module_name, class_name))
    return klass(*args, **kwargs)


class _RegistryLike(Protocol):
    def register(self, strategy: str, factory: object) -> None: ...

    def list(self) -> tuple[str, ...]: ...

    def create(self, strategy: str) -> object: ...


def _new_registry() -> _RegistryLike:
    registry_cls = cast(
        type[_RegistryLike], _load_attr("tools.engines.registry", "EngineRegistry")
    )
    return registry_cls()


@dataclass(frozen=True)
class Composer:
    policy: PolicyConfig

    @classmethod
    def from_policy_path(cls, policy_path: str) -> "Composer":
        policy = load_policy_config(policy_path)
        validate_policy_config(policy)
        return cls(policy=policy)

    def build_evidence_registry(self) -> _RegistryLike:
        registry = _new_registry()
        registry.register(
            "rule",
            lambda: _construct(
                "tools.engines.evidence.rule_extractor", "RuleEvidenceExtractor"
            ),
        )
        return registry

    def build_matching_registry(self) -> _RegistryLike:
        registry = _new_registry()
        registry.register(
            "rule",
            lambda: _construct(
                "tools.engines.matching.rule_scorer", "RuleMatchingEngine"
            ),
        )
        return registry

    def build_generation_registry(self) -> _RegistryLike:
        registry = _new_registry()
        registry.register(
            "template",
            lambda: _construct(
                "tools.engines.generation.template_assembler", "TemplateAssembler"
            ),
        )
        return registry

    def build_evaluation_registry(self) -> _RegistryLike:
        registry = _new_registry()
        registry.register(
            "rule",
            lambda: _construct(
                "tools.engines.evaluation.rule_evaluator", "RuleEvaluationEngine"
            ),
        )
        return registry

    def build_discovery_registry(self) -> _RegistryLike:
        registry = _new_registry()
        registry.register(
            "rule",
            lambda: _construct(
                "tools.engines.discovery.discovery_engine",
                "DiscoveryEngine",
                self.policy,
            ),
        )
        return registry

    def add_llm_strategies(
        self,
        llm_client: LLMClient,
        model: str,
        evidence_registry: _RegistryLike,
        matching_registry: _RegistryLike,
        generation_registry: _RegistryLike,
        evaluation_registry: _RegistryLike,
    ) -> None:
        evidence_registry.register(
            "llm",
            lambda: _construct(
                "tools.engines.evidence.llm_extractor",
                "LLMEvidenceExtractor",
                llm_client,
                model,
            ),
        )
        matching_registry.register(
            "llm",
            lambda: _construct(
                "tools.engines.matching.llm_matcher",
                "LLMMatchingEngine",
                llm_client,
                model,
            ),
        )
        generation_registry.register(
            "llm",
            lambda: _construct(
                "tools.engines.generation.llm_rewriter",
                "LLMRewriter",
                llm_client,
                model,
            ),
        )
        evaluation_registry.register(
            "llm",
            lambda: _construct(
                "tools.engines.evaluation.llm_evaluator",
                "LLMEvaluationEngine",
                llm_client,
                model,
            ),
        )
