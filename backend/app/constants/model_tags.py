"""模型能力标签预设常量"""

# 预设能力标签
CAPABILITY_TAGS = {
    "reasoning": "推理",
    "creative_writing": "创意写作",
    "coding": "代码",
    "data_analysis": "数据分析",
    "fast_response": "快速响应",
    "deep_thinking": "深度思考",
    "multimodal": "多模态",
    "long_context": "超长上下文",
}

# 场景标签 → 模型能力标签 映射（用于推荐匹配）
SCENE_TO_CAPABILITY = {
    "需求文档": ["reasoning", "creative_writing"],
    "会议管理": ["reasoning", "creative_writing"],
    "周报汇报": ["creative_writing"],
    "数据分析工具": ["data_analysis", "coding"],
    "产品设计": ["reasoning", "creative_writing"],
    "通用工具": [],
}

# 速度等级
SPEED_RATINGS = ["fast", "medium", "slow"]

# 成本等级
COST_RATINGS = ["low", "medium", "high"]
