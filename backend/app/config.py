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

# 의약품 낱알식별정보 API (동일 인증키 사용)
#   품목명/업체명 + 낱알의 모양(DRUG_SHAPE)·색상(COLOR_CLASS1/2)·각인(PRINT_FRONT/BACK)·
#   분할선(LINE_FRONT/BACK)·크기(장축/단축/두께)·제형·성상(CHART)·실제 낱알 이미지(ITEM_IMAGE) 제공.
#   어르신이 '낱알' 하나만 들고 와도 생김새로 약을 식별할 수 있게 해 주는 핵심 데이터.
#   https://www.data.go.kr/data/15057639/openapi.do (MdcinGrnIdntfcInfoService03)
DRUG_IDENTITY_API_KEY = os.getenv("DRUG_IDENTITY_API_KEY", "") or DATA_GO_KR_API_KEY
DRUG_IDENTITY_API_BASE = "https://apis.data.go.kr/1471000/MdcinGrnIdntfcInfoService03"
# 낱알식별 '생김새 역검색'용 로컬 색인 파일(선택).
#   이 API는 모양/색상으로 서버측 필터를 지원하지 않으므로(품목명·EDI코드만 필터),
#   생김새로 찾으려면 전체 낱알DB를 로컬에 내려받아(index) 클라이언트에서 거릅니다.
#   생성:  python tools/drug_preprocess.py fetch-pills -o data/pill_identity.jsonl
_DATA_DIR = os.path.join(_BACKEND_DIR, "data")
PILL_INDEX_PATH = os.getenv("PILL_INDEX_PATH", os.path.join(_DATA_DIR, "pill_identity.jsonl"))

# 건강기능식품(기능성 제품) 영양성분 표준데이터 API
#   data.go.kr "전국건강기능식품영양성분정보표준데이터" (동일 DATA_GO_KR 인증키 사용).
#   제품명(foodNm)·제조사(mfrNm)·1회분량/1일섭취횟수/섭취대상·영양성분 제공.
#   (기능성 내용 필드는 없어 라벨 OCR/데모 DB 로 보강 — health_food.py)
#   foodNm 은 정확일치만 지원하므로 전체를 받아 캐시 후 부분매칭한다.
HEALTH_FOOD_API_BASE = os.getenv(
    "HEALTH_FOOD_API_BASE",
    "https://api.data.go.kr/openapi/tn_pubr_public_health_functional_food_nutrition_info_api",
)
