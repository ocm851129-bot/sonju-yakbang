from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine, Base, SessionLocal
from app.routers import auth, voice, ocr, medications, chat, dur, health, guardian, ad_filter, character, wearable, digital_twin, wellness
from app.fhir import to_fhir_patient, to_fhir_medication_statement, to_fhir_observation, to_fhir_bundle
from app.agent_scheduler import init_scheduler
from app.rag_engine import initialize_knowledge_base

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="손주약방 API",
    description="어르신 건강관리 플랫폼 - 문진 생성 모델 기반 건강관리 서비스",
    version="1.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router, prefix="/api/auth", tags=["인증"])
app.include_router(voice.router, prefix="/api/voice", tags=["음성 문진"])
app.include_router(ocr.router, prefix="/api/ocr", tags=["처방전 OCR"])
app.include_router(medications.router, prefix="/api/medications", tags=["복약 관리"])
app.include_router(chat.router, prefix="/api/chat", tags=["건강 상담"])
app.include_router(dur.router, prefix="/api/dur", tags=["DUR 분석"])
app.include_router(health.router, prefix="/api/health", tags=["건강 관리"])
app.include_router(guardian.router, prefix="/api/guardian", tags=["보호자 연동"])
app.include_router(ad_filter.router, prefix="/api/ad-filter", tags=["허위광고 필터링"])
app.include_router(character.router, prefix="/api/character", tags=["AI 캐릭터"])
app.include_router(wearable.router, prefix="/api/wearable", tags=["웨어러블 IoT"])
app.include_router(digital_twin.router, prefix="/api/twin", tags=["디지털 트윈"])
app.include_router(wellness.router, prefix="/api/wellness", tags=["건강정보 콘텐츠"])


# Agentic AI 스케줄러 + RAG 지식 베이스 초기화 + 데모 데이터
@app.on_event("startup")
def startup_event():
    init_scheduler()
    initialize_knowledge_base()
    _seed_demo_data()


def _seed_demo_data():
    """데모용 기본 사용자 및 데이터 초기화 (DB에 user_id=1이 없을 때만 생성)"""
    from app.database import SessionLocal
    from app.models import User, Medication, ChronicDisease
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.id == 1).first()
        if existing:
            return  # 이미 있으면 스킵

        # 데모 사용자 생성
        demo_user = User(
            id=1,
            name="홍길동",
            phone="010-1234-5678",
            birth_date="1955-03-15",
            gender="남",
            role="patient",
        )
        db.add(demo_user)
        db.flush()

        # 데모 복용약 등록
        meds = [
            Medication(
                user_id=1,
                name="메트포르민정 500mg",
                ingredient="메트포르민",
                dosage="1정",
                frequency="1일 2회 아침·저녁 식후",
                category="prescription",
                start_date="2025-06-21",
                end_date="2025-07-05",
                prescribing_hospital="서울내과의원",
                is_active=True,
            ),
            Medication(
                user_id=1,
                name="심바스타틴정 20mg",
                ingredient="심바스타틴",
                dosage="1정",
                frequency="1일 1회 저녁 식후",
                category="prescription",
                start_date="2025-06-21",
                end_date="2025-07-05",
                prescribing_hospital="서울내과의원",
                is_active=True,
            ),
        ]
        db.add_all(meds)

        # 데모 만성질환 등록
        diseases = [
            ChronicDisease(user_id=1, disease_name="고혈압", status="monitoring"),
            ChronicDisease(user_id=1, disease_name="당뇨", status="monitoring"),
            ChronicDisease(user_id=1, disease_name="고지혈증", status="stable"),
        ]
        db.add_all(diseases)

        db.commit()
        print("[Startup] 데모 사용자 및 데이터 초기화 완료")
    except Exception as e:
        db.rollback()
        print(f"[Startup] 데모 데이터 초기화 실패: {e}")
    finally:
        db.close()


@app.get("/")
def root():
    return {
        "service": "손주약방",
        "description": "어르신 건강관리 AI 플랫폼",
        "version": "1.0.0",
        "tech_stack": {
            "frontend": "PWA (Progressive Web App)",
            "backend": "FastAPI",
            "database": "SQLite (MVP) / PostgreSQL (production)",
            "ai": "OpenAI (Whisper STT, GPT-4o Vision OCR, GPT-4o-mini LLM + 사용자 컨텍스트 RAG)",
            "ocr": "Google Vision API / CLOVA OCR + GPT Vision 구조화",
            "dur": "공공데이터포털 API + Local Rule Engine + AI 보조",
            "medical_standard": "HL7-FHIR R4 호환",
            "realtime": "WebSocket (보호자 알림)",
        },
        "features": [
            "음성 문진 (STT)",
            "처방전 OCR 인식 (Google Vision / CLOVA + GPT)",
            "복약 관리 및 알림",
            "DUR 병용금기 분석 (공공API + Rule + AI)",
            "AI 건강 상담 챗봇",
            "보호자 실시간 WebSocket 연동",
            "만성질환 관리",
            "건강기능식품 추천",
            "고령자 친화 UI (PWA)",
            "AI 캐릭터 정서지원",
        ],
    }


# ==================== HL7-FHIR 호환 엔드포인트 ====================
from fastapi import Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Medication, HealthRecord, DURAlert


@app.get("/fhir/Patient/{user_id}", tags=["FHIR"])
def get_fhir_patient(user_id: int, db: Session = Depends(get_db)):
    """HL7-FHIR Patient 리소스 내보내기"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"error": "Patient not found"}
    return to_fhir_patient(user)


@app.get("/fhir/MedicationStatement/{user_id}", tags=["FHIR"])
def get_fhir_medications(user_id: int, db: Session = Depends(get_db)):
    """HL7-FHIR MedicationStatement Bundle 내보내기"""
    meds = db.query(Medication).filter(
        Medication.user_id == user_id, Medication.is_active == True
    ).all()
    resources = [to_fhir_medication_statement(m, user_id) for m in meds]
    return to_fhir_bundle(resources)


@app.get("/fhir/Observation/{user_id}", tags=["FHIR"])
def get_fhir_observations(user_id: int, db: Session = Depends(get_db)):
    """HL7-FHIR Observation Bundle (바이탈 사인) 내보내기"""
    records = db.query(HealthRecord).filter(
        HealthRecord.user_id == user_id,
        HealthRecord.record_type == "vital_sign",
    ).order_by(HealthRecord.created_at.desc()).limit(20).all()
    resources = [to_fhir_observation(r) for r in records]
    return to_fhir_bundle(resources)
