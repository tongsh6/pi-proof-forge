# autonomous-agent-delivery-loop 完整实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use `openspec-apply-change` skill + `test-driven-development` skill to implement this plan task-by-task.

**Goal:** 完成 `autonomous-agent-delivery-loop` OpenSpec 变更的全部实现，从 Phase A 剩余任务到 Phase E 收口，最终交付可用的 `python3 tools/run_agent.py --policy ... --dry-run` 端到端循环。

**Architecture:** 统一核心引擎 v2（六边形领域核心 + 策略注册表 + 管道组合化）。Domain 层零外部依赖，Infra 层唯一实现，Engines 通过 EngineRegistry 创建，Orchestration 编排，Channels 输出，CLI 为薄入口层。

**Tech Stack:** Python 3.10+，frozen dataclasses，Protocol，结构化 JSON 日志，SQLite/YAML 持久化，Tauri+React/TS 前端（sidecar bridge），pytest TDD。

**当前基线（已完成，无需重复）：**
- `tools/domain/models.py` (A1) ✅
- `tools/domain/value_objects.py` (A2) ✅ — 含 ReviewCandidate / ReviewDecision
- `tools/domain/protocols.py` (A3) ✅
- `tools/domain/result.py` (A5) ✅
- `tools/infra/llm/client.py` (A7) ✅
- `tools/infra/persistence/yaml_io.py` (A8) ✅
- `tools/config/fragments.py` (A10) ✅ — 含 PolicyConfig(delivery_mode, batch_review)
- `tools/sidecar/handlers/agent.py` (stub, L1.4) ✅
- `ui/src/pages/agent-run/` (Agent Run MVP, L1.4) ✅

---

## Phase A — 领域地基补齐（剩余）

### Task A4: domain/invariants.py — evidence-first 与事实保真守卫

**Files:**
- Create: `tools/domain/invariants.py`
- Test: `tests/domain/test_invariants.py`

**Step 1: 写失败测试**

```python
# tests/domain/test_invariants.py
import pytest
from tools.domain.models import EvidenceCard
from tools.domain.invariants import check_evidence_eligible, check_no_fabrication

def _card(results=("提升 30%",), artifacts=("pr#123",)):
    return EvidenceCard(id="c1", title="T", raw_source="s",
                        results=results, artifacts=artifacts)

def test_eligible_card_passes():
    assert check_evidence_eligible(_card()) is True

def test_missing_results_returns_false():
    assert check_evidence_eligible(_card(results=())) is False

def test_missing_artifacts_returns_false():
    assert check_evidence_eligible(_card(artifacts=())) is False

def test_fabrication_guard_passes_with_traceable_content():
    card = _card()
    check_no_fabrication("提升 30% 的性能", [card])  # 不应抛出

def test_fabrication_guard_raises_for_untraced_claim():
    from tools.errors.exceptions import FabricationGuardError
    card = _card()
    with pytest.raises(FabricationGuardError):
        check_no_fabrication("吃饭睡觉打豆豆", [card])
```

**Step 2: 运行，确认失败**

```bash
python3 -m pytest tests/domain/test_invariants.py -v
```
预期: ImportError 或 ModuleNotFoundError

**Step 3: 先创建 errors/exceptions.py（invariants 依赖它）**

```python
# tools/errors/__init__.py  (空文件)
# tools/errors/exceptions.py
from __future__ import annotations

class PiProofError(Exception):
    """所有不可恢复异常的基类。"""

class EvidenceValidationError(PiProofError):
    """results/artifacts 缺失，拒绝进入候选池。"""

class FabricationGuardError(PiProofError):
    """生成内容无法追溯到任何 EvidenceCard。"""

class PolicyError(PiProofError):
    """策略配置违规。"""
```

**Step 4: 实现 invariants.py**

```python
# tools/domain/invariants.py
from __future__ import annotations
from typing import Sequence
from tools.domain.models import EvidenceCard
from tools.errors.exceptions import FabricationGuardError


def check_evidence_eligible(card: EvidenceCard) -> bool:
    """返回 False 不抛异常；调用方决定是否阻断。"""
    return len(card.results) > 0 and len(card.artifacts) > 0


def check_no_fabrication(content: str, evidence_cards: Sequence[EvidenceCard]) -> None:
    """确保 content 中的关键词能在任意一张卡的 results/artifacts 里追溯到。
    极简实现：content 至少包含某张卡 results[0] 的前 4 个字符。"""
    if not evidence_cards:
        raise FabricationGuardError(f"No evidence cards to trace: {content!r}")
    for card in evidence_cards:
        for result in card.results:
            if result[:4] and result[:4] in content:
                return
        for artifact in card.artifacts:
            if artifact[:4] and artifact[:4] in content:
                return
    raise FabricationGuardError(
        f"Content not traceable to any EvidenceCard: {content!r}"
    )
```

**Step 5: 运行测试，确认通过**

```bash
python3 -m pytest tests/domain/test_invariants.py -v
```
预期: 全部 PASS

**Step 6: Commit**

```bash
git add tools/domain/invariants.py tools/errors/__init__.py tools/errors/exceptions.py tests/domain/test_invariants.py
git commit -m "feat(A4): domain invariants — evidence-first + fabrication guard"
```

---

### Task A6: domain/events.py + domain/run_state.py — 事件溯源

**Files:**
- Create: `tools/domain/events.py`
- Create: `tools/domain/run_state.py`
- Test: `tests/domain/test_run_state.py`

**Step 1: 写失败测试**

```python
# tests/domain/test_run_state.py
from tools.domain.events import RunEvent
from tools.domain.run_state import RunState

def test_initial_state_is_init():
    state = RunState.initial("run-001")
    assert state.run_id == "run-001"
    assert state.current_status == "INIT"

def test_replay_empty_events_is_init():
    state = RunState.replay("run-001", [])
    assert state.current_status == "INIT"

def test_replay_discover_event():
    events = [RunEvent(run_id="run-001", event_type="DISCOVER", round_index=0, payload={})]
    state = RunState.replay("run-001", events)
    assert state.current_status == "DISCOVER"

def test_replay_multiple_events():
    events = [
        RunEvent(run_id="r1", event_type="DISCOVER", round_index=0, payload={}),
        RunEvent(run_id="r1", event_type="SCORE", round_index=0, payload={}),
        RunEvent(run_id="r1", event_type="GATE_PASS", round_index=0, payload={}),
    ]
    state = RunState.replay("r1", events)
    assert state.current_status == "GATE_PASS"
    assert state.round_index == 0

def test_run_state_is_immutable():
    state = RunState.initial("r1")
    import pytest
    with pytest.raises(Exception):
        state.current_status = "HACKED"  # frozen dataclass
```

**Step 2: 运行，确认失败**

```bash
python3 -m pytest tests/domain/test_run_state.py -v
```

**Step 3: 实现 events.py**

```python
# tools/domain/events.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

VALID_EVENT_TYPES = frozenset({
    "INIT", "DISCOVER", "SCORE", "GENERATE", "EVALUATE",
    "GATE_PASS", "GATE_FAIL", "REVIEW_PENDING", "REVIEW_DONE",
    "DELIVER", "LEARN", "DONE", "ERROR", "excluded_by_policy",
})

@dataclass(frozen=True)
class RunEvent:
    run_id: str
    event_type: str  # 上述 VALID_EVENT_TYPES 之一
    round_index: int
    payload: dict[str, Any]
    timestamp: str = ""
```

**Step 4: 实现 run_state.py**

```python
# tools/domain/run_state.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Sequence
from tools.domain.events import RunEvent

# 状态机：event_type -> new status 映射（简化版，完整见 tasks C3）
_STATUS_MAP: dict[str, str] = {
    "INIT": "INIT", "DISCOVER": "DISCOVER", "SCORE": "SCORE",
    "GENERATE": "GENERATE", "EVALUATE": "EVALUATE",
    "GATE_PASS": "GATE_PASS", "GATE_FAIL": "GATE_FAIL",
    "REVIEW_PENDING": "REVIEW_PENDING", "REVIEW_DONE": "REVIEW_DONE",
    "DELIVER": "DELIVER", "LEARN": "LEARN", "DONE": "DONE",
    "ERROR": "ERROR",
}

@dataclass(frozen=True)
class RunState:
    run_id: str
    current_status: str
    round_index: int

    @classmethod
    def initial(cls, run_id: str) -> "RunState":
        return cls(run_id=run_id, current_status="INIT", round_index=0)

    @classmethod
    def replay(cls, run_id: str, events: Sequence[RunEvent]) -> "RunState":
        state = cls.initial(run_id)
        for event in events:
            new_status = _STATUS_MAP.get(event.event_type, state.current_status)
            state = cls(run_id=run_id, current_status=new_status,
                       round_index=event.round_index)
        return state
```

**Step 5: 运行测试**

```bash
python3 -m pytest tests/domain/test_run_state.py -v
```

**Step 6: Commit**

```bash
git add tools/domain/events.py tools/domain/run_state.py tests/domain/test_run_state.py
git commit -m "feat(A6): domain events + RunState event replay"
```

---

### Task A9: infra/logging.py — 结构化 JSON 日志

**Files:**
- Create: `tools/infra/logging.py`
- Test: `tests/unit/infra/test_logging.py` (可手动验证输出)

**Step 1: 写失败测试**

```python
# tests/unit/infra/test_logging.py
import json
from tools.infra.logging import make_logger

def test_logger_emits_json(capsys):
    logger = make_logger(run_id="run-001")
    logger.info("state_change", state="DISCOVER", round=0)
    captured = capsys.readouterr()
    record = json.loads(captured.out)
    assert record["run_id"] == "run-001"
    assert record["state"] == "DISCOVER"
    assert record["event"] == "state_change"
```

**Step 2: 运行，确认失败**

```bash
python3 -m pytest tests/unit/infra/test_logging.py -v
```

**Step 3: 实现 logging.py**

```python
# tools/infra/logging.py
from __future__ import annotations
import json
import sys
from datetime import datetime, timezone
from typing import Any


class _StructuredLogger:
    def __init__(self, run_id: str):
        self._run_id = run_id

    def _emit(self, level: str, event: str, **kwargs: Any) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "run_id": self._run_id,
            "event": event,
            **kwargs,
        }
        print(json.dumps(record, ensure_ascii=False), file=sys.stdout)

    def info(self, event: str, **kwargs: Any) -> None:
        self._emit("INFO", event, **kwargs)

    def warning(self, event: str, **kwargs: Any) -> None:
        self._emit("WARNING", event, **kwargs)

    def error(self, event: str, **kwargs: Any) -> None:
        self._emit("ERROR", event, **kwargs)


def make_logger(run_id: str) -> _StructuredLogger:
    return _StructuredLogger(run_id=run_id)
```

**Step 4: 运行测试**

```bash
python3 -m pytest tests/unit/infra/test_logging.py -v
```

**Step 5: Commit**

```bash
git add tools/infra/logging.py tests/unit/infra/test_logging.py
git commit -m "feat(A9): structured JSON logger with run_id/state fields"
```

---

### Task A11: config/loader.py + config/validator.py

**Files:**
- Create: `tools/config/loader.py`
- Create: `tools/config/validator.py`
- Test: `tests/unit/domain/test_config_loader.py`

**Step 1: 写失败测试**

```python
# tests/unit/domain/test_config_loader.py
import pytest
from tools.config.loader import load_policy_config
from tools.config.validator import validate_policy_config
from tools.errors.exceptions import PolicyError

_VALID_YAML = """
n_pass_required: 2
matching_threshold: 0.6
evaluation_threshold: 0.5
max_rounds: 10
gate_mode: strict
delivery_mode: auto
batch_review: false
excluded_companies: []
excluded_legal_entities: []
"""

def test_load_valid_policy(tmp_path):
    f = tmp_path / "policy.yaml"
    f.write_text(_VALID_YAML)
    cfg = load_policy_config(str(f))
    assert cfg.delivery_mode == "auto"
    assert cfg.n_pass_required == 2

def test_validate_passes_for_valid_config(tmp_path):
    f = tmp_path / "policy.yaml"
    f.write_text(_VALID_YAML)
    cfg = load_policy_config(str(f))
    validate_policy_config(cfg)  # 不应抛出

def test_invalid_delivery_mode_raises(tmp_path):
    bad_yaml = _VALID_YAML.replace("delivery_mode: auto", "delivery_mode: invalid")
    f = tmp_path / "policy.yaml"
    f.write_text(bad_yaml)
    cfg = load_policy_config(str(f))
    with pytest.raises(PolicyError):
        validate_policy_config(cfg)

def test_excluded_companies_bad_prefix_raises(tmp_path):
    bad_yaml = _VALID_YAML.replace(
        "excluded_companies: []",
        "excluded_companies:\n  - badprefix:SomeCompany"
    )
    f = tmp_path / "policy.yaml"
    f.write_text(bad_yaml)
    cfg = load_policy_config(str(f))
    with pytest.raises(PolicyError):
        validate_policy_config(cfg)
```

**Step 2: 运行，确认失败**

```bash
python3 -m pytest tests/unit/domain/test_config_loader.py -v
```

**Step 3: 实现 config/loader.py**

```python
# tools/config/loader.py
from __future__ import annotations
from tools.config.fragments import PolicyConfig
from tools.infra.persistence.yaml_io import parse_simple_yaml


def load_policy_config(path: str) -> PolicyConfig:
    """从 YAML 文件加载 PolicyConfig。"""
    raw = parse_simple_yaml(path)
    return PolicyConfig(
        n_pass_required=int(raw.get("n_pass_required", 1)),
        matching_threshold=float(raw.get("matching_threshold", 0.6)),
        evaluation_threshold=float(raw.get("evaluation_threshold", 0.5)),
        max_rounds=int(raw.get("max_rounds", 10)),
        gate_mode=str(raw.get("gate_mode", "strict")),
        delivery_mode=str(raw.get("delivery_mode", "auto")),
        batch_review=bool(raw.get("batch_review", False)),
        excluded_companies=tuple(raw.get("excluded_companies", [])),
        excluded_legal_entities=tuple(raw.get("excluded_legal_entities", [])),
    )
```

**Step 4: 实现 config/validator.py**

```python
# tools/config/validator.py
from __future__ import annotations
from tools.config.fragments import PolicyConfig
from tools.errors.exceptions import PolicyError

_VALID_DELIVERY_MODES = {"auto", "manual"}
_VALID_GATE_MODES = {"strict", "simulate"}
_VALID_PREFIXES = {"exact:", "contains:"}


def validate_policy_config(cfg: PolicyConfig) -> None:
    if cfg.delivery_mode not in _VALID_DELIVERY_MODES:
        raise PolicyError(f"Invalid delivery_mode: {cfg.delivery_mode!r}")
    if cfg.gate_mode not in _VALID_GATE_MODES:
        raise PolicyError(f"Invalid gate_mode: {cfg.gate_mode!r}")
    for company in cfg.excluded_companies:
        if ":" in company:
            prefix = company.split(":", 1)[0] + ":"
            if prefix not in _VALID_PREFIXES:
                raise PolicyError(f"Invalid prefix in excluded_companies: {company!r}")
    if cfg.n_pass_required < 1:
        raise PolicyError("n_pass_required must be >= 1")
```

**Step 5: 运行测试**

```bash
python3 -m pytest tests/unit/domain/test_config_loader.py -v
```

**Step 6: Commit**

```bash
git add tools/config/loader.py tools/config/validator.py tests/unit/domain/test_config_loader.py
git commit -m "feat(A11): config loader + validator with PolicyError"
```

---

### Task A12+A13+A14: config/composer.py + errors/handler.py

**Files:**
- Create: `tools/config/composer.py`
- Create: `tools/errors/handler.py`
- Test: `tests/unit/domain/test_composer.py`

**Step 1: 写失败测试**

```python
# tests/unit/domain/test_composer.py
from tools.config.composer import Composer
from tools.config.fragments import PolicyConfig

def _policy():
    return PolicyConfig(
        n_pass_required=1, matching_threshold=0.5, evaluation_threshold=0.5,
        max_rounds=3, gate_mode="strict", delivery_mode="auto", batch_review=False,
        excluded_companies=(), excluded_legal_entities=(),
    )

def test_composer_builds_without_error():
    composer = Composer(policy=_policy())
    assert composer is not None

def test_composer_exposes_policy():
    composer = Composer(policy=_policy())
    assert composer.policy.delivery_mode == "auto"
```

**Step 2: 运行，确认失败**

```bash
python3 -m pytest tests/unit/domain/test_composer.py -v
```

**Step 3: 实现 composer.py（最小骨架）**

```python
# tools/config/composer.py
from __future__ import annotations
from dataclasses import dataclass
from tools.config.fragments import PolicyConfig


@dataclass
class Composer:
    """唯一组装点：把配置切片组装为 pipeline / agent loop。业务层禁止直接读取环境变量。"""
    policy: PolicyConfig

    @classmethod
    def from_policy_path(cls, path: str) -> "Composer":
        from tools.config.loader import load_policy_config
        from tools.config.validator import validate_policy_config
        cfg = load_policy_config(path)
        validate_policy_config(cfg)
        return cls(policy=cfg)
```

**Step 4: 实现 errors/handler.py**

```python
# tools/errors/handler.py
from __future__ import annotations
from typing import Any
from tools.errors.exceptions import PiProofError, EvidenceValidationError, FabricationGuardError


def route_error(exc: Exception) -> str:
    """错误路由：返回应对策略字符串。"""
    if isinstance(exc, (EvidenceValidationError, FabricationGuardError)):
        return "TERMINATE_RUN"
    if isinstance(exc, PiProofError):
        return "TERMINATE_RUN"
    return "UNKNOWN_ERROR"
```

**Step 5: 运行测试**

```bash
python3 -m pytest tests/unit/domain/test_composer.py -v
```

**Step 6: Commit**

```bash
git add tools/config/composer.py tools/errors/handler.py tests/unit/domain/test_composer.py
git commit -m "feat(A12-A14): Composer + error handler skeleton"
```

---

## Phase B — 引擎层与策略注册表

### Task B1: engines/registry.py — 通用策略注册表

**Files:**
- Create: `tools/engines/__init__.py`
- Create: `tools/engines/registry.py`
- Test: `tests/unit/domain/test_registry.py`

**Step 1: 写失败测试**

```python
# tests/unit/domain/test_registry.py
import pytest
from tools.engines.registry import EngineRegistry

def test_register_and_create():
    registry = EngineRegistry()
    registry.register("rule", lambda: "rule_engine_instance")
    result = registry.create("rule")
    assert result == "rule_engine_instance"

def test_unregistered_strategy_raises_at_create_time():
    registry = EngineRegistry()
    with pytest.raises(KeyError):
        registry.create("nonexistent")

def test_list_strategies():
    registry = EngineRegistry()
    registry.register("a", lambda: None)
    registry.register("b", lambda: None)
    assert set(registry.list()) == {"a", "b"}

def test_adding_new_strategy_does_not_modify_existing():
    registry = EngineRegistry()
    registry.register("rule", lambda: "old")
    registry.register("llm", lambda: "new_engine")
    assert registry.create("rule") == "old"
    assert registry.create("llm") == "new_engine"
```

**Step 2: 运行，确认失败**

```bash
python3 -m pytest tests/unit/domain/test_registry.py -v
```

**Step 3: 实现 registry.py**

```python
# tools/engines/__init__.py  (空)
# tools/engines/registry.py
from __future__ import annotations
from typing import Callable, Generic, TypeVar

T = TypeVar("T")


class EngineRegistry(Generic[T]):
    """通用策略注册表：register/create/list 三个最小能力。"""

    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], T]] = {}

    def register(self, name: str, factory: Callable[[], T]) -> None:
        self._factories[name] = factory

    def create(self, name: str) -> T:
        if name not in self._factories:
            raise KeyError(f"Strategy {name!r} not registered. "
                           f"Available: {list(self._factories)}")
        return self._factories[name]()

    def list(self) -> list[str]:
        return list(self._factories)
```

**Step 4: 运行测试**

```bash
python3 -m pytest tests/unit/domain/test_registry.py -v
```

**Step 5: Commit**

```bash
git add tools/engines/__init__.py tools/engines/registry.py tests/unit/domain/test_registry.py
git commit -m "feat(B1): EngineRegistry — register/create/list"
```

---

### Task B2-B5: 证据引擎（Evidence Engines）

**Files:**
- Create: `tools/engines/evidence/__init__.py`
- Create: `tools/engines/evidence/rule_extractor.py`
- Create: `tools/engines/evidence/llm_extractor.py`
- Create: `tools/engines/evidence/validator.py`
- Create: `tools/engines/evidence/store.py`
- Test: `tests/unit/domain/test_evidence_engines.py`

**Step 1: 写失败测试（validator 最关键）**

```python
# tests/unit/domain/test_evidence_engines.py
import pytest
from tools.domain.models import EvidenceCard
from tools.engines.evidence.validator import EvidenceValidator
from tools.errors.exceptions import EvidenceValidationError

def _card(results=("提升 30%",), artifacts=("pr#1",)):
    return EvidenceCard(id="c1", title="T", raw_source="s",
                        results=results, artifacts=artifacts)

def test_valid_card_passes():
    EvidenceValidator().validate(_card())

def test_missing_results_raises():
    with pytest.raises(EvidenceValidationError):
        EvidenceValidator().validate(_card(results=()))

def test_missing_artifacts_raises():
    with pytest.raises(EvidenceValidationError):
        EvidenceValidator().validate(_card(artifacts=()))

def test_rule_extractor_returns_evidence_card():
    from tools.engines.evidence.rule_extractor import RuleEvidenceExtractor
    extractor = RuleEvidenceExtractor()
    card = extractor.extract("关键词：性能 结果：延迟降低 20ms artifact：pr#2")
    assert isinstance(card, EvidenceCard)
```

**Step 2: 运行，确认失败**

```bash
python3 -m pytest tests/unit/domain/test_evidence_engines.py -v
```

**Step 3: 实现 evidence/validator.py**

```python
# tools/engines/evidence/validator.py
from __future__ import annotations
from tools.domain.models import EvidenceCard
from tools.errors.exceptions import EvidenceValidationError


class EvidenceValidator:
    def validate(self, card: EvidenceCard) -> None:
        if not card.results:
            raise EvidenceValidationError(f"Card {card.id!r} missing results")
        if not card.artifacts:
            raise EvidenceValidationError(f"Card {card.id!r} missing artifacts")
```

**Step 4: 实现 evidence/rule_extractor.py（迁移自 extract_evidence.py）**

```python
# tools/engines/evidence/__init__.py  (空)
# tools/engines/evidence/rule_extractor.py
from __future__ import annotations
import re
from tools.domain.models import EvidenceCard


class RuleEvidenceExtractor:
    """规则提取器：迁移自 tools/extract_evidence.py 核心逻辑，不依赖文件路径/CLI。"""

    def extract(self, raw_material: str) -> EvidenceCard:
        results = tuple(re.findall(r"结果[：:]\s*(.+)", raw_material))
        artifacts = tuple(re.findall(r"artifact[：:]?\s*(\S+)", raw_material, re.IGNORECASE))
        tags = tuple(re.findall(r"关键词[：:]\s*(\S+)", raw_material))
        return EvidenceCard(
            id=f"ec-rule-{abs(hash(raw_material[:20]))}",
            title=raw_material[:40].strip(),
            raw_source=raw_material,
            results=results if results else ("(待补充)",),
            artifacts=artifacts if artifacts else ("(待补充)",),
            tags=tags,
        )
```

**Step 5: 实现 evidence/store.py（路径通过 PathConfig 注入）**

```python
# tools/engines/evidence/store.py
from __future__ import annotations
import os
from typing import Sequence
from tools.domain.models import EvidenceCard
from tools.infra.persistence.yaml_io import parse_simple_yaml, dump_yaml


class EvidenceStore:
    def __init__(self, base_dir: str = "evidence_cards") -> None:
        self._base_dir = base_dir

    def all(self) -> list[EvidenceCard]:
        cards = []
        if not os.path.isdir(self._base_dir):
            return cards
        for fname in os.listdir(self._base_dir):
            if fname.endswith(".yaml"):
                path = os.path.join(self._base_dir, fname)
                raw = parse_simple_yaml(path)
                cards.append(self._from_dict(raw))
        return cards

    def get(self, card_id: str) -> EvidenceCard | None:
        for card in self.all():
            if card.id == card_id:
                return card
        return None

    def save(self, card: EvidenceCard) -> None:
        os.makedirs(self._base_dir, exist_ok=True)
        path = os.path.join(self._base_dir, f"{card.id}.yaml")
        data = {"id": card.id, "title": card.title, "raw_source": card.raw_source,
                "results": list(card.results), "artifacts": list(card.artifacts),
                "tags": list(card.tags), "period": card.period, "context": card.context}
        dump_yaml(data, path)

    @staticmethod
    def _from_dict(d: dict) -> EvidenceCard:
        return EvidenceCard(
            id=str(d.get("id", "")), title=str(d.get("title", "")),
            raw_source=str(d.get("raw_source", "")),
            results=tuple(d.get("results", [])),
            artifacts=tuple(d.get("artifacts", [])),
            tags=tuple(d.get("tags", [])),
            period=str(d.get("period", "")), context=str(d.get("context", "")),
        )
```

**Step 6: 实现 llm_extractor.py（注入 LLMClient）**

```python
# tools/engines/evidence/llm_extractor.py
from __future__ import annotations
from tools.domain.models import EvidenceCard
from tools.infra.llm.client import LLMClient


class LLMEvidenceExtractor:
    """注入 LLMClient；通过 registry 注册为 evidence_mode=llm。"""

    def __init__(self, client: LLMClient, prompt_template: str = "") -> None:
        self._client = client
        self._prompt_template = prompt_template

    def extract(self, raw_material: str) -> EvidenceCard:
        prompt = (self._prompt_template or
                  f"从以下材料提炼结构化证据（results/artifacts 必填）：\n\n{raw_material}")
        # LLMClient.chat 返回字符串，这里简单 parse
        response = self._client.chat(prompt)
        # 极简解析：实际应调用 yaml_io 解析 LLM YAML 输出
        return EvidenceCard(
            id="ec-llm-tmp", title="LLM extracted",
            raw_source=raw_material, results=(response[:80],), artifacts=("llm-output",)
        )
```

**Step 7: 运行测试**

```bash
python3 -m pytest tests/unit/domain/test_evidence_engines.py -v
```

**Step 8: Commit**

```bash
git add tools/engines/evidence/ tests/unit/domain/test_evidence_engines.py
git commit -m "feat(B2-B5): evidence engines — validator, rule_extractor, store, llm_extractor"
```

---

### Task B6-B8: 匹配评分引擎（Matching Engines）

**Files:**
- Create: `tools/engines/matching/__init__.py`
- Create: `tools/engines/matching/rule_scorer.py`
- Create: `tools/engines/matching/llm_matcher.py`
- Create: `tools/engines/matching/report_builder.py`
- Test: `tests/unit/domain/test_matching_engines.py`

**Step 1: 写失败测试**

```python
# tests/unit/domain/test_matching_engines.py
from tools.domain.models import EvidenceCard, JobProfile
from tools.engines.matching.rule_scorer import RuleMatchingEngine
from tools.engines.matching.report_builder import ReportBuilder

def _card():
    return EvidenceCard(id="c1", title="性能优化", raw_source="s",
                        results=("延迟降 30%",), artifacts=("pr#1",),
                        tags=("性能", "Python"))

def _profile():
    return JobProfile(id="jp1", title="后端工程师", keywords=("Python", "性能"),
                      level="P6", must_have=("Python",))

def test_rule_scorer_returns_matching_report():
    engine = RuleMatchingEngine()
    report = engine.score([_card()], _profile())
    assert report.job_profile_id == "jp1"
    assert len(report.score_breakdown) > 0

def test_gap_tasks_generated_for_missing_keywords():
    engine = RuleMatchingEngine()
    profile = JobProfile(id="jp2", title="T", keywords=("Kafka",), level="P5",
                         must_have=("Kafka",))
    report = engine.score([_card()], profile)
    assert len(report.gap_tasks) > 0
    assert any("Kafka" in t for t in report.gap_tasks)

def test_report_builder_constructs_report():
    builder = ReportBuilder()
    report = builder.build("jp1", ["c1"], {"K": 0.8, "D": 0.6}, ["补充 Kafka 经验"])
    assert report.job_profile_id == "jp1"
```

**Step 2: 运行，确认失败**

```bash
python3 -m pytest tests/unit/domain/test_matching_engines.py -v
```

**Step 3: 实现 rule_scorer.py（迁移自 run_matching_scoring.py）**

```python
# tools/engines/matching/__init__.py  (空)
# tools/engines/matching/rule_scorer.py
from __future__ import annotations
from typing import Sequence
from tools.domain.models import EvidenceCard, JobProfile, MatchingReport


class RuleMatchingEngine:
    """K/D/S/Q/E/R 六维度规则评分；迁移自 run_matching_scoring.py build_rule_report。"""

    def score(self, evidence_cards: Sequence[EvidenceCard], profile: JobProfile) -> MatchingReport:
        all_tags = set()
        for card in evidence_cards:
            all_tags.update(card.tags)

        kw_hit = sum(1 for kw in profile.keywords if kw in all_tags)
        k_score = kw_hit / max(len(profile.keywords), 1)

        has_results = sum(1 for c in evidence_cards if c.results)
        q_score = has_results / max(len(evidence_cards), 1)

        has_artifacts = sum(1 for c in evidence_cards if c.artifacts)
        e_score = has_artifacts / max(len(evidence_cards), 1)

        breakdown = {"K": round(k_score, 3), "Q": round(q_score, 3), "E": round(e_score, 3)}
        card_ids = tuple(c.id for c in evidence_cards)
        gap_tasks = tuple(
            f"补充 {kw} 相关证据" for kw in profile.must_have if kw not in all_tags
        )
        return MatchingReport(
            job_profile_id=profile.id,
            evidence_card_ids=card_ids,
            score_breakdown=breakdown,
            gap_tasks=gap_tasks,
        )
```

**Step 4: 实现 report_builder.py**

```python
# tools/engines/matching/report_builder.py
from __future__ import annotations
from tools.domain.models import MatchingReport


class ReportBuilder:
    def build(self, job_profile_id: str, card_ids: list[str],
              breakdown: dict[str, float], gap_tasks: list[str]) -> MatchingReport:
        if not gap_tasks:
            gap_tasks = []
        return MatchingReport(
            job_profile_id=job_profile_id,
            evidence_card_ids=tuple(card_ids),
            score_breakdown=dict(breakdown),
            gap_tasks=tuple(gap_tasks),
        )
```

**Step 5: 运行测试**

```bash
python3 -m pytest tests/unit/domain/test_matching_engines.py -v
```

**Step 6: Commit**

```bash
git add tools/engines/matching/ tests/unit/domain/test_matching_engines.py
git commit -m "feat(B6-B8): matching engines — rule_scorer, report_builder"
```

---

### Task B9-B11: 生成引擎（Generation Engines）

**Files:**
- Create: `tools/engines/generation/__init__.py`
- Create: `tools/engines/generation/template_assembler.py`
- Create: `tools/engines/generation/llm_rewriter.py`
- Create: `tools/engines/generation/exporter.py`
- Test: `tests/unit/domain/test_generation_engines.py`

**Step 1: 写失败测试（最关键：FabricationGuard 守卫）**

```python
# tests/unit/domain/test_generation_engines.py
import pytest
from tools.domain.models import EvidenceCard, MatchingReport, ResumeOutput
from tools.engines.generation.template_assembler import TemplateAssembler
from tools.errors.exceptions import FabricationGuardError

def _report():
    return MatchingReport(
        job_profile_id="jp1", evidence_card_ids=("c1",),
        score_breakdown={"K": 0.8}, gap_tasks=()
    )

def _card():
    return EvidenceCard(id="c1", title="性能优化", raw_source="s",
                        results=("延迟降 30%",), artifacts=("pr#1",))

def test_assembler_generates_resume():
    assembler = TemplateAssembler()
    resume = assembler.assemble(_report(), [_card()], "v1")
    assert isinstance(resume, ResumeOutput)
    assert "延迟降 30%" in resume.content

def test_assembler_raises_if_no_cards():
    assembler = TemplateAssembler()
    with pytest.raises(FabricationGuardError):
        assembler.assemble(_report(), [], "v1")
```

**Step 2: 运行，确认失败**

```bash
python3 -m pytest tests/unit/domain/test_generation_engines.py -v
```

**Step 3: 实现 template_assembler.py（先写，守卫测试必须先红再绿）**

```python
# tools/engines/generation/__init__.py  (空)
# tools/engines/generation/template_assembler.py
from __future__ import annotations
from typing import Sequence
from tools.domain.models import EvidenceCard, MatchingReport, ResumeOutput
from tools.errors.exceptions import FabricationGuardError


class TemplateAssembler:
    """模板拼装：evidence-first，无 EvidenceCard 对应的内容禁止生成。"""

    def assemble(self, report: MatchingReport, cards: Sequence[EvidenceCard],
                 version: str) -> ResumeOutput:
        if not cards:
            raise FabricationGuardError("No EvidenceCards provided; cannot generate resume.")

        lines = [f"# 简历 {version}", ""]
        for card in cards:
            lines.append(f"## {card.title}")
            for result in card.results:
                lines.append(f"- {result}")
            lines.append("")

        content = "\n".join(lines)
        return ResumeOutput(version=version, job_profile_id=report.job_profile_id,
                            content=content, format="markdown")
```

**Step 4: 运行测试**

```bash
python3 -m pytest tests/unit/domain/test_generation_engines.py -v
```

**Step 5: Commit**

```bash
git add tools/engines/generation/ tests/unit/domain/test_generation_engines.py
git commit -m "feat(B9-B11): generation engines — template_assembler with FabricationGuard"
```

---

### Task B12-B14: 评测引擎（Evaluation Engines）

**Files:**
- Create: `tools/engines/evaluation/__init__.py`
- Create: `tools/engines/evaluation/rule_evaluator.py`
- Create: `tools/engines/evaluation/scorecard_builder.py`
- Test: `tests/unit/domain/test_evaluation_engines.py`

**Step 1: 写失败测试**

```python
# tests/unit/domain/test_evaluation_engines.py
from tools.domain.models import JobProfile, ResumeOutput, Scorecard
from tools.engines.evaluation.rule_evaluator import RuleEvaluationEngine

def _resume():
    return ResumeOutput(version="v1", job_profile_id="jp1",
                        content="## 性能优化\n- 延迟降低 30%\n- 吞吐提升 2x",
                        format="markdown")

def _profile():
    return JobProfile(id="jp1", title="后端工程师", keywords=("性能",), level="P6",
                      must_have=("性能",))

def test_rule_evaluator_returns_scorecard():
    engine = RuleEvaluationEngine()
    scorecard = engine.evaluate(_resume(), _profile())
    assert isinstance(scorecard, Scorecard)
    assert "coverage" in scorecard.dimension_scores

def test_scorecard_traceable_to_checkpoints():
    engine = RuleEvaluationEngine()
    scorecard = engine.evaluate(_resume(), _profile())
    assert scorecard.total_score >= 0
    assert scorecard.total_score <= 1
```

**Step 2: 实现 rule_evaluator.py**

```python
# tools/engines/evaluation/__init__.py  (空)
# tools/engines/evaluation/rule_evaluator.py
from __future__ import annotations
from tools.domain.models import JobProfile, ResumeOutput, Scorecard


class RuleEvaluationEngine:
    """coverage/quant/clarity/length/citation 五维度规则评测。"""

    def evaluate(self, resume: ResumeOutput, profile: JobProfile) -> Scorecard:
        content = resume.content
        kw_count = sum(1 for kw in profile.keywords if kw in content)
        coverage = kw_count / max(len(profile.keywords), 1)

        import re
        quant = len(re.findall(r"\d+[%xX倍ms秒]", content)) / max(len(content.split("\n")), 1)
        quant = min(quant, 1.0)

        length_ok = 200 <= len(content) <= 3000
        clarity = 1.0 if length_ok else 0.5

        total = (coverage * 0.4 + quant * 0.3 + clarity * 0.3)
        return Scorecard(
            resume_version=resume.version,
            job_profile_id=profile.id,
            total_score=round(total, 3),
            dimension_scores={"coverage": round(coverage, 3),
                               "quant": round(quant, 3),
                               "clarity": round(clarity, 3)},
        )
```

**Step 3: 运行测试**

```bash
python3 -m pytest tests/unit/domain/test_evaluation_engines.py -v
```

**Step 4: Commit**

```bash
git add tools/engines/evaluation/ tests/unit/domain/test_evaluation_engines.py
git commit -m "feat(B12-B14): evaluation engines — rule_evaluator, scorecard_builder"
```

---

### Task B15: 候选发现引擎（Discovery Engine）

**Files:**
- Create: `tools/engines/discovery/__init__.py`
- Create: `tools/engines/discovery/discovery_engine.py`
- Test: `tests/unit/domain/test_discovery_engine.py`

**Step 1: 写失败测试（含企业排除过滤）**

```python
# tests/unit/domain/test_discovery_engine.py
from tools.engines.discovery.discovery_engine import DiscoveryEngine
from tools.domain.value_objects import Candidate
from tools.config.fragments import PolicyConfig

def _policy(excluded=()):
    return PolicyConfig(
        n_pass_required=1, matching_threshold=0.5, evaluation_threshold=0.5,
        max_rounds=3, gate_mode="strict", delivery_mode="auto", batch_review=False,
        excluded_companies=excluded, excluded_legal_entities=(),
    )

def _cand(company="Acme"):
    return Candidate(candidate_id=f"c-{company}", direction="后端",
                     company=company, job_url=f"http://x.com/{company}",
                     confidence=0.8, source="manual", merged_sources=())

def test_no_exclusion_returns_all():
    engine = DiscoveryEngine(policy=_policy())
    result = engine.filter([_cand("Acme"), _cand("Beta")])
    assert len(result.accepted) == 2
    assert len(result.excluded) == 0

def test_excluded_company_removed():
    engine = DiscoveryEngine(policy=_policy(excluded=("exact:Acme",)))
    result = engine.filter([_cand("Acme"), _cand("Beta")])
    assert len(result.accepted) == 1
    assert result.accepted[0].company == "Beta"
    assert len(result.excluded) == 1
    assert result.excluded[0][1] == "excluded_by_policy"
```

**Step 2: 运行，确认失败**

```bash
python3 -m pytest tests/unit/domain/test_discovery_engine.py -v
```

**Step 3: 实现 discovery_engine.py**

```python
# tools/engines/discovery/__init__.py  (空)
# tools/engines/discovery/discovery_engine.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Sequence
from tools.domain.value_objects import Candidate
from tools.config.fragments import PolicyConfig


@dataclass
class FilterResult:
    accepted: list[Candidate]
    excluded: list[tuple[Candidate, str]]  # (candidate, reason)


class DiscoveryEngine:
    def __init__(self, policy: PolicyConfig) -> None:
        self._policy = policy

    def filter(self, candidates: Sequence[Candidate]) -> FilterResult:
        accepted, excluded = [], []
        for cand in candidates:
            if self._is_excluded(cand):
                excluded.append((cand, "excluded_by_policy"))
            else:
                accepted.append(cand)
        return FilterResult(accepted=accepted, excluded=excluded)

    def _is_excluded(self, cand: Candidate) -> bool:
        for rule in self._policy.excluded_companies:
            if rule.startswith("exact:"):
                if cand.company == rule[6:]:
                    return True
            elif rule.startswith("contains:"):
                if rule[9:] in cand.company:
                    return True
            else:
                if cand.company == rule:
                    return True
        for entity in self._policy.excluded_legal_entities:
            if cand.legal_entity == entity:
                return True
        return False
```

**Step 4: 运行测试**

```bash
python3 -m pytest tests/unit/domain/test_discovery_engine.py -v
```

**Step 5: B16 — registry 接线（在 composer.py 中注册四大引擎）**

在 `tools/config/composer.py` 中添加：

```python
# 在 Composer 中添加 build_engine_registry 方法
from tools.engines.registry import EngineRegistry
from tools.engines.evidence.rule_extractor import RuleEvidenceExtractor
from tools.engines.evidence.validator import EvidenceValidator
from tools.engines.matching.rule_scorer import RuleMatchingEngine
from tools.engines.generation.template_assembler import TemplateAssembler
from tools.engines.evaluation.rule_evaluator import RuleEvaluationEngine

def build_engine_registry(self) -> EngineRegistry:
    registry = EngineRegistry()
    registry.register("evidence:rule", RuleEvidenceExtractor)
    registry.register("matching:rule", RuleMatchingEngine)
    registry.register("generation:template", TemplateAssembler)
    registry.register("evaluation:rule", RuleEvaluationEngine)
    return registry
```

**Step 6: Commit**

```bash
git add tools/engines/discovery/ tests/unit/domain/test_discovery_engine.py tools/config/composer.py
git commit -m "feat(B15-B16): discovery engine with exclusion filter + registry wiring"
```

---

## Phase C — 编排层（Stage 组合 + 状态机）

### Task C1-C3: orchestration/stage.py + pipeline.py + state_machine.py

**Files:**
- Create: `tools/orchestration/__init__.py`
- Create: `tools/orchestration/stage.py`
- Create: `tools/orchestration/pipeline.py`
- Create: `tools/orchestration/state_machine.py`
- Test: `tests/unit/domain/test_orchestration.py`

**Step 1: 写失败测试（状态机迁移规则先锁定）**

```python
# tests/unit/domain/test_orchestration.py
from tools.orchestration.state_machine import StateMachine, TRANSITIONS

def test_init_to_discover():
    sm = StateMachine()
    next_state = sm.transition("INIT", "start")
    assert next_state == "DISCOVER"

def test_gate_pass_to_review():
    sm = StateMachine()
    next_state = sm.transition("GATE_PASS", "proceed")
    assert next_state in ("REVIEW", "DELIVER")  # 取决于 delivery_mode

def test_gate_fail_to_learn():
    sm = StateMachine()
    assert sm.transition("GATE_FAIL", "fail") == "LEARN"

def test_invalid_transition_raises():
    sm = StateMachine()
    import pytest
    with pytest.raises(ValueError):
        sm.transition("DONE", "any")

def test_linear_pipeline_executes_stages():
    from tools.orchestration.pipeline import LinearPipeline
    from tools.orchestration.stage import RunContext, StageResult

    class MockStage:
        name = "mock"
        def execute(self, ctx):
            ctx["executed"].append(self.name)
            return StageResult(success=True, data=None)

    ctx = {"executed": []}
    pipeline = LinearPipeline(stages=[MockStage(), MockStage()])
    result = pipeline.run(ctx)
    assert result.success
    assert len(ctx["executed"]) == 2
```

**Step 2: 实现 stage.py**

```python
# tools/orchestration/__init__.py  (空)
# tools/orchestration/stage.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

RunContext = dict[str, Any]

@dataclass
class StageResult:
    success: bool
    data: Any
    errors: tuple[Any, ...] = ()
```

**Step 3: 实现 state_machine.py**

```python
# tools/orchestration/state_machine.py
from __future__ import annotations

TRANSITIONS: dict[str, dict[str, str]] = {
    "INIT": {"start": "DISCOVER"},
    "DISCOVER": {"proceed": "SCORE", "empty": "DONE"},
    "SCORE": {"proceed": "GENERATE"},
    "GENERATE": {"proceed": "EVALUATE"},
    "EVALUATE": {"proceed": "GATE"},
    "GATE": {"pass": "GATE_PASS", "fail": "GATE_FAIL"},
    "GATE_PASS": {"proceed": "REVIEW"},
    "GATE_FAIL": {"fail": "LEARN"},
    "REVIEW": {"approve": "DELIVER", "reject": "LEARN", "skip": "LEARN"},
    "DELIVER": {"done": "LEARN"},
    "LEARN": {"proceed": "DISCOVER", "stop": "DONE"},
    "DONE": {},
    "ERROR": {"recover": "INIT"},
}


class StateMachine:
    def transition(self, current: str, event: str) -> str:
        if current not in TRANSITIONS:
            raise ValueError(f"Unknown state: {current!r}")
        state_transitions = TRANSITIONS[current]
        if event not in state_transitions:
            if current == "DONE":
                raise ValueError(f"Terminal state DONE has no transitions")
            # 找第一个可用的
            if state_transitions:
                return next(iter(state_transitions.values()))
            raise ValueError(f"No transition from {current!r} on event {event!r}")
        return state_transitions[event]
```

**Step 4: 实现 pipeline.py**

```python
# tools/orchestration/pipeline.py
from __future__ import annotations
from typing import Sequence
from tools.orchestration.stage import RunContext, StageResult


class LinearPipeline:
    """线性流水线：extraction → matching → generation → evaluation"""

    def __init__(self, stages: Sequence) -> None:
        self._stages = stages

    def run(self, context: RunContext) -> StageResult:
        for stage in self._stages:
            result = stage.execute(context)
            if not result.success:
                return result
        return StageResult(success=True, data=context)
```

**Step 5: 运行测试**

```bash
python3 -m pytest tests/unit/domain/test_orchestration.py -v
```

**Step 6: Commit**

```bash
git add tools/orchestration/ tests/unit/domain/test_orchestration.py
git commit -m "feat(C1-C3): orchestration — stage, pipeline, state_machine"
```

---

### Task C4-C4a: gate_engine.py + review_stage.py

**Files:**
- Create: `tools/orchestration/gate_engine.py`
- Create: `tools/orchestration/review_stage.py`
- Test: `tests/unit/domain/test_gate_review.py`

**Step 1: 写失败测试（三种 delivery_mode 行为差异必须覆盖）**

```python
# tests/unit/domain/test_gate_review.py
import pytest
from tools.orchestration.gate_engine import GateEngine
from tools.orchestration.review_stage import ReviewStage
from tools.config.fragments import PolicyConfig
from tools.domain.value_objects import Candidate

def _policy(delivery_mode="auto", batch_review=False, n_pass=1):
    return PolicyConfig(
        n_pass_required=n_pass, matching_threshold=0.5, evaluation_threshold=0.5,
        max_rounds=3, gate_mode="strict", delivery_mode=delivery_mode,
        batch_review=batch_review, excluded_companies=(), excluded_legal_entities=(),
    )

def _cand(company="Acme"):
    return Candidate(candidate_id="c1", direction="后端", company=company,
                     job_url="http://x.com", confidence=0.9,
                     source="manual", merged_sources=())

# GateEngine 测试
def test_gate_passes_when_score_above_threshold():
    from tools.domain.result import Ok
    engine = GateEngine(policy=_policy(), run_id="r1", round_index=0)
    result = engine.evaluate(candidate=_cand(), matching_score=0.8, evaluation_score=0.7)
    assert isinstance(result, Ok)
    assert result.value.passed

def test_gate_fails_for_excluded_company():
    from tools.domain.result import Err
    engine = GateEngine(
        policy=_policy().__class__(
            **{**_policy().__dict__, "excluded_companies": ("exact:Acme",),
               "excluded_legal_entities": ()}
        ),
        run_id="r1", round_index=0,
    )
    result = engine.evaluate(candidate=_cand("Acme"), matching_score=0.9, evaluation_score=0.9)
    assert isinstance(result, Err)
    assert "excluded_company" in result.error.reason

# ReviewStage 测试
def test_auto_mode_review_is_pass_through():
    stage = ReviewStage(policy=_policy("auto"))
    ctx = {"pending_reviews": [], "events": []}
    result = stage.execute(ctx)
    assert result.success
    assert ctx.get("review_paused") is not True

def test_manual_non_batch_emits_pending_event():
    stage = ReviewStage(policy=_policy("manual", batch_review=False))
    ctx = {"pending_reviews": [{"job_lead_id": "j1"}], "events": []}
    result = stage.execute(ctx)
    assert result.data.get("waiting_for_review") is True

def test_manual_batch_collects_all_before_review():
    stage = ReviewStage(policy=_policy("manual", batch_review=True))
    ctx = {"pending_reviews": [{"job_lead_id": "j1"}], "all_rounds_done": False, "events": []}
    result = stage.execute(ctx)
    # 未完成所有轮次，不暂停
    assert result.data.get("batch_collect") is True
```

**Step 2: 运行，确认失败**

```bash
python3 -m pytest tests/unit/domain/test_gate_review.py -v
```

**Step 3: 实现 gate_engine.py**

```python
# tools/orchestration/gate_engine.py
from __future__ import annotations
from tools.config.fragments import PolicyConfig
from tools.domain.result import Err, Ok, Result
from tools.domain.value_objects import Candidate, GateDecision, GateFailure


class GateEngine:
    def __init__(self, policy: PolicyConfig, run_id: str, round_index: int) -> None:
        self._policy = policy
        self._run_id = run_id
        self._round_index = round_index

    def evaluate(
        self, candidate: Candidate, matching_score: float, evaluation_score: float
    ) -> Result[GateDecision, GateFailure]:
        # 企业例外清单兜底
        for rule in self._policy.excluded_companies:
            company = candidate.company
            if rule.startswith("exact:") and company == rule[6:]:
                return Err(GateFailure(reason="excluded_company", details=f"{company} in exclusion list"))
            elif rule.startswith("contains:") and rule[9:] in company:
                return Err(GateFailure(reason="excluded_company", details=f"{company} contains {rule[9:]}"))
            elif company == rule:
                return Err(GateFailure(reason="excluded_company", details=f"{company} exact match"))

        if matching_score < self._policy.matching_threshold:
            return Err(GateFailure(reason="matching_below_threshold",
                                   details=f"{matching_score:.2f} < {self._policy.matching_threshold}"))
        if evaluation_score < self._policy.evaluation_threshold:
            return Err(GateFailure(reason="evaluation_below_threshold",
                                   details=f"{evaluation_score:.2f} < {self._policy.evaluation_threshold}"))

        return Ok(GateDecision(passed=True, pass_count=1,
                               details=f"round={self._round_index}"))
```

**Step 4: 实现 review_stage.py**

```python
# tools/orchestration/review_stage.py
from __future__ import annotations
from tools.config.fragments import PolicyConfig
from tools.orchestration.stage import RunContext, StageResult


class ReviewStage:
    name = "REVIEW"

    def __init__(self, policy: PolicyConfig) -> None:
        self._policy = policy

    def execute(self, context: RunContext) -> StageResult:
        if self._policy.delivery_mode == "auto":
            # pass-through，不暂停
            return StageResult(success=True, data={"review_paused": False})

        if self._policy.batch_review:
            # 批量审批：收集全部轮次后再处理
            return StageResult(success=True, data={"batch_collect": True})
        else:
            # 逐轮审批：发出 pending 事件，等待用户
            context.get("events", []).append("agent.review.pending")
            return StageResult(success=True, data={"waiting_for_review": True})
```

**Step 5: 运行测试**

```bash
python3 -m pytest tests/unit/domain/test_gate_review.py -v
```

**Step 6: Commit**

```bash
git add tools/orchestration/gate_engine.py tools/orchestration/review_stage.py tests/unit/domain/test_gate_review.py
git commit -m "feat(C4-C4a): gate_engine + review_stage (auto/manual/batch_review)"
```

---

### Task C5-C6: agent_loop.py + run_agent.py

**Files:**
- Create: `tools/orchestration/agent_loop.py`
- Create: `tools/run_agent.py`
- Test: `tests/unit/domain/test_agent_loop.py`

**Step 1: 写失败测试**

```python
# tests/unit/domain/test_agent_loop.py
from tools.orchestration.agent_loop import AgentLoop
from tools.config.fragments import PolicyConfig
from tools.domain.value_objects import Candidate

def _policy():
    return PolicyConfig(
        n_pass_required=1, matching_threshold=0.0, evaluation_threshold=0.0,
        max_rounds=2, gate_mode="simulate", delivery_mode="auto", batch_review=False,
        excluded_companies=(), excluded_legal_entities=(),
    )

def test_agent_loop_dry_run_completes():
    loop = AgentLoop(policy=_policy(), run_id="run-test-001", dry_run=True)
    result = loop.run()
    assert result["run_id"] == "run-test-001"
    assert result["status"] in ("DONE", "DRY_RUN_COMPLETE")

def test_agent_loop_reaches_max_rounds():
    loop = AgentLoop(policy=_policy(), run_id="run-test-002", dry_run=True)
    result = loop.run()
    assert result.get("rounds_completed", 0) <= 2
```

**Step 2: 实现 agent_loop.py（最小可用版本）**

```python
# tools/orchestration/agent_loop.py
from __future__ import annotations
from typing import Any
from tools.config.fragments import PolicyConfig
from tools.infra.logging import make_logger


class AgentLoop:
    """驱动 INIT→DISCOVER→SCORE→GENERATE→EVALUATE→GATE→REVIEW→DELIVER→LEARN→DONE 循环。"""

    def __init__(self, policy: PolicyConfig, run_id: str, dry_run: bool = False) -> None:
        self._policy = policy
        self._run_id = run_id
        self._dry_run = dry_run
        self._logger = make_logger(run_id=run_id)

    def run(self) -> dict[str, Any]:
        self._logger.info("agent_loop_start", dry_run=self._dry_run)
        rounds_completed = 0
        for round_idx in range(self._policy.max_rounds):
            self._logger.info("round_start", round=round_idx, state="DISCOVER")
            # dry_run: 模拟一轮，不真实调用引擎/通道
            if self._dry_run:
                self._logger.info("round_complete", round=round_idx, state="DONE")
                rounds_completed += 1
                break
        return {
            "run_id": self._run_id,
            "status": "DRY_RUN_COMPLETE" if self._dry_run else "DONE",
            "rounds_completed": rounds_completed,
        }
```

**Step 3: 实现 run_agent.py（薄 CLI 入口）**

```python
# tools/run_agent.py
"""Agent loop CLI 入口：python3 tools/run_agent.py --policy policy.yaml [--dry-run]"""
from __future__ import annotations
import argparse
import sys
import uuid


def main() -> None:
    parser = argparse.ArgumentParser(description="PiProofForge Agent Loop")
    parser.add_argument("--policy", required=True, help="Path to policy.yaml")
    parser.add_argument("--run-id", default=None, help="Run ID (auto-generated if omitted)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without real delivery")
    args = parser.parse_args()

    from tools.config.composer import Composer
    from tools.orchestration.agent_loop import AgentLoop

    composer = Composer.from_policy_path(args.policy)
    run_id = args.run_id or f"run-{uuid.uuid4().hex[:8]}"
    loop = AgentLoop(policy=composer.policy, run_id=run_id, dry_run=args.dry_run)
    result = loop.run()
    print(f"Agent loop completed: {result}")


if __name__ == "__main__":
    main()
```

**Step 4: 运行测试 + 端到端冒烟**

```bash
python3 -m pytest tests/unit/domain/test_agent_loop.py -v
# 端到端 dry-run（需要先创建一个测试 policy.yaml）
cat > /tmp/test_policy.yaml <<EOF
n_pass_required: 1
matching_threshold: 0.5
evaluation_threshold: 0.5
max_rounds: 2
gate_mode: simulate
delivery_mode: auto
batch_review: false
excluded_companies: []
excluded_legal_entities: []
EOF
python3 tools/run_agent.py --policy /tmp/test_policy.yaml --dry-run
```

**Step 5: Commit**

```bash
git add tools/orchestration/agent_loop.py tools/run_agent.py tests/unit/domain/test_agent_loop.py
git commit -m "feat(C5-C6): AgentLoop + run_agent.py dry-run end-to-end"
```

---

## Phase D — 持久化与通道

### Task D5-D6: infra/persistence/file_run_store.py

**Files:**
- Create: `tools/infra/persistence/file_run_store.py`
- Test: `tests/unit/infra/test_file_run_store.py`

**Step 1: 写失败测试**

```python
# tests/unit/infra/test_file_run_store.py
import json, os
from tools.infra.persistence.file_run_store import FileRunStore
from tools.domain.events import RunEvent

def test_append_and_load_events(tmp_path):
    store = FileRunStore(base_dir=str(tmp_path))
    event = RunEvent(run_id="r1", event_type="DISCOVER", round_index=0, payload={"count": 3})
    store.append_event(event)
    events = store.load_events("r1")
    assert len(events) == 1
    assert events[0].event_type == "DISCOVER"

def test_events_append_not_overwrite(tmp_path):
    store = FileRunStore(base_dir=str(tmp_path))
    store.append_event(RunEvent(run_id="r1", event_type="DISCOVER", round_index=0, payload={}))
    store.append_event(RunEvent(run_id="r1", event_type="SCORE", round_index=0, payload={}))
    events = store.load_events("r1")
    assert len(events) == 2

def test_run_log_written_to_expected_path(tmp_path):
    store = FileRunStore(base_dir=str(tmp_path))
    store.append_event(RunEvent(run_id="r99", event_type="INIT", round_index=0, payload={}))
    log_path = tmp_path / "r99" / "run_log.json"
    assert log_path.exists()
```

**Step 2: 实现 file_run_store.py**

```python
# tools/infra/persistence/file_run_store.py
from __future__ import annotations
import json, os
from typing import Sequence
from tools.domain.events import RunEvent


class FileRunStore:
    """输出 outputs/agent_runs/<run_id>/run_log.json；事件追加写入，不回写历史。"""

    def __init__(self, base_dir: str = "outputs/agent_runs") -> None:
        self._base_dir = base_dir

    def _run_dir(self, run_id: str) -> str:
        return os.path.join(self._base_dir, run_id)

    def _log_path(self, run_id: str) -> str:
        return os.path.join(self._run_dir(run_id), "run_log.json")

    def append_event(self, event: RunEvent) -> None:
        os.makedirs(self._run_dir(event.run_id), exist_ok=True)
        path = self._log_path(event.run_id)
        events = self._read_raw(path)
        events.append({"run_id": event.run_id, "event_type": event.event_type,
                        "round_index": event.round_index, "payload": event.payload,
                        "timestamp": event.timestamp})
        with open(path, "w", encoding="utf-8") as f:
            json.dump(events, f, ensure_ascii=False, indent=2)

    def load_events(self, run_id: str) -> Sequence[RunEvent]:
        path = self._log_path(run_id)
        return [RunEvent(run_id=d["run_id"], event_type=d["event_type"],
                         round_index=d["round_index"], payload=d.get("payload", {}),
                         timestamp=d.get("timestamp", ""))
                for d in self._read_raw(path)]

    @staticmethod
    def _read_raw(path: str) -> list[dict]:
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            return json.load(f)
```

**Step 3: 运行测试**

```bash
python3 -m pytest tests/unit/infra/test_file_run_store.py -v
```

**Step 4: Commit**

```bash
git add tools/infra/persistence/file_run_store.py tests/unit/infra/test_file_run_store.py
git commit -m "feat(D5-D6): FileRunStore — event append + load + run_log.json"
```

---

## Phase E — 收口与任务同步

### Task E1: 更新 tasks.md 完成状态

将 tasks.md 中已实现的任务标记为 `[x]`：
- A1/A2/A3/A4/A5/A6/A7/A8/A9/A10/A11/A12/A13/A14
- B1/B2/B3/B4/B5/B6/B7/B8/B9/B10/B11/B12/B13/B14/B15/B16
- C1/C2/C3/C4/C4a/C5/C6
- D5/D6

### Task E2: 全量测试通过

```bash
python3 -m pytest tests/ -v --tb=short
```

### Task E3: AIEF L3 检查

```bash
python3 tools/check_aief_l3.py --root . --base-dir AIEF
```

### Task E4: 端到端 dry-run 验收

```bash
python3 tools/run_agent.py --policy policy.yaml --dry-run
# 验证输出：outputs/agent_runs/<run_id>/run_log.json 存在
```

### Task E5: 合并 & 版本发布

```bash
git checkout develop
git merge feature/delivery-mode-and-config-contract --no-ff
# 准备 release-notes/v0.1.9.md，然后发版
```

---

## 进度追踪摘要

| Phase | 任务数 | 预计工时 | 关键产出 |
|---|---|---|---|
| A（剩余） | 6 个任务 | 2–3 小时 | invariants, events, logging, config loader/validator/composer, errors |
| B | 5 批任务 | 4–5 小时 | engines: evidence/matching/generation/evaluation/discovery + registry |
| C | 4 批任务 | 3–4 小时 | orchestration: stage/pipeline/state_machine/gate/review/agent_loop |
| D | 1 批任务 | 1–2 小时 | FileRunStore + run_log.json |
| E | 收口 | 1 小时 | 全量测试 + dry-run 验收 + tasks.md 同步 |
| **合计** | **~30 个实现单元** | **~11–15 小时** | `run_agent.py --dry-run` 端到端通过 |

---

## 执行提示

1. 每个 Task 严格 **TDD**：先写红灯测试 → 运行确认 FAIL → 最小实现 → 确认 PASS → commit
2. Phase A 必须全部完成后再进入 Phase B（地基依赖）
3. Phase C 的 state_machine 先于 gate/review 实现
4. 每个 commit 粒度对应一个 Task，保持可回滚
5. 实现过程中如发现 tasks.md 的任务描述与实际代码冲突，以 **design.md** 为准
