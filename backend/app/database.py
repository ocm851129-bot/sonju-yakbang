from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import DATABASE_URL

# Render 가 제공하는 Postgres 연결문자열은 'postgres://' 스킴으로 올 수 있는데
# SQLAlchemy 2.x 는 'postgresql://' 를 요구하므로 정규화한다.
db_url = DATABASE_URL
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

# SQLite와 PostgreSQL 모두 호환되도록 분기 처리
connect_args = {}
engine_kwargs = {}
if db_url.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
else:
    # Render Postgres 는 유휴 연결을 끊으므로, 끊긴 연결을 자동 복구하도록
    # pre_ping 과 짧은 recycle 을 둔다. (무료 플랜 커넥션 수 제한 대비 pool 축소)
    engine_kwargs = {"pool_pre_ping": True, "pool_recycle": 300, "pool_size": 5, "max_overflow": 5}

engine = create_engine(db_url, connect_args=connect_args, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
