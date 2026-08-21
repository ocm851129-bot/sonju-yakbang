# 🚀 손주약방 배포 가이드

구성: **프론트엔드(PWA) → Vercel**, **백엔드(FastAPI) → Render**
(백엔드는 WebSocket·백그라운드 스케줄러를 사용하므로 Vercel 서버리스가 아닌 상시 서버에 배포합니다.)

---

## 0. 사전 준비

- GitHub 저장소에 코드 푸시 완료 (아래 1번)
- OpenAI API 키(선택 — 없어도 규칙기반 데모로 동작)

---

## 1. GitHub 푸시

```bash
cd sonju-yakbang
git add -A
git commit -m "deploy: 손주약방 배포 준비"
git remote add origin https://github.com/<계정>/sonju-yakbang.git
git branch -M main
git push -u origin main
```

> `.env`, `venv/`, `*.db` 는 `.gitignore` 로 제외됩니다. **실제 API 키는 절대 커밋되지 않습니다.**

---

## 2. 백엔드 배포 (Render)

1. https://render.com 로그인 → **New +** → **Blueprint**
2. 이 GitHub 저장소 선택 → 루트의 `render.yaml` 자동 인식
3. 환경변수 `OPENAI_API_KEY` 입력 (선택), 나머지는 자동
4. **Apply** → 빌드 후 `https://sonju-yakbang-api.onrender.com` 형태 URL 발급

수동 설정 시:
| 항목 | 값 |
|------|-----|
| Root Directory | `backend` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Python Version | `3.12.7` |

> Render 무료 플랜은 15분 미사용 시 슬립 → 첫 요청이 느릴 수 있습니다(콜드스타트).
> 무료 플랜은 디스크가 비영구적이라 SQLite 데이터가 재시작 시 초기화됩니다(데모 시드 자동 재생성). 영구 저장이 필요하면 PostgreSQL로 전환하세요.

---

## 3. 프론트엔드 배포 (Vercel)

### 3-1. 백엔드 URL 연결
`frontend/config.js` 의 `PROD_API_ORIGIN` 을 2번에서 발급된 백엔드 URL로 교체 후 커밋/푸시:

```js
var PROD_API_ORIGIN = 'https://sonju-yakbang-api.onrender.com'; // ← 실제 URL
```

### 3-2. Vercel 배포
1. https://vercel.com 로그인 → **Add New → Project** → GitHub 저장소 선택
2. **Root Directory** 를 `frontend` 로 지정 (중요)
3. Framework Preset: **Other** (정적 사이트), Build/Output 설정 없음
4. **Deploy** → `https://sonju-yakbang.vercel.app` 형태 URL 발급

### CLI 로 배포하는 경우
```bash
cd sonju-yakbang/frontend
npx vercel        # 최초 로그인 + 프리뷰 배포
npx vercel --prod # 프로덕션 배포
```

---

## 4. 배포 후 점검

| 확인 항목 | 방법 |
|-----------|------|
| 백엔드 헬스 | `https://<backend>/` 접속 → JSON 응답 |
| API 문서 | `https://<backend>/docs` |
| 프론트 로딩 | Vercel URL 접속 → 로그인 화면 |
| API 연결 | 로그인/챗봇 동작 확인 (DevTools Network 탭) |
| CORS | 백엔드는 `allow_origins=["*"]` 로 열려 있음 |

---

## 참고: 로컬 실행

```bash
# 백엔드
cd backend && uvicorn app.main:app --reload --port 8000
# 프론트엔드
cd frontend && python -m http.server 3000
```
`config.js` 가 `localhost` 를 감지하면 자동으로 `localhost:8000` 백엔드를 사용합니다.
