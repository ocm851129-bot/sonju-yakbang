"""식품의약품안전처 의약품 정보 연동 모듈

두 개의 공공데이터포털(data.go.kr) 공개 API를 조합하여 약품 정보를 제공합니다.

  1) 의약품 제품 허가정보 (DrugPrdtPrmsnInfoService06)
     - 품목명/업체명/전문·일반 구분/성분/효능효과/용법용량/주의사항/저장방법/유효기간
     - 허가받은 '공식' 정보 (요청하신 API)
  2) 의약품개요정보 e약은요 (DrbEasyDrugInfoService)
     - 어르신도 이해하기 쉬운 '쉬운말' 효능/사용법/주의사항/보관법 + 낱알 이미지

처리 흐름:
  1차) 제품 허가정보 API 조회 (성분·효능·용법·주의·저장)
  2차) e약은요 API 조회 (쉬운말 설명 + 이미지) 로 보강
  3차) 둘 다 실패 시 로컬 데모 데이터(고령자 다빈도 약) 폴백

DUR_API_KEY(공공데이터포털 인증키)를 그대로 사용합니다. 키가 없으면 데모 모드로 동작합니다.
"""
import re
import html
import httpx
from typing import Optional
import xml.etree.ElementTree as ET
from app.config import (
    DRUG_PERMIT_API_KEY,
    DRUG_EASY_API_KEY,
    DRUG_PERMIT_API_BASE,
    DRUG_EASY_API_BASE,
)


# ==================== 공통 유틸 ====================

def _clean_item_name(name: str) -> str:
    """OCR로 인식된 품목명에서 검색 정확도를 높이기 위해 노이즈를 제거한다.
    예) '아모디핀정 5mg(암로디핀베실산염)' -> '아모디핀정'
    """
    if not name:
        return ""
    n = name.strip()
    # 괄호 안 성분 설명 제거
    n = re.sub(r"[\(\[（【].*?[\)\]）】]", "", n)
    # 용량 표기(5mg, 500밀리그램, 20 mg 등) 제거
    n = re.sub(r"\d+(\.\d+)?\s*(mg|밀리그램|밀리그람|g|mcg|㎎|㎍|IU|단위|정|캡슐|ml|㎖)", "", n, flags=re.IGNORECASE)
    n = re.sub(r"\s+", " ", n).strip()
    return n or name.strip()


def _parse_doc_data(doc_data: str) -> str:
    """허가정보 API의 EE/UD/NB_DOC_DATA(XML 문서형 데이터)를 평문 텍스트로 변환한다.

    구조 예:
      <DOC title="효능효과" type="EE"><SECTION><ARTICLE title="...">
        <PARAGRAPH>본태성 고혈압</PARAGRAPH></ARTICLE></SECTION></DOC>
    """
    if not doc_data:
        return ""
    text = doc_data.strip()
    # XML 형태면 태그를 파싱하여 문단 텍스트만 수집
    if text.startswith("<"):
        try:
            root = ET.fromstring(text)
            parts = []
            for elem in root.iter():
                # ARTICLE 제목(title 속성)도 소제목으로 포함
                title = (elem.attrib.get("title") or "").strip()
                if title and elem.tag.upper() == "ARTICLE":
                    parts.append(f"■ {title}")
                if elem.text and elem.text.strip():
                    parts.append(elem.text.strip())
            cleaned = "\n".join(p for p in parts if p)
            if cleaned:
                return html.unescape(cleaned)
        except ET.ParseError:
            pass
    # XML 파싱 실패 시 태그만 대충 제거
    stripped = re.sub(r"<[^>]+>", " ", text)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    return html.unescape(stripped)


def _truncate(text: str, limit: int = 600) -> str:
    if not text:
        return ""
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rstrip() + " …"


# ==================== 1차: 의약품 제품 허가정보 API ====================

async def search_drug_permission(item_name: str) -> Optional[dict]:
    """의약품 제품 허가정보 API로 품목 상세정보를 조회한다."""
    if not DRUG_PERMIT_API_KEY or not item_name:
        return None

    url = f"{DRUG_PERMIT_API_BASE}/getDrugPrdtPrmsnDtlInq05"
    params = {
        "serviceKey": DRUG_PERMIT_API_KEY,
        "item_name": item_name,
        "type": "json",
        "numOfRows": 3,
        "pageNo": 1,
    }
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                return None
            data = resp.json()
            items = (data.get("body", {}) or {}).get("items", [])
            if not items:
                return None
            # items 원소가 {"item": {...}} 로 감싸져 오는 경우 처리
            first = items[0]
            item = first.get("item", first) if isinstance(first, dict) else first
            return _normalize_permit_item(item)
    except Exception:
        return None


def _normalize_permit_item(item: dict) -> dict:
    """허가정보 API 원본 필드를 앱 표준 스키마로 정규화한다."""
    etc_otc = (item.get("ETC_OTC_CODE") or item.get("ETC_OTC_NAME") or "").strip()
    if "전문" in etc_otc:
        category = "prescription"
    elif "일반" in etc_otc:
        category = "otc"
    else:
        category = "prescription"

    return {
        "item_name": (item.get("ITEM_NAME") or "").strip(),
        "item_seq": (item.get("ITEM_SEQ") or "").strip(),
        "company": (item.get("ENTP_NAME") or "").strip(),
        "etc_otc": etc_otc,
        "category": category,
        "class_name": (item.get("CLASS_NO_NAME") or item.get("CLASS_NO") or "").strip(),
        "ingredient": _truncate(item.get("MATERIAL_NAME") or item.get("MAIN_ITEM_INGR") or "", 300),
        "appearance": (item.get("CHART") or "").strip(),
        "storage": (item.get("STORAGE_METHOD") or "").strip(),
        "valid_term": (item.get("VALID_TERM") or "").strip(),
        "bar_code": (item.get("BAR_CODE") or "").strip(),
        "permit_date": (item.get("ITEM_PERMIT_DATE") or "").strip(),
        "cancel_name": (item.get("CANCEL_NAME") or "").strip(),
        "effect": _truncate(_parse_doc_data(item.get("EE_DOC_DATA") or "")),
        "usage": _truncate(_parse_doc_data(item.get("UD_DOC_DATA") or "")),
        "caution": _truncate(_parse_doc_data(item.get("NB_DOC_DATA") or "")),
        "source": "식약처 의약품 제품 허가정보",
    }


# ==================== 2차: e약은요(개요정보) API ====================

async def search_easy_drug(item_name: str) -> Optional[dict]:
    """e약은요 API로 어르신 친화 쉬운말 설명 + 낱알 이미지를 조회한다."""
    if not DRUG_EASY_API_KEY or not item_name:
        return None

    url = f"{DRUG_EASY_API_BASE}/getDrbEasyDrugList"
    params = {
        "serviceKey": DRUG_EASY_API_KEY,
        "itemName": item_name,
        "type": "json",
        "numOfRows": 3,
        "pageNo": 1,
    }
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                return None
            data = resp.json()
            items = (data.get("body", {}) or {}).get("items", [])
            if not items:
                return None
            item = items[0]
            item = item.get("item", item) if isinstance(item, dict) else item
            return {
                "item_name": (item.get("itemName") or "").strip(),
                "company": (item.get("entpName") or "").strip(),
                "easy_effect": _truncate(item.get("efcyQesitm") or ""),
                "easy_usage": _truncate(item.get("useMethodQesitm") or ""),
                "easy_warn": _truncate(item.get("atpnWarnQesitm") or ""),
                "easy_caution": _truncate(item.get("atpnQesitm") or ""),
                "easy_interaction": _truncate(item.get("intrcQesitm") or ""),
                "easy_side_effect": _truncate(item.get("seQesitm") or ""),
                "easy_storage": _truncate(item.get("depositMethodQesitm") or "", 200),
                "image_url": (item.get("itemImage") or "").strip(),
                "source": "식약처 e약은요",
            }
    except Exception:
        return None


# ==================== 3차: 로컬 데모 데이터 (고령자 다빈도 약) ====================

DEMO_DRUG_DB = {
    "암로디핀": {
        "item_name": "아모디핀정 5mg", "company": "한미약품", "category": "prescription",
        "etc_otc": "전문의약품", "class_name": "혈압강하제", "ingredient": "암로디핀베실산염 6.93mg",
        "appearance": "흰색의 원형 정제", "storage": "실온(1~30℃) 보관", "valid_term": "제조일로부터 36개월",
        "effect": "고혈압, 협심증 치료에 사용합니다.",
        "usage": "성인 1일 1회 1정(5mg)을 복용합니다. 최대 1일 10mg까지 증량할 수 있습니다.",
        "caution": "갑자기 복용을 중단하지 마세요. 어지러움이 나타날 수 있으니 자리에서 천천히 일어나세요.",
        "easy_effect": "혈압을 낮추고 심장으로 가는 혈액을 늘려 가슴 통증(협심증)을 줄여줍니다.",
        "easy_caution": "얼굴이 붓거나 어지러우면 의사와 상담하세요. 자몽주스와 함께 드시지 마세요.",
    },
    "메트포르민": {
        "item_name": "메트포르민정 500mg", "company": "대웅제약", "category": "prescription",
        "etc_otc": "전문의약품", "class_name": "당뇨병용제", "ingredient": "메트포르민염산염 500mg",
        "appearance": "흰색의 필름코팅정", "storage": "기밀용기, 실온 보관", "valid_term": "제조일로부터 36개월",
        "effect": "제2형 당뇨병 환자의 혈당 조절에 사용합니다.",
        "usage": "1일 2~3회 식사 중 또는 식후에 복용합니다.",
        "caution": "음주 시 유산산증 위험이 있으니 삼가세요. 조영제 촬영 전후에는 복용을 중단하세요.",
        "easy_effect": "몸에서 당이 잘 쓰이도록 도와 혈당을 낮춰줍니다.",
        "easy_caution": "속이 메스껍거나 설사가 있을 수 있어요. 술은 피하세요.",
    },
    "아토르바스타틴": {
        "item_name": "아토르바스타틴칼슘정 20mg", "company": "화이자제약", "category": "prescription",
        "etc_otc": "전문의약품", "class_name": "동맥경화용제", "ingredient": "아토르바스타틴칼슘삼수화물",
        "appearance": "흰색의 타원형 필름코팅정", "storage": "실온 보관", "valid_term": "제조일로부터 36개월",
        "effect": "고콜레스테롤혈증, 이상지질혈증 치료에 사용합니다.",
        "usage": "1일 1회 저녁 또는 취침 전에 복용합니다.",
        "caution": "근육통이 심하거나 소변색이 진해지면 즉시 병원에 방문하세요. 자몽주스를 피하세요.",
        "easy_effect": "나쁜 콜레스테롤을 낮춰 혈관이 막히는 것을 예방합니다.",
        "easy_caution": "근육이 아프고 힘이 빠지면 바로 알려주세요.",
    },
    "심바스타틴": {
        "item_name": "심바스타틴정 20mg", "company": "종근당", "category": "prescription",
        "etc_otc": "전문의약품", "class_name": "동맥경화용제", "ingredient": "심바스타틴 20mg",
        "appearance": "연갈색의 원형 필름코팅정", "storage": "실온 보관", "valid_term": "제조일로부터 36개월",
        "effect": "고지혈증, 관상동맥질환 위험 감소에 사용합니다.",
        "usage": "1일 1회 저녁에 복용합니다.",
        "caution": "자몽주스와 병용하지 마세요. 근육통 발생 시 상담하세요.",
        "easy_effect": "콜레스테롤을 낮춰 심장병을 예방합니다.",
        "easy_caution": "저녁에 드시고, 근육통이 있으면 알려주세요.",
    },
    "아스피린": {
        "item_name": "아스피린프로텍트정 100mg", "company": "바이엘코리아", "category": "otc",
        "etc_otc": "일반의약품", "class_name": "해열·진통·소염제", "ingredient": "아스피린 100mg",
        "appearance": "흰색의 장용정", "storage": "실온 보관", "valid_term": "제조일로부터 36개월",
        "effect": "혈전 생성 억제로 심근경색·뇌졸중 예방에 사용합니다.",
        "usage": "1일 1회 100mg을 복용합니다.",
        "caution": "위장출혈 위험이 있으니 검은 변이 보이면 병원에 방문하세요. 다른 진통제와 병용에 주의하세요.",
        "easy_effect": "피를 묽게 하여 혈관이 막히는 것을 예방합니다.",
        "easy_caution": "속쓰림이나 검은 변이 있으면 알려주세요.",
    },
}


def _lookup_demo(item_name: str, ingredient: str = "") -> Optional[dict]:
    """로컬 데모 DB에서 성분/품목명 부분일치로 조회한다.

    매칭 기준(검색어 기준):
      1) 성분 키(예: '암로디핀')가 검색어에 포함, 또는
      2) 데모 품목명의 앞부분(용량 앞, 예: '아모디핀정')이 검색어에 포함
    """
    haystack = f"{item_name} {ingredient}"
    for key, info in DEMO_DRUG_DB.items():
        base = re.split(r"[\s\d]", info["item_name"], maxsplit=1)[0]  # '아모디핀정'
        if key in haystack or (base and base in haystack):
            result = dict(info)
            result["source"] = "로컬 데모 데이터(오프라인)"
            result["is_demo"] = True
            return result
    return None


# ==================== 오케스트레이션 ====================

async def get_drug_full_info(item_name: str, ingredient: str = "") -> dict:
    """약품명을 받아 허가정보 + e약은요 + 데모를 조합한 통합 정보를 반환한다.

    반환 스키마:
      matched(bool), item_name, company, category, etc_otc, class_name,
      ingredient, appearance, storage, valid_term, effect, usage, caution,
      easy_* (쉬운말 설명), image_url, sources(list), is_demo(bool)
    """
    query = _clean_item_name(item_name)

    permit = await search_drug_permission(query)
    easy = await search_easy_drug(query)

    if not permit and not easy:
        # 원본 이름 그대로 한 번 더 시도 (정제로 인해 놓친 경우)
        if query != item_name.strip():
            permit = await search_drug_permission(item_name.strip())
            easy = await search_easy_drug(item_name.strip())

    result = {
        "matched": False,
        "query": query,
        "item_name": item_name,
        "company": "",
        "category": "prescription",
        "etc_otc": "",
        "class_name": "",
        "ingredient": ingredient,
        "appearance": "",
        "storage": "",
        "valid_term": "",
        "effect": "",
        "usage": "",
        "caution": "",
        "easy_effect": "",
        "easy_usage": "",
        "easy_warn": "",
        "easy_caution": "",
        "easy_interaction": "",
        "easy_side_effect": "",
        "easy_storage": "",
        "image_url": "",
        "sources": [],
        "is_demo": False,
    }

    if permit:
        result["matched"] = True
        for k in ("item_name", "company", "category", "etc_otc", "class_name",
                  "appearance", "storage", "valid_term", "effect", "usage", "caution"):
            if permit.get(k):
                result[k] = permit[k]
        if permit.get("ingredient"):
            result["ingredient"] = permit["ingredient"]
        result["sources"].append(permit["source"])

    if easy:
        result["matched"] = True
        for k in ("easy_effect", "easy_usage", "easy_warn", "easy_caution",
                  "easy_interaction", "easy_side_effect", "easy_storage", "image_url"):
            if easy.get(k):
                result[k] = easy[k]
        if not result["company"] and easy.get("company"):
            result["company"] = easy["company"]
        if not result["item_name"] and easy.get("item_name"):
            result["item_name"] = easy["item_name"]
        result["sources"].append(easy["source"])

    # 폴백: 데모 데이터
    if not result["matched"]:
        demo = _lookup_demo(item_name, ingredient)
        if demo:
            result.update({k: v for k, v in demo.items() if v})
            result["matched"] = True
            result["is_demo"] = True
            result["sources"] = [demo["source"]]

    return result
