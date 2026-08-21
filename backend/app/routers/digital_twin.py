"""디지털 트윈 - 개인 건강 프로파일 시뮬레이션 및 예측

기능:
- "만약 약을 안 먹으면?" 시나리오 시뮬레이션
- 복약 순응도 기반 건강 결과 예측
- 생활습관 변화에 따른 건강 지표 변화 예측
- 주간/월간 건강 트렌드 분석 및 미래 예측
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
from openai import OpenAI
from app.database import get_db
from app.models import User, Medication, HealthRecord, MedicationAlarm, ChronicDisease
from app.config import OPENAI_API_KEY
import json

router = APIRouter()
client = OpenAI(api_key=OPENAI_API_KEY)


class SimulationScenario(BaseModel):
    user_id: int
    scenario: str  # "stop_medication", "miss_3_days", "add_exercise", "reduce_salt", "stop_supplement"
    target_medication: Optional[str] = None


class SimulationResult(BaseModel):
    scenario_name: str
    current_state: dict
    predicted_outcome: dict
    risk_change: str
    timeline: str
    recommendation: str
    confidence: float


class HealthTrend(BaseModel):
    period: str
    data_points: List[dict]
    trend_direction: str  # improving, stable, declining
    prediction_7days: dict
    ai_insight: str


@router.post("/simulate", response_model=SimulationResult)
def simulate_scenario(data: SimulationScenario, db: Session = Depends(get_db)):
    """건강 시나리오 시뮬레이션 — "만약 ~하면?" 예측"""
    user = db.query(User).filter(User.id == data.user_id).first()
    if not user:
        return SimulationResult(
            scenario_name="", current_state={}, predicted_outcome={},
            risk_change="", timeline="", recommendation="", confidence=0
        )

    # 현재 상태 수집
    medications = db.query(Medication).filter(
        Medication.user_id == data.user_id, Medication.is_active == True
    ).all()

    recent_vitals = db.query(HealthRecord).filter(
        HealthRecord.user_id == data.user_id,
        HealthRecord.record_type == "vital_sign",
    ).order_by(HealthRecord.created_at.desc()).limit(7).all()

    med_list = [f"{m.name}({m.ingredient})" for m in medications]
    vital_summary = _summarize_vitals(recent_vitals)

    # 시나리오별 시뮬레이션
    scenario_prompts = {
        "stop_medication": f"환자가 현재 복용 중인 약({data.target_medication or '전체'})을 갑자기 중단한다면?",
        "miss_3_days": f"환자가 3일간 약({data.target_medication or '전체'})을 빠뜨린다면?",
        "add_exercise": "환자가 매일 30분 걷기 운동을 시작한다면?",
        "reduce_salt": "환자가 저염식(1일 나트륨 2000mg 이하)으로 바꾼다면?",
        "stop_supplement": f"환자가 건강기능식품({data.target_medication or '전체'})을 중단한다면?",
    }

    scenario_prompt = scenario_prompts.get(data.scenario, f"시나리오: {data.scenario}")

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """당신은 임상약학 시뮬레이션 전문가입니다.
환자의 현재 상태와 시나리오를 기반으로 건강 결과를 예측합니다.
의학적 근거에 기반하여 보수적으로 예측하세요.

JSON으로 응답:
{
    "scenario_name": "시나리오 설명",
    "current_state": {"혈압": "130/80", "위험도": "중간"},
    "predicted_outcome": {"예상_혈압": "150/95", "예상_위험도": "높음", "예상_증상": ["두통", "어지러움"]},
    "risk_change": "위험도 30% 상승",
    "timeline": "1~2주 내 혈압 상승 시작, 4주 후 위험 수준 도달 가능",
    "recommendation": "절대 임의로 약을 중단하지 마세요. 의사와 상담 후 감량하세요.",
    "confidence": 0.75
}"""
                },
                {
                    "role": "user",
                    "content": f"""환자 정보:
- 이름: {user.name}, 생년월일: {user.birth_date}
- 복용약: {', '.join(med_list)}
- 최근 바이탈: {vital_summary}

시나리오: {scenario_prompt}

이 상황에서 예상되는 건강 결과를 시뮬레이션해주세요.""",
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.4,
        )

        result = json.loads(response.choices[0].message.content)
        return SimulationResult(**result)

    except Exception:
        return SimulationResult(
            scenario_name=scenario_prompt,
            current_state={"status": "데이터 부족"},
            predicted_outcome={"message": "시뮬레이션을 수행할 수 없습니다"},
            risk_change="알 수 없음",
            timeline="",
            recommendation="정확한 예측을 위해 건강 데이터를 더 기록해주세요.",
            confidence=0.0,
        )


@router.get("/trend/{user_id}", response_model=HealthTrend)
def get_health_trend(user_id: int, db: Session = Depends(get_db)):
    """주간 건강 트렌드 분석 및 7일 예측"""
    two_weeks_ago = datetime.utcnow() - timedelta(days=14)

    records = db.query(HealthRecord).filter(
        HealthRecord.user_id == user_id,
        HealthRecord.record_type == "vital_sign",
        HealthRecord.created_at >= two_weeks_ago,
    ).order_by(HealthRecord.created_at.asc()).all()

    data_points = []
    systolic_values = []

    for r in records:
        if r.structured_data:
            point = {
                "date": str(r.created_at)[:10],
                "systolic": r.structured_data.get("systolic"),
                "diastolic": r.structured_data.get("diastolic"),
                "blood_sugar": r.structured_data.get("blood_sugar"),
            }
            data_points.append(point)
            if r.structured_data.get("systolic"):
                systolic_values.append(r.structured_data["systolic"])

    # 트렌드 방향 판정
    trend_direction = "stable"
    if len(systolic_values) >= 3:
        recent = systolic_values[-3:]
        if recent[-1] > recent[0] + 10:
            trend_direction = "declining"  # 악화
        elif recent[-1] < recent[0] - 10:
            trend_direction = "improving"  # 개선

    # 7일 예측 (선형 추세 기반)
    prediction = {}
    if systolic_values:
        avg = sum(systolic_values) / len(systolic_values)
        if trend_direction == "declining":
            prediction = {"predicted_systolic": int(avg + 5), "risk": "상승 추세 주의"}
        elif trend_direction == "improving":
            prediction = {"predicted_systolic": int(avg - 3), "risk": "양호한 추세"}
        else:
            prediction = {"predicted_systolic": int(avg), "risk": "안정 유지"}

    # AI 인사이트
    ai_insight = _generate_trend_insight(trend_direction, data_points)

    return HealthTrend(
        period="최근 2주",
        data_points=data_points[-14:],
        trend_direction=trend_direction,
        prediction_7days=prediction,
        ai_insight=ai_insight,
    )


@router.get("/scenarios/{user_id}")
def get_available_scenarios(user_id: int, db: Session = Depends(get_db)):
    """사용자에게 가능한 시뮬레이션 시나리오 목록"""
    medications = db.query(Medication).filter(
        Medication.user_id == user_id, Medication.is_active == True
    ).all()

    scenarios = [
        {"id": "add_exercise", "name": "매일 30분 걷기를 시작하면?", "icon": "🏃"},
        {"id": "reduce_salt", "name": "저염식으로 바꾸면?", "icon": "🥗"},
    ]

    for med in medications:
        if med.category == "prescription":
            scenarios.append({
                "id": "stop_medication",
                "name": f"{med.name}을 중단하면?",
                "icon": "⚠️",
                "target": med.name,
            })
        elif med.category == "supplement":
            scenarios.append({
                "id": "stop_supplement",
                "name": f"{med.name}을 중단하면?",
                "icon": "🌿",
                "target": med.name,
            })

    if medications:
        scenarios.insert(0, {"id": "miss_3_days", "name": "약을 3일 빠뜨리면?", "icon": "💊"})

    return {"scenarios": scenarios}


def _summarize_vitals(records) -> str:
    if not records:
        return "최근 기록 없음"
    values = []
    for r in records[:3]:
        if r.structured_data:
            s = r.structured_data
            parts = []
            if s.get("systolic"):
                parts.append(f"혈압 {s['systolic']}/{s.get('diastolic', '?')}")
            if s.get("blood_sugar"):
                parts.append(f"혈당 {s['blood_sugar']}")
            if parts:
                values.append(", ".join(parts))
    return " | ".join(values) if values else "기록 부족"


def _generate_trend_insight(direction: str, data_points: list) -> str:
    if direction == "improving":
        return "좋은 소식이에요! 건강 수치가 개선되는 추세입니다. 현재 생활습관을 유지하세요."
    elif direction == "declining":
        return "건강 수치가 조금 올라가는 추세예요. 저염식과 규칙적인 복약이 도움됩니다. 다음 진료 시 의사에게 말씀하세요."
    else:
        return "건강 수치가 안정적으로 유지되고 있어요. 꾸준히 관리하고 계시네요!"
