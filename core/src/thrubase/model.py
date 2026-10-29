"""Data model shared by every part of Thrubase, with JSON (de)serialization.

Every type is a plain dataclass. ``to_json``/``from_json`` round-trip them through plain
dicts, and ``json_schema`` derives a JSON Schema from the type hints so clients in other
languages can validate what core sends.
"""

from __future__ import annotations

import dataclasses
import json
import types
import typing
from dataclasses import dataclass, field
from typing import Any, Literal, TypeVar, Union, get_args, get_origin, get_type_hints

from . import SCHEMA_VERSION

NodeKind = Literal["module", "class", "function", "method"]
EdgeKind = Literal["call", "inherit", "ref"]
Role = Literal["entry", "summit", "isolated"]
SegmentStatus = Literal["passed", "weak", "skipped", "todo"]
CheckpointType = Literal["flow", "locate", "diff_edge"]
TrailKind = Literal["full", "diff"]


@dataclass
class Repo:
    root: str
    name: str
    snapshot: str
    files: int
    skipped: int
    languages: list[str] = field(default_factory=list)


@dataclass
class Node:
    id: str
    kind: NodeKind
    name: str
    qualname: str
    file: str
    start_line: int
    end_line: int
    loc: int
    h: float = 0.0
    x: float = 0.0
    y: float = 0.0
    role: Role | None = None
    entry_kind: str | None = None
    body_hash: str = ""


@dataclass
class Edge:
    src: str
    dst: str | None
    kind: EdgeKind
    line: int
    name: str
    resolved: bool = True
    #: target guessed from a unique method name; drawn on the map, never used for questions
    inferred: bool = False
    #: call into code outside the repository (stdlib, dependencies, builtins); dropped from the Map
    external: bool = False


@dataclass
class Stats:
    files: int
    skipped_files: int
    parse_errors: int
    calls: int
    external_calls: int
    resolved_calls: int
    #: resolved / (calls - external_calls)
    resolution_rate: float
    seconds: float = 0.0


@dataclass
class Map:
    repo: Repo
    nodes: list[Node]
    edges: list[Edge]
    entries: list[str]
    summits: list[str]
    isolated: list[str]
    stats: Stats
    weights: dict[str, float] = field(default_factory=dict)
    #: public API of a library (exports of top-level packages); reached even without a caller
    library: list[str] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION

    def node(self, node_id: str) -> Node:
        return self.node_index()[node_id]

    def node_index(self) -> dict[str, Node]:
        cache: dict[str, Node] | None = getattr(self, "_index", None)
        if cache is None or len(cache) != len(self.nodes):
            cache = {n.id: n for n in self.nodes}
            object.__setattr__(self, "_index", cache)
        return cache


@dataclass
class EdgeRef:
    src: str
    dst: str
    line: int


@dataclass
class GraphDiff:
    base: str
    changed_files: list[str]
    added_nodes: list[str]
    removed_nodes: list[str]
    changed_nodes: list[str]
    renamed: dict[str, str]
    added_edges: list[EdgeRef]
    removed_edges: list[EdgeRef]
    new_isolated: list[str]

    @property
    def touched(self) -> list[str]:
        """Current node ids whose code changed (added, changed or renamed)."""
        seen: dict[str, None] = {}
        for n in [*self.changed_nodes, *self.added_nodes, *self.renamed.values()]:
            seen[n] = None
        return list(seen)


@dataclass
class Option:
    id: str
    label: str


@dataclass
class Checkpoint:
    id: str
    type: CheckpointType
    prompt: str
    node: str
    options: list[Option] = field(default_factory=list)
    #: option id for flow/diff_edge; for locate, a list of [start, end] line ranges.
    answer: Any = None
    evidence_lines: list[int] = field(default_factory=list)
    hint: str = ""
    explanation: str = ""
    file: str = ""
    #: i18n message keys and parameters, so every text can be re-rendered in the viewer's language:
    #: {"prompt": [key, params], "hint": [key, params], "explanation": [[key, params], ...]}
    text: dict[str, Any] = field(default_factory=dict)

    def public(self) -> dict[str, Any]:
        """The checkpoint as sent to clients: never the answer, hint or explanation."""
        d: dict[str, Any] = to_json(self)
        for k in ("answer", "explanation", "hint", "evidence_lines", "text"):
            d.pop(k, None)
        return d


@dataclass
class Segment:
    order: int
    title: str
    file: str
    start_line: int
    end_line: int
    nodes: list[str]
    detour: bool = False
    changed: bool = False
    isolated: bool = False
    checkpoints: list[Checkpoint] = field(default_factory=list)

    @property
    def key(self) -> str:
        return "|".join(sorted(self.nodes))


@dataclass
class Trail:
    id: str
    kind: TrailKind
    snapshot: str
    segments: list[Segment]
    path: list[str]
    since: str | None = None
    diff: GraphDiff | None = None
    schema_version: int = SCHEMA_VERSION

    def segment(self, order: int) -> Segment:
        for s in self.segments:
            if s.order == order:
                return s
        raise KeyError(order)

    def checkpoint(self, checkpoint_id: str) -> tuple[Segment, Checkpoint]:
        for s in self.segments:
            for c in s.checkpoints:
                if c.id == checkpoint_id:
                    return s, c
        raise KeyError(checkpoint_id)

    def public(self) -> dict[str, Any]:
        d: dict[str, Any] = to_json(self)
        for seg, seg_d in zip(self.segments, d["segments"], strict=True):
            seg_d["checkpoints"] = [c.public() for c in seg.checkpoints]
        return d


@dataclass
class CheckpointState:
    attempts: int = 0
    state: Literal["idle", "hint", "passed", "revealed", "skipped"] = "idle"


@dataclass
class SegmentProgress:
    key: str
    status: SegmentStatus = "todo"
    checkpoints: dict[str, CheckpointState] = field(default_factory=dict)


@dataclass
class Progress:
    trail_id: str
    kind: TrailKind
    segments: dict[str, SegmentProgress] = field(default_factory=dict)
    current: int | None = None
    updated: float = 0.0


# --------------------------------------------------------------------------- JSON

T = TypeVar("T")


def to_json(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_json(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, dict):
        return {str(k): to_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_json(v) for v in obj]
    return obj


def _hints(cls: type) -> dict[str, Any]:
    return get_type_hints(cls, globalns=globals())


def _is_union(tp: Any) -> bool:
    return get_origin(tp) is Union or isinstance(tp, types.UnionType)


def _convert(tp: Any, value: Any) -> Any:
    if value is None:
        return None
    if tp is Any:
        return value
    if _is_union(tp):
        args = [a for a in get_args(tp) if a is not type(None)]
        if len(args) == 1:
            return _convert(args[0], value)
        return value
    origin = get_origin(tp)
    if origin is Literal:
        return value
    if origin in (list, typing.List):  # noqa: UP006
        (arg,) = get_args(tp) or (Any,)
        return [_convert(arg, v) for v in value]
    if origin in (dict, typing.Dict):  # noqa: UP006
        _, varg = get_args(tp) or (Any, Any)
        return {k: _convert(varg, v) for k, v in value.items()}
    if isinstance(tp, type) and dataclasses.is_dataclass(tp):
        return from_json(tp, value)
    if tp is float and isinstance(value, int):
        return float(value)
    return value


def from_json(cls: type[T], data: dict[str, Any]) -> T:
    hints = _hints(cls)
    kwargs: dict[str, Any] = {}
    for f in dataclasses.fields(cls):  # type: ignore[arg-type]
        if f.name in data:
            kwargs[f.name] = _convert(hints[f.name], data[f.name])
    return cls(**kwargs)


def dumps(obj: Any, *, indent: int | None = None) -> str:
    return json.dumps(to_json(obj), ensure_ascii=False, indent=indent, sort_keys=False)


# --------------------------------------------------------------------------- JSON Schema


def _schema_for(tp: Any, defs: dict[str, Any]) -> dict[str, Any]:
    if tp is Any:
        return {}
    if _is_union(tp):
        options = [_schema_for(a, defs) for a in get_args(tp)]
        return {"anyOf": options}
    if tp is type(None):
        return {"type": "null"}
    origin = get_origin(tp)
    if origin is Literal:
        return {"enum": list(get_args(tp))}
    if origin in (list, typing.List):  # noqa: UP006
        (arg,) = get_args(tp) or (Any,)
        return {"type": "array", "items": _schema_for(arg, defs)}
    if origin in (dict, typing.Dict):  # noqa: UP006
        _, varg = get_args(tp) or (Any, Any)
        return {"type": "object", "additionalProperties": _schema_for(varg, defs)}
    if tp is str:
        return {"type": "string"}
    if tp is bool:
        return {"type": "boolean"}
    if tp is int:
        return {"type": "integer"}
    if tp is float:
        return {"type": "number"}
    if isinstance(tp, type) and dataclasses.is_dataclass(tp):
        name = tp.__name__
        if name not in defs:
            defs[name] = {}  # placeholder against recursion
            hints = _hints(tp)
            props = {f.name: _schema_for(hints[f.name], defs) for f in dataclasses.fields(tp)}
            required = [
                f.name
                for f in dataclasses.fields(tp)
                if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
            ]
            defs[name] = {"type": "object", "properties": props, "required": required}
        return {"$ref": f"#/$defs/{name}"}
    raise TypeError(f"no schema for {tp!r}")


def json_schema() -> dict[str, Any]:
    """JSON Schema (2020-12) for the documents core produces: Map, Trail and Progress."""
    defs: dict[str, Any] = {}
    for cls in (Map, Trail, Progress):
        _schema_for(cls, defs)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://github.com/regx64/thrubase/schema/v{SCHEMA_VERSION}.json",
        "title": "Thrubase documents",
        "oneOf": [{"$ref": "#/$defs/Map"}, {"$ref": "#/$defs/Trail"}, {"$ref": "#/$defs/Progress"}],
        "$defs": defs,
    }
