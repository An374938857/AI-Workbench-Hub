"""
多 Skill 管理测试
测试多 Skill 组合、工具去重等功能
"""

import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.skill_activation_manager import SkillActivationManager


def test_combine_multiple_prompts():
    """测试多 Skill prompt 组合"""
    print("=== 测试: 多 Skill prompt 组合 ===")

    # 模拟多个 Skill
    skills = [
        {
            "id": 1,
            "name": "PRD 专家",
            "brief_desc": "擅长产品需求文档生成",
            "system_prompt": "你是 PRD 专家，帮助用户生成产品需求文档。",
        },
        {
            "id": 2,
            "name": "周报生成专家",
            "brief_desc": "擅长工作总结和周报撰写",
            "system_prompt": "你是周报生成专家，帮助用户撰写高质量的周报。",
        },
        {
            "id": 3,
            "name": "会议纪要专家",
            "brief_desc": "擅长会议内容整理",
            "system_prompt": "你是会议纪要专家，帮助用户整理会议要点。",
        },
    ]

    # 测试组合
    combined = SkillActivationManager.combine_multiple_prompts(skills)
    print(f"组合后的 prompt 长度: {len(combined)} 字符")
    print(f"组合内容预览:\n{combined[:500]}...")

    # 验证包含所有 Skill
    for skill in skills:
        assert skill["name"] in combined, f"应该包含 {skill['name']}"
        assert skill["system_prompt"] in combined, (
            f"应该包含 {skill['name']} 的 system_prompt"
        )

    print("✓ 多 Skill prompt 组合测试通过\n")


def test_combine_empty_skills():
    """测试空 Skill 列表组合"""
    print("=== 测试: 空 Skill 列表组合 ===")

    combined = SkillActivationManager.combine_multiple_prompts([])
    assert combined == "", "空列表应该返回空字符串"

    print("✓ 空 Skill 列表组合测试通过\n")


def test_combine_single_skill():
    """测试单个 Skill 组合"""
    print("=== 测试: 单个 Skill 组合 ===")

    skills = [
        {
            "id": 1,
            "name": "PRD 专家",
            "brief_desc": "擅长产品需求文档生成",
            "system_prompt": "你是 PRD 专家。",
        }
    ]

    combined = SkillActivationManager.combine_multiple_prompts(skills)
    assert "PRD 专家" in combined, "应该包含 Skill 名称"
    assert "你是 PRD 专家。" in combined, "应该包含 system_prompt"

    print("✓ 单个 Skill 组合测试通过\n")


def test_skill_order():
    """测试 Skill 组合顺序（最后激活的在最后）"""
    print("=== 测试: Skill 组合顺序 ===")

    skills = [
        {
            "id": 1,
            "name": "第一个技能",
            "brief_desc": "第一个",
            "system_prompt": "这是第一个技能。",
        },
        {
            "id": 2,
            "name": "第二个技能",
            "brief_desc": "第二个",
            "system_prompt": "这是第二个技能。",
        },
    ]

    combined = SkillActivationManager.combine_multiple_prompts(skills)

    # 检查顺序：第一个技能的 prompt 应该在第二个之前
    first_pos = combined.find("第一个技能")
    second_pos = combined.find("第二个技能")

    assert first_pos < second_pos, "第一个技能应该排在第二个技能之前"
    assert first_pos != -1, "应该找到第一个技能"
    assert second_pos != -1, "应该找到第二个技能"

    print("✓ Skill 组合顺序测试通过\n")


def test_tool_deduplication_mock():
    """测试工具去重逻辑（模拟）"""
    print("=== 测试: 工具去重逻辑 ===")

    # 模拟有重复工具的 Skill 列表
    skills = [
        {
            "id": 1,
            "name": "Skill A",
            "bound_mcps": [{"id": 1, "name": "MCP 1"}, {"id": 2, "name": "MCP 2"}],
        },
        {
            "id": 2,
            "name": "Skill B",
            "bound_mcps": [
                {"id": 2, "name": "MCP 2"},  # 重复
                {"id": 3, "name": "MCP 3"},
            ],
        },
    ]

    # 收集所有 MCP ID
    all_mcp_ids = set()
    for skill in skills:
        bound_mcps = skill.get("bound_mcps", [])
        for mcp in bound_mcps:
            if isinstance(mcp, dict) and "id" in mcp:
                all_mcp_ids.add(mcp["id"])

    # 验证去重
    assert len(all_mcp_ids) == 3, "应该有 3 个唯一的 MCP ID"
    assert all_mcp_ids == {1, 2, 3}, "MCP ID 应该是 1, 2, 3"

    print(f"✓ 工具去重逻辑测试通过（唯一 MCP 数: {len(all_mcp_ids)}）\n")


def test_max_active_skills():
    """测试最大激活数量限制"""
    print("=== 测试: 最大激活数量限制 ===")

    max_skills = SkillActivationManager.MAX_ACTIVE_SKILLS
    print(f"最大激活数量: {max_skills}")

    assert max_skills == 3, "最大激活数量应该是 3"

    print("✓ 最大激活数量限制测试通过\n")


def test_enforce_skill_limit_replaces_oldest():
    """测试超出上限时自动移除最早激活技能"""
    print("=== 测试: 超限自动替换最早技能 ===")

    active_ids = [11, 22, 33]
    removed_ids = SkillActivationManager.enforce_skill_limit(active_ids)
    active_ids.append(44)

    assert removed_ids == [11], "应移除最早激活的技能"
    assert active_ids == [22, 33, 44], "激活列表应保留最近三个技能"

    print("✓ 超限自动替换最早技能测试通过\n")


def test_prompt_format():
    """测试 prompt 格式正确性"""
    print("=== 测试: Prompt 格式 ===")

    skills = [
        {
            "id": 1,
            "name": "测试技能",
            "brief_desc": "用于测试",
            "system_prompt": "这是测试内容。",
        }
    ]

    combined = SkillActivationManager.combine_multiple_prompts(skills)

    # 验证格式
    assert "=== Skill 上下文 ===" in combined, "应该包含分隔符"
    assert "技能名称：" in combined, "应该包含'技能名称：'"
    assert "技能说明：" in combined, "应该包含'技能说明：'"
    assert "执行要求：" in combined, "应该包含'执行要求：'"

    print("✓ Prompt 格式测试通过\n")


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("多 Skill 管理测试")
    print("=" * 60)
    print()

    tests = [
        test_combine_multiple_prompts,
        test_combine_empty_skills,
        test_combine_single_skill,
        test_skill_order,
        test_tool_deduplication_mock,
        test_max_active_skills,
        test_enforce_skill_limit_replaces_oldest,
        test_prompt_format,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"✗ {test.__name__} 失败: {e}")
            import traceback

            traceback.print_exc()
            print()

    print("=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
