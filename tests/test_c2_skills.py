"""Tests for Component 2: Skill Registry (IF-REQ-016)."""
from ironframe.skills.registry_v1_0 import SkillRegistry, SkillDefinition


def test_skill_registry_instantiates():
    reg = SkillRegistry()
    assert reg.summary()["total"] == 0


def test_skill_registers_with_metadata():
    reg = SkillRegistry()
    skill = SkillDefinition(name="test-skill", description="A test skill", tier="domain")
    reg._skills[skill.name] = skill
    assert reg.get("test-skill") is not None
    assert reg.get("test-skill").description == "A test skill"


def test_registered_skill_discoverable_by_id():
    reg = SkillRegistry()
    skill = SkillDefinition(name="finder-test", description="Find me", tier="core")
    reg._skills[skill.name] = skill
    found = reg.get("finder-test")
    assert found is not None
    assert found.name == "finder-test"


def test_skill_lookup_returns_none_for_unknown():
    reg = SkillRegistry()
    assert reg.get("nonexistent-skill") is None


def test_registry_lists_all_registered():
    reg = SkillRegistry()
    reg._skills["a"] = SkillDefinition(name="a", description="Skill A")
    reg._skills["b"] = SkillDefinition(name="b", description="Skill B")
    names = reg.list()
    assert "a" in names
    assert "b" in names
    assert len(names) == 2
