#!/usr/bin/env python3
"""손주약방 RAG 의약품 데이터 전처리 도구 (비개발자용)

원본 파일(CSV / JSON / JSONL / 식약처 API XML·JSON)을 넣으면,
RAG 시스템이 바로 읽을 수 있는 '표준 JSONL' 형식으로 자동 변환하고
누락·중복을 검사해 보고서를 보여줍니다.

표준 스키마(한 줄 = 약 1건):
  필수 : source(출처), 그리고 text(본문) 또는 (drug_name+효능 등) 중 하나
  선택 : id, category, drug_name, ingredient, amount, effect, usage,
         caution, side_effect, storage, interaction, appearance, updated_at

사용법 (backend 폴더에서):
  # 1) 변환 : 원본 → 표준 JSONL
  python tools/drug_preprocess.py convert 원본.csv -o knowledge/my_drugs.jsonl

  # 2) 검증 : 표준 JSONL 에 문제가 없는지 확인
  python tools/drug_preprocess.py validate knowledge/my_drugs.jsonl

  # 3) 합치기+중복제거 : 여러 JSONL 을 하나로
  python tools/drug_preprocess.py merge a.jsonl b.jsonl -o knowledge/all.jsonl

변환 후에는 서버에서 POST /api/rag/reload 를 호출하면 즉시 반영됩니다.
"""
import argparse
import csv
import json
import os
import sys
import hashlib
import datetime
import xml.etree.ElementTree as ET

# Windows 콘솔(cp949)에서도 한글·이모지가 깨지지 않도록 UTF-8 출력 고정
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# ==================== 컬럼/필드 이름 매핑 ====================
# 왼쪽(입력에서 쓰일 수 있는 다양한 이름) → 오른쪽(표준 필드)
FIELD_ALIASES = {
    # 식별/분류
    "id": "id", "아이디": "id", "item_seq": "id", "ITEM_SEQ": "id",
    "category": "category", "분류": "category", "카테고리": "category",
    # 이름/성분/함량
    "drug_name": "drug_name", "의약품명": "drug_name", "약품명": "drug_name",
    "품목명": "drug_name", "제품명": "drug_name", "item_name": "drug_name", "ITEM_NAME": "drug_name",
    "ingredient": "ingredient", "성분": "ingredient", "성분명": "ingredient",
    "주성분": "ingredient", "MATERIAL_NAME": "ingredient",
    "amount": "amount", "함량": "amount", "용량": "amount", "dosage": "amount",
    # 내용
    "effect": "effect", "효능": "effect", "효능효과": "effect", "효능·효과": "effect", "EE_DOC_DATA": "effect",
    "usage": "usage", "용법": "usage", "복용법": "usage", "용법용량": "usage", "UD_DOC_DATA": "usage",
    "caution": "caution", "주의": "caution", "주의사항": "caution", "NB_DOC_DATA": "caution",
    "side_effect": "side_effect", "부작용": "side_effect",
    "storage": "storage", "보관": "storage", "보관법": "storage", "STORAGE_METHOD": "storage",
    "interaction": "interaction", "상호작용": "interaction",
    "appearance": "appearance", "생김새": "appearance", "성상": "appearance", "CHART": "appearance",
    # 출처/본문/갱신
    "source": "source", "출처": "source", "ENTP_NAME": "company",
    "text": "text", "본문": "text", "내용": "text",
    "updated_at": "updated_at", "갱신일": "updated_at", "수정일": "updated_at",
}

# text 자동 합성에 쓰이는 라벨
COMPOSE_LABELS = [
    ("effect", "효능·효과"), ("usage", "복용법"), ("caution", "주의사항"),
    ("side_effect", "부작용"), ("storage", "보관법"),
    ("interaction", "상호작용"), ("appearance", "생김새"),
]

STANDARD_FIELDS = ["id", "category", "drug_name", "ingredient", "amount", "text",
                   "effect", "usage", "caution", "side_effect", "storage",
                   "interaction", "appearance", "source", "updated_at"]


def _today():
    return datetime.date.today().isoformat()


def _map_record(raw: dict) -> dict:
    """원본 레코드의 키를 표준 필드명으로 변환한다."""
    out = {}
    for k, v in raw.items():
        if v is None:
            continue
        key = FIELD_ALIASES.get(k.strip(), k.strip()) if isinstance(k, str) else k
        val = v.strip() if isinstance(v, str) else v
        if val == "" or val == []:
            continue
        # 이미 채워진 표준 필드를 빈 값으로 덮어쓰지 않음
        if key in out and not val:
            continue
        out[key] = val
    return out


def _compose_text(rec: dict) -> str:
    """text 가 없으면 구조화 필드로 자연어 본문을 만든다(rag_engine 과 동일 규칙)."""
    t = (rec.get("text") or "").strip()
    if t:
        return t
    name = (rec.get("drug_name") or "").strip()
    parts = []
    ing = (rec.get("ingredient") or "").strip()
    amt = (rec.get("amount") or "").strip()
    head = f"{name}({' '.join(x for x in (ing, amt) if x)})".strip() if (ing or amt) else name
    if head:
        parts.append(head)
    for key, label in COMPOSE_LABELS:
        val = (rec.get(key) or "").strip()
        if val:
            parts.append(f"{label}: {val}")
    return ". ".join(parts).strip()


def _make_id(rec: dict, text: str) -> str:
    if rec.get("id"):
        return str(rec["id"]).strip()
    name = (rec.get("drug_name") or "").strip()
    if name:
        return f"drug:{name}"
    return f"hash:{hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}"


def _finalize(rec: dict) -> dict:
    """표준 레코드로 마감: text 합성, id/category/updated_at 보정, 표준 필드만 남김."""
    text = _compose_text(rec)
    rec["text"] = text
    rec["id"] = _make_id(rec, text)
    rec.setdefault("category", "drug")
    rec.setdefault("updated_at", _today())
    return {k: rec[k] for k in STANDARD_FIELDS if k in rec and rec[k] not in ("", [], None)}


def _validate(rec: dict) -> list:
    """레코드 문제점 목록을 반환(빈 리스트면 정상)."""
    problems = []
    if not (rec.get("source") or "").strip():
        problems.append("출처(source) 누락")
    if not (rec.get("text") or "").strip():
        problems.append("본문(text) 비어있음 — 효능/주의 등 내용 또는 text 가 필요")
    return problems


# ==================== 원본 포맷별 로더 ====================

def _load_raw(path: str) -> list:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    if ext == ".jsonl":
        rows = []
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("//"):
                    rows.append(json.loads(line))
        return rows
    if ext == ".json":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 식약처 응답({"body":{"items":[...]}}) 또는 배열 모두 지원
        if isinstance(data, dict):
            body = data.get("body", data)
            items = body.get("items", data) if isinstance(body, dict) else data
            if isinstance(items, dict):
                items = items.get("item", [items])
            return items if isinstance(items, list) else [items]
        return data if isinstance(data, list) else [data]
    if ext == ".xml":
        tree = ET.parse(path)
        rows = []
        for item in tree.iter("item"):
            rows.append({child.tag: (child.text or "") for child in item})
        return rows
    raise ValueError(f"지원하지 않는 형식: {ext} (csv/json/jsonl/xml 만 가능)")


# ==================== 명령: convert ====================

def cmd_convert(args):
    rows = _load_raw(args.input)
    written, skipped, dups = [], [], 0
    seen = {}
    for i, raw in enumerate(rows, 1):
        rec = _finalize(_map_record(raw))
        problems = _validate(rec)
        if problems:
            skipped.append((i, problems, rec.get("drug_name") or rec.get("text", "")[:20]))
            continue
        if rec["id"] in seen:
            dups += 1
            seen[rec["id"]] = rec  # 나중 레코드가 덮어씀
        else:
            seen[rec["id"]] = rec
    written = list(seen.values())

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for rec in written:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print("=" * 56)
    print(f"  변환 완료: {args.input}  →  {args.output}")
    print("=" * 56)
    print(f"  원본 {len(rows)}건 중")
    print(f"   ✅ 저장   : {len(written)}건")
    print(f"   🔁 중복제거: {dups}건 (같은 id는 마지막 것만 유지)")
    print(f"   ⚠️ 건너뜀 : {len(skipped)}건 (아래 사유)")
    for lineno, probs, name in skipped[:30]:
        print(f"       - {lineno}행 '{name}': {', '.join(probs)}")
    if len(skipped) > 30:
        print(f"       ... 외 {len(skipped) - 30}건")
    print("-" * 56)
    print("  다음 단계: 서버에서  POST /api/rag/reload  호출 → 즉시 반영")
    return 0 if written else 1


# ==================== 명령: validate ====================

def cmd_validate(args):
    total, ok, bad = 0, 0, 0
    ids = {}
    for path in args.inputs:
        with open(path, "r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith("//"):
                    continue
                total += 1
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError as e:
                    bad += 1
                    print(f"  ❌ {os.path.basename(path)}:{lineno} JSON 오류 - {e}")
                    continue
                problems = _validate(rec)
                rid = rec.get("id", "")
                if rid in ids:
                    problems.append(f"id 중복 (앞서 {ids[rid]} 에 존재)")
                else:
                    ids[rid] = f"{os.path.basename(path)}:{lineno}"
                if problems:
                    bad += 1
                    print(f"  ⚠️ {os.path.basename(path)}:{lineno} '{rec.get('drug_name','')}' - {', '.join(problems)}")
                else:
                    ok += 1
    print("=" * 56)
    print(f"  검증 결과: 총 {total}건 / 정상 {ok} / 문제 {bad}")
    print("=" * 56)
    return 0 if bad == 0 else 1


# ==================== 명령: merge ====================

def cmd_merge(args):
    seen = {}
    dups = 0
    for path in args.inputs:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("//"):
                    continue
                rec = json.loads(line)
                rec = _finalize(rec)
                if rec["id"] in seen:
                    dups += 1
                seen[rec["id"]] = rec
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for rec in seen.values():
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"  병합 완료 → {args.output} : {len(seen)}건 (중복 {dups}건 제거)")
    return 0


# ==================== 명령: fetch-pills (낱알식별 전체 색인 다운로드) ====================

def cmd_fetch_pills(args):
    """식약처 낱알식별정보 전체를 내려받아 '생김새 역검색용' 로컬 색인(jsonl)을 만든다."""
    try:
        import httpx
    except ImportError:
        print("httpx 가 필요합니다. (가상환경 python 으로 실행하세요)")
        return 1

    key = args.key or os.getenv("DATA_GO_KR_API_KEY") or os.getenv("DRUG_EASY_API_KEY", "")
    if not key:
        # backend/.env 에서 키 읽기 시도
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
        if os.path.exists(env_path):
            with open(env_path, encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith(("DATA_GO_KR_API_KEY", "DRUG_EASY_API_KEY")) and "=" in line:
                        key = line.split("=", 1)[1].strip()
                        break
    if not key:
        print("인증키가 없습니다. --key 로 전달하거나 .env 에 DRUG_EASY_API_KEY 를 설정하세요.")
        return 1

    url = "https://apis.data.go.kr/1471000/MdcinGrnIdntfcInfoService03/getMdcinGrnIdntfcInfoList03"
    # 응답 UPPER_SNAKE 필드 → 색인 표준 필드
    def norm(it):
        colors = [c for c in (it.get("COLOR_CLASS1", ""), it.get("COLOR_CLASS2", "")) if c]
        return {
            "item_name": it.get("ITEM_NAME", ""), "item_seq": it.get("ITEM_SEQ", ""),
            "company": it.get("ENTP_NAME", ""), "etc_otc": it.get("ETC_OTC_NAME", ""),
            "class_name": it.get("CLASS_NAME", ""), "drug_shape": it.get("DRUG_SHAPE", ""),
            "colors": colors, "chart": it.get("CHART", ""),
            "print_front": it.get("PRINT_FRONT", ""), "print_back": it.get("PRINT_BACK", ""),
            "line_front": it.get("LINE_FRONT", ""), "line_back": it.get("LINE_BACK", ""),
            "size_long": it.get("LENG_LONG", ""), "form_name": it.get("FORM_CODE_NAME", ""),
            "mark_front": it.get("MARK_CODE_FRONT_ANAL", ""), "mark_back": it.get("MARK_CODE_BACK_ANAL", ""),
            "image_url": it.get("ITEM_IMAGE", ""),
        }

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    rows_per = 100
    page = 1
    total = None
    written = 0
    with open(args.output, "w", encoding="utf-8") as out:
        with httpx.Client(timeout=30) as client:
            while True:
                params = {"serviceKey": key, "type": "json", "numOfRows": rows_per, "pageNo": page}
                try:
                    r = client.get(url, params=params)
                    data = r.json()
                except Exception as e:
                    print(f"  {page}페이지 조회 실패: {e} (재시도 없이 중단)")
                    break
                body = data.get("body", {}) or {}
                if total is None:
                    total = int(body.get("totalCount", 0) or 0)
                    print(f"  전체 {total}건 다운로드 시작 (페이지당 {rows_per}건)")
                items = body.get("items", []) or []
                if isinstance(items, dict):
                    items = [items]
                if not items:
                    break
                for it in items:
                    it = it.get("item", it) if isinstance(it, dict) else it
                    out.write(json.dumps(norm(it), ensure_ascii=False) + "\n")
                    written += 1
                if args.max_pages and page >= args.max_pages:
                    print(f"  (--max-pages={args.max_pages} 도달, 조기 종료)")
                    break
                if total and written >= total:
                    break
                page += 1
                if page % 10 == 0:
                    print(f"    ... {written}건 진행중")
    print("=" * 56)
    print(f"  낱알 색인 저장 완료 → {args.output} : {written}건")
    print("  서버에서 생김새 역검색(/api/drug-info/identify)이 활성화됩니다.")
    print("=" * 56)
    return 0


def main():
    p = argparse.ArgumentParser(description="손주약방 RAG 의약품 데이터 전처리 도구")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("convert", help="원본(csv/json/jsonl/xml) → 표준 JSONL")
    c.add_argument("input")
    c.add_argument("-o", "--output", required=True)
    c.set_defaults(func=cmd_convert)

    v = sub.add_parser("validate", help="표준 JSONL 검증")
    v.add_argument("inputs", nargs="+")
    v.set_defaults(func=cmd_validate)

    m = sub.add_parser("merge", help="여러 JSONL 병합 + 중복제거")
    m.add_argument("inputs", nargs="+")
    m.add_argument("-o", "--output", required=True)
    m.set_defaults(func=cmd_merge)

    fp = sub.add_parser("fetch-pills", help="식약처 낱알식별 전체 → 생김새 역검색용 로컬 색인")
    fp.add_argument("-o", "--output", default="data/pill_identity.jsonl")
    fp.add_argument("--key", default="", help="data.go.kr 인증키(생략 시 .env 에서 읽음)")
    fp.add_argument("--max-pages", type=int, default=0, help="테스트용 페이지 제한(0=전체)")
    fp.set_defaults(func=cmd_fetch_pills)

    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
