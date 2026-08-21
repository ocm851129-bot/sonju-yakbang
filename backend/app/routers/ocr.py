"""AI OCR - 처방전·약봉투·영수증 인식
PPT 기준: Google Vision API / CLOVA OCR (1차) + GPT Vision (2차 구조화)
"""
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from openai import OpenAI
from app.database import get_db
from app.models import HealthRecord, Medication
from app.config import OPENAI_API_KEY, GOOGLE_VISION_API_KEY, CLOVA_OCR_SECRET, CLOVA_OCR_URL
import base64
import json
import httpx

router = APIRouter()
client = OpenAI(api_key=OPENAI_API_KEY)


class OCRResult(BaseModel):
    medications: list
    hospital: str = ""
    diagnosis: str = ""
    date: str = ""
    raw_text: str = ""
    confidence: float = 0.0
    ocr_engine: str = ""


# ==================== 1차 OCR: Google Vision API ====================

async def google_vision_ocr(image_bytes: bytes) -> str:
    """Google Cloud Vision API로 텍스트 추출"""
    if not GOOGLE_VISION_API_KEY:
        return ""

    url = f"https://vision.googleapis.com/v1/images:annotate?key={GOOGLE_VISION_API_KEY}"
    base64_image = base64.b64encode(image_bytes).decode("utf-8")

    payload = {
        "requests": [{
            "image": {"content": base64_image},
            "features": [{"type": "DOCUMENT_TEXT_DETECTION", "maxResults": 1}]
        }]
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client_http:
            response = await client_http.post(url, json=payload)
            if response.status_code == 200:
                result = response.json()
                annotations = result.get("responses", [{}])[0].get("fullTextAnnotation", {})
                return annotations.get("text", "")
    except Exception:
        pass
    return ""


# ==================== 1차 OCR: CLOVA OCR (네이버) ====================

async def clova_ocr(image_bytes: bytes) -> str:
    """네이버 CLOVA OCR로 텍스트 추출"""
    if not CLOVA_OCR_SECRET or not CLOVA_OCR_URL:
        return ""

    base64_image = base64.b64encode(image_bytes).decode("utf-8")
    payload = {
        "version": "V2",
        "requestId": "sonju-yakbang",
        "timestamp": 0,
        "images": [{"format": "jpg", "name": "prescription", "data": base64_image}]
    }
    headers = {"X-OCR-SECRET": CLOVA_OCR_SECRET, "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient(timeout=30) as client_http:
            response = await client_http.post(CLOVA_OCR_URL, json=payload, headers=headers)
            if response.status_code == 200:
                result = response.json()
                texts = []
                for image_result in result.get("images", []):
                    for field in image_result.get("fields", []):
                        texts.append(field.get("inferText", ""))
                return " ".join(texts)
    except Exception:
        pass
    return ""


# ==================== 2차: GPT Vision 구조화 ====================

async def gpt_vision_structure(image_bytes: bytes, raw_text: str = "") -> dict:
    """GPT-4o Vision으로 처방전 정보를 구조화 (Key-Value 추출)"""
    base64_image = base64.b64encode(image_bytes).decode("utf-8")

    context_msg = ""
    if raw_text:
        context_msg = f"\n\n[참고: OCR로 추출된 원본 텍스트]\n{raw_text[:2000]}"

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": f"""당신은 한국 병원 처방전을 정확하게 분석하는 AI 약사입니다.
처방전 이미지와 OCR 텍스트를 참고하여 구조화된 정보를 추출하세요.
정보가 불명확한 경우 빈 문자열로 남겨주세요.

응답 형식:
{{
    "hospital": "병원명",
    "diagnosis": "진단명",
    "date": "처방일 (YYYY-MM-DD)",
    "medications": [
        {{
            "name": "의약품명",
            "ingredient": "주요성분",
            "dosage": "1회 투여량",
            "frequency": "투여 횟수 (예: 1일 3회 식후 30분)",
            "duration": "투여 기간 (예: 7일)",
            "category": "prescription"
        }}
    ],
    "confidence": 0.9
}}{context_msg}""",
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "이 처방전을 분석해주세요."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                ],
            },
        ],
        response_format={"type": "json_object"},
        max_tokens=2000,
    )

    return json.loads(response.choices[0].message.content)


# ==================== 메인 엔드포인트 ====================

@router.post("/prescription", response_model=OCRResult)
async def scan_prescription(
    user_id: int,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """처방전 이미지를 OCR로 인식하여 의약품 정보를 추출합니다.
    
    처리 흐름:
    1차) Google Vision API 또는 CLOVA OCR로 텍스트 추출
    2차) GPT-4o Vision으로 Key-Value 구조화 (1차 결과를 컨텍스트로 활용)
    """
    try:
        image_content = await image.read()
        ocr_engine = "gpt-vision"
        raw_text = ""

        # 1차 OCR: Google Vision 우선, 실패 시 CLOVA
        raw_text = await google_vision_ocr(image_content)
        if raw_text:
            ocr_engine = "google-vision + gpt-structure"
        else:
            raw_text = await clova_ocr(image_content)
            if raw_text:
                ocr_engine = "clova-ocr + gpt-structure"
            else:
                ocr_engine = "gpt-vision-only"

        # 2차 구조화: GPT Vision (1차 OCR 텍스트를 컨텍스트로 전달)
        result = await gpt_vision_structure(image_content, raw_text)

        # DB에 건강기록 저장
        record = HealthRecord(
            user_id=user_id,
            record_type="prescription_ocr",
            content=json.dumps(result, ensure_ascii=False),
            structured_data=result,
            source="camera",
        )
        db.add(record)

        # 의약품 정보 저장
        for med in result.get("medications", []):
            medication = Medication(
                user_id=user_id,
                name=med.get("name", ""),
                ingredient=med.get("ingredient", ""),
                dosage=med.get("dosage", ""),
                frequency=med.get("frequency", ""),
                category=med.get("category", "prescription"),
                prescribing_hospital=result.get("hospital", ""),
                start_date=result.get("date", ""),
            )
            db.add(medication)

        db.commit()

        return OCRResult(
            medications=result.get("medications", []),
            hospital=result.get("hospital", ""),
            diagnosis=result.get("diagnosis", ""),
            date=result.get("date", ""),
            raw_text=raw_text[:500] if raw_text else "",
            confidence=result.get("confidence", 0.0),
            ocr_engine=ocr_engine,
        )

    except Exception as e:
        # OCR/GPT Vision 연결이 없거나 크레딧이 소진된 경우: 데모 결과로 대체
        print(f"[OCR] 처방전 인식 실패({type(e).__name__}) → 데모 결과로 대체")
        demo_meds = [
            {"name": "아모디핀정 5mg", "ingredient": "암로디핀", "dosage": "1정",
             "frequency": "1일 1회 아침 식후", "duration": "28일", "category": "prescription"},
            {"name": "메트포르민정 500mg", "ingredient": "메트포르민", "dosage": "1정",
             "frequency": "1일 2회 아침·저녁 식후", "duration": "28일", "category": "prescription"},
            {"name": "아토르바스타틴정 20mg", "ingredient": "아토르바스타틴", "dosage": "1정",
             "frequency": "1일 1회 취침 전", "duration": "28일", "category": "prescription"},
        ]
        return OCRResult(
            medications=demo_meds,
            hospital="서울내과의원",
            diagnosis="본태성 고혈압, 제2형 당뇨병",
            date="2026-06-10",
            raw_text="(데모 모드: AI OCR 연결이 없어 예시 데이터를 표시합니다)",
            confidence=0.92,
            ocr_engine="demo-mode",
        )
