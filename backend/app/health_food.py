"""건강기능식품(기능성 제품) 정보 연동 모듈

처방전(전문·일반의약품)뿐 아니라 건강기능식품/영양제까지 OCR·검색으로
정보를 제공하기 위한 모듈입니다. 의약품은 drug_permission.py 가 담당하고,
건강기능식품은 이 모듈이 담당합니다.

정보 출처 우선순위:
  1차) 식약처 건강기능식품 품목정보 공공 API (data.go.kr, DATA_GO_KR_API_KEY 공용)
       - 활용신청 필요: "식품의약품안전처_건강기능식품 품목정보" 서비스.
         활용신청 후 config.HEALTH_FOOD_API_BASE / 오퍼레이션명이 맞는지 확인하세요.
  2차) 라벨 자체(법적으로 기능성·섭취방법·주의사항이 포장에 인쇄됨)를 GPT Vision 이
       직접 읽어 structured_data 로 추출 (ocr.py). 이 모듈이 비어도 라벨값은 유지됨.
  3차) 로컬 데모 DB(고령자 다빈도 건강기능식품) 폴백.
"""
import re
import httpx
from typing import Optional
from app.config import DATA_GO_KR_API_KEY, HEALTH_FOOD_API_BASE


def _truncate(text: str, limit: int = 500) -> str:
    if not text:
        return ""
    text = str(text).strip()
    return text if len(text) <= limit else text[:limit].rstrip() + " …"


def _clean_name(name: str) -> str:
    """제품명에서 용량·단위 등 노이즈를 줄여 검색 정확도를 높인다."""
    if not name:
        return ""
    n = re.sub(r"[\(\[（【].*?[\)\]）】]", "", name)
    n = re.sub(r"\d+(\.\d+)?\s*(mg|mcg|㎎|㎍|g|ml|㎖|정|캡슐|포|병|IU|억|billion)", "", n, flags=re.IGNORECASE)
    n = re.sub(r"\s+", " ", n).strip()
    return n or name.strip()


# ==================== 식약처 건강기능식품 품목정보 API ====================

async def search_health_food_api(item_name: str) -> Optional[dict]:
    """식약처 건강기능식품 품목정보 API 조회 (best-effort).

    활용신청/엔드포인트가 아직 확정되지 않았거나 응답이 없으면 None 을 반환하여
    상위에서 라벨값 또는 데모 DB 로 폴백하도록 한다.
    """
    if not DATA_GO_KR_API_KEY or not HEALTH_FOOD_API_BASE or not item_name:
        return None

    params = {
        "serviceKey": DATA_GO_KR_API_KEY,
        "prduct": item_name,   # 제품명 (서비스에 따라 'prdlstNm' 등으로 다를 수 있음)
        "type": "json",
        "numOfRows": 3,
        "pageNo": 1,
    }
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get(HEALTH_FOOD_API_BASE, params=params)
            if resp.status_code != 200:
                return None
            data = resp.json()
            body = data.get("body", data) or {}
            items = body.get("items", []) if isinstance(body, dict) else []
            if not items:
                return None
            first = items[0]
            item = first.get("item", first) if isinstance(first, dict) else first
            return {
                "item_name": (item.get("PRDUCT") or item.get("PRDLST_NM") or item_name).strip(),
                "company": (item.get("ENTRPS") or item.get("BSSH_NM") or "").strip(),
                "functional_content": _truncate(item.get("MAIN_FNCTN") or item.get("PRIMARY_FNCLTY") or ""),
                "intake_method": _truncate(item.get("SRV_USE") or item.get("NTK_MTHD") or ""),
                "caution": _truncate(item.get("IFTKN_ATNT_MATR_CN") or item.get("INTAKE_HINT1") or ""),
                "raw_material": _truncate(item.get("RAWMTRL_NM") or item.get("RAWMTRL_NM_LISTING") or "", 300),
                "standard": _truncate(item.get("STDR_STND") or "", 200),
                "source": "식약처 건강기능식품 품목정보",
            }
    except Exception:
        return None


# ==================== 로컬 데모 DB (고령자 다빈도 건강기능식품) ====================

HEALTH_FOOD_DEMO_DB = {
    "오메가3": {
        "item_name": "오메가3 (EPA·DHA 함유 유지)", "company": "",
        "functional_content": "혈중 중성지방 개선 · 혈행 개선 · 기억력 개선에 도움을 줄 수 있음",
        "intake_method": "1일 1회, 1회 1캡슐을 충분한 물과 함께 섭취합니다.",
        "caution": "항응고제(와파린 등)·아스피린 복용자는 출혈 위험이 있어 섭취 전 상담하세요.",
        "raw_material": "정제어유(EPA·DHA)",
    },
    "비타민d": {
        "item_name": "비타민D", "company": "",
        "functional_content": "칼슘 흡수·이용에 필요 · 뼈의 형성과 유지 · 골다공증 발생 위험 감소에 도움",
        "intake_method": "1일 1회, 1회 1정을 섭취합니다.",
        "caution": "과다 섭취 시 고칼슘혈증이 생길 수 있으니 권장량을 지키세요.",
        "raw_material": "비타민D3(콜레칼시페롤)",
    },
    "프로바이오틱스": {
        "item_name": "프로바이오틱스(유산균)", "company": "",
        "functional_content": "유산균 증식 및 유해균 억제 · 배변활동 원활에 도움을 줄 수 있음",
        "intake_method": "1일 1회, 1포(또는 1캡슐)를 식후에 섭취합니다.",
        "caution": "항생제 복용 중에는 2시간 이상 간격을 두고 섭취하세요.",
        "raw_material": "락토바실러스·비피도박테리움 등 프로바이오틱스",
    },
    "밀크씨슬": {
        "item_name": "밀크씨슬(실리마린) 추출물", "company": "",
        "functional_content": "간 건강에 도움을 줄 수 있음",
        "intake_method": "1일 1회, 1정을 물과 함께 섭취합니다.",
        "caution": "국화과 식물 알레르기가 있으면 주의하세요.",
        "raw_material": "밀크씨슬 추출물(실리마린)",
    },
    "루테인": {
        "item_name": "루테인", "company": "",
        "functional_content": "노화로 인해 감소할 수 있는 황반색소 밀도 유지에 도움을 줄 수 있음",
        "intake_method": "1일 1회, 1정을 섭취합니다.",
        "caution": "흡연자는 베타카로틴 복합제품 섭취에 주의하세요.",
        "raw_material": "마리골드꽃 추출물(루테인)",
    },
    "코엔자임": {
        "item_name": "코엔자임Q10", "company": "",
        "functional_content": "항산화 · 높은 혈압 감소에 도움을 줄 수 있음",
        "intake_method": "1일 1회, 1정을 섭취합니다.",
        "caution": "혈압약·와파린 복용자는 섭취 전 상담하세요.",
        "raw_material": "코엔자임Q10",
    },
    "홍삼": {
        "item_name": "홍삼", "company": "",
        "functional_content": "면역력 증진 · 피로 개선 · 혈행 개선 · 기억력 개선에 도움",
        "intake_method": "1일 1회, 1포를 섭취합니다.",
        "caution": "혈압약·당뇨약·항응고제 복용자는 섭취 전 상담하세요.",
        "raw_material": "홍삼농축액",
    },
    "칼슘": {
        "item_name": "칼슘/마그네슘/비타민D", "company": "",
        "functional_content": "뼈·치아 형성에 필요 · 신경과 근육 기능 유지에 도움",
        "intake_method": "1일 1~2회, 1회 1정을 섭취합니다.",
        "caution": "갑상선호르몬제·일부 항생제와 2~4시간 간격을 두세요.",
        "raw_material": "탄산칼슘·산화마그네슘·비타민D3",
    },
    "종합비타민": {
        "item_name": "종합비타민·미네랄", "company": "",
        "functional_content": "각종 비타민·미네랄 보충으로 결핍 예방에 도움",
        "intake_method": "1일 1회, 1정을 식후에 섭취합니다.",
        "caution": "다른 영양제와 성분이 겹치지 않게 하세요.",
        "raw_material": "비타민B군·C·D·아연·셀렌 등",
    },
    "비타민c": {
        "item_name": "비타민C", "company": "",
        "functional_content": "항산화 · 결합조직 형성과 기능 유지 · 철 흡수에 도움",
        "intake_method": "1일 1회, 1정을 섭취합니다.",
        "caution": "과다 섭취 시 위장장애가 있을 수 있습니다.",
        "raw_material": "비타민C(아스코르브산)",
    },
    "콜라겐": {
        "item_name": "저분자콜라겐펩타이드", "company": "",
        "functional_content": "피부 보습 · 자외선에 의한 피부 손상으로부터 보호에 도움",
        "intake_method": "1일 1회, 1포를 섭취합니다.",
        "caution": "어류 알레르기가 있으면 원료를 확인하세요.",
        "raw_material": "콜라겐펩타이드(어류 유래)",
    },
    "가르시니아": {
        "item_name": "가르시니아캄보지아 추출물", "company": "",
        "functional_content": "탄수화물이 지방으로 합성되는 것을 억제하여 체지방 감소에 도움",
        "intake_method": "1일 2~3회, 식사 30분~1시간 전에 섭취합니다.",
        "caution": "간 질환자·임산부는 섭취를 피하고, 당뇨약 복용자는 상담하세요.",
        "raw_material": "가르시니아캄보지아 추출물(HCA)",
    },
}

# OCR 텍스트/검색어에서 건강기능식품을 식별하기 위한 별칭 키워드
HEALTH_FOOD_ALIASES = {
    "오메가3": ["오메가3", "오메가쓰리", "omega", "epa", "dha", "오메가-3"],
    "비타민d": ["비타민d", "비타민디", "vitamind", "vitamin d", "콜레칼시페롤"],
    "프로바이오틱스": ["프로바이오틱스", "유산균", "probiotics", "락토바실러스", "비피더스"],
    "밀크씨슬": ["밀크씨슬", "실리마린", "milkthistle", "밀크시슬"],
    "루테인": ["루테인", "lutein", "황반"],
    "코엔자임": ["코엔자임", "큐텐", "q10", "coq10", "코큐텐"],
    "홍삼": ["홍삼", "정관장", "홍삼정", "redginseng"],
    "칼슘": ["칼슘", "마그네슘", "칼마디", "calcium", "magnesium"],
    "종합비타민": ["종합비타민", "멀티비타민", "multivitamin", "센트룸", "종합영양제"],
    "비타민c": ["비타민c", "비타민씨", "vitaminc", "vitamin c", "아스코르브산"],
    "콜라겐": ["콜라겐", "collagen", "저분자콜라겐"],
    "가르시니아": ["가르시니아", "garcinia", "hca"],
}


def _lookup_demo(name: str) -> Optional[dict]:
    """로컬 데모 DB에서 제품명/별칭 부분일치로 건강기능식품을 조회한다."""
    hay = re.sub(r"[\s\-_.]+", "", str(name or "")).lower()
    if not hay:
        return None
    for key, aliases in HEALTH_FOOD_ALIASES.items():
        for a in aliases:
            na = re.sub(r"[\s\-_.]+", "", a).lower()
            if na and (na in hay or hay in na):
                info = dict(HEALTH_FOOD_DEMO_DB[key])
                info["source"] = "기기 내 건강기능식품 DB(오프라인)"
                info["is_demo"] = True
                return info
    return None


def find_health_foods_in_text(raw_text: str) -> list:
    """OCR 원문 텍스트에서 건강기능식품들을 찾아 목록으로 반환."""
    hay = re.sub(r"[\s\-_.]+", "", str(raw_text or "")).lower()
    found, seen = [], set()
    for key, aliases in HEALTH_FOOD_ALIASES.items():
        if key in seen:
            continue
        for a in aliases:
            na = re.sub(r"[\s\-_.]+", "", a).lower()
            if na and na in hay:
                info = dict(HEALTH_FOOD_DEMO_DB[key])
                found.append({
                    "name": info["item_name"],
                    "product_type": "health_functional_food",
                    "category": "supplement",
                    "functional_content": info["functional_content"],
                    "intake_method": info["intake_method"],
                    "caution": info["caution"],
                    "raw_material": info["raw_material"],
                })
                seen.add(key)
                break
    return found


# ==================== 오케스트레이션 ====================

async def get_health_food_info(item_name: str) -> dict:
    """제품명을 받아 건강기능식품 통합 정보를 반환한다.

    반환 스키마:
      matched, product_type('health_functional_food'), item_name, company,
      functional_content(기능성), intake_method(섭취방법), caution,
      raw_material(원료), standard, image_url, sources(list), is_demo
    """
    query = _clean_name(item_name)
    result = {
        "matched": False,
        "product_type": "health_functional_food",
        "item_name": item_name,
        "company": "",
        "functional_content": "",
        "intake_method": "",
        "caution": "",
        "raw_material": "",
        "standard": "",
        "image_url": "",
        "sources": [],
        "is_demo": False,
    }

    api = await search_health_food_api(query) or await search_health_food_api(item_name.strip())
    if api:
        result["matched"] = True
        for k in ("item_name", "company", "functional_content", "intake_method",
                  "caution", "raw_material", "standard"):
            if api.get(k):
                result[k] = api[k]
        result["sources"].append(api["source"])
        return result

    demo = _lookup_demo(item_name)
    if demo:
        result["matched"] = True
        for k in ("item_name", "company", "functional_content", "intake_method",
                  "caution", "raw_material"):
            if demo.get(k):
                result[k] = demo[k]
        result["is_demo"] = True
        result["sources"] = [demo["source"]]

    return result
