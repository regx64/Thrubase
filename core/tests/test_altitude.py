"""C8: altitude order on star, chain and cyclic graphs."""

import networkx as nx

from thrubase.engine.altitude import altitude, pagerank


def g(edges: list[tuple[str, str]]) -> nx.DiGraph:
    graph = nx.DiGraph()
    for a, b in edges:
        graph.add_edge(a, b, weight=1)
    return graph


def order(h: dict[str, float]) -> list[str]:
    return [k for k, _ in sorted(h.items(), key=lambda kv: (-kv[1], kv[0]))]


def test_star_center_is_highest() -> None:
    # Many callers of one helper, and one dispatcher calling many: both are hubs.
    graph = g([(f"c{i}", "hub") for i in range(6)])
    h = altitude(graph, {n: 10 for n in graph})
    assert order(h)[0] == "hub"
    assert max(h.values()) == 1.0 and min(h.values()) >= 0


def test_fan_out_driver_is_high() -> None:
    graph = g([("main", f"w{i}") for i in range(6)])
    h = altitude(graph, {n: 10 for n in graph})
    assert order(h)[0] == "main"


def test_chain_middle_vs_ends() -> None:
    graph = g([("a", "b"), ("b", "c"), ("c", "d"), ("d", "e")])
    h = altitude(graph, {n: 10 for n in graph})
    # Ends have only one direction of flow; the inner nodes collect both.
    assert h["c"] >= h["a"] and h["c"] >= h["e"]


def test_cycle_is_symmetric() -> None:
    graph = g([("a", "b"), ("b", "c"), ("c", "a")])
    h = altitude(graph, {n: 10 for n in graph})
    assert abs(h["a"] - h["b"]) < 1e-6 and abs(h["b"] - h["c"]) < 1e-6
    pr = pagerank(graph)
    assert abs(sum(pr.values()) - 1.0) < 1e-9


def test_loc_and_weights_matter() -> None:
    graph = g([("a", "x"), ("b", "y")])
    h = altitude(graph, {"a": 1, "b": 1, "x": 1, "y": 500})
    assert h["y"] > h["x"]
    h2 = altitude(graph, {"a": 1, "b": 1, "x": 1, "y": 500}, {"alpha": 1, "beta": 0, "gamma": 0})
    assert abs(h2["y"] - h2["x"]) < 1e-9


def test_empty_graph() -> None:
    assert altitude(nx.DiGraph(), {}) == {}
