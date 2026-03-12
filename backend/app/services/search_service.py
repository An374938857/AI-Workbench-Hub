"""搜索服务"""
from typing import List, Dict, Any, Optional
from elasticsearch import Elasticsearch
from app.config import get_settings
import logging

settings = get_settings()
logger = logging.getLogger(__name__)

class SearchService:
    def __init__(self):
        self.es = Elasticsearch([settings.ELASTICSEARCH_URL])
        self.index_name = "conversations"
    
    async def search_conversations(
        self, 
        user_id: int, 
        query: str, 
        page: int = 1, 
        page_size: int = 10,
        skill_id: Optional[int] = None,
        skill_name: Optional[str] = None,
        conversation_ids: Optional[List[int]] = None,
        tags: Optional[List[str]] = None,
        date_start: Optional[str] = None,
        date_end: Optional[str] = None
    ) -> Dict[str, Any]:
        """搜索对话"""
        try:
            must_clauses = [
                {"term": {"user_id": str(user_id)}}
            ]

            if conversation_ids is not None:
                if not conversation_ids:
                    return {"total": 0, "results": []}
                must_clauses.append(
                    {"terms": {"conversation_id": [str(cid) for cid in conversation_ids]}}
                )
            
            # 只有提供了关键词才添加全文搜索条件
            if query:
                must_clauses.append({
                    "bool": {
                        "should": [
                            {"match": {"title": {"query": query, "boost": 3}}},
                            {"nested": {
                                "path": "messages",
                                "query": {"match": {"messages.content": query}},
                                "inner_hits": {
                                    "highlight": {
                                        "fields": {"messages.content": {"fragment_size": 100, "number_of_fragments": 3}},
                                        "pre_tags": ["<em>"], "post_tags": ["</em>"]
                                    }
                                }
                            }}
                        ],
                        "minimum_should_match": 1
                    }
                })
            
            if skill_name:
                must_clauses.append({"term": {"skill_name": skill_name}})
            if tags:
                must_clauses.append({"terms": {"tags.keyword": tags}})
            if date_start or date_end:
                date_range = {}
                if date_start:
                    date_range["gte"] = date_start
                if date_end:
                    date_range["lte"] = date_end
                must_clauses.append({"range": {"created_at": date_range}})
            
            body = {
                "query": {"bool": {"must": must_clauses}},
                "from": (page - 1) * page_size,
                "size": page_size,
                "highlight": {
                    "fields": {"title": {}},
                    "pre_tags": ["<em>"],
                    "post_tags": ["</em>"]
                }
            }
            
            result = self.es.search(index=self.index_name, body=body)
            
            results = []
            for hit in result["hits"]["hits"]:
                highlights = hit.get("highlight", {})
                # 从 nested inner_hits 提取消息高亮
                inner = hit.get("inner_hits", {}).get("messages", {}).get("hits", {}).get("hits", [])
                for ih in inner:
                    for frags in ih.get("highlight", {}).values():
                        highlights.setdefault("messages.content", []).extend(frags)
                results.append({
                    "conversation_id": int(hit["_source"]["conversation_id"]),
                    "title": hit["_source"]["title"],
                    "skill_name": hit["_source"].get("skill_name"),
                    "active_skills": hit["_source"].get("active_skills", []),
                    "tags": hit["_source"].get("tags", []),
                    "updated_at": hit["_source"].get("updated_at"),
                    "highlights": highlights,
                    "score": hit["_score"]
                })
            
            return {
                "total": result["hits"]["total"]["value"],
                "results": results
            }
        except Exception as e:
            logger.error(f"搜索失败: {e}", exc_info=True)
            return {"total": 0, "results": []}
    
    async def index_conversation(
        self,
        conversation_id: int,
        user_id: int,
        title: str,
        messages: List[Dict[str, Any]],
        active_skills: Optional[List[Dict[str, Any]]] = None,
    ):
        """索引对话"""
        try:
            normalized_active_skills = []
            if active_skills:
                for item in active_skills:
                    skill_id = item.get("id")
                    skill_name = item.get("name")
                    if skill_id is None or not skill_name:
                        continue
                    normalized_active_skills.append(
                        {"id": int(skill_id), "name": str(skill_name)}
                    )

            skill_name = normalized_active_skills[0]["name"] if normalized_active_skills else None
            skill_ids = [item["id"] for item in normalized_active_skills]
            skill_names = [item["name"] for item in normalized_active_skills]

            doc = {
                "conversation_id": str(conversation_id),
                "user_id": str(user_id),
                "title": title,
                "skill_name": skill_name,
                "skill_ids": skill_ids,
                "skill_names": skill_names,
                "active_skills": normalized_active_skills,
                "messages": [
                    {
                        "message_id": str(msg["id"]),
                        "role": msg["role"],
                        "content": msg["content"],
                        "created_at": msg["created_at"].isoformat() if hasattr(msg["created_at"], "isoformat") else msg["created_at"]
                    }
                    for msg in messages
                ],
                "created_at": messages[0]["created_at"].isoformat() if messages and hasattr(messages[0]["created_at"], "isoformat") else None,
                "updated_at": messages[-1]["created_at"].isoformat() if messages and hasattr(messages[-1]["created_at"], "isoformat") else None
            }
            
            self.es.index(index=self.index_name, id=str(conversation_id), document=doc)
            logger.info(f"已索引对话 {conversation_id}")
        except Exception as e:
            logger.error(f"索引对话失败: {e}", exc_info=True)
    
    async def delete_conversation(self, conversation_id: int):
        """删除对话索引"""
        try:
            self.es.delete(index=self.index_name, id=str(conversation_id), ignore=[404])
            logger.info(f"已删除对话索引 {conversation_id}")
        except Exception as e:
            logger.error(f"删除对话索引失败: {e}", exc_info=True)

# 创建全局实例
search_service = SearchService()
