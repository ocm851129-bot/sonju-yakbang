"""DUR 공공데이터 연동 모듈
공공데이터포털 의약품안전나라 DUR API 연동

API 서비스:
- DURPrdlstInfoService03: 병용금기, 특정연령대금기, 용량주의 등
- 식약처 의약품 개요 정보 (e약은요)

참고: https://www.data.go.kr/data/15075057/openapi.do
"""
import httpx
from typing import Optional
from app.config import DUR_API_KEY, DUR_API_BASE


# ==================== 공공 DUR API 조회 ====================

async def search_dur_contraindication(ingredient_a: str, ingredient_b: str) -> list:
    """병용금기 조회 (의약품안전나라 DUR API)
    
    두 성분 간 병용금기 정보를 공공데이터에서 조회합니다.
    """
    if not DUR_API_KEY:
        return []

    url = f"{DUR_API_BASE}/getUsjntTabooInfoList03"
    params = {
        "serviceKey": DUR_API_KEY,
        "typeName": "병용금기",
        "itemName": ingredient_a,
        "type": "json",
        "numOfRows": 20,
        "pageNo": 1,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                items = data.get("body", {}).get("items", [])
                if isinstance(items, list):
                    # ingredient_b와 매칭되는 것만 필터링
                    return [
                        item for item in items
                        if ingredient_b.lower() in (item.get("MIXTURE_ITEM_NAME", "") or "").lower()
                        or ingredient_b.lower() in (item.get("INGR_NAME", "") or "").lower()
                    ]
    except Exception:
        pass
    return []


async def search_dur_elderly_caution(ingredient: str) -> list:
    """특정연령대금기(노인주의) 조회"""
    if not DUR_API_KEY:
        return []

    url = f"{DUR_API_BASE}/getSpcifyAgrdeTabooInfoList03"
    params = {
        "serviceKey": DUR_API_KEY,
        "typeName": "특정연령대금기",
        "itemName": ingredient,
        "type": "json",
        "numOfRows": 20,
        "pageNo": 1,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                items = data.get("body", {}).get("items", [])
                return items if isinstance(items, list) else []
    except Exception:
        pass
    return []


async def search_dur_duplicate(ingredient: str) -> list:
    """효능군중복주의 조회"""
    if not DUR_API_KEY:
        return []

    url = f"{DUR_API_BASE}/getEfcyDplctInfoList03"
    params = {
        "serviceKey": DUR_API_KEY,
        "typeName": "효능군중복",
        "itemName": ingredient,
        "type": "json",
        "numOfRows": 20,
        "pageNo": 1,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                items = data.get("body", {}).get("items", [])
                return items if isinstance(items, list) else []
    except Exception:
        pass
    return []


async def search_drug_info(drug_name: str) -> Optional[dict]:
    """의약품 기본 정보 조회 (e약은요 API)"""
    if not DUR_API_KEY:
        return None

    url = "http://apis.data.go.kr/1471000/DrbEasyDrugInfoService/getDrbEasyDrugList"
    params = {
        "serviceKey": DUR_API_KEY,
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
