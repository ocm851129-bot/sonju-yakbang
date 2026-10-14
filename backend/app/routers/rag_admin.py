"""RAG 지식베이스 관리 라우터

데이터 담당자가 backend/knowledge/*.jsonl 을 추가·수정한 뒤,
서버 재시작 없이 아래 엔드포인트로 반영/확인할 수 있습니다.

  GET /api/rag/status   → 현재 지식 문서 수·분류·출처·캐시 현황
  POST /api/rag/reload  → 지식파일 다시 읽어 반영(변경분만 임베딩)
  GET /api/rag/search   → 테스트용 유사도 검색(디버깅)
"""
from fastapi import APIRouter
from app.rag_engine import reload_knowledge_base, knowledge_status, search_knowledge

router = APIRouter()


@router.get("/status")
def rag_status():
    """현재 RAG 지식베이스 현황을 반환합니다."""
    return knowledge_status()


@router.post("/reload")
def rag_reload():
    """knowledge/*.jsonl 을 다시 읽어 지식베이스를 갱신합니다(변경분만 임베딩).

    반환 통계: 총 문서 수, 중복 제거 수, 임베딩 재사용/신규/실패 수.
    """
    stats = reload_knowledge_base()
    return {"ok": True, "message": "지식베이스를 갱신했습니다.", "stats": stats}


@router.get("/search")
def rag_search(q: str, top_k: int = 3):
    """테스트용: 질의와 유사한 지식 문서를 조회합니다(관리/디버깅)."""
    docs = search_knowledge(q, top_k=top_k)
    return {
        "query": q,
        "results": [
            {"id": d.get("id"), "text": d["text"], "source": d["source"], "category": d["category"]}
            for d in docs
        ],
    }
