"""약품정보 조회 - 식약처 의약품 제품 허가정보 + e약은요 연동

어르신이 약 이름(또는 OCR로 인식된 품목명)으로 검색하면
공식 허가정보(효능·용법·주의·저장)와 쉬운말 설명을 함께 보여줍니다.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.database import get_db
from app.models import Medication
from app.drug_permission import get_drug_full_info
from app.drug_identification import identify_pill, search_identity_by_name
from app.health_food import get_health_food_info

router = APIRouter()


class DrugInfoResult(BaseModel):
    matched: bool
    query: str
    item_name: str
    company: str = ""
    category: str = "prescription"
    product_type: str = "prescription"  # prescription | otc | health_functional_food
    etc_otc: str = ""
    class_name: str = ""
    ingredient: str = ""
    appearance: str = ""
    storage: str = ""
    valid_term: str = ""
    effect: str = ""
    usage: str = ""
    caution: str = ""
    easy_effect: str = ""
    easy_usage: str = ""
    easy_warn: str = ""
    easy_caution: str = ""
    easy_interaction: str = ""
    easy_side_effect: str = ""
    easy_storage: str = ""
    # 건강기능식품 전용 필드
    functional_content: str = ""
    intake_method: str = ""
    raw_material: str = ""
    image_url: str = ""
    # 낱알식별 전용 필드 (생김새로 약을 식별)
    drug_shape: str = ""
    colors: list = []
    print_front: str = ""
    print_back: str = ""
    line_front: str = ""
    line_back: str = ""
    size_long: str = ""
    sources: list = []
    is_demo: bool = False


class PillCandidate(BaseModel):
    item_name: str = ""
    company: str = ""
    etc_otc: str = ""
    class_name: str = ""
    drug_shape: str = ""
    colors: list = []
    print_front: str = ""
    print_back: str = ""
    line_front: str = ""
    appearance: str = ""
    image_url: str = ""
    source: str = ""


class PillIdentifyResult(BaseModel):
    matched: bool
    count: int
    candidates: list = []
    mode: str = ""
    scanned: int = 0
    note: str = ""


def _health_food_to_result(info: dict, query: str) -> dict:
    """건강기능식품 정보를 DrugInfoResult 스키마로 변환."""
    fc = info.get("functional_content", "")
    im = info.get("intake_method", "")
    return {
        "matched": info.get("matched", False),
        "query": query,
        "item_name": info.get("item_name", query),
        "company": info.get("company", ""),
        "category": "supplement",
        "product_type": "health_functional_food",
        "etc_otc": "건강기능식품",
        "class_name": "건강기능식품",
        "ingredient": info.get("raw_material", ""),
        "effect": fc,
        "usage": im,
        "caution": info.get("caution", ""),
        "easy_effect": fc,
        "easy_usage": im,
        "easy_caution": info.get("caution", ""),
        "functional_content": fc,
        "intake_method": im,
        "raw_material": info.get("raw_material", ""),
        "sources": info.get("sources", []),
        "is_demo": info.get("is_demo", False),
    }


@router.get("/search", response_model=DrugInfoResult)
async def search_drug(name: str, ingredient: str = ""):
    """품목명으로 정보를 검색합니다. 의약품(식약처 허가정보)을 먼저 찾고,
    없으면 건강기능식품(기능성 제품) 정보로 폴백합니다.

    예) /api/drug-info/search?name=아모디핀정 5mg
        /api/drug-info/search?name=오메가3
    """
    if not name or not name.strip():
        raise HTTPException(status_code=400, detail="제품명을 입력해주세요")
    info = await get_drug_full_info(name, ingredient)
    if info.get("matched"):
        return DrugInfoResult(**info)
    # 의약품에서 못 찾으면 건강기능식품으로 폴백
    hf = await get_health_food_info(name)
    if hf.get("matched"):
        return DrugInfoResult(**_health_food_to_result(hf, name))
    return DrugInfoResult(**info)


@router.get("/identify", response_model=PillIdentifyResult)
async def identify_pill_endpoint(
    shape: str = "",
    color: str = "",
    mark: str = "",
    line: str = "",
    form: str = "",
    limit: int = 10,
):
    """낱알(알약)의 생김새로 약 후보를 역검색합니다.

    어르신이 약봉투 없이 '알약 하나'만 들고 있을 때, 모양·색·각인으로 약을 찾습니다.
    예) /api/drug-info/identify?shape=원형&color=하양&mark=AD
        /api/drug-info/identify?color=노랑&line=있음
    """
    if not any([shape, color, mark, line, form]):
        raise HTTPException(status_code=400, detail="모양·색상·각인 중 하나 이상을 입력해주세요")
    res = await identify_pill(
        shape=shape, color=color, mark=mark, line=line, form=form, limit=limit
    )
    candidates = res.get("candidates", [])

    def _to_candidate(c: dict) -> PillCandidate:
        vals = {}
        for k in PillCandidate.model_fields:
            v = c.get(k)
            if k == "colors":
                vals[k] = v or []
            else:
                vals[k] = v if isinstance(v, str) else ("" if v is None else str(v))
        return PillCandidate(**vals)

    return PillIdentifyResult(
        matched=bool(candidates),
        count=len(candidates),
        candidates=[_to_candidate(c) for c in candidates],
        mode=res.get("mode", ""),
        scanned=res.get("scanned", 0),
        note=res.get("note", ""),
    )


@router.get("/identify/by-name", response_model=PillCandidate)
async def identify_by_name(name: str):
    """품목명으로 낱알식별정보(생김새·이미지)만 단독 조회합니다."""
    if not name or not name.strip():
        raise HTTPException(status_code=400, detail="제품명을 입력해주세요")
    info = await search_identity_by_name(name.strip())
    if not info:
        raise HTTPException(status_code=404, detail="낱알식별정보를 찾을 수 없습니다")
    return PillCandidate(**{k: info.get(k, "") for k in PillCandidate.model_fields})


@router.get("/health-food/search", response_model=DrugInfoResult)
async def search_health_food(name: str):
    """건강기능식품(기능성 제품) 전용 검색.

    예) /api/drug-info/health-food/search?name=프로바이오틱스
    """
    if not name or not name.strip():
        raise HTTPException(status_code=400, detail="제품명을 입력해주세요")
    hf = await get_health_food_info(name)
    return DrugInfoResult(**_health_food_to_result(hf, name))


@router.get("/medication/{medication_id}", response_model=DrugInfoResult)
async def drug_info_for_medication(medication_id: int, db: Session = Depends(get_db)):
    """등록된 복용약의 상세 허가정보를 조회합니다."""
    med = db.query(Medication).filter(Medication.id == medication_id).first()
    if not med:
        raise HTTPException(status_code=404, detail="약을 찾을 수 없습니다")
    info = await get_drug_full_info(med.name, med.ingredient or "")

    # 조회된 성분/저장 정보를 등록약에 보강 (비어있을 때만)
    updated = False
    if info.get("matched"):
        if not med.ingredient and info.get("ingredient"):
            med.ingredient = info["ingredient"]
            updated = True
        if not med.notes and info.get("easy_caution"):
            med.notes = info["easy_caution"]
            updated = True
    if updated:
        db.commit()

    return DrugInfoResult(**info)
