"""Tests for Component 14: Multi-Agent Coordination."""
import pytest

from ironframe.coordination.messages_v1_0 import (
    AgentMessage, MessageType, create_message,
)
from ironframe.coordination.tasks_v1_0 import TaskGraph, SubTask, CircularDependency


def test_create_message_valid_fields():
    msg = create_message(
        sender_id="agent-A",
        sender_trust_tier=2,
        receiver_id="agent-B",
        message_type=MessageType.ASSIGNMENT.value,
        payload={"task_id": "t1"},
    )
    assert msg.sender_id == "agent-A"
    assert msg.sender_trust_tier == 2
    assert msg.receiver_id == "agent-B"
    assert msg.message_type == "ASSIGNMENT"
    assert msg.message_id  # auto-generated
    assert msg.timestamp   # auto-generated


def test_effective_tier_returns_min():
    msg = create_message(
        sender_id="agent-A",
        sender_trust_tier=2,
        receiver_id="agent-B",
        message_type=MessageType.ASSIGNMENT.value,
    )
    assert msg.effective_tier_for_receiver(3) == 2
    assert msg.effective_tier_for_receiver(1) == 1
    assert msg.effective_tier_for_receiver(2) == 2


def test_effective_tier_no_escalation():
    msg = create_message(
        sender_id="low-trust",
        sender_trust_tier=1,
        receiver_id="high-trust",
        message_type=MessageType.QUERY.value,
    )
    assert msg.effective_tier_for_receiver(4) == 1


def test_task_graph_topological_sort():
    graph = TaskGraph()
    graph.add_task(SubTask(task_id="A", dependencies=[]))
    graph.add_task(SubTask(task_id="B", dependencies=["A"]))
    graph.add_task(SubTask(task_id="C", dependencies=["B"]))
    graph.compute_all_priorities()
    a = graph.get_task("A")
    c = graph.get_task("C")
    assert a.priority >= c.priority


def test_task_graph_rejects_cycle():
    graph = TaskGraph()
    graph.add_task(SubTask(task_id="X", dependencies=[]))
    graph.add_task(SubTask(task_id="Y", dependencies=["X"]))
    with pytest.raises(CircularDependency):
        graph.add_task(SubTask(task_id="X2", task_type="", dependencies=["Y"]))
        graph.add_task(SubTask(task_id="Z", dependencies=["X2"]))
        # Force cycle: add X depending on Z
        graph._tasks["X"].dependencies = ["Z"]
        graph._topological_sort()


def test_task_graph_ready_tasks():
    graph = TaskGraph()
    graph.add_task(SubTask(task_id="A", dependencies=[]))
    graph.add_task(SubTask(task_id="B", dependencies=["A"]))
    ready = graph.ready_tasks()
    assert any(t.task_id == "A" for t in ready)
    assert not any(t.task_id == "B" for t in ready)


def test_broadcast_message():
    msg = create_message(
        sender_id="orchestrator",
        sender_trust_tier=3,
        receiver_id="BROADCAST",
        message_type=MessageType.HALT.value,
    )
    assert msg.is_broadcast
