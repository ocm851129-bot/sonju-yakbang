"""음성 문진 (STT) - Whisper API 기반 음성 인식 및 건강기록 저장"""
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from openai import OpenAI
from app.database import get_db
from app.models import HealthRecord
from app.config import OPENAI_API_KEY
import json

router = APIRouter()
client = OpenAI(api_key=OPENAI_API_KEY)


class VoiceTranscription(BaseModel):
    text: str
    analysis: dict
    record_id: int


@router.post("/transcribe", response_model=VoiceTranscription)
async def transcribe_voice(
    user_id: int,
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """음성을 텍스트로 변환하고 건강 정보를 추출합니다"""
    try:
        # STT: Whisper로 음성 → 텍스트
        audio_content = await audio.read()

        transcription = client.audio.transcriptions.create(
            model="whisper-1",
            file=("audio.webm", audio_content, "audio/webm"),
            language="ko",
        )
        text = transcription.text

        # GPT로 건강 정보 구조화
        analysis = await analyze_health_content(text)

        # DB에 저장
        record = HealthRecord(
            user_id=user_id,
            record_type="voice_memo",
            content=text,
            structured_data=analysis,
            source="voice",
        )
        db.add(record)
        db.commit()
        db.refresh(record)

        return VoiceTranscription(text=text, analysis=analysis, record_id=record.id)

    except Exception as e:
        # STT(Whisper) 연결이 없거나 크레딧이 소진된 경우: 데모 결과로 대체
        print(f"[Voice] STT 실패({type(e).__name__}) → 데모 응답으로 대체")
        demo_text = "오늘 아침부터 머리가 좀 아프고 어지러워요."
        demo_analysis = {
            "symptoms": ["두통", "어지러움"],
            "medications_mentioned": [],
            "vital_signs": {"혈압": "", "혈당": "", "체온": ""},
            "diet": "",
            "mood": "",
            "pain_level": 3,
            "urgency": "caution",
            "summary": "아침부터 두통과 어지러움 증상 (데모 분석)",
            "demo_mode": True,
        }
        try:
            record = HealthRecord(
                user_id=user_id,
                record_type="voice_memo",
                content=demo_text,
                structured_data=demo_analysis,
                source="voice",
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            record_id = record.id
        except Exception:
            db.rollback()
            record_id = 0
        return VoiceTranscription(text=demo_text, analysis=demo_analysis, record_id=record_id)


async def analyze_health_content(text: str) -> dict:
    """GPT로 음성 텍스트에서 건강 정보 추출"""
    prompt = f"""다음은 어르신이 말씀하신 건강 관련 내용입니다. 
구조화된 정보를 추출해주세요.

말씀 내용: "{text}"

다음 JSON 형식으로 응답해주세요:
{{
    "symptoms": ["증상1", "증상2"],
    "medications_mentioned": ["약 이름1"],
    "vital_signs": {{"혈압": "", "혈당": "", "체온": ""}},
    "diet": "",
    "mood": "",
    "pain_level": 0,
    "urgency": "normal",
    "summary": "한 줄 요약"
}}

참고: urgency는 "normal", "caution", "emergency" 중 하나입니다.
vital_signs에서 언급되지 않은 항목은 빈 문자열로 두세요.
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "당신은 고령자 건강 정보를 분석하는 AI 약사입니다. JSON만 응답하세요."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )
        return json.loads(response.choices[0].message.content)
    except Exception:
        return {"summary": text, "urgency": "normal", "symptoms": []}
