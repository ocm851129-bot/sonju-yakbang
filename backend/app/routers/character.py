"""AI 캐릭터 정서지원 - 개인 맞춤형 AI 캐릭터 생성 및 관리"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from openai import OpenAI
from app.database import get_db
from app.models import User
from app.config import OPENAI_API_KEY
import json

router = APIRouter()
client = OpenAI(api_key=OPENAI_API_KEY)

# 캐릭터 프리셋 (성별·성격 기반)
CHARACTER_PRESETS = {
    "grandson_warm": {
        "name": "따뜻한 손주",
        "emoji": "👦",
        "personality": "따뜻하고 다정한 손주. 항상 걱정하며 안부를 묻는 성격.",
        "greeting_style": "할머니/할아버지~ 오늘 기분 어떠세요?",
        "speech_style": "존댓말과 반말을 섞어 친근하게",
    },
    "granddaughter_cheerful": {
        "name": "밝은 손녀",
        "emoji": "👧",
        "personality": "밝고 긍정적인 손녀. 칭찬을 많이 하고 응원하는 성격.",
        "greeting_style": "할머니/할아버지! 오늘도 멋지세요~",
        "speech_style": "밝고 에너지 넘치게, 이모지 활용",
    },
    "pharmacist_kind": {
        "name": "친절한 약사",
        "emoji": "👨‍⚕️",
        "personality": "전문적이면서도 친절한 동네 약사. 쉬운 말로 설명하는 성격.",
        "greeting_style": "안녕하세요, 오늘 건강 상태는 어떠신가요?",
        "speech_style": "존댓말, 전문 용어를 쉽게 풀어서",
    },
    "friend_warm": {
        "name": "다정한 친구",
        "emoji": "🧓",
        "personality": "같은 또래의 다정한 친구. 공감하고 위로하는 성격.",
        "greeting_style": "친구야~ 오늘 하루 어땠어?",
        "speech_style": "반말, 편안하고 친근하게",
    },
    "doctor_gentle": {
        "name": "부드러운 의사",
        "emoji": "👩‍⚕️",
        "personality": "부드럽고 차분한 여성 의사. 걱정을 덜어주는 성격.",
        "greeting_style": "안녕하세요, 오늘 불편하신 곳은 없으신가요?",
        "speech_style": "차분한 존댓말, 안심시키는 어조",
    },
}


class CharacterSelect(BaseModel):
    user_id: int
    character_type: str  # CHARACTER_PRESETS의 key


class CharacterProfile(BaseModel):
    character_type: str
    name: str
    emoji: str
    personality: str
    greeting: str
    daily_message: str


class MoodCheckResult(BaseModel):
    mood: str
    score: int
    response: str
    character_emoji: str


@router.get("/presets")
def get_character_presets():
    """사용 가능한 캐릭터 프리셋 목록"""
    return {
        "presets": [
            {
                "type": key,
                "name": val["name"],
                "emoji": val["emoji"],
                "description": val["personality"],
            }
            for key, val in CHARACTER_PRESETS.items()
        ]
    }


@router.post("/select")
def select_character(data: CharacterSelect, db: Session = Depends(get_db)):
    """사용자의 AI 캐릭터 선택/변경"""
    if data.character_type not in CHARACTER_PRESETS:
        raise HTTPException(status_code=400, detail="존재하지 않는 캐릭터입니다")

    # TODO: User 모델에 character_type 필드 추가 시 DB 저장
    preset = CHARACTER_PRESETS[data.character_type]
    return {
        "message": f"{preset['name']} 캐릭터가 설정되었습니다",
        "character": preset,
    }


@router.get("/profile/{user_id}", response_model=CharacterProfile)
def get_character_profile(user_id: int, db: Session = Depends(get_db)):
    """현재 사용자의 캐릭터 프로필 및 오늘의 메시지"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

    # 기본 캐릭터 (추후 DB에서 사용자 선택 캐릭터 조회)
    char_type = "grandson_warm"
    preset = CHARACTER_PRESETS[char_type]

    # 시간대별 + 사용자 정보 기반 개인화 메시지 생성
    daily_message = _generate_daily_message(user, preset)

    return CharacterProfile(
        character_type=char_type,
        name=preset["name"],
        emoji=preset["emoji"],
        personality=preset["personality"],
        greeting=preset["greeting_style"],
        daily_message=daily_message,
    )


@router.post("/mood-check", response_model=MoodCheckResult)
def mood_check(user_id: int, message: str = "", db: Session = Depends(get_db)):
    """감정 상태 확인 및 정서 지원 응답 생성"""
    user = db.query(User).filter(User.id == user_id).first()
    char_type = "grandson_warm"
    preset = CHARACTER_PRESETS[char_type]

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": f"""당신은 '{preset["name"]}' 캐릭터입니다.
성격: {preset["personality"]}
말투: {preset["speech_style"]}

어르신의 말씀에서 감정 상태를 파악하고, 캐릭터에 맞게 따뜻하게 응대하세요.
JSON으로 응답:
{{"mood": "기쁨/평온/외로움/슬픔/불안/화남", "score": 1~10, "response": "캐릭터 답변"}}

score: 10=매우 좋음, 5=보통, 1=매우 나쁨""",
                },
                {
                    "role": "user",
                    "content": message or "오늘 기분이 어때요?",
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.8,
        )
        result = json.loads(response.choices[0].message.content)
        return MoodCheckResult(
            mood=result.get("mood", "평온"),
            score=result.get("score", 5),
            response=result.get("response", "오늘도 좋은 하루 보내세요!"),
            character_emoji=preset["emoji"],
        )
    except Exception:
        return MoodCheckResult(
            mood="평온",
            score=5,
            response="오늘도 건강하고 좋은 하루 보내세요!",
            character_emoji=preset["emoji"],
        )


def _generate_daily_message(user, preset: dict) -> str:
    """시간대·사용자 기반 개인화 일일 메시지"""
    from datetime import datetime
    hour = datetime.now().hour

    if hour < 9:
        time_context = "아침"
        base_msg = "좋은 아침이에요! 오늘도 건강한 하루 시작하세요."
    elif hour < 12:
        time_context = "오전"
        base_msg = "오전 약은 드셨나요? 물 한 잔과 함께 드세요."
    elif hour < 14:
        time_context = "점심"
        base_msg = "점심은 맛있게 드셨어요? 식후 약 잊지 마세요."
    elif hour < 18:
        time_context = "오후"
        base_msg = "오후에도 건강하게 보내고 계시죠? 산책도 좋아요."
    else:
        time_context = "저녁"
        base_msg = "오늘 하루도 수고하셨어요. 푹 쉬세요."

    return f"{preset['emoji']} {base_msg}"
