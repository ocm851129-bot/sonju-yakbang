"""DUR 병용금기 분석 - 전문약·일반약·건기식 통합 안전성 점검

처리 흐름:
1차) 공공데이터포털 DUR API 조회 (의약품안전나라)
2차) 로컬 Rule Engine (API 불가 시 fallback)
3차) AI 보조 분석 (Rule Engine에서 잡지 못한 상호작용)
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from openai import OpenAI
from app.database import get_db
from app.models import Medication, DURAlert, ChronicDisease
from app.config import OPENAI_API_KEY, DUR_API_KEY
from app.dur_database import (
    search_dur_contraindication,
    search_dur_elderly_caution,
    local_dur_check,
)
from app.interaction_engine import check_interaction
from app.drug_permission import get_drug_full_info
import json
import asyncio

# DUR 외부 API 폭주 방지:
#   병용금기 검사는 약 쌍마다 호출(O(N^2))이라 약이 많으면 수천 번 호출 → 150초 초과.
#   그래서 (1) 서로 다른 약만 추려 상한을 두고, (2) 외부 API 전체에 시간 예산을 둔다.
#   예산을 넘으면 외부 API는 건너뛰고 빠른 로컬 규칙 엔진 결과로 응답한다.
MAX_DUR_MEDS = 15
DUR_API_BUDGET_SEC = 12.0
_DUR_CONCURRENCY = 6


def _dedupe_cap_meds(medications: list) -> list:
    """같은 이름의 약(중복)을 제거하고 최대 MAX_DUR_MEDS 개로 제한한다."""
    seen = set()
    out = []
    for m in medications:
        key = (getattr(m, "name", "") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(m)
        if len(out) >= MAX_DUR_MEDS:
            break
    return out

router = APIRouter()
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


# ==================== 병용 확인(새 제품 vs 기존약) 핵심 기능 ====================

class ProductIn(BaseModel):
    name: str
    ingredients: List[str] = []
    category: str = ""


class InteractionCheckRequest(BaseModel):
    new_product: ProductIn
    current_medications: List[ProductIn] = []
    conditions: List[str] = []
    user_id: Optional[int] = None
    resolve_ingredients: bool = True


async def _resolve_ingredients(name: str, given: List[str]) -> List[str]:
    """성분이 비어있으면 식약처 허가정보/e약은요로 성분 문자열을 보강한다.
    classify()는 부분일치로 동작하므로 원문 성분 문자열 그대로 넣어도 분류가 잡힌다."""
    ings = [i for i in (given or []) if i and i.strip()]
    if ings:
        return ings
    try:
        info = await get_drug_full_info(name, "")
        if info.get("ingredient"):
            return [info["ingredient"]]
    except Exception:
        pass
    return []


@router.post("/check-interaction")
async def check_new_product_interaction(req: InteractionCheckRequest, db: Session = Depends(get_db)):
    """'새로 드시려는 제품'을 기존 복용약과 비교해 병용 안전성을 확인한다.

    - current_medications 를 주면 그대로 비교, 없고 user_id 가 있으면 DB의 복용약을 사용.
    - conditions(만성질환)도 user_id 로 자동 보강.
    - 반환: 3단계 위험도(danger/caution/info) + 각 건의 무엇/왜/어떻게 + 안전고지.
    """
    # 기존 복용약 확보
    current = [{"name": m.name, "ingredients": m.ingredients} for m in req.current_medications]
    conditions = list(req.conditions)
    if not current and req.user_id:
        meds = db.query(Medication).filter(
            Medication.user_id == req.user_id, Medication.is_active == True
        ).all()
        current = [{"name": m.name, "ingredients": [m.ingredient] if m.ingredient else []} for m in meds]
    if not conditions and req.user_id:
        diseases = db.query(ChronicDisease).filter(ChronicDisease.user_id == req.user_id).all()
        conditions = [d.disease_name for d in diseases if d.disease_name]

    # 성분 보강
    if req.resolve_ingredients:
        new_ings = await _resolve_ingredients(req.new_product.name, req.new_product.ingredients)
        resolved_current = []
        for c in current:
            ci = c["ingredients"] if c["ingredients"] else await _resolve_ingredients(c["name"], [])
            resolved_current.append({"name": c["name"], "ingredients": ci})
        current = resolved_current
    else:
        new_ings = req.new_product.ingredients

    result = check_interaction(
        new_product={"name": req.new_product.name, "ingredients": new_ings,
                     "category": req.new_product.category},
        current_medications=current,
        conditions=conditions,
    )
    return result


class DURAnalysisResult(BaseModel):
    alerts: list
    total_risk_score: int
    summary: str
    recommendation: str
    data_source: str


@router.get("/analyze/{user_id}", response_model=DURAnalysisResult)
async def analyze_dur(user_id: int, db: Session = Depends(get_db)):
    """사용자의 전체 복용약에 대한 DUR 분석 수행
    
    분석 순서:
    1. 공공데이터포털 DUR API (HIRA/식약처) - 병용금기, 노인주의
    2. 로컬 Rule Engine - API 미응답 시 fallback
    3. AI 보조 분석 - 건기식·OTC 포함 추가 분석
    """
    medications = (
        db.query(Medication)
        .filter(Medication.user_id == user_id, Medication.is_active == True)
        .all()
    )

    if not medications:
        return DURAnalysisResult(
            alerts=[],
            total_risk_score=0,
            summary="현재 등록된 복용약이 없습니다.",
            recommendation="복용 중인 약을 등록해주세요.",
            data_source="none",
        )

    alerts = []
    data_source = "local_rule"

    # ===== 1차: 공공데이터포털 DUR API 조회 (중복제거·상한·시간예산) =====
    if DUR_API_KEY:
        dur_meds = _dedupe_cap_meds(medications)
        try:
            api_alerts, elderly_alerts = await asyncio.wait_for(
                asyncio.gather(
                    _check_dur_api(dur_meds),
                    _check_elderly_caution(dur_meds),
                ),
                timeout=DUR_API_BUDGET_SEC,
            )
            if api_alerts:
                alerts.extend(api_alerts)
                data_source = "공공데이터포털 DUR API"
            alerts.extend(elderly_alerts)
        except asyncio.TimeoutError:
            print(f"[DUR] 외부 API 시간예산({DUR_API_BUDGET_SEC}s) 초과 → 로컬 규칙 엔진으로 대체")
        except Exception as e:
            print(f"[DUR] 외부 API 조회 실패({type(e).__name__}) → 로컬 규칙 엔진으로 대체")

    # ===== 2차: 로컬 Rule Engine (API 결과 보완) =====
    local_alerts = _check_local_rules(medications)
    # API에서 이미 찾은 것과 중복 제거
    existing_pairs = {(a.get("medication_a", ""), a.get("medication_b", "")) for a in alerts}
    for la in local_alerts:
        pair = (la["medication_a"], la["medication_b"])
        if pair not in existing_pairs:
            alerts.append(la)
            if data_source == "local_rule":
                data_source = "로컬 Rule Engine"

    # ===== 3차: AI 보조 분석 (건기식·OTC 포함) =====
    if len(medications) >= 2:
        ai_alerts = _ai_dur_analysis(medications)
        for aa in ai_alerts:
            pair = (aa.get("medication_a", ""), aa.get("medication_b", ""))
            if pair not in existing_pairs:
                alerts.append(aa)
                existing_pairs.add(pair)
        if data_source == "none":
            data_source = "AI 분석"

    # DB에 알림 저장
    for alert in alerts:
        db_alert = DURAlert(
            user_id=user_id,
            alert_type=alert.get("type", "interaction"),
            severity=alert.get("severity", "medium"),
            medication_a=alert.get("medication_a", ""),
            medication_b=alert.get("medication_b", ""),
            description=alert.get("description", ""),
            recommendation=alert.get("recommendation", ""),
        )
        db.add(db_alert)
    db.commit()

    # 위험도 점수 계산
    score_map = {"high": 30, "medium": 15, "low": 5}
    total_score = sum(score_map.get(a.get("severity", "low"), 5) for a in alerts)

    # 종합 요약
    if total_score == 0:
        summary = "현재 복용 중인 약물 간 특별한 상호작용이 발견되지 않았습니다."
        recommendation = "현재 복약 상태를 유지하시고, 새 약 추가 시 다시 검사해주세요."
    elif total_score <= 30:
        summary = f"주의가 필요한 약물 조합이 {len(alerts)}건 발견되었습니다."
        recommendation = "다음 병원 방문 시 담당 의사에게 말씀해 주세요."
    else:
        summary = f"위험한 약물 조합이 {len(alerts)}건 발견되었습니다. 즉시 확인이 필요합니다."
        recommendation = "가능한 빨리 약사 또는 담당 의사와 상담하세요."

    return DURAnalysisResult(
        alerts=alerts,
        total_risk_score=total_score,
        summary=summary,
        recommendation=recommendation,
        data_source=data_source,
    )


async def _check_dur_api(medications: list) -> list:
    """공공데이터포털 DUR API로 병용금기 조회 (약 쌍을 병렬 조회)."""
    sem = asyncio.Semaphore(_DUR_CONCURRENCY)

    async def _one_pair(med_a, med_b):
        async with sem:
            try:
                results = await search_dur_contraindication(
                    med_a.ingredient or med_a.name,
                    med_b.ingredient or med_b.name,
                )
            except Exception:
                return []
        return [{
            "type": "contraindication",
            "severity": "high",
            "medication_a": med_a.name,
            "medication_b": med_b.name,
            "description": r.get("PROHBT_CONTENT", "병용금기 약물입니다"),
            "recommendation": "의사 또는 약사와 상담하세요",
            "source": "DUR_API",
        } for r in results]

    pairs = [(medications[i], medications[j])
             for i in range(len(medications)) for j in range(i + 1, len(medications))]
    nested = await asyncio.gather(*[_one_pair(a, b) for a, b in pairs])
    return [alert for sub in nested for alert in sub]


async def _check_elderly_caution(medications: list) -> list:
    """노인주의 약물 조회 (약별 병렬 조회)."""
    sem = asyncio.Semaphore(_DUR_CONCURRENCY)

    async def _one(med):
        async with sem:
            try:
                return med, await search_dur_elderly_caution(med.ingredient or med.name)
            except Exception:
                return med, []

    alerts = []
    for med, results in await asyncio.gather(*[_one(m) for m in medications]):
        for r in results:
            alerts.append({
                "type": "elderly_caution",
                "severity": "medium",
                "medication_a": med.name,
                "medication_b": "",
                "description": r.get("PROHBT_CONTENT", "노인에게 주의가 필요한 약물입니다"),
                "recommendation": r.get("REMARK", "의사와 상담하세요"),
                "source": "DUR_API",
            })
    return alerts


def _check_local_rules(medications: list) -> list:
    """로컬 Rule Engine 기반 점검"""
    alerts = []
    for i, med_a in enumerate(medications):
        for j, med_b in enumerate(medications):
            if i >= j:
                continue
            found = local_dur_check(
                med_a.name, med_a.ingredient or "",
                med_b.name, med_b.ingredient or "",
            )
            alerts.extend(found)
    return alerts


def _ai_dur_analysis(medications: list) -> list:
    """AI 기반 추가 DUR 분석 (건기식·OTC 포함, Rule Engine 보완)"""
    med_info = "\n".join([
        f"- {m.name} ({m.category}): {m.ingredient or '성분 미상'}, {m.frequency}"
        for m in medications
    ])

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """당신은 DUR(의약품 적정사용) 전문 약사입니다.
복용 약물 목록을 분석하여 병용금기, 중복처방, 용량초과, 고령자 주의사항을 찾아주세요.
주의: 확실한 근거가 있는 경우만 알림을 생성하세요. 추측하지 마세요.
JSON으로 응답하세요. 문제가 없으면 빈 배열을 반환하세요.

형식: {"alerts": [{"type": "interaction|duplicate|overdose|elderly_caution", "severity": "high|medium|low", "medication_a": "약1", "medication_b": "약2", "description": "설명", "recommendation": "권고", "source": "AI_analysis"}]}""",
                },
                {"role": "user", "content": f"다음 복용 약물을 분석해주세요:\n{med_info}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        result = json.loads(response.choices[0].message.content)
        return result.get("alerts", [])
    except Exception:
        return []
