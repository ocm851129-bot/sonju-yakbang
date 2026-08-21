"""DUR 병용금기 분석 - 전문약·일반약·건기식 통합 안전성 점검

처리 흐름:
1차) 공공데이터포털 DUR API 조회 (의약품안전나라)
2차) 로컬 Rule Engine (API 불가 시 fallback)
3차) AI 보조 분석 (Rule Engine에서 잡지 못한 상호작용)
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from openai import OpenAI
from app.database import get_db
from app.models import Medication, DURAlert
from app.config import OPENAI_API_KEY, DUR_API_KEY
from app.dur_database import (
    search_dur_contraindication,
    search_dur_elderly_caution,
    local_dur_check,
)
import json

router = APIRouter()
client = OpenAI(api_key=OPENAI_API_KEY)


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

    # ===== 1차: 공공데이터포털 DUR API 조회 =====
    if DUR_API_KEY:
        api_alerts = await _check_dur_api(medications)
        if api_alerts:
            alerts.extend(api_alerts)
            data_source = "공공데이터포털 DUR API"

        # 노인주의 약물 조회
        elderly_alerts = await _check_elderly_caution(medications)
        alerts.extend(elderly_alerts)

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
    """공공데이터포털 DUR API로 병용금기 조회"""
    alerts = []
    for i, med_a in enumerate(medications):
        for j, med_b in enumerate(medications):
            if i >= j:
                continue
            results = await search_dur_contraindication(
                med_a.ingredient or med_a.name,
                med_b.ingredient or med_b.name,
            )
            for r in results:
                alerts.append({
                    "type": "contraindication",
                    "severity": "high",
                    "medication_a": med_a.name,
                    "medication_b": med_b.name,
                    "description": r.get("PROHBT_CONTENT", "병용금기 약물입니다"),
                    "recommendation": "의사 또는 약사와 상담하세요",
                    "source": "DUR_API",
                })
    return alerts


async def _check_elderly_caution(medications: list) -> list:
    """노인주의 약물 조회"""
    alerts = []
    for med in medications:
        results = await search_dur_elderly_caution(med.ingredient or med.name)
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
