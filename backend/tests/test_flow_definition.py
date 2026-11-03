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


def test_marker_must_be_reached_on_every_path() -> None:
    def optional_marker(d: dict[str, Any]) -> None:
        d["nodes"] = [
            {"id": "a", "type": "goto", "url": "http://x/login"},
            {"id": "b", "type": "branch", "if_visible": "#banner"},
            {"id": "m", "type": "wait_for", "selector": ".me", "role": "logged_in_marker"},
            {"id": "s", "type": "save_session"},
            {"id": "end", "type": "click", "selector": "#done"},
        ]
        d["edges"] = [["a", "b"], ["b", "m", "yes"], ["b", "end", "no"], ["m", "s"]]

    with pytest.raises(ValidationError, match="every path"):
        load(optional_marker)


def test_flow_without_save_session_is_rejected() -> None:
    def drop(d: dict[str, Any]) -> None:
        d["nodes"].pop()

    with pytest.raises(ValidationError, match="save_session"):
        load(drop)


def test_draft_may_omit_the_logged_in_marker_and_save_session() -> None:
    data = deepcopy(sample_flow_dict())
    data["nodes"] = data["nodes"][:-2]
    data["edges"] = data["edges"][:-2]
    flow = FlowDefinition.model_validate(data, context={"draft": True})
    assert [node.id for node in flow.nodes][-1] == "n8"


def test_label_on_a_non_branch_edge_is_rejected() -> None:
    def label(d: dict[str, Any]) -> None:
        d["edges"][0] = ["n1", "n2", "yes"]

    with pytest.raises(ValidationError, match="only branch"):
        load(label)


def test_cycle_apart_from_the_main_path_is_rejected() -> None:
    def island(d: dict[str, Any]) -> None:
        d["nodes"] += [{"id": "c", "type": "save_session"}, {"id": "d", "type": "save_session"}]
        d["edges"] += [["c", "d"], ["d", "c"]]

    with pytest.raises(ValidationError, match="cycle|start"):
        load(island)


def test_many_sequential_branches_load_quickly() -> None:
    def diamonds(d: dict[str, Any]) -> None:
        nodes: list[dict[str, Any]] = [{"id": "s0", "type": "goto", "url": "http://x/"}]
        edges: list[list[str]] = []
        previous = "s0"
        for i in range(40):
            nodes += [
                {"id": f"b{i}", "type": "branch", "if_visible": "#x"},
                {"id": f"y{i}", "type": "click", "selector": "#y"},
                {"id": f"j{i}", "type": "click", "selector": "#j"},
            ]
            edges += [[previous, f"b{i}"], [f"b{i}", f"y{i}", "yes"], [f"b{i}", f"j{i}", "no"],
                      [f"y{i}", f"j{i}"]]
            previous = f"j{i}"
        nodes += [
            {"id": "m", "type": "wait_for", "selector": ".me", "role": "logged_in_marker"},
            {"id": "s", "type": "save_session"},
        ]
        edges += [[previous, "m"], ["m", "s"]]
        d["nodes"], d["edges"] = nodes, edges

    assert len(load(diamonds).nodes) > 100


def test_email_code_without_email_settings_is_rejected() -> None:
    def no_email(d: dict[str, Any]) -> None:
        del d["nodes"][5]["email"]

    with pytest.raises(ValidationError, match="email"):
        load(no_email)


def test_template_outside_fill_is_rejected() -> None:
    def in_url(d: dict[str, Any]) -> None:
        d["nodes"][0]["url"] = "http://x/login?u={{credentials.username}}"

    with pytest.raises(ValidationError, match="only supported in fill"):
        load(in_url)


def test_an_empty_stock_selector_is_refused_when_saving() -> None:
    def empty(d: dict[str, Any]) -> None:
        d["extract"]["stock_selector"] = ""

    with pytest.raises(ValidationError, match="stock_selector"):
        load(empty)


def test_an_empty_stock_selector_is_allowed_in_a_draft() -> None:
    data = deepcopy(sample_flow_dict())
    data["extract"]["stock_selector"] = ""
    flow = FlowDefinition.model_validate(data, context={"draft": True})
    assert flow.extract.stock_selector == ""


@pytest.mark.parametrize(
    ("stop", "expected"),
    [(None, True), ("n1", False), ("n2", True), ("n4", True)],
)
def test_credentials_are_only_needed_by_the_steps_that_will_run(
    stop: str | None, expected: bool
) -> None:
    assert load().uses_credentials(stop) is expected
