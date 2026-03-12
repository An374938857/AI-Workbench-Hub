"""提示词优化 API"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.deps import get_db, get_current_user
from app.models.user import User
from app.services.prompt_optimizer import optimize_prompt_stream

router = APIRouter()


class OptimizePromptRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=5000, description="原始提示词")


class OptimizePromptResponse(BaseModel):
    optimized_prompt: str = Field(..., description="优化后的提示词")


@router.post("/optimize")
async def optimize_prompt_api(
    body: OptimizePromptRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    优化用户输入的提示词（流式输出）
    
    调用路由规则中名为"prompt优化"的模型进行优化
    """
    from fastapi.responses import StreamingResponse
    import json
    
    async def generate():
        try:
            async for chunk_dict in optimize_prompt_stream(body.prompt, db):
                # chunk_dict 是 {"type": "content_delta", "content": "..."} 格式
                if isinstance(chunk_dict, dict) and chunk_dict.get("type") == "content_delta":
                    content = chunk_dict.get("content", "")
                    if content:
                        yield f"data: {json.dumps({'content': content}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except ValueError as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': f'优化失败: {str(e)}'}, ensure_ascii=False)}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )
