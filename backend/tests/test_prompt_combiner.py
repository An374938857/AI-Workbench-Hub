from app.services.prompt_combiner import PromptCombiner


def test_truncate_keeps_skill_layer_when_prompt_is_too_long():
    base = "=== 基础定位 ===\n基础内容\n\n=== 角色模板 ===\n模板内容"
    skill = (
        "=== Skill 上下文 ===\n"
        "技能名称：会议纪要\n"
        "执行要求：\n" + ("A" * 50000)
    )
    prompt = f"{base}\n\n{skill}"

    truncated = PromptCombiner.truncate_if_needed(prompt, max_tokens=200)

    assert "=== Skill 上下文 ===" in truncated
    assert "=== 基础定位 ===" in truncated


def test_truncate_non_skill_prompt_still_returns_text():
    prompt = "=== 基础定位 ===\n" + ("B" * 30000)
    truncated = PromptCombiner.truncate_if_needed(prompt, max_tokens=120)

    assert truncated
    assert "基础定位" in truncated


def test_skill_sandbox_note_contains_mounted_path_and_usage():
    note = PromptCombiner._build_skill_sandbox_note("weekly-report")

    assert "skills/weekly-report/" in note
    assert "sandbox_list_files" in note
    assert "weekly-report/assets/config.yaml" in note
    assert "weekly-report/hooks/openclaw/HOOK.md" in note
