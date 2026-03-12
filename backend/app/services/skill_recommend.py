"""Skill 智能推荐服务 - 基于 ES multi_match + function_score"""
import logging
from typing import Optional, Dict, Any, List

from elasticsearch import Elasticsearch

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

INDEX_NAME = "skills"


class SkillRecommendService:
    def __init__(self):
        self.es = Elasticsearch([settings.ELASTICSEARCH_URL])

    def index_skill(self, skill_id: int, name: str, brief_desc: str,
                    detail_desc: str, tags: List[str], usage_example: str = "",
                    use_count: int = 0, updated_at: str = None):
        """索引单个 Skill 到 ES"""
        doc = {
            "skill_id": skill_id,
            "name": name,
            "brief_desc": brief_desc,
            "detail_desc": detail_desc,
            "tags": tags,
            "usage_example": usage_example or "",
            "use_count": use_count,
            "updated_at": updated_at,
        }
        try:
            self.es.index(index=INDEX_NAME, id=str(skill_id), document=doc)
            logger.info(f"已索引 Skill {skill_id}: {name}")
        except Exception as e:
            logger.error(f"索引 Skill {skill_id} 失败: {e}", exc_info=True)

    def delete_skill(self, skill_id: int):
        """从 ES 删除 Skill 索引"""
        try:
            self.es.delete(index=INDEX_NAME, id=str(skill_id), ignore=[404])
            logger.info(f"已删除 Skill 索引 {skill_id}")
        except Exception as e:
            logger.error(f"删除 Skill 索引 {skill_id} 失败: {e}", exc_info=True)

    def recommend(self, query: str, top_k: int = 3, min_score: float = 5.0) -> List[Dict[str, Any]]:
        """根据用户输入推荐最匹配的 Skill

        使用 function_score 综合考虑：
        1. multi_match 文本相关性（name 权重最高，tags 次之，brief_desc/usage_example 辅助）
        2. use_count 热度加分（log1p 平滑）
        """
        body = {
            "query": {
                "function_score": {
                    "query": {
                        "multi_match": {
                            "query": query,
                            "fields": [
                                "name^5",
                                "tags^4",
                                "brief_desc^3",
                                "usage_example^2",
                                "detail_desc",
                            ],
                            "type": "best_fields",
                            "tie_breaker": 0.3,
                        }
                    },
                    "functions": [
                        {
                            "field_value_factor": {
                                "field": "use_count",
                                "modifier": "log1p",
                                "factor": 0.5,
                                "missing": 0,
                            }
                        }
                    ],
                    "boost_mode": "sum",
                    "score_mode": "sum",
                }
            },
            "size": top_k,
            "min_score": min_score,
        }

        try:
            result = self.es.search(index=INDEX_NAME, body=body)
            hits = result["hits"]["hits"]
            return [
                {"skill_id": hit["_source"]["skill_id"], "name": hit["_source"]["name"], "score": hit["_score"]}
                for hit in hits
            ]
        except Exception as e:
            logger.error(f"Skill 推荐失败: {e}", exc_info=True)
            return []

    def recommend_best(self, query: str, min_score: float = 5.0) -> Optional[int]:
        """返回最佳匹配的 skill_id，无匹配返回 None"""
        results = self.recommend(query, top_k=1, min_score=min_score)
        return results[0]["skill_id"] if results else None


# 单例
_service: Optional[SkillRecommendService] = None


def get_skill_recommend_service() -> SkillRecommendService:
    global _service
    if _service is None:
        _service = SkillRecommendService()
    return _service
