"""식품의약품안전처 '의약품 낱알식별정보' 연동 모듈

공공데이터포털(data.go.kr) MdcinGrnIdntfcInfoService03 / getMdcinGrnIdntfcInfoList03.
낱알(정제·캡슐) 하나의 '생김새'로 약을 식별하기 위한 데이터를 제공합니다.

제공 항목(주요):
  품목명/업체명/성상(CHART)/모양(DRUG_SHAPE)/색상(COLOR_CLASS1·2)/
  앞·뒷면 각인(PRINT_FRONT·BACK)/분할선(LINE_FRONT·BACK)/
  크기(장축 LENG_LONG·단축 LENG_SHORT·두께 THICK)/제형(FORM_CODE_NAME)/
  전문·일반 구분(ETC_OTC_NAME)/분류(CLASS_NAME)/실제 낱알 이미지(ITEM_IMAGE)

두 가지 사용 방식:
  1) 품목명으로 조회  → search_identity_by_name()   : 허가정보/e약은요를 '생김새·이미지'로 보강
  2) 생김새로 식별    → identify_pill()              : 모양/색/각인으로 후보 약 목록 역검색

인증키가 없으면 조용히 None/빈 목록을 반환합니다(데모 모드 호환).
"""
import re
import html
import httpx
from typing import Optional, List
import xml.etree.ElementTree as ET
import os
import json
from app.config import DRUG_IDENTITY_API_KEY, DRUG_IDENTITY_API_BASE, PILL_INDEX_PATH

_LIST_ENDPOINT = "/getMdcinGrnIdntfcInfoList03"


def _s(v) -> str:
    return (v or "").strip() if isinstance(v, str) else ("" if v is None else str(v).strip())


def _normalize_identity_item(item: dict) -> dict:
    """낱알식별 API 원본 필드를 앱 표준 스키마로 정규화한다."""
    etc_otc = _s(item.get("ETC_OTC_NAME"))
    if "전문" in etc_otc:
        category = "prescription"
    elif "일반" in etc_otc:
        category = "otc"
    else:
        category = "prescription"

    colors = [c for c in (_s(item.get("COLOR_CLASS1")), _s(item.get("COLOR_CLASS2"))) if c]
    prints = {
        "front": _s(item.get("PRINT_FRONT")),
        "back": _s(item.get("PRINT_BACK")),
    }
    lines = {
        "front": _s(item.get("LINE_FRONT")),
        "back": _s(item.get("LINE_BACK")),
    }
    size = {
        "long": _s(item.get("LENG_LONG")),
        "short": _s(item.get("LENG_SHORT")),
        "thick": _s(item.get("THICK")),
    }

    # 어르신 친화 한 줄 생김새 요약 (예: "흰색 원형 정제, 앞면 'AD' 각인, 분할선 있음")
    desc_parts = []
    if colors:
        desc_parts.append("·".join(colors))
    if _s(item.get("DRUG_SHAPE")):
        desc_parts.append(_s(item.get("DRUG_SHAPE")))
    if _s(item.get("FORM_CODE_NAME")):
        desc_parts.append(_s(item.get("FORM_CODE_NAME")))
    appearance = html.unescape(" ".join(desc_parts)) if desc_parts else _s(item.get("CHART"))
    if prints["front"] or prints["back"]:
        mark = "/".join(p for p in (prints["front"], prints["back"]) if p)
        appearance = f"{appearance}, 각인 '{mark}'".strip(", ")
    if size["long"]:
        appearance = f"{appearance} (장축 {size['long']}mm)".rstrip()

    return {
        "item_name": _s(item.get("ITEM_NAME")),
        "item_seq": _s(item.get("ITEM_SEQ")),
        "company": _s(item.get("ENTP_NAME")),
        "etc_otc": etc_otc,
        "category": category,
        "class_name": _s(item.get("CLASS_NAME")),
        "drug_shape": _s(item.get("DRUG_SHAPE")),
        "colors": colors,
        "chart": html.unescape(_s(item.get("CHART"))),
        "print_front": prints["front"],
        "print_back": prints["back"],
        "line_front": lines["front"],
        "line_back": lines["back"],
        "size_long": size["long"],
        "size_short": size["short"],
        "size_thick": size["thick"],
        "form_name": _s(item.get("FORM_CODE_NAME")),
        "mark_front": _s(item.get("MARK_CODE_FRONT_ANAL")),
        "mark_back": _s(item.get("MARK_CODE_BACK_ANAL")),
        "appearance": appearance,
        "image_url": _s(item.get("ITEM_IMAGE")),
        "source": "식약처 의약품 낱알식별정보",
    }


def _extract_items(data) -> List[dict]:
    """JSON 응답(body.items)에서 item 리스트를 평탄화한다."""
    body = (data.get("body") or {}) if isinstance(data, dict) else {}
    items = body.get("items") or []
    if isinstance(items, dict):  # 단건이 dict 로 올 때
        items = items.get("item", items)
    out = []
    for it in (items if isinstance(items, list) else [items]):
        if isinstance(it, dict):
            out.append(it.get("item", it))
    return [i for i in out if isinstance(i, dict)]


async def _request(params: dict) -> List[dict]:
    """낱알식별 목록 API 공통 호출. JSON 우선, 실패 시 XML 파싱으로 폴백."""
    if not DRUG_IDENTITY_API_KEY:
        return []
    url = f"{DRUG_IDENTITY_API_BASE}{_LIST_ENDPOINT}"
    base = {"serviceKey": DRUG_IDENTITY_API_KEY, "type": "json", "pageNo": 1}
    base.update(params)
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get(url, params=base)
            if resp.status_code != 200:
                return []
            text = resp.text.lstrip()
            if text.startswith("{"):
                return _extract_items(resp.json())
            # XML 폴백
            return _parse_xml_items(text)
    except Exception:
        return []


def _parse_xml_items(text: str) -> List[dict]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    out = []
    for item in root.iter("item"):
        out.append({child.tag: (child.text or "") for child in item})
    return out


# ==================== 1) 품목명으로 조회 (생김새·이미지 보강용) ====================

async def search_identity_by_name(item_name: str) -> Optional[dict]:
    """품목명으로 낱알식별정보 1건을 조회한다(허가정보 보강용)."""
    if not item_name:
        return None
    items = await _request({"item_name": item_name, "numOfRows": 3})
    if not items:
        return None
    return _normalize_identity_item(items[0])


# ==================== 2) 생김새로 식별 (역검색) ====================
#
# 주의: getMdcinGrnIdntfcInfoList03 는 모양/색상/각인을 '서버측 조건검색'으로
#       지원하지 않습니다(item_name/edi_code 만 필터됨 — 실측 확인).
#       따라서 생김새로 찾으려면 전체 낱알DB(약 2.5만건)를 로컬 색인
#       (data/pill_identity.jsonl)으로 내려받아 클라이언트에서 거릅니다.
#       색인 생성:  python tools/drug_preprocess.py fetch-pills -o data/pill_identity.jsonl

_pill_index_cache: Optional[List[dict]] = None


def _load_pill_index() -> List[dict]:
    """로컬 낱알 색인(jsonl)을 메모리에 로드한다(최초 1회)."""
    global _pill_index_cache
    if _pill_index_cache is not None:
        return _pill_index_cache
    rows: List[dict] = []
    if os.path.exists(PILL_INDEX_PATH):
        try:
            with open(PILL_INDEX_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        rows.append(json.loads(line))
        except Exception:
            rows = []
    _pill_index_cache = rows
    return rows


def reload_pill_index():
    """색인 파일을 다시 읽도록 캐시를 비운다(fetch-pills 갱신 후 호출)."""
    global _pill_index_cache
    _pill_index_cache = None


def _norm(s: str) -> str:
    return (s or "").replace(" ", "").lower()


def _match_pill(item: dict, shape: str, color: str, mark: str, line: str, form: str) -> bool:
    """색인 1건이 입력한 생김새 조건을 모두 만족하는지 검사한다(부분일치/관대)."""
    if shape and _norm(shape) not in _norm(item.get("drug_shape", "")):
        return False
    if color:
        colors = item.get("colors") or []
        if not any(_norm(color) in _norm(c) for c in colors):
            return False
    if form and _norm(form) not in _norm(item.get("form_name", "")):
        return False
    if line:
        want = _norm(line)
        has = _norm(item.get("line_front", "")) + _norm(item.get("line_back", ""))
        # '있음'=분할선 표기 존재 / '없음'=표기 없음
        if want in ("있음", "유", "yes"):
            if "분할선" not in has and not has:
                return False
        elif want in ("없음", "무", "no"):
            if "분할선" in has:
                return False
        elif want not in has:
            return False
    if mark:
        m = _norm(mark)
        hay = _norm(item.get("print_front", "")) + "|" + _norm(item.get("print_back", "")) + \
              "|" + _norm(item.get("mark_front", "")) + "|" + _norm(item.get("mark_back", ""))
        if m not in hay:
            return False
    return True


async def identify_pill(
    shape: str = "",
    color: str = "",
    mark: str = "",
    line: str = "",
    form: str = "",
    limit: int = 10,
) -> dict:
    """낱알의 물리적 특징으로 후보 약 목록을 역검색한다.

    반환: {"candidates": [...], "mode": "local_index"|"unavailable", "scanned": N, "note": "..."}

    인자(모두 선택): shape 모양, color 색상, mark 각인/식별문자,
      line 분할선(있음/없음), form 제형(정제/경질캡슐 등)
    """
    if not any([shape, color, mark, line, form]):
        return {"candidates": [], "mode": "unavailable", "scanned": 0,
                "note": "모양·색상·각인 중 하나 이상을 입력해주세요."}

    index = _load_pill_index()
    if not index:
        return {
            "candidates": [], "mode": "unavailable", "scanned": 0,
            "note": ("낱알 생김새 검색을 쓰려면 먼저 색인을 만들어야 합니다. "
                     "backend 폴더에서 다음을 실행하세요:  "
                     "python tools/drug_preprocess.py fetch-pills -o data/pill_identity.jsonl"),
        }

    matched = []
    for item in index:
        if _match_pill(item, shape, color, mark, line, form):
            matched.append(item)
            if len(matched) >= limit:
                break
    return {
        "candidates": matched,
        "mode": "local_index",
        "scanned": len(index),
        "note": "" if matched else "조건에 맞는 약을 찾지 못했습니다. 각인·색상을 확인해 다시 시도해보세요.",
    }
