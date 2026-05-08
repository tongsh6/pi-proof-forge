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

    def build_agent_loop(
        self,
        run_id: str,
        dry_run: bool = False,
        run_store: object | None = None,
        evidence_cards: object | None = None,
        job_profile: object | None = None,
        candidates: object | None = None,
        *,
        llm_client: object | None = None,
        llm_model: str = "",
    ) -> object:
        """Build a fully wired AgentLoop.

        Without llm_client: uses rule-mode engines (fast, deterministic).
        With llm_client: uses hybrid matching + LLM evaluator (semantic).

        Caller provides data inputs (evidence_cards, job_profile, candidates).
        """
        matching_reg = self.build_matching_registry()
        generation_reg = self.build_generation_registry()
        evaluation_reg = self.build_evaluation_registry()
        discovery_reg = self.build_discovery_registry()

        use_llm = llm_client is not None and bool(llm_model)
        if use_llm:
            self.add_llm_strategies(
                llm_client, llm_model,
                self.build_evidence_registry(),
                matching_reg, generation_reg, evaluation_reg,
            )

        matching_engine = matching_reg.create("hybrid" if use_llm else "rule")
        generation_engine = generation_reg.create("template")
        evaluation_engine = evaluation_reg.create("llm" if use_llm else "rule")
        discovery_engine = discovery_reg.create("rule")

        gate_engine = _construct(
            "tools.orchestration.gate_engine", "GateEngine",
            self.policy, run_id, 0,
        )
        review_stage = _construct(
            "tools.orchestration.review_stage", "ReviewStage",
            self.policy,
        )
        state_machine = _construct(
            "tools.orchestration.state_machine", "StateMachine",
        )

        liepin_channel = _construct(
            "tools.channels.liepin", "LiepinChannel",
        )
        email_channel = _construct(
            "tools.channels.email", "EmailChannel",
        )
        channels = [liepin_channel, email_channel]

        agent_loop_cls = cast(
            type[object],
            _load_attr("tools.orchestration.agent_loop", "AgentLoop"),
        )
        return agent_loop_cls(
            policy=self.policy,
            run_id=run_id,
            dry_run=dry_run,
            run_store=run_store,
            matching_engine=matching_engine,
            generation_engine=generation_engine,
            evaluation_engine=evaluation_engine,
            discovery_engine=discovery_engine,
            gate_engine=gate_engine,
            review_stage=review_stage,
            state_machine=state_machine,
            channels=channels,
            evidence_cards=evidence_cards,
            job_profile=job_profile,
            candidates=candidates,
        )

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
        matching_registry.register(
            "hybrid",
            lambda: _construct(
                "tools.engines.matching.hybrid_matcher",
                "HybridMatchingEngine",
                llm_client,
                model,
                5,
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
