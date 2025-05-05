# tests/test_topology.py
"""
Topology helper tests: generator and YAML loader.
"""
import yaml

from topo import random_connected, load_yaml


def test_random_connected_is_undirected_and_connected():
    topo = random_connected(8, 3.0, seed=123)

    # Every edge appears exactly once in the stored set
    for a, b in topo.edges:
        assert (b, a) not in topo.edges

    # Undirected property reflected in neighbour_map
    for a, b in topo.edges:
        assert a in topo.neighbour_map[b]
        assert b in topo.neighbour_map[a]

    # Connectivity via BFS/DFS
    start = next(iter(topo.agents))
    visited = set()
    stack = [start]
    while stack:
        node = stack.pop()
        if node in visited:
            continue
        visited.add(node)
        stack.extend(topo.neighbour_map[node])

    assert visited == set(topo.agents)


def test_yaml_round_trip(tmp_path):
    """
    Write a generated topology to YAML,
    then reload and compare edges.
    """
    topo1 = random_connected(5, 2.0, seed=9)

    yaml_path = tmp_path / "g.yaml"
    data = {"agents": list(topo1.agents), "edges": [list(e) for e in topo1.edges]}
    yaml_path.write_text(yaml.safe_dump(data), encoding="utf-8")

    topo2 = load_yaml(str(yaml_path))
    assert topo1.edges == topo2.edges
