"""
沙箱文件管理器单元测试
测试 SandboxFileManager 的核心功能
"""
import os
import tempfile
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.sandbox_file_manager import SandboxFileManager


def test_sandbox_file_manager():
    """测试沙箱文件管理器的核心功能"""

    # 创建临时目录作为沙箱基础目录
    with tempfile.TemporaryDirectory() as temp_dir:
        # 修改设置
        class MockSettings:
            UPLOAD_DIR = temp_dir

        file_manager = SandboxFileManager(MockSettings())

        conversation_id = 123

        print("=== 测试 1: 初始化沙箱 ===")
        sandbox_path = file_manager.init_sandbox(conversation_id)
        print(f"沙箱路径: {sandbox_path}")
        assert os.path.exists(sandbox_path), "沙箱目录应该存在"
        assert os.path.exists(os.path.join(sandbox_path, "uploads")), "uploads 子目录应该存在"
        assert os.path.exists(os.path.join(sandbox_path, "generated")), "generated 子目录应该存在"
        assert os.path.exists(os.path.join(sandbox_path, "skills")), "skills 子目录应该存在"
        print("✓ 沙箱初始化成功\n")

        print("=== 测试 2: 创建文件 ===")
        result = file_manager.create_file(
            conversation_id,
            "test.txt",
            "Hello, World!",
            subdir="uploads"
        )
        print(f"创建结果: {result}")
        assert result["success"], "文件创建应该成功"
        assert result["size"] > 0, "文件大小应该大于0"
        print("✓ 文件创建成功\n")

        print("=== 测试 3: 读取文件 ===")
        result = file_manager.read_file(
            conversation_id,
            "test.txt",
            subdir="uploads"
        )
        print(f"读取结果: {result}")
        assert result["success"], "文件读取应该成功"
        assert result["content"] == "Hello, World!", "文件内容应该正确"
        assert result["message"] == "文件读取成功", "正常按 subdir 命中时不应误报路径自动纠正"
        print("✓ 文件读取成功\n")

        print("=== 测试 3.1: 不指定子目录读取文件 ===")
        result = file_manager.read_file(
            conversation_id,
            "test.txt"
        )
        print(f"读取结果: {result}")
        assert result["success"], "未指定子目录时也应该能读取成功"
        assert result["content"] == "Hello, World!", "文件内容应该正确"
        print("✓ 子目录自动兜底读取成功\n")

        print("=== 测试 4: 列出文件 ===")
        result = file_manager.list_files(conversation_id)
        print(f"列出结果: {result}")
        assert result["success"], "文件列表获取应该成功"
        assert len(result["files"]) == 1, "应该有1个文件"
        assert result["files"][0]["filename"] == "test.txt", "文件名应该正确"
        print("✓ 文件列表获取成功\n")

        print("=== 测试 4.0: 支持自定义子目录 ===")
        result = file_manager.create_file(
            conversation_id,
            "result.md",
            "# Result",
            subdir="workspace/output"
        )
        print(f"创建结果: {result}")
        assert result["success"], "自定义子目录文件创建应该成功"
        custom_list = file_manager.list_files(conversation_id, "workspace")
        print(f"列出结果: {custom_list}")
        assert custom_list["success"], "自定义目录列出应该成功"
        custom_paths = {item["sandbox_path"] for item in custom_list["files"]}
        assert "workspace/output/result.md" in custom_paths, "应包含自定义目录文件"
        print("✓ 自定义子目录支持成功\n")

        print("=== 测试 4.1: 复制技能目录到沙箱并递归列出 ===")
        package_dir = os.path.join(temp_dir, "skill_pkg")
        os.makedirs(os.path.join(package_dir, "references"), exist_ok=True)
        with open(os.path.join(package_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("---\nname: weekly-report\n---\n# Skill")
        with open(
            os.path.join(package_dir, "references", "template-structure.md"),
            "w",
            encoding="utf-8",
        ) as f:
            f.write("template")

        copy_result = file_manager.copy_skill_directory(
            conversation_id, 8, package_dir
        )
        print(f"复制结果: {copy_result}")
        assert copy_result["success"], "技能目录复制应该成功"

        nested_list = file_manager.list_files(conversation_id, "skills")
        print(f"递归列出结果: {nested_list}")
        assert nested_list["success"], "递归列出应该成功"
        relative_paths = {item["relative_path"] for item in nested_list["files"]}
        assert "weekly-report/SKILL.md" in relative_paths, "应该包含挂载后的 SKILL.md"
        assert (
            "weekly-report/references/template-structure.md" in relative_paths
        ), "应该包含挂载后的模板文件"
        nested_item = next(
            item
            for item in nested_list["files"]
            if item["relative_path"] == "weekly-report/references/template-structure.md"
        )
        assert (
            nested_item["sandbox_path"]
            == "skills/weekly-report/references/template-structure.md"
        ), "sandbox_path 应保留完整嵌套路径"
        print("✓ 技能目录复制与递归列出成功\n")

        print("=== 测试 4.2: 兼容旧 references 目录读取 ===")
        legacy_root = os.path.join(sandbox_path, "references", "legacy-skill")
        os.makedirs(legacy_root, exist_ok=True)
        with open(os.path.join(legacy_root, "legacy.md"), "w", encoding="utf-8") as f:
            f.write("legacy")

        legacy_read = file_manager.read_file(
            conversation_id,
            "legacy-skill/legacy.md",
            subdir="skills",
        )
        print(f"读取结果: {legacy_read}")
        assert legacy_read["success"], "skills 子目录读取应兼容 references 历史路径"
        assert legacy_read["content"] == "legacy", "兼容读取内容应正确"

        legacy_list = file_manager.list_files(conversation_id, "skills")
        legacy_relative_paths = {item["relative_path"] for item in legacy_list["files"]}
        assert "legacy-skill/legacy.md" in legacy_relative_paths, "skills 列表应兼容展示 references 历史文件"
        print("✓ 兼容旧 references 目录读取成功\n")

        print("=== 测试 4.3: 兼容重复 skills 前缀参数 ===")
        duplicated_prefix_read = file_manager.read_file(
            conversation_id,
            "skills/weekly-report/SKILL.md",
            subdir="skills",
        )
        print(f"读取结果: {duplicated_prefix_read}")
        assert duplicated_prefix_read["success"], "重复 skills 前缀时应自动归一化后读取成功"

        duplicated_mount_read = file_manager.read_file(
            conversation_id,
            "weekly-report/references/template-structure.md",
            subdir="skills/weekly-report",
        )
        print(f"读取结果: {duplicated_mount_read}")
        assert (
            duplicated_mount_read["success"]
        ), "subdir 包含挂载目录且 filename 再带挂载目录时应自动归一化"

        sandbox_prefixed_subdir_read = file_manager.read_file(
            conversation_id,
            "weekly-report/SKILL.md",
            subdir="sandbox/123/skills",
        )
        print(f"读取结果: {sandbox_prefixed_subdir_read}")
        assert (
            sandbox_prefixed_subdir_read["success"]
        ), "subdir 包含 sandbox/{conversation_id} 前缀时应自动归一化"

        duplicated_prefix_list = file_manager.list_files(
            conversation_id, "sandbox/123/skills"
        )
        print(f"列出结果: {duplicated_prefix_list}")
        assert duplicated_prefix_list["success"], "带 sandbox 前缀的目录参数应兼容"
        duplicated_paths = {item["relative_path"] for item in duplicated_prefix_list["files"]}
        assert "weekly-report/SKILL.md" in duplicated_paths, "应能列出 skills 目录文件"
        print("✓ 重复前缀参数兼容成功\n")

        print("=== 测试 4.4: 非 skills 子目录仍可正常读写 ===")
        generated_create = file_manager.create_file(
            conversation_id,
            "generated-notes.md",
            "non-skill content",
            subdir="generated",
        )
        assert generated_create["success"], "generated 子目录创建应成功"

        generated_read = file_manager.read_file(
            conversation_id,
            "generated-notes.md",
            subdir="generated",
        )
        assert generated_read["success"], "generated 子目录读取应成功"
        assert generated_read["content"] == "non-skill content", "generated 内容应正确"

        generated_read_with_prefix = file_manager.read_file(
            conversation_id,
            "generated/generated-notes.md",
            subdir="generated",
        )
        assert generated_read_with_prefix["success"], "generated 重复前缀参数应兼容"

        generated_list = file_manager.list_files(conversation_id, "generated")
        assert generated_list["success"], "generated 列表应成功"
        generated_rel_paths = {item["relative_path"] for item in generated_list["files"]}
        assert "generated-notes.md" in generated_rel_paths, "generated 列表应包含文件"
        print("✓ 非 skills 子目录读写兼容成功\n")

        print("=== 测试 4.5: 路径错误时按文件名全沙箱唯一命中兜底 ===")
        single_match_result = file_manager.read_file(
            conversation_id,
            "weekly-report/custom/generated-notes.md",
            subdir="skills/weekly-report",
        )
        print(f"读取结果: {single_match_result}")
        assert single_match_result["success"], "路径错误但唯一同名时应自动纠正读取成功"
        assert "路径自动纠正" in single_match_result["message"], "应明确告知发生了路径自动纠正"
        assert (
            single_match_result["resolved_path"]
            == "generated/generated-notes.md"
        ), "应返回实际读取路径"

        print("=== 测试 4.6: 路径错误且多同名时返回冲突提示 ===")
        create_a = file_manager.create_file(
            conversation_id,
            "nested-a/duplicate.md",
            "A",
            subdir="generated",
        )
        assert create_a["success"], "创建 duplicate A 应成功"
        create_b = file_manager.create_file(
            conversation_id,
            "nested-b/duplicate.md",
            "B",
            subdir="uploads",
        )
        assert create_b["success"], "创建 duplicate B 应成功"

        multiple_match_result = file_manager.read_file(
            conversation_id,
            "missing/duplicate.md",
            subdir="skills",
        )
        print(f"读取结果: {multiple_match_result}")
        assert not multiple_match_result["success"], "多同名时不应盲目读取"
        assert "多个同名文件" in multiple_match_result["message"], "应返回多同名冲突提示"

        print("=== 测试 5: 更新文件 ===")
        result = file_manager.update_file(
            conversation_id,
            "test.txt",
            "Updated content",
            subdir="uploads"
        )
        print(f"更新结果: {result}")
        assert result["success"], "文件更新应该成功"
        print("✓ 文件更新成功\n")

        print("=== 测试 6: 获取沙箱大小 ===")
        size = file_manager.get_sandbox_size(conversation_id)
        print(f"沙箱大小: {size} bytes")
        assert size > 0, "沙箱大小应该大于0"
        print("✓ 沙箱大小获取成功\n")

        print("=== 测试 7: 文件名验证 ===")
        try:
            file_manager.create_file(conversation_id, "../etc/passwd", "test")
            print("✗ 文件名验证失败：应该拒绝包含 .. 的文件名")
        except ValueError as e:
            print(f"✓ 文件名验证成功: {e}\n")

        print("=== 测试 8: 删除文件 ===")
        result = file_manager.delete_file(
            conversation_id,
            "test.txt",
            subdir="uploads"
        )
        print(f"删除结果: {result}")
        assert result["success"], "文件删除应该成功"
        print("✓ 文件删除成功\n")

        print("=== 测试 8.1: 删除目录 ===")
        nested_dir = os.path.join(sandbox_path, "generated", "reports", "daily")
        os.makedirs(nested_dir, exist_ok=True)
        with open(os.path.join(nested_dir, "summary.md"), "w", encoding="utf-8") as f:
            f.write("# summary")

        result = file_manager.delete_directory(conversation_id, "generated/reports")
        print(f"删除目录结果: {result}")
        assert result["success"], "目录删除应该成功"
        assert not os.path.exists(os.path.join(sandbox_path, "generated", "reports")), "目录应该被递归删除"
        print("✓ 目录删除成功\n")

        print("=== 测试 9: 清理沙箱 ===")
        result = file_manager.cleanup_sandbox(conversation_id)
        print(f"清理结果: {result}")
        assert result["success"], "沙箱清理应该成功"
        assert not os.path.exists(sandbox_path), "沙箱目录应该被删除"
        print("✓ 沙箱清理成功\n")


def test_resolve_skill_mount_dirname_prefers_frontmatter_name():
    with tempfile.TemporaryDirectory() as temp_dir:
        skill_dir = os.path.join(temp_dir, "6c0fc52e")
        os.makedirs(skill_dir, exist_ok=True)
        with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write("---\nname: weekly-report\n---\n# Skill")

        mount_name = SandboxFileManager.resolve_skill_mount_dirname(
            skill_dir, "周报生成"
        )
        assert mount_name == "weekly-report"


def test_sandbox_file_handler():
    """测试沙箱文件操作处理器"""

    from app.mcp.handlers.sandbox_file_handler import SandboxFileHandler, get_sandbox_tools

    print("=== 测试 10: 获取工具定义 ===")
    tools = get_sandbox_tools()
    print(f"工具数量: {len(tools)}")
    assert len(tools) == 6, "应该有6个工具"
    tool_names = [t["function"]["name"] for t in tools]
    print(f"工具名称: {tool_names}")
    print("✓ 工具定义获取成功\n")

    # 创建临时目录
    with tempfile.TemporaryDirectory() as temp_dir:
        class MockSettings:
            UPLOAD_DIR = temp_dir

        # 覆盖全局设置
        from app.services.sandbox_file_manager import SandboxFileManager as SFM
        original_init = SFM.__init__
        SFM.__init__ = lambda self, settings=None: original_init(self, MockSettings())

        try:
            handler = SandboxFileHandler()
            conversation_id = 456

            print("=== 测试 11: 处理创建文件工具调用 ===")
            result = handler.handle_tool_call(
                "sandbox_create_file",
                {"filename": "test.md", "content": "# Test", "subdir": "generated"},
                conversation_id
            )
            print(f"处理结果: {result}")
            assert result["success"], "工具调用应该成功"
            print("✓ 创建文件工具调用处理成功\n")

            print("=== 测试 12: 处理读取文件工具调用 ===")
            result = handler.handle_tool_call(
                "sandbox_read_file",
                {"filename": "test.md", "subdir": "generated"},
                conversation_id
            )
            print(f"处理结果（预览）: {result['content'][:200] if result['success'] else result}")
            assert result["success"], "工具调用应该成功"
            print("✓ 读取文件工具调用处理成功\n")

            print("=== 测试 13: 处理列出文件工具调用 ===")
            result = handler.handle_tool_call(
                "sandbox_list_files",
                {"subdir": "generated"},
                conversation_id
            )
            print(f"处理结果: {result}")
            assert result["success"], "工具调用应该成功"
            print("✓ 列出文件工具调用处理成功\n")

            print("=== 测试 14: 处理获取大小工具调用 ===")
            result = handler.handle_tool_call(
                "sandbox_get_size",
                {},
                conversation_id
            )
            print(f"处理结果: {result}")
            assert result["success"], "工具调用应该成功"
            print("✓ 获取大小工具调用处理成功\n")

        finally:
            # 恢复原始初始化
            SFM.__init__ = original_init


def test_sandbox_file_handler_mutations_bump_unread_change_counter():
    """sandbox_create_file / update / delete 成功时应累加未读变更计数"""

    import app.mcp.handlers.sandbox_file_handler as handler_module
    from app.mcp.handlers.sandbox_file_handler import SandboxFileHandler
    from app.services.sandbox_file_manager import SandboxFileManager as SFM

    with tempfile.TemporaryDirectory() as temp_dir:
        class MockSettings:
            UPLOAD_DIR = temp_dir

        original_init = SFM.__init__
        original_increase_counter = handler_module.increase_sandbox_unread_change_count
        counter_calls: list[tuple[int, int]] = []

        def fake_increase_counter(_db, conversation_id: int, *, delta: int = 1):
            counter_calls.append((conversation_id, delta))
            return 0

        SFM.__init__ = lambda self, settings=None: original_init(self, MockSettings())
        handler_module.increase_sandbox_unread_change_count = fake_increase_counter

        try:
            handler = SandboxFileHandler(db=object())
            conversation_id = 457

            create_result = handler.handle_tool_call(
                "sandbox_create_file",
                {"filename": "counter.md", "content": "# Counter", "subdir": "generated"},
                conversation_id,
            )
            assert create_result["success"], "创建文件应成功"

            update_result = handler.handle_tool_call(
                "sandbox_update_file",
                {"filename": "counter.md", "content": "# Counter update", "subdir": "generated"},
                conversation_id,
            )
            assert update_result["success"], "更新文件应成功"

            delete_result = handler.handle_tool_call(
                "sandbox_delete_file",
                {"filename": "counter.md", "subdir": "generated"},
                conversation_id,
            )
            assert delete_result["success"], "删除文件应成功"

            assert counter_calls == [
                (conversation_id, 1),
                (conversation_id, 1),
                (conversation_id, 1),
            ]
        finally:
            SFM.__init__ = original_init
            handler_module.increase_sandbox_unread_change_count = original_increase_counter


if __name__ == "__main__":
    print("=" * 60)
    print("沙箱文件管理器测试")
    print("=" * 60)
    print()

    try:
        test_sandbox_file_manager()
        print("\n" + "=" * 60)
        print("第一阶段测试通过")
        print("=" * 60 + "\n")

        test_sandbox_file_handler()
        print("\n" + "=" * 60)
        print("所有测试通过！")
        print("=" * 60)

    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
