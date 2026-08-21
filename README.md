# 🏥 손주약방 - 어르신 건강관리 AI 플랫폼

> 문진 생성 모델을 기반으로 하는 건강 관리 서비스 제공 방법 및 시스템

## 핵심 기능 10가지

| # | 기능 | 기술 |
|---|------|------|
| 1 | STT 기반 음성 문진 | OpenAI Whisper |
| 2 | AI OCR 처방전 인식 | Google Vision / CLOVA OCR + GPT-4o 구조화 |
| 3 | 복약 관리 및 알림 | Rule Engine + 스케줄러 + TTS 음성 알림 |
| 4 | DUR 병용금기 분석 | 공공데이터포털 API + Rule Engine + GPT |
| 5 | AI 건강 상담 챗봇 | GPT-4o + 사용자 컨텍스트 RAG (복용약·건강기록 기반) |
| 6 | 보호자 실시간 연동 | WebSocket + Push 알림 |
| 7 | 만성질환 관리 | 바이탈 사인 추적 |
| 8 | 건강기능식품 추천 + 허위광고 필터링 | GPT Vision + 식약처 금지표현 Rule Engine |
| 9 | 고령자 친화 UI | PWA + 큰 글씨 + 음성 중심 + TTS 출력 |
| 10 | AI 캐릭터 정서지원 | 5종 프리셋 캐릭터 + 감정 분석 + 개인화 메시지 |

## 기술 스택

- **Frontend**: PWA (Progressive Web App) — HTML5 + CSS3 + JS, 홈화면 설치 가능
- **Backend**: FastAPI (Python 3.9+)
- **Database**: SQLite (MVP) → PostgreSQL (확장)
- **AI**: OpenAI API (GPT-4o-mini, Whisper STT, Vision OCR, Embeddings)
- **OCR**: Google Vision API / CLOVA OCR (1차) + GPT Vision (2차 구조화)
- **DUR**: 공공데이터포털 API (의약품안전나라) + 로컬 Rule Engine + AI 보조
- **RAG**: OpenAI Embeddings + 인메모리 벡터 스토어 (의약학 지식 14건 내장)
- **의료표준**: HL7-FHIR R4 호환 데이터 매핑 레이어
- **실시간**: WebSocket (보호자 알림) + Push Notification
- **IoT**: 웨어러블 연동 API (Samsung Health Connect, Bluetooth 혈압계/혈당계)
- **Agentic AI**: APScheduler 기반 자율 판단 (복약 누락 감지, 건강 패턴 분석, 선제 알림)
- **배포**: 로컬 개발 → AWS (Activate 크레딧 활용)

## 실행 방법

### 1. 백엔드 실행

```bash
cd sonju-yakbang/backend

# 가상환경 생성 (선택)
python -m venv venv
venv\Scripts\activate

# 패키지 설치
pip install -r requirements.txt

# 환경변수 설정
copy .env.example .env
# .env 파일에 OPENAI_API_KEY 입력

# 서버 실행
uvicorn app.main:app --reload --port 8000
```

### 2. 프론트엔드 실행

```bash
cd sonju-yakbang/frontend

# 간단한 웹서버로 실행
python -m http.server 3000
```

브라우저에서 `http://localhost:3000` 접속

### 3. API 문서 확인

서버 실행 후 `http://localhost:8000/docs` 에서 Swagger UI 확인

## 프로젝트 구조

```
sonju-yakbang/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI 앱 엔트리포인트
│   │   ├── config.py            # 환경 설정
│   │   ├── database.py          # DB 연결 (SQLite/PostgreSQL 호환)
│   │   ├── models.py            # SQLAlchemy 모델
│   │   ├── fhir.py              # HL7-FHIR R4 매핑 레이어
│   │   ├── rag_engine.py        # RAG 벡터 검색 엔진 (의약학 14건)
│   │   ├── dur_database.py      # 공공데이터포털 DUR API 연동
│   │   ├── agent_scheduler.py   # Agentic AI 자율 스케줄러 (5개 작업)
│   │   ├── security.py          # AES-256 암호화 + 감사 로그
│   │   └── routers/
│   │       ├── auth.py          # 인증 (회원가입/로그인)
│   │       ├── voice.py         # 음성 문진 (STT)
│   │       ├── ocr.py           # 처방전 OCR (3단계)
│   │       ├── medications.py   # 복약 관리
│   │       ├── chat.py          # AI 건강 상담 (RAG + 장기 기억)
│   │       ├── dur.py           # DUR 병용금기 분석 (3단계)
│   │       ├── health.py        # 만성질환/건강점수
│   │       ├── guardian.py      # 보호자 WebSocket 연동
│   │       ├── ad_filter.py     # 허위광고 필터링
│   │       ├── character.py     # AI 캐릭터 정서지원
│   │       ├── wearable.py      # 웨어러블 IoT 연동
│   │       └── digital_twin.py  # 디지털 트윈 시뮬레이션
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── index.html               # 메인 HTML (PWA SPA)
│   ├── styles.css               # 반응형 UI (iOS/Android/태블릿)
│   ├── app.js                   # 클라이언트 로직 + 기기 감지
│   ├── offline-dur.js           # Edge AI 오프라인 DUR
│   ├── sw.js                    # Service Worker (PWA 오프라인)
│   └── manifest.json            # PWA 매니페스트
└── README.md
```

## 고령자 친화 UI 설계 원칙

1. **큰 글씨**: 기본 17px, 제목 24px (기기별 자동 조정)
2. **고대비**: 텍스트 #2D3436 / 배경 #F0F7F4, 다크모드·고대비 모드 지원
3. **큰 터치 영역**: 최소 44px (WCAG 2.5.5 준수)
4. **음성 우선**: 모든 입력에 음성 대안 제공 + TTS 음성 출력 (속도 0.85x)
5. **단순 레이아웃**: 한 화면에 하나의 액션, 2×3 격자 메뉴
6. **친근한 어조**: AI 캐릭터가 손주처럼 대화 (5종 프리셋)
7. **접근성**: WCAG 2.1 준수 (aria-label, focus-visible, reduced-motion)

## iOS / Android 멀티 플랫폼 지원

PWA(Progressive Web App) 기반으로 iOS·Android 모두 네이티브 앱처럼 동작합니다.

### iOS 지원

| 항목 | 적용 내용 |
|------|-----------|
| 노치/다이나믹 아일랜드 | `viewport-fit=cover` + `env(safe-area-inset-top)` |
| 홈 인디케이터 | `env(safe-area-inset-bottom)` 하단바 패딩 |
| 100vh 버그 해결 | `100dvh` + JS `--real-vh` 동적 계산 |
| 홈화면 추가 (전체화면) | `apple-mobile-web-app-capable` |
| 입력 확대 방지 | `font-size: 16px` (iOS 16px 미만 시 자동 확대 방지) |

### Android 지원

| 항목 | 적용 내용 |
|------|-----------|
| 상태바 색상 | `theme-color: #5DB075` |
| 3버튼/제스처 네비게이션 | 하단바 safe-area 대응 |
| 키보드 감지 | 높이 변화 감지 → 하단바 숨김 + 채팅 레이아웃 자동 조정 |
| PWA 설치 | manifest.json `maskable` 아이콘 |

### 화면 크기별 자동 조율

| 기기 예시 | 화면 폭 | 레이아웃 |
|-----------|---------|----------|
| iPhone SE | ~360px | 2×2 그리드, 컴팩트 카드 |
| iPhone 12~14 | 361~393px | 2×3 그리드 |
| iPhone 14 Pro Max / Galaxy S24 | 394~430px | 2×3 그리드, 여유 간격 |
| Galaxy S24 Ultra+ | 400px+, 높이 850px+ | 큰 캐릭터, 넓은 카드 |
| 태블릿 | 431px+ | 중앙 정렬 + 좌우 테두리 |
| 가로 모드 | landscape | 컴팩트 3열 레이아웃 |

### 테스트 방법

1. **Chrome DevTools**: `F12` → `Ctrl+Shift+M` → 기기 프리셋 선택
2. **실제 폰 접속**: 같은 Wi-Fi에서 `http://[PC IP]:3000` 접속
3. **iOS Safari 개발자 도구**: Mac 연결 후 Safari > Develop > iPhone

## 면책 사항

※ 이 서비스는 건강 정보 관리를 위한 참고용 도구이며, 의료적 판단이나 처방을 대체하지 않습니다. 
정확한 진단과 치료는 반드시 의료 전문가와 상담하세요.

## 라이선스

© 2026 손주약방. All rights reserved.
특허 출원번호: 10-2025-0086181
