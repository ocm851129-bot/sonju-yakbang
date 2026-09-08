"""DUR 공공데이터 연동 모듈
공공데이터포털 '의약품안전사용서비스(DUR) 성분정보' API(DURIrdntInfoService03) 연동

성분(Ingredient) 기준으로 아래 7종 안전정보를 조회합니다:
  - getUsjntTabooInfoList02      병용금기
  - getSpcifyAgrdeTabooInfoList02 특정연령대금기
  - getPwnmTabooInfoList02        임부금기
  - getCpctyAtentInfoList02       용량주의
  - getMdctnPdAtentInfoList02     투여기간주의
  - getOdsnAtentInfoList02        노인주의
  - getEfcyDplctInfoList02        효능군중복

검색 파라미터는 오퍼레이션마다 ingrName / ingrKorName 로 상이하여 둘 다 전송합니다
(미인식 파라미터는 API가 무시하므로 안전). 실측 검증 완료.

참고: https://www.data.go.kr/data/15075057/openapi.do (e약은요는 drug_permission.py 사용)
"""
import httpx
from typing import Optional
from app.config import DUR_API_KEY, DUR_API_BASE, DRUG_EASY_API_KEY


# ==================== 공공 DUR 성분정보 API 조회 ====================

async def _dur_get(operation: str, ingredient: str, num_rows: int = 30) -> list:
    """DUR 성분정보 서비스의 특정 오퍼레이션을 성분명으로 조회한다."""
    if not DUR_API_KEY or not ingredient:
        return []

    url = f"{DUR_API_BASE}/{operation}"
    params = {
        "serviceKey": DUR_API_KEY,
        # 오퍼레이션별 검색 파라미터 상이 → 둘 다 전송(미인식 파라미터는 무시됨)
        "ingrName": ingredient,
        "ingrKorName": ingredient,
        "type": "json",
        "numOfRows": num_rows,
        "pageNo": 1,
    }
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            response = await client.get(url, params=params)
            if response.status_code != 200:
                return []
            data = response.json()
            items = (data.get("body", {}) or {}).get("items", []) or []
            if isinstance(items, dict):
                items = [items]
            # 일부 응답은 [{"item": {...}}] 형태
            return [it.get("item", it) if isinstance(it, dict) else it for it in items]
    except Exception:
        return []


async def search_dur_contraindication(ingredient_a: str, ingredient_b: str) -> list:
    """병용금기 조회 — 성분A로 조회 후 상대성분B가 포함된 항목만 반환."""
    items = await _dur_get("getUsjntTabooInfoList02", ingredient_a)
    b = (ingredient_b or "").lower()
    results = []
    for item in items:
        mixture = (item.get("MIXTURE_INGR_KOR_NAME", "") or "").lower()
        mixture_eng = (item.get("MIXTURE_INGR_ENG_NAME", "") or "").lower()
        if not b or b in mixture or b in mixture_eng:
            results.append(item)
    return results


async def search_dur_elderly_caution(ingredient: str) -> list:
    """노인주의 조회 (고령자 특화)."""
    return await _dur_get("getOdsnAtentInfoList02", ingredient)


async def search_dur_age_taboo(ingredient: str) -> list:
    """특정연령대금기 조회."""
    return await _dur_get("getSpcifyAgrdeTabooInfoList02", ingredient)


async def search_dur_pregnancy_taboo(ingredient: str) -> list:
    """임부금기 조회."""
    return await _dur_get("getPwnmTabooInfoList02", ingredient)


async def search_dur_capacity_caution(ingredient: str) -> list:
    """용량주의 조회."""
    return await _dur_get("getCpctyAtentInfoList02", ingredient)


async def search_dur_period_caution(ingredient: str) -> list:
    """투여기간주의 조회."""
    return await _dur_get("getMdctnPdAtentInfoList02", ingredient)


async def search_dur_duplicate(ingredient: str) -> list:
    """효능군중복 조회."""
    return await _dur_get("getEfcyDplctInfoList02", ingredient)


async def search_drug_info(drug_name: str) -> Optional[dict]:
    """의약품 기본 정보 조회 (e약은요 API)"""
    if not DRUG_EASY_API_KEY:
        return None

    url = "https://apis.data.go.kr/1471000/DrbEasyDrugInfoService/getDrbEasyDrugList"
    params = {
        "serviceKey": DRUG_EASY_API_KEY,
        "itemName": drug_name,
        "type": "json",
        "numOfRows": 1,
        "pageNo": 1,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                items = data.get("body", {}).get("items", [])
                if items:
                    return items[0]
    except Exception:
        pass
    return None


# ==================== 로컬 DUR 룰 (API 비가용 시 fallback) ====================

LOCAL_DUR_RULES = [
    {"drug_a": "와파린", "drug_b": "아스피린", "type": "contraindication", "severity": "high",
     "description": "출혈 위험이 크게 증가합니다", "recommendation": "의사와 상담하여 용량 조절이 필요합니다"},
    {"drug_a": "와파린", "drug_b": "오메가3", "type": "contraindication", "severity": "medium",
     "description": "출혈 경향이 증가할 수 있습니다", "recommendation": "복용 간격을 두고, 출혈 징후를 관찰하세요"},
    {"drug_a": "와파린", "drug_b": "은행잎", "type": "contraindication", "severity": "high",
     "description": "은행잎 추출물이 항응고 작용을 강화합니다", "recommendation": "병용을 피하세요"},
    {"drug_a": "메트포르민", "drug_b": "알코올", "type": "contraindication", "severity": "high",
     "description": "유산산증 위험이 증가합니다", "recommendation": "음주를 삼가세요"},
    {"drug_a": "ACE억제제", "drug_b": "칼륨보충제", "type": "contraindication", "severity": "high",
     "description": "고칼륨혈증 위험이 있습니다", "recommendation": "정기적으로 혈중 칼륨 수치를 확인하세요"},
    {"drug_a": "스타틴", "drug_b": "자몽", "type": "interaction", "severity": "medium",
     "description": "자몽이 약물 대사를 방해하여 부작용 위험이 증가합니다", "recommendation": "자몽 섭취를 피하세요"},
    {"drug_a": "혈압약", "drug_b": "진통소염제", "type": "interaction", "severity": "medium",
     "description": "진통소염제가 혈압약 효과를 감소시킬 수 있습니다", "recommendation": "아세트아미노펜으로 대체를 고려하세요"},
    {"drug_a": "당뇨약", "drug_b": "스테로이드", "type": "interaction", "severity": "high",
     "description": "스테로이드가 혈당을 높여 당뇨약 효과를 감소시킵니다", "recommendation": "혈당 모니터링을 강화하세요"},
    {"drug_a": "디곡신", "drug_b": "아미오다론", "type": "contraindication", "severity": "high",
     "description": "디곡신 혈중농도가 상승하여 부정맥 위험이 있습니다", "recommendation": "디곡신 용량 감량 필요"},
    {"drug_a": "씨프로플록사신", "drug_b": "제산제", "type": "interaction", "severity": "medium",
     "description": "제산제가 항생제 흡수를 방해합니다", "recommendation": "2시간 이상 간격을 두고 복용하세요"},
    {"drug_a": "클로피도그렐", "drug_b": "오메프라졸", "type": "interaction", "severity": "medium",
     "description": "클로피도그렐의 항혈소판 효과가 감소할 수 있습니다", "recommendation": "다른 위산분비억제제로 변경을 고려하세요"},
    {"drug_a": "리튬", "drug_b": "이부프로펜", "type": "contraindication", "severity": "high",
     "description": "리튬 혈중농도가 상승하여 독성 위험이 있습니다", "recommendation": "리튬 농도 모니터링 필요"},
]


def local_dur_check(med_name_a: str, ingredient_a: str, med_name_b: str, ingredient_b: str) -> list:
    """로컬 DUR 룰 기반 점검 (API 불가 시 fallback)"""
    alerts = []
    for rule in LOCAL_DUR_RULES:
        a_match = (
            rule["drug_a"].lower() in med_name_a.lower()
            or rule["drug_a"].lower() in ingredient_a.lower()
        )
        b_match = (
            rule["drug_b"].lower() in med_name_b.lower()
            or rule["drug_b"].lower() in ingredient_b.lower()
        )
        if a_match and b_match:
            alerts.append({
                "type": rule["type"],
                "severity": rule["severity"],
                "medication_a": med_name_a,
                "medication_b": med_name_b,
                "description": rule["description"],
                "recommendation": rule["recommendation"],
                "source": "local_rule",
            })
    return alerts
