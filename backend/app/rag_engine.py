"""RAG (Retrieval-Augmented Generation) 엔진
벡터 DB 기반 의약학 지식 검색 → GPT 프롬프트 주입

구조:
1. 의약학 문서(고혈압 가이드라인, 복약 지침 등)를 임베딩하여 저장
2. 사용자 질문 시 유사 문서 검색 (semantic search)
3. 검색된 문서를 GPT 프롬프트에 컨텍스트로 주입
4. 근거 기반 답변 생성 (할루시네이션 방지)
"""
from openai import OpenAI
from app.config import OPENAI_API_KEY
from typing import List, Tuple
import json
import os

client = OpenAI(api_key=OPENAI_API_KEY)

# ==================== 인메모리 벡터 스토어 (MVP용) ====================
# 프로덕션에서는 ChromaDB, Pinecone, Milvus 등으로 교체

_knowledge_base: List[dict] = []  # {"text": ..., "embedding": [...], "source": ..., "category": ...}


# ==================== 의약학 지식 베이스 (기본 내장) ====================

MEDICAL_KNOWLEDGE = [
    # 고혈압 관리 가이드라인
    {"text": "고혈압 환자는 수축기 혈압 130mmHg 미만, 이완기 혈압 80mmHg 미만을 목표로 합니다. 65세 이상은 140/90mmHg 미만이 현실적 목표입니다.",
     "source": "대한고혈압학회 진료지침 2022", "category": "hypertension"},
    {"text": "고혈압 약은 매일 같은 시간에 복용해야 합니다. 약을 빠뜨렸을 때 두 배로 복용하면 안 됩니다. 다음 복용 시간에 정상 용량만 드세요.",
     "source": "고혈압 복약지도 가이드", "category": "hypertension"},
    {"text": "혈압약 복용 중 어지러움이 있으면 급하게 일어나지 마세요. 천천히 일어나고, 증상이 심하면 담당 의사에게 알려주세요.",
     "source": "고혈압 복약지도 가이드", "category": "hypertension"},

    # 당뇨 관리
    {"text": "당뇨 환자의 공복 혈당 목표는 80~130mg/dL, 식후 2시간 혈당은 180mg/dL 미만입니다. HbA1c 목표는 6.5~7.0% 미만입니다.",
     "source": "대한당뇨병학회 진료지침 2023", "category": "diabetes"},
    {"text": "메트포르민은 식사와 함께 복용하면 위장장애를 줄일 수 있습니다. 신장 기능이 저하된 경우 용량 조절이 필요합니다.",
     "source": "당뇨병 복약지도", "category": "diabetes"},
    {"text": "저혈당 증상(식은땀, 떨림, 어지러움)이 나타나면 즉시 사탕, 주스 등 당분을 15g 섭취하고 15분 후 재측정하세요.",
     "source": "저혈당 대처 가이드", "category": "diabetes"},

    # 다약제 복용 주의
    {"text": "65세 이상 고령자가 5종 이상의 약을 동시 복용(다약제 복용)하면 약물 상호작용과 부작용 위험이 크게 증가합니다. 정기적으로 약사와 복약 상담을 받으세요.",
     "source": "대한노인약료학회", "category": "polypharmacy"},
    {"text": "와파린 복용 시 비타민K가 풍부한 녹색 채소(시금치, 브로콜리) 섭취량을 일정하게 유지하세요. 급격한 변화는 약효에 영향을 줍니다.",
     "source": "항응고제 복약지도", "category": "polypharmacy"},

    # 건강기능식품 주의
    {"text": "오메가3는 혈액응고를 억제할 수 있으므로 항응고제(와파린) 복용자는 반드시 의사와 상담 후 복용하세요.",
     "source": "건강기능식품 병용 가이드", "category": "supplement"},
    {"text": "홍삼은 혈압을 올릴 수 있으므로 고혈압 환자는 주의가 필요합니다. 혈압약과 병용 시 혈압 변동을 관찰하세요.",
     "source": "건강기능식품 병용 가이드", "category": "supplement"},
    {"text": "은행잎 추출물은 출혈 위험을 높일 수 있습니다. 수술 2주 전부터 중단하고, 혈액응고억제제와 병용을 피하세요.",
     "source": "건강기능식품 안전정보", "category": "supplement"},

    # 복약 일반
    {"text": "약을 물 없이 삼키면 식도에 걸려 궤양을 유발할 수 있습니다. 반드시 물 한 컵(200mL) 이상과 함께 복용하세요.",
     "source": "일반 복약지도", "category": "general"},
    {"text": "냉장보관 약(인슐린, 일부 안약)은 냉동하면 안 됩니다. 냉장실(2~8°C)에 보관하고, 개봉 후에는 사용 기간을 확인하세요.",
     "source": "의약품 보관 가이드", "category": "general"},
    {"text": "낙상 위험을 높이는 약물: 수면제, 항불안제, 혈압강하제, 이뇨제. 이런 약을 복용 중이면 야간에 특히 주의하세요.",
     "source": "고령자 낙상 예방 가이드", "category": "elderly_safety"},
]


def initialize_knowledge_base():
    """지식 베이스 초기화 (임베딩 생성)"""
    global _knowledge_base

    if _knowledge_base:
        return  # 이미 초기화됨

    if not OPENAI_API_KEY:
        # API 키 없으면 키워드 매칭 모드로 동작
        for doc in MEDICAL_KNOWLEDGE:
            _knowledge_base.append({
                "text": doc["text"],
                "embedding": [],
                "source": doc["source"],
                "category": doc["category"],
            })
        return

    for doc in MEDICAL_KNOWLEDGE:
        try:
            embedding = _get_embedding(doc["text"])
            _knowledge_base.append({
                "text": doc["text"],
                "embedding": embedding,
                "source": doc["source"],
                "category": doc["category"],
            })
        except Exception:
            _knowledge_base.append({
                "text": doc["text"],
                "embedding": [],
                "source": doc["source"],
                "category": doc["category"],
            })


def search_knowledge(query: str, top_k: int = 3) -> List[dict]:
    """쿼리와 유사한 의학 지식 검색"""
    if not _knowledge_base:
        initialize_knowledge_base()

    try:
        query_embedding = _get_embedding(query)
    except Exception:
        # 임베딩 실패 시 키워드 매칭 fallback
        return _keyword_search(query, top_k)

    # 코사인 유사도 계산
    scored = []
    for doc in _knowledge_base:
        if doc["embedding"]:
            score = _cosine_similarity(query_embedding, doc["embedding"])
            scored.append((score, doc))

    # 상위 k개 반환
    scored.sort(key=lambda x: x[0], reverse=True)
    return [doc for _, doc in scored[:top_k]]


def get_rag_context(query: str) -> str:
    """RAG 컨텍스트 생성: 질문과 관련된 의학 지식을 문자열로 반환"""
    relevant_docs = search_knowledge(query, top_k=3)

    if not relevant_docs:
        return ""

    context = "\n\n[참고 의약학 정보]\n"
    for i, doc in enumerate(relevant_docs, 1):
        context += f"{i}. {doc['text']} (출처: {doc['source']})\n"

    return context


def _get_embedding(text: str) -> List[float]:
    """OpenAI 임베딩 생성"""
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text,
    )
    return response.data[0].embedding


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """코사인 유사도 계산"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _keyword_search(query: str, top_k: int) -> List[dict]:
    """키워드 기반 검색 (임베딩 불가 시 fallback)"""
    scored = []
    query_lower = query.lower()
    for doc in _knowledge_base:
        score = sum(1 for word in query_lower.split() if word in doc["text"].lower())
        if score > 0:
            scored.append((score, doc))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [doc for _, doc in scored[:top_k]]
