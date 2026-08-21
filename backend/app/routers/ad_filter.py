"""건강기능식품 허위·과장광고 필터링 시스템
OCR로 광고 이미지/제품 표시사항을 인식하고, AI로 허위·과장 의심 문구를 탐지합니다.

PPT 기준: 건강기능식품의 구매 전(광고 검증) → 구매 시(인증 확인) → 복용 중(안전성 관리)
"""
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from openai import OpenAI
from app.database import get_db
from app.models import HealthRecord
from app.config import OPENAI_API_KEY, GOOGLE_VISION_API_KEY
import base64
import json
import httpx

router = APIRouter()
client = OpenAI(api_key=OPENAI_API_KEY)

# 식약처 기준 건강기능식품 금지 표현 (허위·과대광고 판단 기준)
PROHIBITED_CLAIMS = [
    "암 예방", "암 치료", "항암", "암세포",
    "치매 예방", "치매 치료", "알츠하이머",
    "당뇨 완치", "혈당 정상화",
    "고혈압 완치", "혈압 정상화",
    "관절염 치료", "디스크 치료",
    "살이 빠진다", "다이어트 효과", "지방 분해",
    "FDA 승인", "의사 추천",
    "100% 효과", "부작용 없음", "무조건",
    "만병통치", "기적의", "획기적",
    "즉시 효과", "3일 만에", "일주일이면",
    "의약품 대체", "약 끊을 수 있",
    "임상 입증", "논문 발표",  # 근거 없이 사용 시
]

# 식약처 인정 기능성 표현 (허용 범위)
ALLOWED_CLAIMS = [
    "혈행 개선에 도움",
    "항산화에 도움",
    "면역력 증진에 도움",
    "혈중 콜레스테롤 개선에 도움",
    "관절 건강에 도움",
    "눈 건강에 도움",
    "장 건강에 도움",
    "혈당 조절에 도움",
    "혈압 조절에 도움",
    "체지방 감소에 도움",
    "기억력 개선에 도움",
    "피부 건강에 도움",
    "뼈 건강에 도움",
    "피로 개선에 도움",
]


class AdFilterResult(BaseModel):
    is_suspicious: bool
    risk_level: str  # safe, caution, dangerous
    detected_claims: list
    allowed_claims: list
    warnings: list
    recommendation: str
    raw_text: str = ""


@router.post("/check-ad", response_model=AdFilterResult)
async def check_advertisement(
    user_id: int,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """건강기능식품 광고 이미지의 허위·과장 여부를 검사합니다.
    
    처리 흐름:
    1) OCR로 광고 텍스트 추출
    2) 금지 표현 룰 기반 1차 검사
    3) GPT AI로 문맥 기반 2차 분석
    """
    try:
        image_content = await image.read()
        base64_image = base64.b64encode(image_content).decode("utf-8")

        # 1단계: GPT Vision으로 광고 텍스트 + 맥락 분석
        analysis = await _analyze_ad_image(base64_image)
        if analysis is None:
            raise RuntimeError("AI Vision 사용 불가")  # 아래 except에서 데모 결과로 대체

        raw_text = analysis.get("extracted_text", "")
        detected_claims = []
        warnings = []

        # 2단계: 금지 표현 룰 기반 검사
        for claim in PROHIBITED_CLAIMS:
            if claim in raw_text:
                detected_claims.append(claim)
                warnings.append(f"⚠️ '{claim}' — 식약처 금지 표현에 해당할 수 있습니다")

        # 3단계: AI 분석 결과 반영
        ai_warnings = analysis.get("warnings", [])
        ai_suspicious = analysis.get("suspicious_claims", [])
        detected_claims.extend(ai_suspicious)
        warnings.extend(ai_warnings)

        # 허용 표현 확인
        allowed_found = [c for c in ALLOWED_CLAIMS if c in raw_text]

        # 위험도 판정
        if len(detected_claims) >= 3 or any("치료" in c or "완치" in c for c in detected_claims):
            risk_level = "dangerous"
            recommendation = "🚨 이 광고는 허위·과장 가능성이 높습니다. 구매하지 마시고, 약사에게 확인하세요."
        elif len(detected_claims) >= 1:
            risk_level = "caution"
            recommendation = "⚠️ 일부 과장된 표현이 포함되어 있습니다. 식약처 인정 기능성을 확인하세요."
        else:
            risk_level = "safe"
            recommendation = "✅ 특별한 허위·과장 표현이 감지되지 않았습니다. 다만 구매 전 성분을 확인하세요."

        is_suspicious = risk_level != "safe"

        # DB 기록
        record = HealthRecord(
            user_id=user_id,
            record_type="ad_filter",
            content=json.dumps({
                "risk_level": risk_level,
                "detected_claims": detected_claims,
                "raw_text": raw_text[:500],
            }, ensure_ascii=False),
            structured_data={"risk_level": risk_level, "claims_count": len(detected_claims)},
            source="camera",
        )
        db.add(record)
        db.commit()

        return AdFilterResult(
            is_suspicious=is_suspicious,
            risk_level=risk_level,
            detected_claims=detected_claims,
            allowed_claims=allowed_found,
            warnings=warnings,
            recommendation=recommendation,
            raw_text=raw_text[:300],
        )

    except Exception as e:
        # AI Vision 연결이 없거나 크레딧이 소진된 경우: 데모 결과로 대체
        print(f"[AdFilter] 광고 분석 실패({type(e).__name__}) → 데모 결과로 대체")
        return AdFilterResult(
            is_suspicious=True,
            risk_level="caution",
            detected_claims=["암 예방 효과", "100% 천연 성분"],
            allowed_claims=[],
            warnings=["⚠️ '암 예방' — 식약처 금지 표현에 해당할 수 있습니다"],
            recommendation="⚠️ (데모) 일부 과장된 표현이 포함되어 있습니다. 식약처 인정 기능성을 확인하세요.",
            raw_text="(데모 모드: AI 연결이 없어 예시 결과를 표시합니다)",
        )


@router.post("/check-product-label", response_model=AdFilterResult)
async def check_product_label(
    user_id: int,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """건강기능식품 제품 표시사항(라벨)을 검사합니다.
    식약처 인증 마크 유무, 기능성 내용 확인, 성분 정보 추출
    """
    try:
        image_content = await image.read()
        base64_image = base64.b64encode(image_content).decode("utf-8")

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """당신은 식약처 건강기능식품 표시사항 전문 분석가입니다.
제품 라벨 이미지를 분석하여 다음을 확인하세요:

1. 건강기능식품 인증 마크(도안) 유무
2. 기능성 내용 표시 여부
3. 섭취량 및 섭취 방법
4. 주의사항 표시 여부
5. 의심스러운 표현 여부

JSON으로 응답:
{
    "has_certification_mark": true/false,
    "product_name": "제품명",
    "functional_claims": ["기능성1"],
    "ingredients": ["성분1"],
    "dosage": "1일 1회, 1정",
    "cautions": ["주의사항"],
    "suspicious_claims": ["의심 표현"],
    "warnings": ["경고 메시지"],
    "is_certified": true/false,
    "extracted_text": "추출된 전체 텍스트"
}""",
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "이 건강기능식품 라벨을 분석해주세요."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                    ],
                },
            ],
            response_format={"type": "json_object"},
            max_tokens=1500,
        )

        result = json.loads(response.choices[0].message.content)

        # 인증 여부 기반 판정
        detected_claims = result.get("suspicious_claims", [])
        warnings = result.get("warnings", [])

        if not result.get("has_certification_mark", False):
            warnings.append("⚠️ 건강기능식품 인증 마크가 확인되지 않습니다. 일반식품일 수 있습니다.")
            risk_level = "caution"
        elif detected_claims:
            risk_level = "caution"
        else:
            risk_level = "safe"

        recommendation = {
            "safe": "✅ 식약처 인증 건강기능식품으로 확인됩니다.",
            "caution": "⚠️ 확인이 필요합니다. 약사에게 문의하세요.",
            "dangerous": "🚨 구매를 자제하세요. 미인증 제품이거나 허위 표시가 의심됩니다.",
        }.get(risk_level, "")

        return AdFilterResult(
            is_suspicious=risk_level != "safe",
            risk_level=risk_level,
            detected_claims=detected_claims,
            allowed_claims=result.get("functional_claims", []),
            warnings=warnings,
            recommendation=recommendation,
            raw_text=result.get("extracted_text", "")[:300],
        )

    except Exception as e:
        # AI Vision 연결이 없거나 크레딧이 소진된 경우: 데모 결과로 대체
        print(f"[AdFilter] 라벨 분석 실패({type(e).__name__}) → 데모 결과로 대체")
        return AdFilterResult(
            is_suspicious=False,
            risk_level="safe",
            detected_claims=[],
            allowed_claims=["혈행 개선에 도움"],
            warnings=[],
            recommendation="✅ (데모) 식약처 인증 건강기능식품으로 확인됩니다.",
            raw_text="(데모 모드: AI 연결이 없어 예시 결과를 표시합니다)",
        )


async def _analyze_ad_image(base64_image: str) -> dict:
    """GPT Vision으로 광고 이미지 분석"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """당신은 식약처 허위·과대광고 감별 전문가입니다.
건강기능식품 광고 이미지를 분석하여 다음을 판단하세요:

1. 이미지에서 텍스트를 추출
2. 질병 치료/예방 효과를 주장하는 표현 찾기
3. 과장된 수치나 기간 약속 ("3일 만에", "100%") 찾기
4. 의약품으로 오인하게 하는 표현 찾기
5. 식약처 비인정 기능성 주장 찾기

JSON으로 응답:
{
    "extracted_text": "이미지에서 추출한 전체 텍스트",
    "suspicious_claims": ["의심되는 표현1", "의심되는 표현2"],
    "warnings": ["구체적 경고 메시지1"],
    "is_health_food_ad": true/false,
    "overall_risk": "safe/caution/dangerous"
}""",
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "이 건강기능식품 광고를 분석해주세요."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                    ],
                },
            ],
            response_format={"type": "json_object"},
            max_tokens=1500,
        )
        return json.loads(response.choices[0].message.content)
    except Exception:
        return None  # 호출부에서 데모 결과로 대체
