# 손주약방 설계 도면 (Blueprint)

> 고도화(2차 개발) 착수 전 기준 설계도. 현재 코드베이스 기준으로 작성.
> GitHub/VSCode Mermaid 미리보기로 렌더링됩니다.

- 대상: `C:\Users\오창민\Desktop\여성발명\TalkFile_sonju-yakbang\sonju-yakbang`
- 스택: PWA(정적 HTML/CSS/JS) + Capacitor 모바일 / FastAPI(Python) + SQLAlchemy + APScheduler + WebSocket / SQLite(MVP)→PostgreSQL(운영)
- 작성 기준일: 2026-09-07

---

## 1. 시스템 아키텍처 도면

```mermaid
flowchart TB
    subgraph CLIENT["📱 클라이언트 계층"]
        PWA["PWA 웹앱<br/>(Vercel · index.html/app.js)"]
        MOBILE["모바일 앱<br/>(Capacitor · Android/iOS)"]
        SW["Service Worker<br/>(오프라인 DUR · sw.js)"]
    end

    subgraph EDGE["🌐 통신 계층"]
        REST["REST API<br/>/api/*"]
        WS["WebSocket<br/>/api/guardian/ws"]
        FHIREP["FHIR 엔드포인트<br/>/fhir/*"]
    end

    subgraph BACKEND["⚙️ 백엔드 (FastAPI · main.py)"]
        subgraph ROUTERS["라우터"]
            R1["auth 인증"]
            R2["voice 음성문진"]
            R3["ocr 처방전"]
            R4["medications 복약"]
            R5["dur 병용금기"]
            R6["chat AI상담"]
            R7["health 건강관리"]
            R8["guardian 보호자"]
            R9["wellness 건강정보"]
            R10["ad_filter 광고검증"]
            R11["character AI캐릭터"]
            R12["wearable 웨어러블"]
            R13["digital_twin 디지털트윈"]
        end
        subgraph ENGINE["공통 엔진"]
            E1["RAG Engine<br/>rag_engine.py"]
            E2["DUR Rule Engine<br/>dur_database.py"]
            E3["Agent Scheduler<br/>agent_scheduler.py"]
            E4["FHIR Export<br/>fhir.py"]
            E5["Security<br/>security.py"]
        end
    end

    subgraph DATA["🗄️ 데이터 계층"]
        DB[("SQLite / PostgreSQL<br/>models.py")]
    end

    subgraph EXTERNAL["☁️ 외부 연동"]
        X1["OpenAI<br/>Whisper · GPT-4o Vision · GPT-4o-mini"]
        X2["공공데이터포털<br/>DUR API"]
        X3["Google Vision / CLOVA OCR"]
    end

    PWA --> REST
    MOBILE --> REST
    PWA --> WS
    PWA -.캐시.-> SW
    PWA --> FHIREP

    REST --> ROUTERS
    WS --> R8
    FHIREP --> E4

    ROUTERS --> ENGINE
    ROUTERS --> DB
    ENGINE --> DB

    R2 --> X1
    R3 --> X1
    R3 --> X3
    R6 --> X1
    E1 --> X1
    R5 --> X2
    E2 --> X2
```

---

## 2. 화면 흐름 / UI 와이어프레임 (Screen Flow)

```mermaid
flowchart TD
    START(["앱 실행"]) --> HOME

    subgraph BOTTOMNAV["하단 네비게이션 (5탭)"]
        HOME["🏠 홈<br/>건강점수·오늘의 약·AI캐릭터 인사"]
        HEALTH["💚 건강정보<br/>질환/식단/건기식/심신안정"]
        MEDS["💊 복약<br/>처방약·일반약·건기식·DUR"]
        MYSTATUS["📊 내 건강상태<br/>혈압/혈당/체중·7일 차트"]
        CHAT["💬 AI 상담<br/>GPT+RAG 챗봇"]
    end

    HOME <--> HEALTH
    HEALTH <--> MEDS
    MEDS <--> MYSTATUS
    MYSTATUS <--> CHAT

    HOME --> VOICE["🎤 음성 문진<br/>녹음→STT→증상분석"]
    HOME --> OCR["📷 처방전 OCR<br/>촬영→인식→약 등록"]
    HOME --> ADCHECK["🔍 광고 검증<br/>건기식 허위광고 판별"]
    HOME --> PROFILE["👤 프로필<br/>로그인/회원가입/내정보"]

    OCR -->|"약 자동 등록"| MEDS
    VOICE -->|"증상 컨텍스트"| CHAT
    MEDS -->|"병용금기 검사"| MEDS
    PROFILE -->|"로그인"| HOME

    classDef nav fill:#e8f5e9,stroke:#2e7d32,color:#1b5e20;
    classDef sub fill:#e3f2fd,stroke:#1565c0,color:#0d47a1;
    class HOME,HEALTH,MEDS,MYSTATUS,CHAT nav;
    class VOICE,OCR,ADCHECK,PROFILE sub;
```

---

## 3. 데이터 모델 도면 (ERD)

```mermaid
erDiagram
    USERS ||--o{ MEDICATIONS : "복용"
    USERS ||--o{ HEALTH_RECORDS : "기록"
    USERS ||--o{ CHAT_MESSAGES : "대화"
    USERS ||--o{ MEDICATION_ALARMS : "알람"
    USERS ||--o{ DUR_ALERTS : "경고"
    USERS ||--o{ CHRONIC_DISEASES : "질환"
    USERS ||--o{ USERS : "보호자(guardian_id)"
    MEDICATIONS ||--o{ MEDICATION_ALARMS : "대상약"

    USERS {
        int id PK
        string name
        string phone UK
        string birth_date
        string gender
        string role "patient/guardian/caregiver"
        int guardian_id FK
        datetime created_at
    }
    MEDICATIONS {
        int id PK
        int user_id FK
        string name
        string ingredient
        string dosage
        string frequency
        string category "prescription/otc/supplement"
        string start_date
        string end_date
        string prescribing_hospital
        text notes
        bool is_active
    }
    HEALTH_RECORDS {
        int id PK
        int user_id FK
        string record_type "symptom/vital_sign/prescription_ocr/voice_memo"
        text content
        json structured_data
        string source "voice/camera/manual"
        datetime created_at
    }
    CHAT_MESSAGES {
        int id PK
        int user_id FK
        string role "user/assistant"
        text content
        datetime created_at
    }
    MEDICATION_ALARMS {
        int id PK
        int user_id FK
        int medication_id FK
        string alarm_time "HH:MM"
        bool is_taken
        datetime taken_at
    }
    DUR_ALERTS {
        int id PK
        int user_id FK
        string alert_type "contraindication/duplicate/overdose/elderly_caution"
        string severity "high/medium/low"
        string medication_a
        string medication_b
        text description
        text recommendation
        bool is_resolved
    }
    CHRONIC_DISEASES {
        int id PK
        int user_id FK
        string disease_name
        string diagnosis_date
        json target_values
        json latest_values
        string status "monitoring/stable/warning/danger"
    }
```

---

## 4. 기능 연계 흐름도 (Data Flow / Sequence)

### 4-1. 핵심 데이터 흐름

```mermaid
flowchart LR
    subgraph IN["입력 채널"]
        A1["① 음성문진"]
        A2["② 처방전 OCR"]
        A10["⑩ 사용자 등록"]
    end
    subgraph CORE["핵심 처리"]
        C3["③ 복약관리"]
        C4["④ DUR 분석"]
        C5["⑤ AI 상담<br/>(RAG 컨텍스트)"]
    end
    subgraph OUT["출력 / 활용"]
        O6["⑥ 맞춤 건강정보"]
        O7["⑦ 건강상태·점수"]
        O8["⑧ 광고 검증"]
        O9["⑨ 보호자 알림"]
    end

    A1 -->|STT 증상구조화| C5
    A2 -->|약 자동등록| C3
    A10 -->|개인화 기반| C3
    C3 --> C4
    C3 --> C5
    C4 -->|병용금기 경고| C5
    C4 --> O8
    C3 --> O6
    C5 --> O6
    C3 --> O7
    C3 --> O9
    O7 -->|이상치 감지| O9
```

### 4-2. 시나리오: 처방전 → 안전성 확인 → 복약 시작

```mermaid
sequenceDiagram
    actor U as 어르신
    participant F as PWA
    participant OCR as ocr 라우터
    participant AI as OpenAI GPT Vision
    participant MED as medications
    participant DUR as dur
    participant CHAT as chat(AI)
    participant WS as guardian(WebSocket)
    actor G as 보호자

    U->>F: 처방전 촬영
    F->>OCR: POST /api/ocr/prescription
    OCR->>AI: 이미지 구조화 요청
    AI-->>OCR: 약물 목록(JSON)
    OCR->>MED: 복약 목록 자동 등록
    MED->>DUR: DUR 자동 검사
    DUR-->>MED: 병용금기 결과
    MED-->>F: 등록완료 + 경고
    F->>CHAT: 주의사항 안내 요청
    CHAT-->>U: "이 약은 ~ 주의하세요"
    MED->>WS: 신규 처방 이벤트
    WS-->>G: 실시간 알림
```

---

## 5. 고도화(2차) 확장 포인트

| 영역 | 현재 | 고도화 방향 |
|------|------|-------------|
| DB | SQLite 단일 파일 | PostgreSQL 전환 · 마이그레이션(Alembic) |
| 인증 | phone 기반 단순 | JWT/OTP 세션, 보호자-환자 권한 분리 |
| 웨어러블 | wearable 라우터(스텁) | 실기기 연동 → HEALTH_RECORDS 자동 입력 |
| 디지털 트윈 | digital_twin 라우터 | 통합 건강모델 시뮬레이션 고도화 |
| FHIR | Patient/Medication/Observation | 병원 EMR 양방향 연동 |
| 알림 | WebSocket | FCM 푸시 · 지자체 돌봄 연계 |

*작성: Claude Code · 기준 커밋 기준 코드 분석*
