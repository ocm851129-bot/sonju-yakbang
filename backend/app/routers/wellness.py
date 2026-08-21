"""건강정보 콘텐츠 - 식단팁, 심신안정 음악/콘텐츠 추천, 질환정보"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from openai import OpenAI
from app.database import get_db
from app.models import ChronicDisease, Medication
from app.config import OPENAI_API_KEY
import json

router = APIRouter()
client = OpenAI(api_key=OPENAI_API_KEY)


@router.get("/disease-info/{user_id}")
def get_disease_info(user_id: int, db: Session = Depends(get_db)):
    """사용자의 만성질환 정보 및 관리 가이드"""
    diseases = (
        db.query(ChronicDisease)
        .filter(ChronicDisease.user_id == user_id)
        .all()
    )

    if not diseases:
        return {
            "diseases": [],
            "tags": ["#건강관리"],
            "guide": "등록된 질환 정보가 없습니다. 건강 기록을 시작해보세요!",
        }

    disease_list = [
        {
            "name": d.disease_name,
            "diagnosed_date": d.diagnosed_date if hasattr(d, "diagnosed_date") else None,
            "severity": d.severity if hasattr(d, "severity") else "보통",
        }
        for d in diseases
    ]

    # 개인화 해시태그 생성
    tags = []
    for d in diseases:
        name = d.disease_name
        if "고혈압" in name:
            tags.append("#혈압관리")
        elif "당뇨" in name:
            tags.append("#혈당관리")
        elif "고지혈" in name or "콜레스테롤" in name:
            tags.append("#콜레스테롤관리")
        elif "관절" in name:
            tags.append("#관절건강")
        else:
            tags.append(f"#{name}관리")
    tags.append("#마음의 안정")

    return {
        "diseases": disease_list,
        "tags": tags,
        "guide": f"현재 {', '.join([d.disease_name for d in diseases])} 관리 중입니다.",
    }


@router.get("/diet-tips/{user_id}")
def get_diet_tips(user_id: int, db: Session = Depends(get_db)):
    """질환 기반 맞춤 식단팁 추천"""
    diseases = (
        db.query(ChronicDisease)
        .filter(ChronicDisease.user_id == user_id)
        .all()
    )
    disease_names = [d.disease_name for d in diseases] if diseases else ["일반 건강"]

    medications = (
        db.query(Medication)
        .filter(Medication.user_id == user_id, Medication.is_active == True)
        .all()
    )
    med_names = [m.name for m in medications] if medications else []

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """당신은 고령자 전문 영양사입니다. 
사용자의 질환과 복용약을 고려하여 안전하고 실용적인 식단팁을 제공하세요.
고령자가 쉽게 이해할 수 있도록 간결하게 작성하세요.
JSON으로 응답하세요.
형식: {
    "title": "오늘의 식단팁 제목",
    "description": "간단한 설명",
    "tips": [{"category": "카테고리", "content": "팁 내용", "foods": ["추천 음식 목록"]}],
    "avoid_foods": ["피해야 할 음식"],
    "meal_suggestion": "오늘 추천 식단 한 줄"
}""",
                },
                {
                    "role": "user",
                    "content": f"질환: {', '.join(disease_names)}\n복용약: {', '.join(med_names) if med_names else '없음'}\n\n이 분에게 적합한 식단팁을 추천해주세요.",
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.4,
        )
        result = json.loads(response.choices[0].message.content)
        result["disclaimer"] = "※ 개인 상태에 따라 다를 수 있으니, 담당 의사와 상의하세요."
        return result
    except Exception:
        # 기본 식단팁 (API 실패 시)
        return {
            "title": "단백질이 풍부한 식단",
            "description": "근육 유지와 면역력 강화에 도움되는 식단입니다",
            "tips": [
                {
                    "category": "단백질",
                    "content": "매 끼니 단백질을 포함하세요",
                    "foods": ["두부", "계란", "생선", "닭가슴살", "콩"],
                },
                {
                    "category": "식이섬유",
                    "content": "채소와 과일을 충분히 드세요",
                    "foods": ["브로콜리", "시금치", "당근", "사과", "바나나"],
                },
                {
                    "category": "수분",
                    "content": "하루 6~8잔의 물을 드세요",
                    "foods": ["물", "보리차", "녹차"],
                },
            ],
            "avoid_foods": ["짠 음식", "가공식품", "튀긴 음식"],
            "meal_suggestion": "아침: 두부된장국 + 현미밥 + 나물반찬",
            "disclaimer": "※ 개인 상태에 따라 다를 수 있으니, 담당 의사와 상의하세요.",
        }


@router.get("/relax-content/{user_id}")
def get_relax_content(user_id: int, db: Session = Depends(get_db)):
    """심신안정 콘텐츠 추천 (음악, 명상, 활동)"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """당신은 고령자 정서 건강 전문가입니다.
마음 안정과 정서적 웰빙에 도움되는 콘텐츠를 추천하세요.
고령자가 쉽게 접근할 수 있는 것 위주로 추천하세요.
JSON으로 응답하세요.
형식: {
    "mood_message": "오늘의 정서 메시지",
    "music": [{"title": "곡명", "artist": "아티스트", "genre": "장르", "benefit": "효과"}],
    "activities": [{"name": "활동명", "duration": "소요시간", "benefit": "효과"}],
    "breathing": {"name": "호흡법 이름", "steps": ["단계별 설명"]}
}""",
                },
                {
                    "role": "user",
                    "content": "60~80대 어르신의 마음 안정에 좋은 콘텐츠를 추천해주세요. 한국 정서에 맞는 것으로요.",
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.6,
        )
        result = json.loads(response.choices[0].message.content)
        return result
    except Exception:
        # 기본 심신안정 콘텐츠 (API 실패 시)
        return {
            "mood_message": "오늘도 편안한 하루 보내세요. 잠시 쉬어가도 괜찮아요.",
            "music": [
                {
                    "title": "봄날은 간다",
                    "artist": "이미자",
                    "genre": "가요",
                    "benefit": "향수와 편안함",
                },
                {
                    "title": "Canon in D",
                    "artist": "파헬벨",
                    "genre": "클래식",
                    "benefit": "심박수 안정",
                },
                {
                    "title": "자연의 소리 - 계곡물",
                    "artist": "자연음",
                    "genre": "자연음",
                    "benefit": "스트레스 해소",
                },
            ],
            "activities": [
                {
                    "name": "산책하기",
                    "duration": "15~20분",
                    "benefit": "기분 전환, 혈액순환",
                },
                {
                    "name": "스트레칭",
                    "duration": "10분",
                    "benefit": "근육 이완, 통증 완화",
                },
                {
                    "name": "그림 그리기 / 색칠하기",
                    "duration": "20분",
                    "benefit": "집중력, 정서 안정",
                },
            ],
            "breathing": {
                "name": "4-7-8 호흡법",
                "steps": [
                    "코로 4초간 천천히 숨을 들이쉽니다",
                    "7초간 숨을 참습니다",
                    "입으로 8초간 천천히 내쉽니다",
                    "3~4회 반복합니다",
                ],
            },
        }


@router.get("/health-tags/{user_id}")
def get_health_tags(user_id: int, db: Session = Depends(get_db)):
    """개인화 건강 해시태그 생성"""
    diseases = (
        db.query(ChronicDisease)
        .filter(ChronicDisease.user_id == user_id)
        .all()
    )

    tags = []
    for d in diseases:
        name = d.disease_name
        if "고혈압" in name:
            tags.extend(["#혈압관리", "#저염식"])
        elif "당뇨" in name:
            tags.extend(["#혈당관리", "#식이요법"])
        elif "고지혈" in name:
            tags.extend(["#콜레스테롤", "#운동습관"])
        elif "관절" in name:
            tags.extend(["#관절건강", "#스트레칭"])
        else:
            tags.append(f"#{name}")

    # 기본 태그
    tags.extend(["#마음의 안정", "#규칙적인 생활"])

    return {"tags": list(set(tags))[:6]}  # 최대 6개
