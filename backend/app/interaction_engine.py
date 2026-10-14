"""병용(함께 복용) 안전 확인 엔진 — 손주약방 핵심 기능

시나리오:
  어르신이 '새로 드시려는 약/건강기능식품'을 촬영(또는 검색)하면,
  이미 드시고 있는 약 목록과 비교해서 아래 3가지를 쉬운 말로 알려준다.
    ① 무엇이 문제인지(what)  ② 왜 조심해야 하는지(why)  ③ 지금 어떻게 해야 하는지(how)

위험도 3단계(색상+행동):
    danger  🔴 복용 전 반드시 확인   (출혈 등 중요한 위험 우려)
    caution 🟡 성분 확인 후 복용     (성분 중복·건강상태 확인 필요)
    info    🟢 복용 정보 안내        (복용시간·일반 주의)

안전 원칙:
  - 이미 처방받아 복용 중인 약(자렐토·콩코르 등)을 이 안내만 보고 임의로 중단하게 하지 않는다.
  - '새로 추가하려는 제품'을 먼저 확인하도록 안내하고, 전문가 상담을 권한다.
  - 실제 위험도는 식약처 DUR·허가사항·성분/함량·환자 상태로 최종 판정해야 함을 고지한다.

판정은 '성분 → 약효분류' 매핑 + '분류쌍 상호작용 룰'로 이루어진다(오프라인에서도 동작).
공공 DUR API 결과가 있으면 보강에 쓸 수 있으나, 본 엔진만으로 시나리오를 재현한다.
"""
import re
from typing import List, Dict

# ==================== 성분 → 약효 분류 ====================
# 키워드는 공백 제거 + 소문자 비교. 성분명/품목명 어디에 있든 부분일치로 탐지.

CLASS_KEYWORDS: Dict[str, List[str]] = {
    "anticoagulant": ["리바록사반", "rivaroxaban", "와파린", "warfarin", "아픽사반", "apixaban",
                       "다비가트란", "dabigatran", "에독사반", "edoxaban", "헤파린", "heparin"],
    "antiplatelet": ["아스피린", "aspirin", "클로피도그렐", "clopidogrel", "티카그렐러", "ticagrelor",
                     "실로스타졸", "cilostazol", "프라수그렐", "prasugrel"],
    "nsaid": ["펠루비프로펜", "pelubiprofen", "이부프로펜", "ibuprofen", "나프록센", "naproxen",
              "아세클로페낙", "aceclofenac", "디클로페낙", "diclofenac", "멜록시캄", "meloxicam",
              "세레콕시브", "셀레콕시브", "celecoxib", "록소프로펜", "loxoprofen", "덱시부프로펜",
              "케토프로펜", "ketoprofen", "피록시캄", "piroxicam", "나부메톤", "에토돌락"],
    "acetaminophen": ["아세트아미노펜", "acetaminophen", "파라세타몰", "paracetamol"],
    "opioid": ["트라마돌", "tramadol", "코데인", "codeine", "옥시코돈", "oxycodone",
               "모르핀", "morphine", "타펜타돌", "하이드로코돈"],
    "muscle_relaxant": ["에페리손", "eperisone", "바클로펜", "baclofen", "티자니딘", "tizanidine",
                        "클로르족사존", "chlorzoxazone", "메토카르바몰"],
    "sympathomimetic": ["메틸에페드린", "methylephedrine", "슈도에페드린", "pseudoephedrine",
                        "페닐에프린", "phenylephrine", "에페드린", "ephedrine"],
    "antihistamine": ["클로르페니라민", "chlorpheniramine", "디펜히드라민", "diphenhydramine",
                      "트리프롤리딘", "triprolidine", "독실아민", "세티리진", "로라타딘"],
    "beta_blocker": ["비소프롤롤", "bisoprolol", "카르베딜롤", "carvedilol", "아테놀롤", "atenolol",
                     "메토프롤롤", "metoprolol", "프로프라놀롤", "propranolol", "네비볼롤"],
    "ace_arb_diuretic": ["라미프릴", "에날라프릴", "ramipril", "enalapril", "로사르탄", "losartan",
                         "발사르탄", "valsartan", "텔미사르탄", "칸데사르탄", "히드로클로로티아지드",
                         "hydrochlorothiazide", "푸로세미드", "furosemide", "스피로노락톤"],
    "ginkgo": ["은행엽", "은행잎", "징코", "ginkgo", "ginkgobiloba"],
    "vitamin_e": ["비타민e", "토코페롤", "tocopherol", "vitamine"],
    "statin": ["심바스타틴", "아토르바스타틴", "로수바스타틴", "프라바스타틴", "statin", "스타틴"],
}

# 분류 → 어르신용 쉬운 이름
CLASS_LABEL = {
    "anticoagulant": "피를 묽게 하는 약(항응고제)",
    "antiplatelet": "피를 묽게 하는 약(항혈소판제)",
    "nsaid": "소염진통제",
    "acetaminophen": "해열진통 성분(아세트아미노펜)",
    "opioid": "마약성 진통 성분",
    "muscle_relaxant": "근육이완제",
    "sympathomimetic": "코막힘·기침 완화 성분(교감신경 자극)",
    "antihistamine": "항히스타민(콧물·알레르기) 성분",
    "beta_blocker": "심장박동·혈압 조절약",
    "ace_arb_diuretic": "혈압약",
    "ginkgo": "은행잎 추출물",
    "vitamin_e": "비타민E",
    "statin": "콜레스테롤약(스타틴)",
}

TIER_META = {
    "danger":  {"icon": "🔴", "label": "복용 전 반드시 확인", "action": "지금 드시지 말고 먼저 확인", "rank": 3},
    "caution": {"icon": "🟡", "label": "성분 확인 후 복용",   "action": "성분·복용량 확인 후 복용", "rank": 2},
    "info":    {"icon": "🟢", "label": "복용 정보 안내",       "action": "안내 내용 참고", "rank": 1},
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", (s or "")).lower()


def classify(ingredients: List[str], name: str = "") -> Dict[str, List[str]]:
    """성분 목록(+품목명)에서 약효 분류를 탐지한다.

    반환: {class_code: [탐지된 성분/근거 텍스트, ...]}
    """
    hay_items = [(_norm(ing), ing) for ing in (ingredients or []) if ing]
    name_norm = _norm(name)
    found: Dict[str, List[str]] = {}
    for cls, keywords in CLASS_KEYWORDS.items():
        for kw in keywords:
            kwn = _norm(kw)
            # 성분에서 탐지
            for ing_norm, ing_raw in hay_items:
                if kwn in ing_norm:
                    found.setdefault(cls, [])
                    if ing_raw not in found[cls]:
                        found[cls].append(ing_raw)
            # 품목명에서 탐지(성분 정보가 없을 때 보조)
            if kwn in name_norm:
                found.setdefault(cls, [])
                tag = f"{name}(성분 추정)"
                if tag not in found[cls] and not found[cls]:
                    found[cls].append(tag)
    return found


# ==================== 분류쌍 상호작용 룰 ====================
# kind="pair"  : 새 제품의 분류 A + 기존약의 분류 B 조합
# kind="dup"   : 같은 분류가 새 제품과 기존약 양쪽에 존재(성분 중복)
# kind="cond"  : 새 제품의 분류 A + 사용자의 질환/상태

PAIR_RULES = [
    {"kind": "pair", "a": "anticoagulant", "b": "nsaid", "tier": "danger",
     "what": "출혈 위험이 커질 수 있는 조합이에요.",
     "why": "피를 묽게 하는 약과 소염진통제를 함께 드시면 위장 출혈 등 피가 나는 위험이 커질 수 있어요.",
     "how": "새 진통제를 드시기 전에 의사·약사에게 함께 복용해도 되는지 꼭 확인하세요. 검은 변, 잇몸 출혈, 멍이 쉽게 생기면 바로 알리세요."},
    {"kind": "pair", "a": "anticoagulant", "b": "antiplatelet", "tier": "danger",
     "what": "피를 묽게 하는 약이 겹쳐요.",
     "why": "항응고제와 항혈소판제를 함께 쓰면 출혈 위험이 크게 올라갈 수 있어요.",
     "how": "임의로 함께 드시지 말고, 반드시 의사·약사와 먼저 상담하세요."},
    {"kind": "pair", "a": "anticoagulant", "b": "ginkgo", "tier": "danger",
     "what": "출혈 위험에 영향을 줄 수 있어요.",
     "why": "은행잎 추출물은 피를 묽게 하는 약(예: 자렐토)과 함께 드시면 출혈 경향을 더 키울 수 있어요.",
     "how": "치매 예방 광고만 믿고 시작하지 마시고, 드시기 전에 의사·약사에게 꼭 확인하세요."},
    {"kind": "pair", "a": "anticoagulant", "b": "vitamin_e", "tier": "caution",
     "what": "비타민E 함량·복용 상황 확인이 필요해요.",
     "why": "고용량 비타민E는 피를 묽게 하는 약과 함께일 때 출혈 경향에 영향을 줄 수 있어요.",
     "how": "제품의 비타민E 함량을 확인하고, 함께 드셔도 되는지 약사에게 물어보세요."},
    {"kind": "pair", "a": "antiplatelet", "b": "nsaid", "tier": "caution",
     "what": "출혈 경향이 늘 수 있어요.",
     "why": "항혈소판제(예: 아스피린)와 소염진통제를 함께 쓰면 위장 자극·출혈 위험이 늘 수 있어요.",
     "how": "속쓰림·검은 변이 있으면 알리고, 함께 복용해도 되는지 약사에게 확인하세요."},
    {"kind": "pair", "a": "sympathomimetic", "b": "beta_blocker", "tier": "caution",
     "what": "심장박동·혈압에 영향을 줄 수 있어요.",
     "why": "감기약의 코막힘·기침 완화 성분은 심장박동이나 혈압을 올릴 수 있어, 심장·혈압약을 드시는 분은 주의가 필요해요.",
     "how": "감기약을 고르기 전에 약사에게 심장·혈압약 복용 사실을 알리고 확인하세요."},
    {"kind": "pair", "a": "nsaid", "b": "ace_arb_diuretic", "tier": "caution",
     "what": "혈압약 효과가 줄 수 있어요.",
     "why": "소염진통제는 혈압약의 효과를 약하게 하거나 콩팥에 부담을 줄 수 있어요.",
     "how": "가능하면 아세트아미노펜 계열을 고려하고, 혈압약 복용 중임을 약사에게 알리세요."},
    {"kind": "pair", "a": "nsaid", "b": "beta_blocker", "tier": "caution",
     "what": "혈압 조절에 영향을 줄 수 있어요.",
     "why": "소염진통제는 혈압을 올리거나 혈압약 효과를 줄일 수 있어요.",
     "how": "혈압약 복용 중임을 약사에게 알리고, 혈압 변화를 살펴보세요."},
]

DUP_RULES = {
    "acetaminophen": {"tier": "caution",
        "what": "같은 성분이 중복돼요 (아세트아미노펜).",
        "why": "새 제품과 기존 약에 모두 아세트아미노펜이 들어 있어, 함께 드시면 진통 성분이 겹쳐 간에 부담이 될 수 있어요.",
        "how": "두 제품의 성분과 하루 총 복용량을 확인하세요. 아세트아미노펜은 하루 4,000mg를 넘기지 마세요."},
    "nsaid": {"tier": "caution",
        "what": "소염진통제가 겹쳐요.",
        "why": "소염진통제를 두 가지 이상 함께 드시면 위장·콩팥에 부담과 출혈 위험이 늘 수 있어요.",
        "how": "한 가지만 쓰도록 성분을 확인하고, 약사와 상의하세요."},
    "opioid": {"tier": "caution",
        "what": "진통(마약성) 성분이 겹쳐요.",
        "why": "같은 계열 진통 성분이 겹치면 졸림·어지럼·호흡 억제 위험이 커질 수 있어요.",
        "how": "함께 드시기 전 약사·의사에게 확인하세요."},
    "muscle_relaxant": {"tier": "caution",
        "what": "근육이완제가 겹쳐요.",
        "why": "기존에 드시던 약에 근육이완제가 있어, 함께 드시면 졸림·어지럼 등 부작용 위험이 커질 수 있어요.",
        "how": "새로 드시기 전에 약사에게 확인하세요."},
    "antihistamine": {"tier": "caution",
        "what": "졸림 유발 성분이 겹칠 수 있어요.",
        "why": "항히스타민 성분이 겹치면 졸림·입마름·어지럼이 심해져 낙상 위험이 늘 수 있어요.",
        "how": "함께 드셔도 되는지 약사에게 확인하세요."},
}

COND_RULES = [
    {"cond_any": ["심방세동", "부정맥", "심장", "협심증", "심부전"], "a": "sympathomimetic", "tier": "caution",
     "what": "심장에 영향을 줄 수 있는 성분이에요.",
     "why": "감기약의 일부 성분은 심장박동을 빠르게 할 수 있어, 심장질환이 있는 분은 주의가 필요해요.",
     "how": "감기약을 고르기 전에 심장질환이 있음을 약사에게 알리세요."},
    {"cond_any": ["고혈압", "혈압"], "a": "sympathomimetic", "tier": "caution",
     "what": "혈압에 영향을 줄 수 있는 성분이에요.",
     "why": "코막힘·기침 완화 성분은 혈압을 올릴 수 있어요.",
     "how": "혈압이 높으신 경우 약사에게 알리고 다른 감기약을 추천받으세요."},
]


def _finding(tier, title, rule, new_name, related, basis):
    meta = TIER_META[tier]
    return {
        "tier": tier,
        "icon": meta["icon"],
        "label": meta["label"],
        "action": meta["action"],
        "rank": meta["rank"],
        "title": title,
        "what": rule["what"],
        "why": rule["why"],
        "how": rule["how"],
        "new_product": new_name,
        "related_medications": related,
        "basis": basis,
    }


def check_interaction(new_product: dict, current_medications: List[dict],
                      conditions: List[str] = None) -> dict:
    """새 제품 vs 기존 복용약 병용 안전 확인.

    인자:
      new_product: {"name": str, "ingredients": [str], "category": "otc|prescription|supplement"}
      current_medications: [{"name": str, "ingredients": [str]}, ...]
      conditions: 사용자의 만성질환/상태 목록(선택) 예: ["고혈압", "심방세동"]
    """
    conditions = conditions or []
    new_name = (new_product.get("name") or "새 제품").strip()
    new_cls = classify(new_product.get("ingredients") or [], new_name)

    # 기존약 분류 집계: class -> [med_name,...]
    existing_cls: Dict[str, List[str]] = {}
    for med in current_medications or []:
        mname = (med.get("name") or "").strip()
        mcls = classify(med.get("ingredients") or [], mname)
        for cls in mcls:
            existing_cls.setdefault(cls, [])
            if mname and mname not in existing_cls[cls]:
                existing_cls[cls].append(mname)

    findings = []
    seen = set()

    # 1) 분류쌍 룰 (새 제품 A + 기존약 B, 양방향)
    for rule in PAIR_RULES:
        a, b = rule["a"], rule["b"]
        hit_related = None
        if a in new_cls and b in existing_cls:
            hit_related = existing_cls[b]
        elif b in new_cls and a in existing_cls:
            hit_related = existing_cls[a]
        if hit_related:
            key = ("pair", a, b)
            if key in seen:
                continue
            seen.add(key)
            basis = f"{CLASS_LABEL.get(a, a)} + {CLASS_LABEL.get(b, b)}"
            title = f"{new_name} + {', '.join(hit_related)}"
            findings.append(_finding(rule["tier"], title, rule, new_name, hit_related, basis))

    # 2) 성분 중복 룰 (새 제품과 기존약에 같은 분류 존재)
    for cls, rule in DUP_RULES.items():
        if cls in new_cls and cls in existing_cls:
            key = ("dup", cls)
            if key in seen:
                continue
            seen.add(key)
            related = existing_cls[cls]
            basis = f"{CLASS_LABEL.get(cls, cls)} 중복"
            title = f"{new_name} + {', '.join(related)}"
            findings.append(_finding(rule["tier"], title, rule, new_name, related, basis))

    # 3) 질환/상태 룰 (새 제품 A + 사용자 질환)
    cond_norm = [_norm(c) for c in conditions]
    for rule in COND_RULES:
        if rule["a"] in new_cls and any(_norm(c) in "".join(cond_norm) or _norm(c) in cond_norm for c in rule["cond_any"]):
            matched_cond = [c for c in conditions if any(_norm(k) in _norm(c) for k in rule["cond_any"])]
            key = ("cond", rule["a"], tuple(matched_cond))
            if key in seen:
                continue
            seen.add(key)
            basis = f"{CLASS_LABEL.get(rule['a'], rule['a'])} + 기저질환({', '.join(matched_cond)})"
            title = f"{new_name} + {', '.join(matched_cond)}"
            findings.append(_finding(rule["tier"], title, rule, new_name, matched_cond, basis))

    # 정렬: 위험도 높은 순
    findings.sort(key=lambda f: f["rank"], reverse=True)

    # 종합 판정
    if not findings:
        overall = "none"
        summary = f"'{new_name}'은(는) 지금 드시는 약과 함께 복용할 때 특별히 확인된 위험은 없어요."
    else:
        overall = findings[0]["tier"]
        n_danger = sum(1 for f in findings if f["tier"] == "danger")
        n_caution = sum(1 for f in findings if f["tier"] == "caution")
        bits = []
        if n_danger:
            bits.append(f"반드시 확인 {n_danger}건")
        if n_caution:
            bits.append(f"주의 {n_caution}건")
        summary = f"'{new_name}'에 대해 {', '.join(bits)}이 확인됐어요."

    return {
        "headline": "새로 드시려는 제품, 기존 약과 함께 먹어도 괜찮을까요?",
        "intro": "평소 드시는 약과 비교해 출혈 위험, 성분 중복, 심장·혈압 관련 주의사항을 확인해 드려요.",
        "new_product": {"name": new_name,
                        "ingredients": new_product.get("ingredients") or [],
                        "detected_classes": [CLASS_LABEL.get(c, c) for c in new_cls]},
        "overall_tier": overall,
        "summary": summary,
        "findings": findings,
        "safety_notice": ("이미 처방받아 드시던 약(예: 자렐토, 콩코르)은 이 안내만 보고 "
                          "임의로 중단하지 마세요. 새로 드시려는 제품을 먼저 확인하시고, "
                          "궁금하면 의사·약사와 상담하세요."),
        "disclaimer": ("이 안내는 성분·분류에 근거한 참고용이며, 실제 위험도는 식약처 DUR 자료와 "
                       "제품 허가사항, 성분·함량, 건강상태에 따라 달라질 수 있어요."),
    }
