import os
from dotenv import load_dotenv

load_dotenv()

# Core
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
SECRET_KEY = os.getenv("SECRET_KEY", "sonju-yakbang-secret-2026")

# DB 경로: 실행 디렉터리와 무관하게 항상 backend/sonju_yakbang.db 를 사용하도록 절대경로로 고정한다.
# (상대경로면 uvicorn을 다른 폴더에서 띄웠을 때 빈 DB가 새로 생겨 데이터가 사라진 것처럼 보이는 문제가 있음)
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_DB_PATH = os.path.join(_BACKEND_DIR, "sonju_yakbang.db")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{_DEFAULT_DB_PATH}")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# OCR APIs
GOOGLE_VISION_API_KEY = os.getenv("GOOGLE_VISION_API_KEY", "")
CLOVA_OCR_SECRET = os.getenv("CLOVA_OCR_SECRET", "")
CLOVA_OCR_URL = os.getenv("CLOVA_OCR_URL", "")

# ==================== 식약처 공공데이터포털(data.go.kr) 공용 인증키 ====================
# 같은 data.go.kr 계정으로 여러 서비스를 활용신청하면 하나의 인증키로 모두 호출됩니다.
# .env 에 DATA_GO_KR_API_KEY 한 줄만 넣으면 아래 3개 서비스가 모두 동작합니다.
# (하위호환: 기존 DRUG_EASY_API_KEY 값도 공용키로 인식)
DATA_GO_KR_API_KEY = os.getenv("DATA_GO_KR_API_KEY", "") or os.getenv("DRUG_EASY_API_KEY", "")

# DUR 공공데이터 API — 승인된 '의약품안전사용서비스(DUR) 성분정보' 서비스
#   병용금기/특정연령대금기/임부금기/용량주의/투여기간주의/노인주의/효능군중복 (성분 기준)
#   https://www.data.go.kr/tcs/dss/selectApiDataDetailView.do (DURIrdntInfoService03)
DUR_API_KEY = os.getenv("DUR_API_KEY", "") or DATA_GO_KR_API_KEY
DUR_API_BASE = "https://apis.data.go.kr/1471000/DURIrdntInfoService03"

# 의약품 정보 공공 API (동일 인증키 사용)
#   1) 의약품 제품 허가정보: 품목/성분/효능효과/용법용량/주의사항/저장방법 (전문·일반 모두)
#      https://www.data.go.kr/data/15095677/openapi.do
#   2) 의약품개요정보(e약은요): 고령자 친화 쉬운말 효능/사용법/주의사항 + 낱알 이미지
#      https://www.data.go.kr/data/15075057/openapi.do
DRUG_PERMIT_API_KEY = os.getenv("DRUG_PERMIT_API_KEY", "") or DATA_GO_KR_API_KEY
DRUG_EASY_API_KEY = os.getenv("DRUG_EASY_API_KEY", "") or DATA_GO_KR_API_KEY
DRUG_PERMIT_API_BASE = "https://apis.data.go.kr/1471000/DrugPrdtPrmsnInfoService08"
DRUG_EASY_API_BASE = "https://apis.data.go.kr/1471000/DrbEasyDrugInfoService"

# 건강기능식품(기능성 제품) 품목정보 공공 API (동일 data.go.kr 인증키 사용)
#   라이브 데이터를 쓰려면 data.go.kr 에서 "식품의약품안전처_건강기능식품 품목정보"
#   서비스를 활용신청한 뒤, 아래 엔드포인트/파라미터가 실제 서비스와 맞는지 확인하세요.
#   (미설정/미승인 시 라벨 OCR 값 + 로컬 데모 DB 로 자동 폴백 — health_food.py)
HEALTH_FOOD_API_BASE = os.getenv(
    "HEALTH_FOOD_API_BASE",
    "https://apis.data.go.kr/1471000/HtfsInfoService03/getHtfsItem01",
)
