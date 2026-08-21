import os
from dotenv import load_dotenv

load_dotenv()

# Core
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
SECRET_KEY = os.getenv("SECRET_KEY", "sonju-yakbang-secret-2026")
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./sonju_yakbang.db")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# OCR APIs
GOOGLE_VISION_API_KEY = os.getenv("GOOGLE_VISION_API_KEY", "")
CLOVA_OCR_SECRET = os.getenv("CLOVA_OCR_SECRET", "")
CLOVA_OCR_URL = os.getenv("CLOVA_OCR_URL", "")

# DUR 공공데이터 API
DUR_API_KEY = os.getenv("DUR_API_KEY", "")  # 공공데이터포털 인증키
DUR_API_BASE = "http://apis.data.go.kr/1471000/DURPrdlstInfoService03"
