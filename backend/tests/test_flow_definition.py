import json
from copy import deepcopy
from typing import Any

import pytest
from pydantic import ValidationError

from app.flows.definition import FlowDefinition
from tests.fakes import sample_flow_dict


def load(mutate: Any = None) -> FlowDefinition:
    data = deepcopy(sample_flow_dict())
    if mutate:
        mutate(data)
    return FlowDefinition.model_validate(json.loads(json.dumps(data)))


def test_plan_example_loads() -> None:
    flow = load()
    assert flow.supplier == "supplier-a"
    assert [n.type for n in flow.nodes][:3] == ["goto", "fill", "fill"]


def test_start_node_is_the_one_with_no_incoming_edge() -> None:
    assert load().start.id == "n1"


def test_logged_in_marker_comes_from_the_wait_for_node() -> None:
    assert load().logged_in_marker == ".me"


def test_unknown_node_type_is_rejected() -> None:
    with pytest.raises(ValidationError):
        load(lambda d: d["nodes"].append({"id": "n11", "type": "teleport"}))


def test_duplicate_node_ids_are_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate"):
        load(lambda d: d["nodes"].append({"id": "n1", "type": "save_session"}))


def test_edge_to_a_missing_node_is_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown node"):
        load(lambda d: d["edges"].append(["n10", "nope"]))


def test_cycle_is_rejected() -> None:
    with pytest.raises(ValidationError, match="cycle"):
        load(lambda d: d["edges"].append(["n10", "n2"]))


def test_node_with_two_plain_outgoing_edges_is_rejected() -> None:
    with pytest.raises(ValidationError, match="more than one"):
        load(lambda d: d["edges"].append(["n1", "n3"]))


def test_flow_without_a_logged_in_marker_is_rejected() -> None:
    def drop_role(d: dict[str, Any]) -> None:
        del d["nodes"][8]["role"]

    with pytest.raises(ValidationError, match="logged_in_marker"):
        load(drop_role)


def test_unknown_template_variable_is_rejected() -> None:
    def typo(d: dict[str, Any]) -> None:
        d["nodes"][1]["value"] = "{{credentials.usernam}}"

    with pytest.raises(ValidationError, match="credentials.usernam"):
        load(typo)


def test_empty_condition_text_is_rejected() -> None:
    with pytest.raises(ValidationError):
        load(lambda d: d.update(blocked_if={"contains": ""}))


def test_branch_needs_both_yes_and_no_edges() -> None:
    def branch(d: dict[str, Any]) -> None:
        d["nodes"].append({"id": "b1", "type": "branch", "if_visible": "#x"})
        d["edges"].append(["n10", "b1"])
        d["edges"].append(["b1", "n10", "yes"])

    with pytest.raises(ValidationError, match="yes and a no"):
        load(branch)
