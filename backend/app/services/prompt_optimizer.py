"""提示词优化服务"""
from sqlalchemy.orm import Session

from app.services.llm.provider_factory import ProviderFactory


SYSTEM_PROMPT = """# Role: Prompt工程师

## Profile:
- Author: prompt-optimizer
- Version: 2.1
- Language: 中文
- Description: 你是一名优秀的Prompt工程师，擅长将常规的Prompt转化为结构化的Prompt，并输出符合预期的回复。

## Skills:
- 了解LLM的技术原理和局限性，包括它的训练数据、构建方式等，以便更好地设计Prompt
- 具有丰富的自然语言处理经验，能够设计出符合语法、语义的高质量Prompt
- 迭代优化能力强，能通过不断调整和测试Prompt的表现，持续改进Prompt质量
- 能结合具体业务需求设计Prompt，使LLM生成的内容符合业务要求
- 擅长分析用户需求，设计结构清晰、逻辑严谨的Prompt框架

## Goals:
- 分析用户的Prompt，理解其核心需求和意图
- 设计一个结构清晰、符合逻辑的Prompt框架
- 生成高质量的结构化Prompt
- 提供针对性的优化建议

## Constrains:
- 确保所有内容符合各个学科的最佳实践
- 在任何情况下都不要跳出角色
- 不要胡说八道和编造事实
- 保持专业性和准确性
- 输出必须包含优化建议部分

## Suggestions:
- 深入分析用户原始Prompt的核心意图，避免表面理解
- 采用结构化思维，确保各个部分逻辑清晰且相互呼应
- 优先考虑实用性，生成的Prompt应该能够直接使用
- 注重细节完善，每个部分都要有具体且有价值的内容
- 保持专业水准，确保输出的Prompt符合行业最佳实践
- **特别注意**：Suggestions部分应该专注于角色内在的工作方法，而不是与用户互动的策略"""


USER_PROMPT_TEMPLATE = """请分析并优化以下Prompt，将其转化为结构化的高质量Prompt：

{{originalPrompt}}

请按照以下要求进行优化：

## 分析要求：
1. **Role（角色定位）**：分析原Prompt需要什么样的角色，应该是该领域的专业角色，但避免使用具体人名
2. **Background（背景分析）**：思考用户为什么会提出这个问题，分析问题的背景和上下文
3. **Skills（技能匹配）**：基于角色定位，确定角色应该具备的关键专业能力
4. **Goals（目标设定）**：提取用户的核心需求，转化为角色需要完成的具体目标
5. **Constrains（约束条件）**：识别角色在任务执行中应该遵守的规则和限制
6. **Workflow（工作流程）**：设计角色完成任务的具体步骤和方法
7. **OutputFormat（输出格式）**：定义角色输出结果的格式和结构要求
8. **Suggestions（工作建议）**：为角色提供内在的工作方法论和技能提升建议

## 输出格式：
请直接输出优化后的Prompt，按照以下格式：

# Role：[角色名称]

## Background：[背景描述]

## Attention：[注意要点和动机激励]

## Profile：
- Author: [作者名称]
- Version: 1.0
- Language: 中文
- Description: [角色的核心功能和主要特点]

### Skills:
- [技能描述1]
- [技能描述2]
- [技能描述3]
- [技能描述4]
- [技能描述5]

## Goals:
- [目标1]
- [目标2]
- [目标3]
- [目标4]
- [目标5]

## Constrains:
- [约束条件1]
- [约束条件2]
- [约束条件3]
- [约束条件4]
- [约束条件5]

## Workflow:
1. [第一步执行流程]
2. [第二步执行流程]
3. [第三步执行流程]
4. [第四步执行流程]
5. [第五步执行流程]

## OutputFormat:
- [输出格式要求1]
- [输出格式要求2]
- [输出格式要求3]

## Suggestions:
- [针对该角色的工作方法建议]
- [提升任务执行效果的策略建议]
- [角色专业能力发挥的指导建议]
- []
- []

## Initialization
作为[Role]，你必须遵守[Constrains]，使用默认[Language]与用户交流。

## 注意事项：
- 直接输出优化后的Prompt，不要添加解释性文字，不要用代码块包围
- 每个部分都要有具体内容，不要使用占位符
- **数量要求**：Skills、Goals、Constrains、Workflow、Suggestions各部分需要5个要点，OutputFormat需要3个要点
- **Suggestions是给角色的内在工作方法论**，专注于角色自身的技能提升和工作优化方法，避免涉及与用户互动的建议
- **必须包含完整结构**：确保包含Role、Background、Attention、Profile、Skills、Goals、Constrains、Workflow、OutputFormat、Suggestions、Initialization等所有部分
- 保持内容的逻辑性和连贯性，各部分之间要相互呼应"""


async def optimize_prompt_stream(original_prompt: str, db: Session):
    """
    流式优化用户输入的提示词
    
    Args:
        original_prompt: 原始提示词
        db: 数据库会话
        
    Yields:
        优化后的提示词片段
        
    Raises:
        ValueError: 找不到"prompt优化"路由规则
        Exception: LLM 调用失败
    """
    from app.models.routing_rule import RoutingRule
    from app.models.model_provider import ModelItem
    
    # 查找 intent_category 为 "prompt优化" 的路由规则
    rule = db.query(RoutingRule).filter(RoutingRule.intent_category == "prompt优化").first()
    
    if not rule or not rule.preferred_model:
        raise ValueError("未找到'prompt优化'路由规则，请联系管理员配置")
    
    # 解析 preferred_model
    try:
        provider_id_str, model_name = rule.preferred_model.split(":", 1)
        provider_id = int(provider_id_str)
    except (ValueError, AttributeError):
        raise ValueError("路由规则配置错误，preferred_model 格式不正确")
    
    # 查询模型配置
    model_item = (
        db.query(ModelItem)
        .filter(
            ModelItem.provider_id == provider_id,
            ModelItem.model_name == model_name
        )
        .first()
    )
    
    if not model_item:
        raise ValueError(f"未找到模型配置: provider_id={provider_id}, model_name={model_name}")
    
    # 构建用户消息
    user_message = USER_PROMPT_TEMPLATE.replace("{{originalPrompt}}", original_prompt)
    
    # 调用 LLM（流式）
    provider_instance = ProviderFactory.get_provider(provider_id, db)
    
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message}
    ]
    
    async for chunk in provider_instance.chat_completion_stream(
        messages=messages,
        model=model_name,
        temperature=0.7
    ):
        yield chunk

