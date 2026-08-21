"""GPT/RAG 기반 건강 상담 챗봇 - 복약·질환 상담, 정서지원, 장기 기억"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from openai import OpenAI
from app.database import get_db
from app.models import ChatMessage, Medication, HealthRecord, User
from app.config import OPENAI_API_KEY
from app.rag_engine import get_rag_context

router = APIRouter()
client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """당신은 '손주약방'의 AI 건강 도우미입니다. 어르신의 건강 관리를 돕는 친근한 손주 역할을 합니다.

핵심 원칙:
1. 쉬운 말로 설명합니다. 의학 용어는 괄호 안에 쉬운 설명을 붙입니다.
2. 짧고 명확하게 답합니다. 한 번에 3문장 이내로 핵심만 전달합니다.
3. 항상 따뜻하고 존중하는 어조를 사용합니다.
4. 의료적 판단이나 처방은 하지 않습니다. "의사 선생님과 상담하세요"로 안내합니다.
5. 위급한 증상(흉통, 호흡곤란, 편마비, 의식저하)이 감지되면 즉시 119 안내합니다.
6. 복약 정보는 DUR 데이터 기반으로만 안내하며, 추측하지 않습니다.

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

    user_context = f"""
이름: {user.name}
생년월일: {user.birth_date}
현재 복용약: {med_list}
"""

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

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(user_context=user_context) + rag_context + long_term_memory}
    ]
    for msg in history:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": request.message})

    # Multimodal: 이미지가 포함된 경우 GPT Vision으로 처리
    image_analysis = ""
    if request.image_base64:
        messages[-1] = {
            "role": "user",
            "content": [
                {"type": "text", "text": request.message or "이 이미지를 분석해주세요."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{request.image_base64}"}},
            ],
        }

    # GPT 호출 (실패 시 규칙 기반 데모 응답으로 자동 대체)
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=500,
        )
        reply = response.choices[0].message.content
    except Exception as e:
        print(f"[Chat Error] GPT 호출 실패({type(e).__name__}) → 규칙기반 응답으로 대체")
        reply = _demo_reply(request.message, user.name, med_list)

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

    return ChatResponse(reply=reply, urgency=urgency)


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


DISCLAIMER = "\n\n※ 이 정보는 참고용이며, 정확한 판단은 의료진과 상담하세요."

# 증상/키워드 기반 데모 응답 규칙 (OpenAI 미연결·크레딧 소진 시 사용)
_DEMO_RULES = [
    (["흉통", "가슴 통증", "숨을 못", "호흡곤란", "마비", "쓰러", "의식"],
     "말씀하신 증상은 응급 상황일 수 있어요. 지금 바로 119에 전화하시거나 가까운 보호자에게 알려 주세요."),
    (["혈압", "고혈압"],
     "혈압이 걱정되시는군요. 편안히 앉아 5분 쉬신 뒤 다시 측정해 보세요. 수축기 140 이상이 계속되면 병원 진료를 받으시는 게 좋아요. 저염식과 규칙적인 약 복용도 중요해요."),
    (["혈당", "당뇨", "당뇨병"],
     "혈당 관리가 신경 쓰이시죠. 식후 2시간 혈당은 180 아래로 유지하는 게 좋아요. 단 음식과 흰쌀밥은 줄이시고, 가벼운 산책이 혈당을 낮추는 데 도움이 됩니다."),
    (["두통", "머리", "어지", "현기"],
     "머리가 아프고 어지러우시군요. 우선 물을 한 잔 드시고 편히 쉬어 보세요. 혈압을 한 번 재보시는 것도 좋아요. 증상이 계속되거나 말이 어눌해지면 바로 병원에 가셔야 해요."),
    (["잠", "불면", "수면"],
     "잠이 잘 안 오시는군요. 주무시기 2시간 전부터는 밝은 화면과 카페인을 피하시고, 따뜻한 물로 손발을 데우면 도움이 돼요. 낮잠은 30분 이내로 줄여 보세요."),
    (["소화", "속", "위", "체", "배"],
     "속이 불편하시군요. 기름지고 자극적인 음식은 피하시고 미지근한 물을 자주 드셔 보세요. 식사는 조금씩 자주 나눠 드시는 게 좋아요. 통증이 심하면 진료를 받으세요."),
    (["관절", "무릎", "허리", "다리", "근육"],
     "관절이 불편하시군요. 무리한 활동은 피하시고 따뜻하게 찜질해 주세요. 가벼운 스트레칭과 걷기는 도움이 되지만, 붓거나 열이 나면 정형외과 진료를 권해요."),
    (["약", "복용", "복약", "먹는"],
     "현재 복용 중인 약({med_list_placeholder})은 정해진 시간에 잊지 말고 드시는 게 가장 중요해요. 자몽주스나 음주는 약효에 영향을 줄 수 있으니 피하시고, 궁금한 점은 약사님께 확인하세요."),
    (["우울", "외로", "슬프", "불안", "힘들"],
     "많이 힘드셨겠어요. 그런 마음이 드는 건 자연스러운 일이에요. 가까운 사람과 이야기를 나누거나 잠깐 산책을 해보시는 건 어떨까요? 제가 늘 곁에서 응원하고 있어요."),
]


def _demo_reply(message: str, user_name: str, med_list: str) -> str:
    """OpenAI 연결이 없을 때 사용하는 규칙 기반 상담 응답 (데모 모드)."""
    for keywords, answer in _DEMO_RULES:
        if any(kw in message for kw in keywords):
            answer = answer.replace("{med_list_placeholder}", med_list)
            return answer + DISCLAIMER
    name = user_name or "어르신"
    return (
        f"{name}, 말씀 잘 들었어요. 어디가 어떻게 불편하신지 조금만 더 자세히 알려주시면 "
        "더 잘 도와드릴 수 있어요. 증상이 심하거나 오래 가면 꼭 병원 진료를 받으세요." + DISCLAIMER
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
