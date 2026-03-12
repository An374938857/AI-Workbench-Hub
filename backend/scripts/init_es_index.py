"""初始化 ElasticSearch 索引"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from elasticsearch import Elasticsearch
from app.config import get_settings

settings = get_settings()

def init_conversation_index(es: Elasticsearch):
    """初始化对话索引（使用IK分词器）"""
    index_name = "conversations"
    
    # 删除旧索引
    if es.indices.exists(index=index_name):
        es.indices.delete(index=index_name)
        print(f"✅ 已删除旧索引: {index_name}")
    
    mapping = {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "analysis": {
                "analyzer": {
                    "ik_smart_analyzer": {
                        "type": "custom",
                        "tokenizer": "ik_smart"
                    },
                    "ik_max_word_analyzer": {
                        "type": "custom",
                        "tokenizer": "ik_max_word"
                    }
                }
            }
        },
        "mappings": {
            "properties": {
                "conversation_id": {"type": "keyword"},
                "user_id": {"type": "keyword"},
                "title": {
                    "type": "text",
                    "analyzer": "ik_max_word",
                    "search_analyzer": "ik_smart"
                },
                "skill_name": {
                    "type": "keyword"
                },
                "skill_ids": {
                    "type": "integer"
                },
                "skill_names": {
                    "type": "keyword"
                },
                "active_skills": {
                    "type": "nested",
                    "properties": {
                        "id": {"type": "integer"},
                        "name": {"type": "keyword"},
                    }
                },
                "messages": {
                    "type": "nested",
                    "properties": {
                        "message_id": {"type": "keyword"},
                        "role": {"type": "keyword"},
                        "content": {
                            "type": "text",
                            "analyzer": "ik_max_word",
                            "search_analyzer": "ik_smart"
                        },
                        "created_at": {"type": "date"}
                    }
                },
                "created_at": {"type": "date"},
                "updated_at": {"type": "date"}
            }
        }
    }
    
    es.indices.create(index=index_name, body=mapping)
    print(f"✅ 索引 {index_name} 创建成功（使用IK分词器）")
    
    # 测试分词效果
    result = es.indices.analyze(
        index=index_name,
        body={"analyzer": "ik_smart", "text": "五子棋游戏开发"}
    )
    tokens = [token["token"] for token in result["tokens"]]
    print(f"✅ IK分词测试: '五子棋游戏开发' -> {tokens}")

def init_skills_index(es: Elasticsearch):
    """初始化 Skill 推荐索引（使用IK分词器）"""
    index_name = "skills"

    if es.indices.exists(index=index_name):
        es.indices.delete(index=index_name)
        print(f"✅ 已删除旧索引: {index_name}")

    mapping = {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "analysis": {
                "analyzer": {
                    "ik_smart_analyzer": {"type": "custom", "tokenizer": "ik_smart"},
                    "ik_max_word_analyzer": {"type": "custom", "tokenizer": "ik_max_word"},
                }
            },
        },
        "mappings": {
            "properties": {
                "skill_id": {"type": "integer"},
                "name": {
                    "type": "text",
                    "analyzer": "ik_max_word",
                    "search_analyzer": "ik_smart",
                    "fields": {"keyword": {"type": "keyword"}},
                },
                "brief_desc": {
                    "type": "text",
                    "analyzer": "ik_max_word",
                    "search_analyzer": "ik_smart",
                },
                "detail_desc": {
                    "type": "text",
                    "analyzer": "ik_max_word",
                    "search_analyzer": "ik_smart",
                },
                "tags": {"type": "keyword"},
                "usage_example": {
                    "type": "text",
                    "analyzer": "ik_max_word",
                    "search_analyzer": "ik_smart",
                },
                "use_count": {"type": "integer"},
                "updated_at": {"type": "date"},
            }
        },
    }

    es.indices.create(index=index_name, body=mapping)
    print(f"✅ 索引 {index_name} 创建成功（使用IK分词器）")

    result = es.indices.analyze(
        index=index_name,
        body={"analyzer": "ik_smart", "text": "帮我写一份周报"},
    )
    tokens = [t["token"] for t in result["tokens"]]
    print(f"✅ IK分词测试: '帮我写一份周报' -> {tokens}")


def main():
    es = Elasticsearch([settings.ELASTICSEARCH_URL])
    
    if not es.ping():
        print("❌ 无法连接到 ElasticSearch")
        sys.exit(1)
    
    print("🔗 已连接到 ElasticSearch")
    init_conversation_index(es)
    init_skills_index(es)
    print("✅ 所有索引初始化完成")

if __name__ == "__main__":
    main()
