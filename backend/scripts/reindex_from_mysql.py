#!/usr/bin/env python3
"""直接从MySQL读取并索引到ES（对话 + Skill）"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pymysql
import requests
import json
from datetime import datetime
from typing import Dict, List

from app.config import get_settings
from app.services.skill_recommend import get_skill_recommend_service

settings = get_settings()

# 数据库配置
DB_CONFIG = {
    'host': 'mysql',
    'port': 3306,
    'user': 'root',
    'password': 'password',
    'database': 'ai_platform',
    'charset': 'utf8mb4'
}

ES_URL = 'http://elasticsearch:9200'

def get_conversations():
    """从MySQL获取所有对话"""
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    
    cursor.execute("""
        SELECT c.id, c.user_id, c.title, c.created_at, c.updated_at, c.skill_id, c.active_skill_ids, s.name as skill_name
        FROM conversations c
        LEFT JOIN skills s ON c.skill_id = s.id
        ORDER BY c.id
    """)
    conversations = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return conversations

def get_skill_name_map() -> Dict[int, str]:
    """获取 skill_id -> skill_name 映射。"""
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    cursor.execute("SELECT id, name FROM skills")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return {int(row["id"]): row["name"] for row in rows}

def parse_active_skill_ids(raw: str) -> List[int]:
    """兼容 conversations.active_skill_ids 的新旧结构。"""
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []

    ids: List[int] = []
    if isinstance(payload, dict):
        skills = payload.get("skills")
        if isinstance(skills, list):
            for item in skills:
                if not isinstance(item, dict):
                    continue
                skill_id = item.get("id")
                try:
                    parsed_id = int(skill_id)
                except (TypeError, ValueError):
                    continue
                if parsed_id > 0 and parsed_id not in ids:
                    ids.append(parsed_id)

        legacy_ids = payload.get("skill_ids")
        if isinstance(legacy_ids, list):
            for value in legacy_ids:
                try:
                    parsed_id = int(value)
                except (TypeError, ValueError):
                    continue
                if parsed_id > 0 and parsed_id not in ids:
                    ids.append(parsed_id)
    elif isinstance(payload, list):
        for value in payload:
            try:
                parsed_id = int(value)
            except (TypeError, ValueError):
                continue
            if parsed_id > 0 and parsed_id not in ids:
                ids.append(parsed_id)

    return ids

def get_messages(conv_id):
    """获取对话的所有消息"""
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    
    cursor.execute("""
        SELECT id, role, content, created_at 
        FROM messages 
        WHERE conversation_id = %s 
        ORDER BY created_at
    """, (conv_id,))
    messages = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return messages

def index_conversation(conv, messages, skill_name_map):
    """索引单个对话到ES"""
    active_skill_ids = parse_active_skill_ids(conv.get("active_skill_ids"))
    if conv.get("skill_id"):
        sid = int(conv["skill_id"])
        if sid > 0 and sid not in active_skill_ids:
            active_skill_ids.insert(0, sid)

    active_skills = []
    for sid in active_skill_ids:
        name = skill_name_map.get(sid)
        if not name:
            continue
        active_skills.append({"id": sid, "name": name})

    if not active_skills and conv.get("skill_id") and conv.get("skill_name"):
        active_skills = [{"id": int(conv["skill_id"]), "name": conv["skill_name"]}]

    skill_name = active_skills[0]["name"] if active_skills else None
    skill_ids = [item["id"] for item in active_skills]
    skill_names = [item["name"] for item in active_skills]

    doc = {
        "conversation_id": str(conv['id']),
        "user_id": str(conv['user_id']),
        "title": conv['title'] or '',
        "skill_name": skill_name,
        "skill_ids": skill_ids,
        "skill_names": skill_names,
        "active_skills": active_skills,
        "messages": [
            {
                "message_id": str(msg['id']),
                "role": msg['role'],
                "content": msg['content'],
                "created_at": msg['created_at'].isoformat() if isinstance(msg['created_at'], datetime) else str(msg['created_at'])
            }
            for msg in messages
        ],
        "created_at": conv['created_at'].isoformat() if isinstance(conv['created_at'], datetime) else str(conv['created_at']),
        "updated_at": conv['updated_at'].isoformat() if isinstance(conv['updated_at'], datetime) else str(conv['updated_at'])
    }
    
    response = requests.put(
        f"{ES_URL}/conversations/_doc/{conv['id']}",
        headers={'Content-Type': 'application/json'},
        data=json.dumps(doc)
    )
    
    return response.json().get('result') in ['created', 'updated']

def reindex_skills():
    """从MySQL读取已发布Skill并索引到ES"""
    print("\n📦 索引 Skill 数据...")
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor(pymysql.cursors.DictCursor)

    cursor.execute("""
        SELECT s.id, s.name, s.use_count, s.updated_at,
               sv.brief_desc, sv.detail_desc, sv.usage_example
        FROM skills s
        JOIN skill_versions sv ON s.published_version_id = sv.id
        WHERE s.status = 'published'
    """)
    skills = cursor.fetchall()

    # 获取每个 skill 的 tags
    for sk in skills:
        cursor.execute("""
            SELECT st.name FROM scene_tags st
            JOIN skill_tags skt ON st.id = skt.tag_id
            WHERE skt.skill_id = %s
        """, (sk['id'],))
        sk['tags'] = [r['name'] for r in cursor.fetchall()]

    cursor.close()
    conn.close()

    svc = get_skill_recommend_service()
    for sk in skills:
        svc.index_skill(
            skill_id=sk['id'],
            name=sk['name'],
            brief_desc=sk['brief_desc'],
            detail_desc=sk['detail_desc'],
            tags=sk['tags'],
            usage_example=sk.get('usage_example') or "",
            use_count=sk.get('use_count') or 0,
            updated_at=sk['updated_at'].isoformat() if isinstance(sk['updated_at'], datetime) else str(sk['updated_at']),
        )
        print(f"  ✅ Skill {sk['id']} - {sk['name']}")

    print(f"✅ Skill 索引完成: {len(skills)} 个")


def main():
    print("📊 从数据库获取对话...")
    conversations = get_conversations()
    skill_name_map = get_skill_name_map()
    print(f"找到 {len(conversations)} 个对话\n")
    
    success = 0
    for i, conv in enumerate(conversations, 1):
        try:
            messages = get_messages(conv['id'])
            if not messages:
                print(f"⚠️  [{i}/{len(conversations)}] 对话 {conv['id']} 没有消息，跳过")
                continue
            
            if index_conversation(conv, messages, skill_name_map):
                success += 1
                title = conv['title'] or 'Untitled'
                print(f"✅ [{i}/{len(conversations)}] 已索引对话 {conv['id']}: {title[:50]}")
            else:
                print(f"⚠️  [{i}/{len(conversations)}] 对话 {conv['id']} 索引可能失败")
        except Exception as e:
            print(f"❌ [{i}/{len(conversations)}] 对话 {conv['id']} 索引失败: {e}")
    
    print(f"\n✅ 重新索引完成: {success}/{len(conversations)} 个对话")

    reindex_skills()

if __name__ == "__main__":
    main()
