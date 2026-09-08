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

router = APIRouter()


class DrugInfoResult(BaseModel):
    matched: bool
    query: str
    item_name: str
    company: str = ""
    category: str = "prescription"
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
    image_url: str = ""
    sources: list = []
    is_demo: bool = False


@router.get("/search", response_model=DrugInfoResult)
async def search_drug(name: str, ingredient: str = ""):
    """약품명으로 식약처 허가정보를 검색합니다.

    예) /api/drug-info/search?name=아모디핀정 5mg
    """
    if not name or not name.strip():
        raise HTTPException(status_code=400, detail="약품명을 입력해주세요")
    info = await get_drug_full_info(name, ingredient)
    return DrugInfoResult(**info)


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
