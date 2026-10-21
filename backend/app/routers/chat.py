"""Claude/GPT + RAG 기반 건강 상담 챗봇 - 복약·질환 상담, 정서지원, 장기 기억

상담 엔진 우선순위: Anthropic Claude → OpenAI GPT → 규칙기반 데모.
ANTHROPIC_API_KEY 가 설정되면 Claude를 1순위로 사용합니다.
"""
import re
import random
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from openai import OpenAI
from app.database import get_db
from app.models import ChatMessage, Medication, HealthRecord, User, ChronicDisease
from app.config import OPENAI_API_KEY, ANTHROPIC_API_KEY, ANTHROPIC_MODEL
from app.rag_engine import get_rag_context
from app.interaction_engine import check_interaction, classify, CLASS_KEYWORDS

router = APIRouter()
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

try:
    from anthropic import Anthropic
    anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None
except Exception:
    anthropic_client = None

SYSTEM_PROMPT = """당신은 '손주약방'의 AI 건강 도우미입니다. 어르신의 건강 관리를 돕는 친근한 손주 역할을 합니다.

핵심 원칙:
1. 쉬운 말로 설명합니다. 의학 용어는 괄호 안에 쉬운 설명을 붙입니다.
2. 짧고 명확하게 답합니다. 한 번에 3문장 이내로 핵심만 전달합니다.
3. 항상 따뜻하고 존중하는 어조를 사용합니다.
4. 의료적 판단이나 처방은 하지 않습니다. "의사 선생님과 상담하세요"로 안내합니다.
5. 위급한 증상(흉통, 호흡곤란, 편마비, 의식저하)이 감지되면 즉시 119 안내합니다.
6. 복약 정보는 DUR 데이터 기반으로만 안내하며, 추측하지 않습니다.

대화 방식(매일의 건강 돌봄):
- 식사·복약 여부를 다정하게 확인하고, 잘하신 점은 구체적으로 칭찬합니다.
- "평소와 달라진 점은 없으세요?"처럼 새 증상을 먼저 여쭙습니다.
- 새 증상이 나오면 ①언제부터·갑자기인지 ②함께 나타나는 위험 신호(어지럼·갑작스런 난청·마비 등)를 한두 가지만 확인한 뒤, 과하게 겁주지 않고 필요한 진료과를 안내합니다.
- 어르신이 '새로 산/드시려는 약·영양제·건강식품'을 언급하면, 먼저 기존 복용약과 기저질환(예: 심방세동)을 고려해 함께 드셔도 되는지 확인해 드리겠다고 말하고, 제품 이름이나 포장 사진을 보여달라고 요청합니다. 혼자 추측해 안전하다/위험하다 단정하지 않습니다.
- 병용 확인 결과가 아래 [병용확인 결과]로 주어지면, 그 내용만 근거로 '무엇이·왜·어떻게'를 쉬운 말로 전하고 위험도(🔴/🟡/🟢)를 함께 알려줍니다. 처방받아 드시던 약을 임의로 끊게 하지 않습니다.

면책: 모든 답변 끝에 "※ 이 정보는 참고용이며, 정확한 판단은 의료진과 상담하세요."를 포함합니다.

사용자 정보:
{user_context}
"""


class ChatRequest(BaseModel):
    user_id: int
    message: str
    image_base64: str = ""  # Multimodal: 이미지 동시 입력 (optional)


class ChatResponse(BaseModel):
    reply: str
    urgency: str = "normal"
    image_analysis: str = ""  # 이미지 분석 결과 (있을 경우)
    engine: str = ""  # 응답 생성 엔진: claude | gpt | demo
    interaction: Optional[dict] = None  # 병용확인 결과(새 제품 vs 기존약). 있으면 프론트가 카드로 렌더


@router.post("/send", response_model=ChatResponse)
def send_message(request: ChatRequest, db: Session = Depends(get_db)):
    """건강 상담 메시지 전송"""
    # 사용자 컨텍스트 구성
    user = db.query(User).filter(User.id == request.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

    medications = (
        db.query(Medication)
        .filter(Medication.user_id == request.user_id, Medication.is_active == True)
        .all()
    )
    med_list = ", ".join([f"{m.name}({m.category})" for m in medications]) or "없음"

    conditions = [
        d.disease_name
        for d in db.query(ChronicDisease).filter(ChronicDisease.user_id == request.user_id).all()
        if d.disease_name
    ]
    cond_list = ", ".join(conditions) or "없음"

    user_context = f"""
이름: {user.name}
생년월일: {user.birth_date}
현재 복용약: {med_list}
앓고 계신 질환(기저질환): {cond_list}
"""

    # 병용확인: 어르신이 '새 약·영양제를 함께 먹어도 되는지' 물으면,
    # 기존 복용약 + 기저질환과 비교해 실제 상호작용을 점검하거나, 제품 확인을 요청한다.
    interaction_result, interaction_context, demo_interaction_text = _prepare_interaction(
        request.message, medications, conditions
    )

    # RAG: 질문 관련 의약학 지식 검색
    rag_context = get_rag_context(request.message)

    # 장기 기억: 최근 대화 요약 (최근 50개에서 핵심 추출)
    long_term_memory = _get_long_term_memory(request.user_id, db)

    # 최근 대화 히스토리 (최근 10개)
    history = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == request.user_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(10)
        .all()
    )
    history.reverse()

    system_content = (
        SYSTEM_PROMPT.format(user_context=user_context)
        + rag_context + long_term_memory + interaction_context
    )
    history_msgs = [{"role": msg.role, "content": msg.content} for msg in history]

    # 상담 응답 생성: Claude → GPT → 규칙기반 데모 순 폴백
    reply, engine = _generate_reply(
        system_content, history_msgs, request.message, request.image_base64,
        user.name, med_list, demo_interaction_text,
    )

    # 위급 상황 감지
    urgency = "normal"
    emergency_keywords = ["흉통", "가슴 통증", "숨을 못", "호흡곤란", "팔다리 마비", "편마비", "의식", "쓰러"]
    if any(kw in request.message for kw in emergency_keywords):
        urgency = "emergency"
        reply = "⚠️ 위급 상황이 의심됩니다. 즉시 119에 전화하시거나, 보호자에게 연락해 주세요.\n\n" + reply

    # 대화 저장
    db.add(ChatMessage(user_id=request.user_id, role="user", content=request.message))
    db.add(ChatMessage(user_id=request.user_id, role="assistant", content=reply))
    db.commit()

    return ChatResponse(reply=reply, urgency=urgency, engine=engine, interaction=interaction_result)


@router.get("/history/{user_id}")
def get_chat_history(user_id: int, limit: int = 20, db: Session = Depends(get_db)):
    """대화 히스토리 조회"""
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
        .all()
    )
    messages.reverse()
    return {
        "messages": [
            {"role": m.role, "content": m.content, "created_at": str(m.created_at)}
            for m in messages
        ]
    }


# ==================== 병용확인(새 제품 vs 기존약) 챗봇 연동 ====================
# 어르신이 "새로 산 약·영양제를 지금 약과 함께 먹어도 되나요?"라고 물으면,
# 제품을 특정할 수 있으면 interaction_engine 으로 실제 점검을, 아니면 제품 확인을 요청한다.

_CHECK_VERBS = ["먹어도 되", "먹어도 돼", "복용해도 되", "복용해도 돼", "드셔도 되", "드셔도 돼",
                "같이 먹", "함께 먹", "같이 복용", "함께 복용", "같이 드셔", "함께 드셔",
                "같이 드시", "함께 드시", "병용", "괜찮을까", "괜찮은지", "같이 드셔도", "함께 드셔도"]
_PRODUCT_HINTS = ["샀", "사 왔", "사왔", "구입", "새로 산", "새로산", "새 약", "새로운 약",
                  "영양제", "건강식품", "건강기능식품", "보조제", "약을 하나", "약을 샀",
                  "약국에서", "인터넷에서", "주문"]


def _guess_product_name(message: str) -> str:
    """메시지에서 병용확인 대상 제품의 표시용 이름을 추정한다(없으면 일반 명칭)."""
    norm = re.sub(r"\s+", "", message).lower()
    for kws in CLASS_KEYWORDS.values():
        for kw in kws:
            if re.sub(r"\s+", "", kw).lower() in norm:
                return kw
    return "새로 드시려는 제품"


def _summarize_interaction(result: dict) -> str:
    """병용확인 결과를 LLM system 컨텍스트용으로 간결히 요약한다."""
    lines = [result.get("summary", "")]
    for f in result.get("findings", []):
        lines.append(
            f"- {f['icon']} [{f['label']}] {f['title']}: "
            f"무엇={f['what']} / 왜={f['why']} / 어떻게={f['how']}"
        )
    if result.get("safety_notice"):
        lines.append("안전: " + result["safety_notice"])
    return "\n".join(l for l in lines if l)


def _format_interaction_demo(result: dict) -> str:
    """병용확인 결과를 데모 모드 답변 문구로 변환한다(면책문구는 호출부에서 덧붙임)."""
    parts = [result.get("summary", "")]
    findings = result.get("findings", [])
    if not findings:
        parts.append("지금 드시는 약과 함께 복용할 때 특별히 확인된 위험은 없어요. "
                     "그래도 몸에 이상이 느껴지면 약사·의사와 상담하세요.")
    else:
        for f in findings:
            parts.append(
                f"\n{f['icon']} {f['label']} — {f['title']}\n"
                f"· 무엇이: {f['what']}\n· 왜: {f['why']}\n· 어떻게: {f['how']}"
            )
    if result.get("safety_notice"):
        parts.append("\n🛡️ " + result["safety_notice"])
    return "\n".join(parts).strip()


def _prepare_interaction(message: str, medications, conditions):
    """메시지가 '새 제품 병용 여부' 질문이면 상호작용을 점검하거나 제품 확인을 요청한다.

    반환: (interaction_result|None, system_context_str, demo_text_str)
    """
    has_verb = any(k in message for k in _CHECK_VERBS)
    has_hint = any(k in message for k in _PRODUCT_HINTS)
    detected = classify([message], message)
    cond_phrase = ", ".join(conditions) if conditions else ""

    # (A) 제품을 특정할 수 있음 → 실제 병용확인 수행
    if detected and (has_verb or has_hint):
        current = [{"name": m.name, "ingredients": [m.ingredient] if m.ingredient else []}
                   for m in medications]
        result = check_interaction(
            new_product={"name": _guess_product_name(message), "ingredients": [message]},
            current_medications=current,
            conditions=list(conditions),
        )
        ctx = ("\n\n[병용확인 결과] (아래 내용만 근거로, 무엇이·왜·어떻게를 쉬운 말로 전하고 "
               "위험도 아이콘 🔴/🟡/🟢을 함께 알려주세요)\n" + _summarize_interaction(result))
        return result, ctx, _format_interaction_demo(result)

    # (B) 병용 여부를 물었지만 제품을 특정할 수 없음 → 제품 이름/사진 요청
    if has_verb and has_hint:
        if cond_phrase:
            offer = (f"잘 말씀해 주셨어요! 어르신은 평소 {cond_phrase} 관련 약을 드시고 계시니, "
                     "새로 사신 약·영양제를 함께 드셔도 되는지 기존 복용약과 꼼꼼히 비교해서 확인해 드릴게요. "
                     "제품 이름이나 포장 사진을 보여주시겠어요?")
        else:
            offer = ("잘 말씀해 주셨어요! 새로 사신 약·영양제를 지금 드시는 약과 함께 드셔도 되는지 "
                     "확인해 드릴게요. 제품 이름이나 포장 사진을 보여주시겠어요?")
        ctx = ("\n\n[병용확인 안내] 사용자가 새로 산 약/영양제를 기존 약과 함께 먹어도 되는지 물었으나 "
               "제품을 특정할 수 없습니다. 안전하다/위험하다 단정하지 말고, 기존 복용약과 기저질환"
               f"({cond_phrase or '있다면 그 질환'})을 함께 고려해 확인해 주겠다고 안내한 뒤 "
               "제품 이름이나 포장 사진을 요청하세요.")
        return None, ctx, offer

    return None, "", ""


def _generate_reply(system_content, history_msgs, user_message, image_base64,
                    user_name, med_list, demo_interaction_text=""):
    """상담 응답을 생성한다. Claude → OpenAI GPT → 규칙기반 데모 순으로 폴백.

    반환: (reply_text, engine_name)
    """
    # 1순위: Anthropic Claude
    if anthropic_client is not None:
        try:
            return _claude_reply(system_content, history_msgs, user_message, image_base64), "claude"
        except Exception as e:
            print(f"[Chat] Claude 호출 실패({type(e).__name__}) → GPT로 폴백")

    # 2순위: OpenAI GPT
    if client is not None:
        try:
            return _openai_reply(system_content, history_msgs, user_message, image_base64), "gpt"
        except Exception as e:
            print(f"[Chat] GPT 호출 실패({type(e).__name__}) → 규칙기반 응답으로 대체")

    # 3순위: 규칙 기반 데모 (병용확인 안내가 있으면 그것을 우선 전달)
    return _demo_reply(user_message, user_name, med_list, demo_interaction_text), "demo"


def _claude_reply(system_content, history_msgs, user_message, image_base64=""):
    """Anthropic Claude 메시지 API 호출 (system 은 별도 파라미터, 이미지 지원)."""
    messages = [{"role": m["role"], "content": m["content"]} for m in history_msgs]
    if image_base64:
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": user_message or "이 이미지를 분석해주세요."},
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_base64}},
            ],
        })
    else:
        messages.append({"role": "user", "content": user_message})

    resp = anthropic_client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=500,
        temperature=0.7,
        system=system_content,
        messages=messages,
    )
    # content 블록들에서 텍스트만 이어붙임
    parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
    return "".join(parts).strip()


def _openai_reply(system_content, history_msgs, user_message, image_base64=""):
    """OpenAI GPT 호출 (멀티모달 지원)."""
    messages = [{"role": "system", "content": system_content}]
    messages.extend(history_msgs)
    if image_base64:
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": user_message or "이 이미지를 분석해주세요."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
            ],
        })
    else:
        messages.append({"role": "user", "content": user_message})

    response = client.chat.completions.create(
        model="gpt-4o-mini", messages=messages, temperature=0.7, max_tokens=500,
    )
    return response.choices[0].message.content


DISCLAIMER = "\n\n※ 이 정보는 참고용이며, 정확한 판단은 의료진과 상담하세요."

# 증상/키워드 기반 데모 응답 규칙 (LLM 미연결·크레딧 소진 시 사용)
# 각 규칙 = (키워드 목록, 본문, urgent)  — urgent=True면 공감/후속질문 덧붙이지 않고 행동안내를 그대로 전달.
# 위에 있는 규칙이 먼저 매칭되므로, '응급·급성 외상'을 '만성·일반 증상'보다 위에 둔다.
_DEMO_RULES = [
    # ── 응급 ──────────────────────────────────────────────
    (["흉통", "가슴 통증", "가슴이 아", "숨을 못", "숨이 차", "호흡곤란", "마비", "편마비",
      "쓰러", "의식", "말이 어눌", "한쪽", "경련"],
     "말씀하신 증상은 뇌졸중·심장질환 같은 응급 상황일 수 있어요. 지금 바로 119에 전화하시거나 곁에 계신 분께 도움을 요청하세요. 혼자 참고 기다리지 마시고, 증상이 처음 나타난 시각을 기억해 두시면 진료에 큰 도움이 됩니다.", True),
    # ── 급성 외상(부상) ───────────────────────────────────
    (["부러", "골절", "금이 갔", "금 갔", "뼈가", "뼈를", "으스러"],
     "다치셨다니 많이 아프고 놀라셨겠어요. 뼈를 다치셨을 수 있으니, 그 부위를 억지로 움직이거나 누르지 마시고 지금 자세 그대로 두세요. 부은 곳에는 수건에 싼 얼음으로 냉찜질을 해주시고(따뜻한 찜질·파스·스트레칭은 지금은 안 돼요), 다친 다리에는 체중을 싣지 마세요. 뼈가 어긋나 보이거나 통증이 심하거나 전혀 움직일 수 없으면 바로 119나 응급실로 가시고, 그렇지 않더라도 가능한 빨리 정형외과 진료를 받으세요. 지금 혼자 계신가요, 아니면 곁에 도와주실 분이 계신가요?", True),
    (["삐끗", "삐었", "삐어", "접질", "접지르", "염좌", "접질렀"],
     "발이나 관절을 삐끗하셨군요. 많이 아프시죠. 먼저 그 부위를 쉬게 하시고(안정), 수건에 싼 얼음으로 15~20분 냉찜질을 하신 뒤, 붕대로 가볍게 감아 압박하고 다친 곳을 심장보다 높게 올려두시면 붓기가 덜해요. 처음 48시간은 따뜻한 찜질과 술은 피하세요. 디디기 힘들 만큼 아프거나 붓기가 심하면 골절일 수 있으니 정형외과 진료를 받아보세요.", True),
    (["베였", "베어", "베이", "찢어", "피가 나", "피가 멈", "출혈", "상처가"],
     "피가 나는 상처가 있으시군요. 깨끗한 수건이나 거즈로 상처를 직접 5~10분 꾹 눌러 지혈해 주세요. 상처가 깊거나, 피가 잘 멈추지 않거나, 벌어져 있으면 꿰매야 할 수 있으니 바로 병원(응급실)에 가세요. 녹슨 물건에 베이셨다면 파상풍 예방도 확인이 필요해요.", True),
    (["화상", "데였", "데임", "덴 ", "끓는", "뜨거운 물", "불에 데"],
     "화상을 입으셨군요. 바로 흐르는 미지근한 수돗물에 15~20분 정도 식혀 주세요. 물집은 터뜨리지 마시고, 된장·치약·기름 같은 건 절대 바르지 마세요. 화상 범위가 손바닥보다 넓거나 얼굴·손·관절 부위거나 물집이 심하면 병원 진료가 꼭 필요해요.", True),
    (["넘어졌", "넘어져", "낙상", "미끄러", "자빠", "엎어졌"],
     "넘어지셨다니 걱정돼요. 먼저 어디를 부딪히셨는지 살펴봐 주세요. 특히 머리를 부딪혔거나 잠깐이라도 정신을 잃으셨거나 심하게 아픈 곳이 있으면 바로 병원에 가셔야 해요. 당장 괜찮아 보여도 어르신은 하루 이틀 뒤에 통증이 나타날 수 있으니 무리하지 마시고, 넘어지신 일을 보호자에게 꼭 알려주세요.", True),
    # ── 만성·일반 증상 ────────────────────────────────────
    (["혈압", "고혈압"],
     "혈압이 걱정되시는군요. 편안히 앉아 5분 쉬신 뒤 다시 재보세요. 수축기(위 숫자)가 140 이상으로 계속되면 병원 진료를 받으시는 게 좋아요. 국물·젓갈 같은 짠 음식은 줄이시고, 혈압약은 매일 같은 시간에 거르지 않고 드시는 게 가장 중요해요.", False),
    (["혈당", "당뇨", "당뇨병"],
     "혈당 관리가 신경 쓰이시죠. 식후 2시간 혈당은 180 아래로 유지하는 게 좋아요. 단 음식과 흰쌀밥·떡은 조금 줄이시고, 식사 뒤 10~15분 가벼운 산책을 하시면 혈당을 낮추는 데 도움이 됩니다. 손발 저림이나 상처가 잘 안 아물면 꼭 말씀해 주세요.", False),
    (["두통", "머리", "어지", "현기", "띵"],
     "머리가 아프고 어지러우시군요. 우선 물을 한 잔 드시고 밝은 빛을 피해 편히 쉬어 보세요. 혈압을 한 번 재보시는 것도 좋아요. 다만 갑자기 심하게 아프거나, 말이 어눌해지거나, 한쪽 팔다리에 힘이 빠지면 뇌졸중일 수 있으니 바로 병원에 가셔야 해요.", False),
    (["잠", "불면", "수면", "잠이"],
     "잠이 잘 안 오시는군요. 많이 피곤하시겠어요. 주무시기 2시간 전부터는 밝은 화면과 커피·녹차를 피하시고, 따뜻한 물로 손발을 데우면 도움이 돼요. 낮잠은 30분 이내로 줄이시고, 매일 비슷한 시간에 일어나시면 밤잠이 더 깊어집니다.", False),
    (["소화", "속이", "위가", "체했", "속쓰", "배가", "더부룩", "메스"],
     "속이 불편하시군요. 기름지고 맵고 자극적인 음식은 피하시고 미지근한 물을 자주 드셔 보세요. 식사는 한 번에 많이 드시기보다 조금씩 자주 나눠 드시는 게 좋아요. 검은 변을 보시거나 통증이 심하거나 체중이 자꾸 줄면 진료를 받아보세요.", False),
    (["관절", "무릎", "허리", "다리", "근육", "쑤", "결려"],
     "관절이 쑤시고 불편하시군요. 무리한 활동은 피하시고 따뜻하게 찜질해 주세요. 평소에는 가벼운 스트레칭과 천천히 걷기가 도움이 되지만, 부딪히거나 삐끗한 적 없이 아프시다면 무리하지 마세요. 붓거나 열이 나거나 밤에 더 아프면 정형외과 진료를 권해요.", False),
    (["귀에서 소리", "귀울림", "이명", "삐 소리", "삐소리", "윙"],
     "귀에서 소리가 나서 불편하셨겠어요. 언제부터 그러셨는지, 그리고 어지럽거나 갑자기 잘 안 들리는 증상은 없는지 살펴봐 주세요. 귀울림(이명)은 원인이 다양하니 이비인후과 진료로 한 번 확인해 보시는 게 좋아요.", False),
    (["기침", "가래", "콧물", "감기", "열이", "오한", "목이"],
     "감기 기운이 있으시군요. 따뜻한 물을 자주 드시고 푹 쉬시는 게 가장 좋아요. 방 안 공기가 건조하지 않게 해주시고요. 다만 열이 많이 나거나 숨이 차거나 가래에 피가 섞이거나 3~4일이 지나도 나아지지 않으면 꼭 병원 진료를 받으세요.", False),
    (["약", "복용", "복약", "먹는 약", "약을"],
     "현재 드시는 약({med_list_placeholder})은 정해진 시간에 거르지 않고 드시는 게 가장 중요해요. 자몽주스나 음주는 약효에 영향을 줄 수 있으니 피하시고, 깜빡 잊으셨다면 생각난 즉시 한 번만 드시되 다음 약 시간이 가까우면 건너뛰세요. 궁금한 점은 약사님께 확인하시면 돼요.", False),
    (["우울", "외로", "슬프", "불안", "힘들", "눈물", "죽고"],
     "많이 힘드셨겠어요. 그런 마음이 드는 건 결코 이상한 일이 아니에요. 가까운 분과 이야기를 나누거나 잠깐 바깥 공기를 쐬어 보시는 건 어떨까요? 제가 늘 곁에서 어르신 편이 되어 드릴게요. 많이 힘들고 안 좋은 생각이 드실 땐 정신건강상담전화 1577-0199에 전화해 보셔도 좋아요.", False),
]

# 비응급 상담 끝에 번갈아 덧붙이는 따뜻한 후속 질문(같은 질문 반복을 덜어 자연스럽게 만든다)
_DEMO_FOLLOWUPS = [
    "혹시 언제부터 그러셨는지 조금 더 말씀해 주시겠어요?",
    "다른 불편한 곳은 없으신지도 알려주세요.",
    "지금은 좀 어떠세요? 많이 불편하신가요?",
    "제가 더 도와드릴 일이 있으면 편하게 말씀해 주세요.",
]


def _demo_reply(message: str, user_name: str, med_list: str, interaction_text: str = "") -> str:
    """LLM 연결이 없을 때 사용하는 규칙 기반 상담 응답 (데모 모드).

    - 응급·급성 외상은 행동안내를 그대로 전달하고,
    - 일반 상담은 공감·안내에 따뜻한 후속 질문을 덧붙여 반복감을 줄인다.
    """
    # 병용확인 안내(실제 상호작용 결과 또는 제품 확인 요청)가 있으면 최우선으로 전달
    if interaction_text:
        return interaction_text + DISCLAIMER

    name = user_name or "어르신"
    for keywords, body, urgent in _DEMO_RULES:
        if any(kw in message for kw in keywords):
            body = body.replace("{med_list_placeholder}", med_list)
            if urgent:
                return body + DISCLAIMER
            # 비응급: 가끔 이름을 부르고, 후속 질문을 덧붙여 대화처럼 자연스럽게
            opener = f"{name}, " if random.random() < 0.5 else ""
            return f"{opener}{body} {random.choice(_DEMO_FOLLOWUPS)}" + DISCLAIMER

    # 매칭 없음: 공감 + 구체적인 되물음
    return (
        f"{name}, 말씀 잘 들었어요. 어디가 어떻게 불편하신지 — 언제부터인지, 어느 정도인지 "
        "조금만 더 자세히 들려주시면 더 잘 도와드릴 수 있어요. 증상이 갑자기 심해지거나 오래 가면 "
        "꼭 병원 진료를 받으세요. " + random.choice(_DEMO_FOLLOWUPS) + DISCLAIMER
    )


def _get_long_term_memory(user_id: int, db: Session) -> str:
    """장기 기억: 이전 대화에서 핵심 정보를 추출하여 컨텍스트로 제공
    
    최근 50개 대화에서 증상, 건강 변화, 감정 상태 등 핵심만 요약합니다.
    이를 통해 "지난주에 어지럽다고 하셨는데 좋아지셨어요?" 같은 연속성 있는 대화가 가능합니다.
    """
    # 최근 50개 대화 조회 (최근 10개는 이미 히스토리로 사용하므로 11~50번째)
    older_messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.created_at.desc())
        .offset(10)
        .limit(40)
        .all()
    )

    if not older_messages:
        return ""

    # 핵심 키워드가 포함된 대화만 추출
    health_keywords = ["아프", "통증", "어지러", "혈압", "혈당", "약", "병원", "잠", "식사", "운동", "기분", "우울", "불안"]
    relevant = []
    for msg in older_messages:
        if msg.role == "user" and any(kw in msg.content for kw in health_keywords):
            relevant.append(f"[{str(msg.created_at)[:10]}] {msg.content[:100]}")

    if not relevant:
        return ""

    memory_text = "\n\n[장기 기억 - 이전 대화에서 언급된 건강 관련 내용]\n"
    memory_text += "\n".join(relevant[:5])  # 최대 5개만
    return memory_text
