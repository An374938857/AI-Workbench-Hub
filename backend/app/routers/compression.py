"""
对话压缩相关 API
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.deps import get_db
from app.services.compression_service import compress_conversation, get_compression_summary
from pydantic import BaseModel


router = APIRouter()


class CompressionResponse(BaseModel):
    saved_tokens: int
    summary: str
    original_token_count: int
    compressed_token_count: int


class CompressionSummaryResponse(BaseModel):
    summary: str
    original_token_count: int
    compressed_token_count: int
    saved_tokens: int
    split_message_id: int | None
    created_at: str


@router.post("/conversations/{conversation_id}/compress", response_model=CompressionResponse)
async def compress_conversation_endpoint(
    conversation_id: int,
    db: Session = Depends(get_db)
):
    """手动压缩对话上下文"""
    try:
        result = await compress_conversation(conversation_id, db)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"压缩失败: {str(e)}")


@router.get("/conversations/{conversation_id}/compression-summary")
async def get_compression_summary_endpoint(
    conversation_id: int,
    db: Session = Depends(get_db)
):
    """获取压缩摘要信息"""
    result = get_compression_summary(conversation_id, db)
    if not result:
        return {"summary": "", "original_token_count": 0, "compressed_token_count": 0, "saved_tokens": 0, "split_message_id": None, "created_at": None}
    
    result["created_at"] = result["created_at"].isoformat()
    return result
