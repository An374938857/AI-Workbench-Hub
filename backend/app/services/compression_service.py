"""
对话上下文压缩服务
"""
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.conversation_compression_log import ConversationCompressionLog
from app.models.message import Message
from app.services.llm.provider_factory import ProviderFactory
import tiktoken


# 摘要生成 Prompt
SUMMARY_PROMPT = """你是一个对话摘要专家。请阅读以下对话内容，生成一个简洁的摘要。

要求：
1. 提取核心话题和关键结论
2. 摘要长度不超过原内容的30%
3. 使用第三人称描述
4. 保留重要的技术细节和决策

对话内容：
{conversation_content}

请生成摘要："""


def count_tokens(text: str, model: str = "gpt-3.5-turbo") -> int:
    """计算文本的 Token 数"""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))


async def compress_conversation(conversation_id: int, db: Session) -> dict:
    """
    压缩对话上下文
    
    Args:
        conversation_id: 对话 ID
        db: 数据库会话
        
    Returns:
        {
            "saved_tokens": int,
            "summary": str,
            "original_token_count": int,
            "compressed_token_count": int
        }
    """
    # 查找已有的压缩记录
    existing_log = db.query(ConversationCompressionLog).filter(
        ConversationCompressionLog.conversation_id == conversation_id
    ).order_by(ConversationCompressionLog.created_at.desc()).first()
    
    # 获取所有消息
    messages = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(Message.created_at).all()
    
    if len(messages) <= 20:
        raise ValueError("对话消息数不足20条，无需压缩")
    
    # 分离早期消息和最近消息（保留最近20条）
    early_messages = messages[:-20]
    recent_messages = messages[-20:]
    
    # 记录分隔位置：最近消息中第一条非 tool 消息的 ID
    split_message_id = None
    for msg in recent_messages:
        if msg.role != 'tool':
            split_message_id = msg.id
            break
    
    # 构建需要压缩的内容
    conversation_content = ""
    
    # 如果已有压缩记录，将上次摘要作为前缀
    if existing_log:
        conversation_content += f"[之前的对话摘要]\n{existing_log.summary}\n\n[后续对话内容]\n"
        # 只压缩上次 split_message_id 之后到本次保留消息之前的部分
        if existing_log.split_message_id:
            early_messages = [m for m in early_messages if m.id >= existing_log.split_message_id]
    
    for msg in early_messages:
        role = "用户" if msg.role == "user" else "AI"
        conversation_content += f"{role}: {msg.content}\n\n"
    
    # 计算原始 Token 数
    original_tokens = count_tokens(conversation_content)
    
    # 调用 LLM 生成摘要
    # 使用默认的 provider (ID=1)
    provider = ProviderFactory.get_provider(1, db)
    
    summary_messages = [
        {"role": "user", "content": SUMMARY_PROMPT.format(conversation_content=conversation_content)}
    ]
    
    # 使用非流式调用
    summary = ""
    async for chunk in provider.chat_completion_stream(
        messages=summary_messages,
        model="deepseek-chat",
        temperature=0.3
    ):
        if chunk.get("type") == "content_delta":
            summary += chunk.get("content", "")
    
    # 计算压缩后 Token 数
    compressed_tokens = count_tokens(summary)
    
    # 记录压缩日志
    log = ConversationCompressionLog(
        conversation_id=conversation_id,
        original_token_count=original_tokens,
        compressed_token_count=compressed_tokens,
        summary=summary,
        split_message_id=split_message_id,
        created_at=datetime.now()
    )
    db.add(log)
    db.commit()
    
    saved_tokens = original_tokens - compressed_tokens
    
    return {
        "saved_tokens": saved_tokens,
        "summary": summary,
        "original_token_count": original_tokens,
        "compressed_token_count": compressed_tokens,
        "split_message_id": split_message_id
    }


def get_compressed_context(conversation_id: int, db: Session) -> str | None:
    """
    获取压缩摘要文本，如果有压缩记录返回摘要，否则返回 None
    """
    latest_log = db.query(ConversationCompressionLog).filter(
        ConversationCompressionLog.conversation_id == conversation_id
    ).order_by(ConversationCompressionLog.created_at.desc()).first()
    
    if not latest_log:
        return None
    
    return latest_log.summary


def get_compression_summary(conversation_id: int, db: Session) -> dict:
    """
    获取压缩摘要信息
    
    Args:
        conversation_id: 对话 ID
        db: 数据库会话
        
    Returns:
        {
            "summary": str,
            "original_token_count": int,
            "compressed_token_count": int,
            "saved_tokens": int,
            "created_at": datetime
        }
    """
    latest_log = db.query(ConversationCompressionLog).filter(
        ConversationCompressionLog.conversation_id == conversation_id
    ).order_by(ConversationCompressionLog.created_at.desc()).first()
    
    if not latest_log:
        return None
    
    return {
        "summary": latest_log.summary,
        "original_token_count": latest_log.original_token_count,
        "compressed_token_count": latest_log.compressed_token_count,
        "saved_tokens": latest_log.original_token_count - latest_log.compressed_token_count,
        "split_message_id": latest_log.split_message_id,
        "created_at": latest_log.created_at
    }
