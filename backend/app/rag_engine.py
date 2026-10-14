"""RAG (Retrieval-Augmented Generation) 엔진
벡터 DB 기반 의약학 지식 검색 → GPT 프롬프트 주입

구조:
1. 의약학 문서(허가정보·복약지침·낱알식별 등)를 임베딩하여 저장
2. 사용자 질문 시 유사 문서 검색 (semantic search)
3. 검색된 문서를 GPT 프롬프트에 컨텍스트로 주입
4. 근거 기반 답변 생성 (할루시네이션 방지)

지식 출처 (두 갈래):
  (A) 내장 기본지식  : 아래 MEDICAL_KNOWLEDGE (코드에 고정)
  (B) 외부 지식파일  : backend/knowledge/*.jsonl  ← 비개발자가 계속 추가/갱신하는 영역
      표준 스키마와 작성법은 backend/knowledge/README.md 참고.

증분 갱신 & 중복관리:
  - 각 문서의 임베딩은 '임베딩 대상 텍스트의 SHA-256 해시'를 키로 디스크 캐시
    (backend/knowledge/.embedding_cache.json)에 저장됩니다.
  - 재기동/리로드 시, 텍스트가 바뀌지 않은 문서는 캐시를 재사용하여 임베딩을
    다시 만들지 않습니다(= OpenAI 비용/시간 절약). 바뀐·새 문서만 임베딩합니다.
  - 문서는 'id' 기준으로 중복 제거되며(같은 id면 나중 문서가 덮어씀),
    id가 없으면 텍스트 해시로 자동 생성됩니다.
"""
from openai import OpenAI
from app.config import OPENAI_API_KEY
from typing import List
import json
import os
import glob
import hashlib

client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

EMBEDDING_MODEL = "text-embedding-3-small"

# 경로: 실행 위치와 무관하게 backend/ 기준 절대경로로 고정
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KNOWLEDGE_DIR = os.path.join(_BACKEND_DIR, "knowledge")
CACHE_PATH = os.path.join(KNOWLEDGE_DIR, ".embedding_cache.json")

# ==================== 인메모리 벡터 스토어 (MVP용) ====================
# 프로덕션에서는 ChromaDB, Pinecone, Milvus 등으로 교체 가능.
# 문서 1건: {"id","text","embedding","source","category", ...메타}
_knowledge_base: List[dict] = []
_embedding_cache: dict = {}   # content_hash -> embedding(list[float])
_last_stats: dict = {}


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


# ==================== 표준 스키마 유틸 ====================

def _content_hash(text: str) -> str:
    return hashlib.sha256((text or "").strip().encode("utf-8")).hexdigest()


def compose_text(doc: dict) -> str:
    """구조화 필드로부터 임베딩 대상 자연어 텍스트를 합성한다.

    JSONL 레코드에 'text'가 이미 있으면 그대로 쓰고, 없으면 의약품 메타
    (품목명/성분/함량/효능/주의/보관 등)를 사람이 읽는 한 문장으로 조립한다.
    → 비개발자는 표(CSV)에 항목만 채우면 text는 자동 생성됩니다.
    """
    t = (doc.get("text") or "").strip()
    if t:
        return t

    name = (doc.get("drug_name") or doc.get("item_name") or "").strip()
    parts = []
    head = name
    ing = (doc.get("ingredient") or "").strip()
    amt = (doc.get("amount") or doc.get("dosage") or "").strip()
    if ing or amt:
        head = f"{name}({' '.join(x for x in (ing, amt) if x)})".strip()
    if head:
        parts.append(head)

    field_labels = [
        ("effect", "효능·효과"), ("usage", "복용법"), ("caution", "주의사항"),
        ("side_effect", "부작용"), ("storage", "보관법"), ("interaction", "상호작용"),
        ("appearance", "생김새"),
    ]
    for key, label in field_labels:
        val = (doc.get(key) or "").strip()
        if val:
            parts.append(f"{label}: {val}")
    return ". ".join(parts).strip()


def _doc_id(doc: dict, text: str) -> str:
    did = (doc.get("id") or "").strip()
    if did:
        return did
    name = (doc.get("drug_name") or doc.get("item_name") or "").strip()
    if name:
        return f"drug:{name}"
    return f"hash:{_content_hash(text)[:16]}"


def _normalize_doc(doc: dict) -> dict:
    """원본 레코드를 벡터스토어 표준 문서로 정규화한다(임베딩 제외)."""
    text = compose_text(doc)
    out = {
        "id": _doc_id(doc, text),
        "text": text,
        "source": (doc.get("source") or "미상").strip(),
        "category": (doc.get("category") or "general").strip(),
        "embedding": [],
    }
    # 표시/필터용 메타는 그대로 보존
    for k in ("drug_name", "item_name", "ingredient", "amount", "updated_at"):
        if doc.get(k):
            out[k] = doc[k]
    return out


# ==================== 외부 지식파일(JSONL) 로딩 ====================

def _load_external_docs() -> List[dict]:
    """knowledge/*.jsonl 의 모든 레코드를 읽어 표준 문서 리스트로 반환한다."""
    docs = []
    if not os.path.isdir(KNOWLEDGE_DIR):
        return docs
    for path in sorted(glob.glob(os.path.join(KNOWLEDGE_DIR, "*.jsonl"))):
        fname = os.path.basename(path)
        try:
            with open(path, "r", encoding="utf-8") as f:
                for lineno, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line.startswith("//"):
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        print(f"[RAG] JSON 파싱 실패: {fname}:{lineno} (건너뜀)")
                        continue
                    nd = _normalize_doc(rec)
                    if nd["text"]:
                        nd["_file"] = fname
                        docs.append(nd)
        except Exception as e:
            print(f"[RAG] 지식파일 읽기 실패 {fname}: {e}")
    return docs


# ==================== 임베딩 캐시 ====================

def _load_cache():
    global _embedding_cache
    if _embedding_cache:
        return
    try:
        if os.path.exists(CACHE_PATH):
            with open(CACHE_PATH, "r", encoding="utf-8") as f:
                _embedding_cache = json.load(f)
    except Exception:
        _embedding_cache = {}


def _save_cache():
    try:
        os.makedirs(KNOWLEDGE_DIR, exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(_embedding_cache, f)
    except Exception as e:
        print(f"[RAG] 임베딩 캐시 저장 실패: {e}")


# ==================== 초기화 / 리로드 ====================

def _build(docs: List[dict]) -> dict:
    """문서 리스트를 임베딩하여 _knowledge_base 를 재구성한다(id 중복 제거 + 캐시 증분)."""
    global _knowledge_base
    _load_cache()

    # id 기준 중복 제거 (나중 문서가 앞 문서를 덮어씀)
    by_id = {}
    for d in docs:
        by_id[d["id"]] = d
    unique = list(by_id.values())

    reused = new = failed = 0
    base = []
    for d in unique:
        h = _content_hash(d["text"])
        emb = _embedding_cache.get(h)
        if emb is not None:
            reused += 1
        elif client is not None:
            try:
                emb = _get_embedding(d["text"])
                _embedding_cache[h] = emb
                new += 1
            except Exception:
                emb = []
                failed += 1
        else:
            emb = []  # API 키 없음 → 키워드 검색 모드
        d["embedding"] = emb
        base.append(d)

    _knowledge_base = base
    if new:
        _save_cache()

    stats = {
        "total_docs": len(base),
        "duplicates_removed": len(docs) - len(unique),
        "embeddings_reused": reused,
        "embeddings_new": new,
        "embeddings_failed": failed,
        "mode": "embedding" if client is not None else "keyword",
        "external_files": sorted({d.get("_file") for d in docs if d.get("_file")}),
    }
    global _last_stats
    _last_stats = stats
    return stats


def initialize_knowledge_base(force: bool = False) -> dict:
    """지식 베이스 초기화 (내장 + 외부 JSONL). 이미 초기화돼 있으면 스킵."""
    if _knowledge_base and not force:
        return _last_stats
    builtin = [_normalize_doc(d) for d in MEDICAL_KNOWLEDGE]
    external = _load_external_docs()
    return _build(builtin + external)


def reload_knowledge_base() -> dict:
    """외부 지식파일을 다시 읽어 지식 베이스를 재구성한다(갱신 반영).

    데이터 담당자가 knowledge/*.jsonl 을 추가·수정한 뒤 이 함수를 호출하면
    서버 재시작 없이 즉시 반영됩니다(변경분만 임베딩).
    """
    return initialize_knowledge_base(force=True)


def knowledge_status() -> dict:
    """현재 지식 베이스 현황(문서 수/출처/분류/최근 통계)."""
    if not _knowledge_base:
        initialize_knowledge_base()
    by_cat, by_source = {}, {}
    for d in _knowledge_base:
        by_cat[d["category"]] = by_cat.get(d["category"], 0) + 1
        by_source[d["source"]] = by_source.get(d["source"], 0) + 1
    return {
        "total_docs": len(_knowledge_base),
        "by_category": by_cat,
        "by_source": by_source,
        "last_build": _last_stats,
        "cached_embeddings": len(_embedding_cache),
    }


# ==================== 검색 ====================

def search_knowledge(query: str, top_k: int = 3) -> List[dict]:
    """쿼리와 유사한 의학 지식 검색"""
    if not _knowledge_base:
        initialize_knowledge_base()

    try:
        query_embedding = _get_embedding(query)
    except Exception:
        return _keyword_search(query, top_k)

    scored = []
    for doc in _knowledge_base:
        if doc["embedding"]:
            score = _cosine_similarity(query_embedding, doc["embedding"])
            scored.append((score, doc))

    if not scored:
        return _keyword_search(query, top_k)

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
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=text)
    return response.data[0].embedding


def _cosine_similarity(a: List[float], b: List[float]) -> float:
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
