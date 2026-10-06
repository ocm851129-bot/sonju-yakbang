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
from app.drug_permission import get_drug_full_info
from app.health_food import get_health_food_info
import base64
import json
import httpx

router = APIRouter()
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


class OCRResult(BaseModel):
    medications: list
    hospital: str = ""
    diagnosis: str = ""
    date: str = ""
    raw_text: str = ""
    confidence: float = 0.0
    ocr_engine: str = ""
    drug_info_source: str = ""  # 허가정보 보강 출처


# 허가정보로 보강할 최대 약품 수 (API 호출 과다 방지)
MAX_ENRICH = 8


def _is_health_food(item: dict) -> bool:
    """OCR로 분류된 품목이 건강기능식품(기능성 제품)인지 판별한다."""
    ptype = (item.get("product_type") or "").lower()
    cat = (item.get("category") or "").lower()
    if ptype in ("health_functional_food", "supplement", "food"):
        return True
    if cat in ("supplement", "health_functional_food"):
        return True
    return False


async def _enrich_drug(med: dict, sources: set) -> None:
    """의약품을 식약처 허가정보/e약은요로 보강한다."""
    info = await get_drug_full_info(med.get("name", ""), med.get("ingredient", ""))
    if not info.get("matched"):
        return
    if not med.get("ingredient") and info.get("ingredient"):
        med["ingredient"] = info["ingredient"]
    if info.get("category"):
        med["category"] = info["category"]
    med["product_type"] = med.get("product_type") or (
        "otc" if info.get("category") == "otc" else "prescription")
    med["permit"] = {
        "kind": "drug",
        "company": info.get("company", ""),
        "etc_otc": info.get("etc_otc", ""),
        "class_name": info.get("class_name", ""),
        "appearance": info.get("appearance", ""),
        "storage": info.get("storage", ""),
        "effect": info.get("effect", ""),
        "usage": info.get("usage", ""),
        "caution": info.get("caution", ""),
        "easy_effect": info.get("easy_effect", ""),
        "easy_caution": info.get("easy_caution", ""),
        "easy_side_effect": info.get("easy_side_effect", ""),
        "image_url": info.get("image_url", ""),
        "is_demo": info.get("is_demo", False),
    }
    for s in info.get("sources", []):
        sources.add(s)


async def _enrich_health_food(med: dict, sources: set) -> None:
    """건강기능식품을 식약처 품목정보/데모 DB로 보강한다.

    라벨(GPT Vision)에서 이미 읽은 기능성/섭취방법이 있으면 유지하고,
    비어있는 값만 품목정보/데모로 채운다.
    """
    med["category"] = "supplement"
    med["product_type"] = "health_functional_food"
    info = await get_health_food_info(med.get("name", ""))
    # 라벨에서 읽은 값 우선, 없으면 조회값으로 보강
    for k in ("functional_content", "intake_method", "caution", "raw_material"):
        if not med.get(k) and info.get(k):
            med[k] = info[k]
    med["permit"] = {
        "kind": "health_food",
        "company": info.get("company", ""),
        "etc_otc": "건강기능식품",
        "class_name": "건강기능식품",
        "functional_content": med.get("functional_content", "") or info.get("functional_content", ""),
        "intake_method": med.get("intake_method", "") or info.get("intake_method", ""),
        "raw_material": med.get("raw_material", "") or info.get("raw_material", ""),
        "effect": med.get("functional_content", "") or info.get("functional_content", ""),
        "usage": med.get("intake_method", "") or info.get("intake_method", ""),
        "caution": med.get("caution", "") or info.get("caution", ""),
        "easy_effect": med.get("functional_content", "") or info.get("functional_content", ""),
        "easy_caution": med.get("caution", "") or info.get("caution", ""),
        "image_url": info.get("image_url", ""),
        "is_demo": info.get("is_demo", False),
    }
    for s in info.get("sources", []):
        sources.add(s)
    # 라벨만으로도 정보가 있으면 출처 표기
    if not info.get("sources") and (med.get("functional_content") or med.get("intake_method")):
        sources.add("제품 라벨(촬영 인식)")


async def enrich_items(items: list) -> str:
    """OCR로 추출한 각 품목을 종류(의약품/건강기능식품)에 맞게 정보 보강한다.

    반환값: 실제로 사용된 데이터 출처 요약 문자열.
    """
    sources: set = set()
    for item in items[:MAX_ENRICH]:
        if not item.get("name"):
            continue
        try:
            if _is_health_food(item):
                await _enrich_health_food(item, sources)
            else:
                await _enrich_drug(item, sources)
        except Exception:
            continue
    return " · ".join(sorted(sources))


# 하위호환: 기존 처방전 엔드포인트가 호출하던 이름 유지
async def enrich_medications_with_permit(medications: list) -> str:
    return await enrich_items(medications)


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
                "content": f"""당신은 한국의 처방전·의약품·건강기능식품을 정확하게 분석하는 AI 약사입니다.
이미지는 (1) 병원 처방전, (2) 약 포장/약봉투, 또는 (3) 건강기능식품·영양제 제품/라벨일 수 있습니다.
이미지와 OCR 텍스트를 참고하여 각 품목을 분류하고 구조화된 정보를 추출하세요.
정보가 불명확하면 빈 문자열로 남기고, 지어내지 마세요.

각 품목의 product_type 을 다음 중 하나로 정확히 분류하세요:
  - "prescription"              : 처방전으로 받는 전문의약품
  - "otc"                       : 약국에서 사는 일반의약품
  - "health_functional_food"    : 건강기능식품/영양제(비타민, 오메가3, 유산균, 홍삼 등)

건강기능식품(health_functional_food)이면 라벨에 적힌 '기능성 내용'과 '섭취방법'을
functional_content, intake_method 에 그대로 옮겨 적으세요(과장 표현은 쓰지 마세요).
의약품이면 ingredient/dosage/frequency 를 채우세요.

응답 형식(JSON):
{{
    "hospital": "병원명(처방전일 때)",
    "diagnosis": "진단명(있으면)",
    "date": "날짜 (YYYY-MM-DD, 있으면)",
    "medications": [
        {{
            "name": "품목명",
            "product_type": "prescription | otc | health_functional_food",
            "category": "prescription | otc | supplement",
            "ingredient": "의약품 주요성분(의약품일 때)",
            "dosage": "1회 투여량(의약품일 때)",
            "frequency": "복용 횟수 (예: 1일 3회 식후 30분)",
            "duration": "투여 기간 (예: 7일)",
            "functional_content": "식약처 기능성 내용(건강기능식품일 때)",
            "intake_method": "섭취방법(건강기능식품일 때)",
            "caution": "섭취/복용 시 주의사항"
        }}
    ],
    "confidence": 0.9
}}{context_msg}""",
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "이 이미지(처방전·약 포장·건강기능식품 중 하나)를 분석해 각 품목을 분류하고 정보를 추출해주세요."},
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

        # 3차 보강: 식약처 의약품 제품 허가정보 + e약은요로 각 약품 정보 채우기
        drug_info_source = await enrich_medications_with_permit(result.get("medications", []))

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
            drug_info_source=drug_info_source,
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
        # 데모 약품도 허가정보(또는 로컬 데모 DB)로 보강
        try:
            demo_source = await enrich_medications_with_permit(demo_meds)
        except Exception:
            demo_source = ""
        return OCRResult(
            medications=demo_meds,
            hospital="서울내과의원",
            diagnosis="본태성 고혈압, 제2형 당뇨병",
            date="2026-06-10",
            raw_text="(데모 모드: AI OCR 연결이 없어 예시 데이터를 표시합니다)",
            confidence=0.92,
            ocr_engine="demo-mode",
            drug_info_source=demo_source,
        )


@router.post("/product", response_model=OCRResult)
async def scan_product(
    user_id: int,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """제품 사진을 OCR로 인식합니다. 처방전·의약품은 물론 건강기능식품(영양제)까지
    자동으로 분류하여, 의약품은 식약처 허가정보로, 건강기능식품은 기능성·섭취방법으로
    정보를 보강합니다.

    처리 흐름:
    1차) Google Vision / CLOVA OCR 로 텍스트 추출
    2차) GPT-4o Vision 으로 품목 분류 + Key-Value 구조화
    3차) 종류별 정보 보강 (의약품→허가정보/e약은요, 건강기능식품→품목정보/라벨)
    """
    try:
        image_content = await image.read()
        ocr_engine = "gpt-vision"

        raw_text = await google_vision_ocr(image_content)
        if raw_text:
            ocr_engine = "google-vision + gpt-structure"
        else:
            raw_text = await clova_ocr(image_content)
            ocr_engine = "clova-ocr + gpt-structure" if raw_text else "gpt-vision-only"

        result = await gpt_vision_structure(image_content, raw_text)
        items = result.get("medications", [])

        # 종류별(의약품/건강기능식품) 정보 보강
        info_source = await enrich_items(items)

        record = HealthRecord(
            user_id=user_id,
            record_type="product_ocr",
            content=json.dumps(result, ensure_ascii=False),
            structured_data=result,
            source="camera",
        )
        db.add(record)

        for it in items:
            db.add(Medication(
                user_id=user_id,
                name=it.get("name", ""),
                ingredient=it.get("ingredient", "") or it.get("raw_material", ""),
                dosage=it.get("dosage", ""),
                frequency=it.get("frequency", "") or it.get("intake_method", ""),
                category=it.get("category", "supplement" if _is_health_food(it) else "prescription"),
                prescribing_hospital=result.get("hospital", ""),
                start_date=result.get("date", ""),
            ))
        db.commit()

        return OCRResult(
            medications=items,
            hospital=result.get("hospital", ""),
            diagnosis=result.get("diagnosis", ""),
            date=result.get("date", ""),
            raw_text=raw_text[:500] if raw_text else "",
            confidence=result.get("confidence", 0.0),
            ocr_engine=ocr_engine,
            drug_info_source=info_source,
        )

    except Exception as e:
        # AI OCR 연결이 없거나 크레딧 소진: 건강기능식품 예시로 데모 응답
        print(f"[OCR] 제품 인식 실패({type(e).__name__}) → 데모 결과로 대체")
        demo_items = [
            {"name": "오메가3", "product_type": "health_functional_food", "category": "supplement",
             "functional_content": "혈중 중성지방 개선·혈행 개선에 도움", "intake_method": "1일 1회 1캡슐"},
            {"name": "비타민D", "product_type": "health_functional_food", "category": "supplement",
             "functional_content": "칼슘 흡수·뼈 건강에 도움", "intake_method": "1일 1회 1정"},
            {"name": "프로바이오틱스", "product_type": "health_functional_food", "category": "supplement",
             "functional_content": "유산균 증식·배변활동 원활에 도움", "intake_method": "1일 1회 1포"},
        ]
        try:
            demo_source = await enrich_items(demo_items)
        except Exception:
            demo_source = ""
        return OCRResult(
            medications=demo_items,
            hospital="",
            diagnosis="",
            date="",
            raw_text="(데모 모드: AI OCR 연결이 없어 예시 데이터를 표시합니다)",
            confidence=0.9,
            ocr_engine="demo-mode",
            drug_info_source=demo_source,
        )
