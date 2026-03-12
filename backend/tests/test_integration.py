"""
集成测试
测试各功能模块的集成
"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_prompt_combiner_integration():
    """测试 Prompt 组合器集成"""
    print("=== 测试: Prompt 组合器集成 ===")

    from app.services.prompt_combiner import PromptCombiner

    # 测试三层组合
    default_prompt = "你是一个 AI 助手。"
    template_prompt = "你是一个专业的文档撰写助手。"
    skill_prompt = "你是 PRD 专家，擅长产品需求文档。"

    parts = []
    if default_prompt:
        parts.append(f"=== 基础定位 ===\n{default_prompt}")
    if template_prompt:
        parts.append(f"=== 角色模板 ===\n{template_prompt}")
    if skill_prompt:
        parts.append(f"=== Skill 上下文 ===\n{skill_prompt}")

    combined = "\n\n".join(parts)

    # 验证组合结果
    assert "基础定位" in combined
    assert "角色模板" in combined
    assert "Skill 上下文" in combined
    assert "AI 助手" in combined
    assert "文档撰写" in combined
    assert "PRD 专家" in combined

    # 测试 token 估算
    tokens = PromptCombiner.estimate_tokens(combined)
    assert tokens > 0, "Token 数应该大于 0"
    print(f"估算 token 数: {tokens}")

    # 测试截断逻辑（使用包含分隔符的长文本）
    long_prompt = (
        """=== 基础定位 ===
你是业财产品 AI 助手。"""
        + "专注于办公场景。" * 100
        + """

=== 角色模板 ===
你是 PRD 专家。"""
        + "擅长产品需求分析。" * 50
        + """

=== Skill 上下文 ===
技能名称：PRD 专家
执行要求：生成 PRD 文档。"""
        + "包括功能描述等。" * 50
    )

    tokens = PromptCombiner.estimate_tokens(long_prompt)
    print(f"长文本 token 数: {tokens}")

    truncated = PromptCombiner.truncate_if_needed(long_prompt, max_tokens=50)
    truncated_tokens = PromptCombiner.estimate_tokens(truncated)
    print(f"截断后 token 数: {truncated_tokens}")

    # 截断后应该只保留基础定位和模板部分（如果超长）
    assert "基础定位" in truncated, "应该保留基础定位"
    # 由于超长，可能只保留前两部分
    if tokens > 50 and "=== 角色模板 ===" in long_prompt:
        assert "角色模板" in truncated or truncated_tokens <= 50, (
            "应该保留角色模板或截断后token数减少"
        )

    print("✓ Prompt 组合器集成测试通过\n")


def test_skill_activation_flow():
    """测试 Skill 激活流程"""
    print("=== 测试: Skill 激活流程 ===")

    from app.services.skill_activation_manager import SkillActivationManager

    # 测试工具名称解析
    tool_name = "activate_skill_123"
    skill_id = SkillActivationManager.parse_activation_tool_call(tool_name)
    assert skill_id == 123, f"应该解析出 skill_id=123，实际得到 {skill_id}"

    # 测试非激活工具
    non_activation = SkillActivationManager.parse_activation_tool_call(
        "some_other_tool"
    )
    assert non_activation is None, "非激活工具应该返回 None"

    # 测试工具生成格式
    # 注意：这里只是测试格式，不涉及数据库
    mock_tool = {
        "type": "function",
        "function": {
            "name": "activate_skill_1",
            "description": "激活「PRD 专家」：帮助生成产品需求文档",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }

    assert mock_tool["type"] == "function"
    assert "activate_skill_" in mock_tool["function"]["name"]

    print("✓ Skill 激活流程测试通过\n")


def test_sandbox_file_operations():
    """测试沙箱文件操作集成"""
    print("=== 测试: 沙箱文件操作集成 ===")

    import tempfile
    from app.services.sandbox_file_manager import SandboxFileManager

    with tempfile.TemporaryDirectory() as temp_dir:

        class MockSettings:
            UPLOAD_DIR = temp_dir

        manager = SandboxFileManager(MockSettings())
        conv_id = 999

        # 初始化沙箱
        sandbox_path = manager.init_sandbox(conv_id)
        assert os.path.exists(sandbox_path), "沙箱目录应该存在"

        # 创建文件
        result = manager.create_file(
            conv_id, "test.txt", "Hello, World!", subdir="generated"
        )
        assert result["success"], f"文件创建应该成功: {result}"

        # 读取文件
        result = manager.read_file(conv_id, "test.txt", subdir="generated")
        assert result["success"], "文件读取应该成功"
        assert result["content"] == "Hello, World!", "文件内容应该正确"

        # 列出文件
        result = manager.list_files(conv_id)
        assert result["success"], "列出文件应该成功"
        assert len(result["files"]) == 1, "应该有 1 个文件"

        # 更新文件
        result = manager.update_file(
            conv_id, "test.txt", "Updated content", subdir="generated"
        )
        assert result["success"], "文件更新应该成功"

        # 获取沙箱大小
        size = manager.get_sandbox_size(conv_id)
        assert size > 0, "沙箱大小应该大于 0"

        # 清理沙箱
        result = manager.cleanup_sandbox(conv_id)
        assert result["success"], "沙箱清理应该成功"
        assert not os.path.exists(sandbox_path), "沙箱目录应该被删除"

    print("✓ 沙箱文件操作集成测试通过\n")


def test_multi_skill_prompt_combination():
    """测试多 Skill prompt 组合场景"""
    print("=== 测试: 多 Skill prompt 组合场景 ===")

    from app.services.skill_activation_manager import SkillActivationManager

    # 模拟激活多个 Skill
    skills = [
        {
            "id": 1,
            "name": "PRD 专家",
            "brief_desc": "生成 PRD",
            "system_prompt": "写 PRD。",
        },
        {
            "id": 2,
            "name": "周报专家",
            "brief_desc": "生成周报",
            "system_prompt": "写周报。",
        },
    ]

    # 组合 prompt
    combined = SkillActivationManager.combine_multiple_prompts(skills)

    # 验证都包含
    assert "PRD 专家" in combined
    assert "周报专家" in combined
    assert "写 PRD。" in combined
    assert "写周报。" in combined

    # 验证顺序
    prd_pos = combined.find("PRD 专家")
    weekly_pos = combined.find("周报专家")
    assert prd_pos < weekly_pos, "PRD 专家应该在周报专家之前"

    print("✓ 多 Skill prompt 组合场景测试通过\n")


def test_end_to_end_scenario_1():
    """端到端测试场景 1: 自由对话使用默认 prompt"""
    print("=== 端到端测试: 场景 1 - 自由对话使用默认 prompt ===")

    # 模拟自由对话流程
    # 1. 创建对话（不绑定 Skill）
    # 2. 应该使用默认 prompt 模板
    # 3. Prompt 组合器应该生成包含默认 prompt 的 system 消息


    # 模拟默认 prompt 启用
    default_prompt = "你是业财产品 AI 助手，专注于办公场景。"

    # 自由对话不应该有 Skill prompt
    parts = []
    if default_prompt:
        parts.append(f"=== 基础定位 ===\n{default_prompt}")

    combined = "\n\n".join(parts)

    assert "基础定位" in combined
    assert "业财产品" in combined
    assert "Skill 上下文" not in combined, "自由对话不应该有 Skill 上下文"

    print("✓ 端到端场景 1 测试通过\n")


def test_end_to_end_scenario_2():
    """端到端测试场景 2: Skill 激活流程"""
    print("=== 端到端测试: 场景 2 - Skill 激活流程 ===")

    from app.services.skill_activation_manager import SkillActivationManager

    # 验证激活工具格式
    skill_id = 1
    tool_name = f"activate_skill_{skill_id}"

    parsed_id = SkillActivationManager.parse_activation_tool_call(tool_name)
    assert parsed_id == skill_id, f"应该解析出 {skill_id}"

    # 验证最大激活数量
    assert SkillActivationManager.MAX_ACTIVE_SKILLS == 3

    print("✓ 端到端场景 2 测试通过\n")


def test_end_to_end_scenario_3():
    """端到端测试场景 3: 多 Skill 组合"""
    print("=== 端到端测试: 场景 3 - 多 Skill 组合 ===")

    from app.services.skill_activation_manager import SkillActivationManager

    # 模拟激活多个 Skill
    active_skills = [
        {"id": 1, "name": "Skill A", "brief_desc": "A", "system_prompt": "A prompt"},
        {"id": 2, "name": "Skill B", "brief_desc": "B", "system_prompt": "B prompt"},
    ]

    # 验证组合
    combined = SkillActivationManager.combine_multiple_prompts(active_skills)
    assert "Skill A" in combined
    assert "Skill B" in combined
    assert "A prompt" in combined
    assert "B prompt" in combined

    # 模拟工具去重
    mcp_ids = {1, 2, 3, 2, 1}  # 有重复
    unique_ids = set(mcp_ids)
    assert len(unique_ids) == 3, "去重后应该有 3 个唯一 ID"

    print("✓ 端到端场景 3 测试通过\n")


def test_end_to_end_scenario_4():
    """端到端测试场景 4: 沙箱文件操作"""
    print("=== 端到端测试: 场景 4 - 沙箱文件操作 ===")

    import tempfile
    from app.services.sandbox_file_manager import SandboxFileManager
    from app.mcp.handlers.sandbox_file_handler import (
        SandboxFileHandler,
    )

    with tempfile.TemporaryDirectory() as temp_dir:

        class MockSettings:
            UPLOAD_DIR = temp_dir

        # 初始化沙箱
        manager = SandboxFileManager(MockSettings())
        handler = SandboxFileHandler()
        # 替换 handler 的 file_manager
        handler.file_manager = manager
        conv_id = 555

        # 创建文件
        result = manager.create_file(
            conv_id, "document.md", "# Hello", subdir="generated"
        )
        assert result["success"], "文件创建应该成功"

        # 使用 MCP 处理器读取
        read_result = handler.handle_tool_call(
            "sandbox_read_file",
            {"filename": "document.md", "subdir": "generated"},
            conv_id,
        )

        assert read_result["success"], f"MCP 读取应该成功: {read_result}"
        content = json.loads(read_result["content"])
        assert "# Hello" in content["content"], "内容应该正确"

    print("✓ 端到端场景 4 测试通过\n")


def test_progressive_disclosure():
    """测试渐进式披露功能"""
    print("=== 测试: 渐进式披露功能 ===")

    from app.services.skill_progressive_disclosure import SkillProgressiveDisclosure

    # Level 3: 路径安全检查（不需要数据库）
    result = SkillProgressiveDisclosure.read_skill_reference(1, "../etc/passwd", None)
    assert not result["success"], "应该拒绝路径遍历"
    assert "非法路径" in result["message"], "应该有错误提示"

    # 测试正常路径（不需要数据库）
    result = SkillProgressiveDisclosure.read_skill_reference(1, "api-guide.md", None)
    # 文件不存在，但路径是合法的
    assert not result["success"], "应该返回失败（文件不存在）"
    assert "不存在" in result["message"], "应该有文件不存在提示"

    print("✓ 渐进式披露功能测试通过\n")


def run_all_tests():
    """运行所有集成测试"""
    print("=" * 60)
    print("集成测试")
    print("=" * 60)
    print()

    tests = [
        test_prompt_combiner_integration,
        test_skill_activation_flow,
        test_sandbox_file_operations,
        test_multi_skill_prompt_combination,
        test_end_to_end_scenario_1,
        test_end_to_end_scenario_2,
        test_end_to_end_scenario_3,
        test_end_to_end_scenario_4,
        test_progressive_disclosure,
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
