"""만성질환 관리 - 고혈압·당뇨 모니터링, 건강점수, 건기식 추천"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from openai import OpenAI
from app.database import get_db
from app.models import ChronicDisease, HealthRecord, Medication
from app.config import OPENAI_API_KEY
import json

router = APIRouter()
client = OpenAI(api_key=OPENAI_API_KEY)


class VitalSignInput(BaseModel):
    user_id: int
    systolic: Optional[int] = None  # 수축기 혈압
    diastolic: Optional[int] = None  # 이완기 혈압
    blood_sugar: Optional[int] = None  # 혈당
    weight: Optional[float] = None
    temperature: Optional[float] = None


class HealthScoreResponse(BaseModel):
    score: int
    level: str
    summary: str
    recommendations: list


@router.post("/vitals/record")
def record_vitals(data: VitalSignInput, db: Session = Depends(get_db)):
    """혈압·혈당 등 바이탈 사인 기록"""
    values = {}
    warnings = []

    if data.systolic and data.diastolic:
        values["systolic"] = data.systolic
        values["diastolic"] = data.diastolic
        if data.systolic >= 180 or data.diastolic >= 120:
            warnings.append("⚠️ 혈압이 매우 높습니다 (고혈압 위기). 즉시 병원에 가세요.")
        elif data.systolic >= 140 or data.diastolic >= 90:
            warnings.append("주의: 혈압이 높습니다. 안정을 취하고 30분 후 다시 측정해주세요.")

    if data.blood_sugar:
        values["blood_sugar"] = data.blood_sugar
        if data.blood_sugar >= 300:
            warnings.append("⚠️ 혈당이 매우 높습니다. 즉시 병원에 가세요.")
        elif data.blood_sugar >= 200:
            warnings.append("주의: 혈당이 높습니다. 수분 섭취 후 1시간 뒤 재측정하세요.")
        elif data.blood_sugar <= 70:
            warnings.append("⚠️ 저혈당입니다. 사탕이나 주스를 드시고 15분 후 재측정하세요.")

    if data.weight:
        values["weight"] = data.weight
    if data.temperature:
        values["temperature"] = data.temperature

    # DB 저장
    record = HealthRecord(
        user_id=data.user_id,
        record_type="vital_sign",
        content=json.dumps(values, ensure_ascii=False),
        structured_data=values,
        source="manual",
    )
    db.add(record)
    db.commit()

    return {
        "message": "건강 수치 기록 완료",
        "values": values,
        "warnings": warnings,
    }


@router.get("/score/{user_id}", response_model=HealthScoreResponse)
def get_health_score(user_id: int, db: Session = Depends(get_db)):
    """오늘의 건강 점수 산출"""
    # 최근 건강 기록 조회
    recent_records = (
        db.query(HealthRecord)
        .filter(HealthRecord.user_id == user_id)
        .order_by(HealthRecord.created_at.desc())
        .limit(10)
        .all()
    )

    medications = (
        db.query(Medication)
        .filter(Medication.user_id == user_id, Medication.is_active == True)
        .all()
    )

    # 기본 점수 계산 (100점 만점)
    score = 70  # 기본
    recommendations = []

    # 복약 등록 여부
    if medications:
        score += 10
    else:
        recommendations.append("복용 중인 약을 등록하면 더 정확한 관리가 가능합니다")

    # 최근 기록 여부
    if recent_records:
        score += 10
        latest = recent_records[0].structured_data or {}
        if latest.get("systolic"):
            if latest["systolic"] < 140:
                score += 5
            else:
                score -= 5
                recommendations.append("혈압이 높습니다. 저염식 식단을 유지하세요")
        if latest.get("blood_sugar"):
            if 80 <= latest["blood_sugar"] <= 130:
                score += 5
            else:
                score -= 5
                recommendations.append("혈당 관리에 주의가 필요합니다")
    else:
        recommendations.append("건강 수치를 기록하면 맞춤형 관리가 가능합니다")

    score = max(0, min(100, score))

    # 레벨 판정
    if score >= 85:
        level = "양호"
    elif score >= 70:
        level = "보통"
    elif score >= 50:
        level = "주의"
    else:
        level = "위험"

    summary = f"오늘의 건강 점수는 {score}점({level})입니다."

    if not recommendations:
        recommendations.append("현재 건강 상태가 양호합니다. 꾸준히 관리해주세요!")

    return HealthScoreResponse(
        score=score,
        level=level,
        summary=summary,
        recommendations=recommendations,
    )


@router.get("/supplement-recommend/{user_id}")
def recommend_supplement(user_id: int, db: Session = Depends(get_db)):
    """개인 맞춤 건강기능식품 추천"""
    medications = (
        db.query(Medication)
        .filter(Medication.user_id == user_id, Medication.is_active == True)
        .all()
    )

    med_info = "\n".join([f"- {m.name} ({m.ingredient})" for m in medications]) or "없음"

    diseases = (
        db.query(ChronicDisease)
        .filter(ChronicDisease.user_id == user_id)
        .all()
    )
    disease_info = ", ".join([d.disease_name for d in diseases]) or "없음"

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """당신은 건강기능식품 전문 약사입니다.
사용자의 복용약과 질환을 고려하여 안전한 건강기능식품을 추천해주세요.
반드시 병용금기를 확인하고, 안전한 것만 추천하세요.
JSON으로 응답하세요.
형식: {"recommendations": [{"name": "제품군명", "benefit": "기대효과", "caution": "주의사항", "safe_with_current_meds": true}], "disclaimer": "면책문구"}""",
                },
                {
                    "role": "user",
                    "content": f"현재 복용약:\n{med_info}\n\n보유 질환: {disease_info}\n\n적합한 건강기능식품을 추천해주세요.",
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        result = json.loads(response.choices[0].message.content)
        result["disclaimer"] = "※ 이 추천은 참고용이며, 구매 전 담당 약사와 상담하세요."
        return result
    except Exception:
        return {
            "recommendations": [],
            "disclaimer": "추천을 생성할 수 없습니다. 잠시 후 다시 시도해주세요.",
        }
