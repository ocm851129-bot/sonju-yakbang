# -*- coding: utf-8 -*-
"""
손주약방 테스트 데이터 시드 스크립트
어르신 건강관리 도메인에 맞는 현실적인 목업 데이터를 약 1000건 생성한다.
실행:  python seed_test_data.py
"""
import random
from datetime import datetime, timedelta

from app.database import SessionLocal, engine, Base
from app.models import (
    User, Medication, HealthRecord, ChatMessage,
    MedicationAlarm, DURAlert, ChronicDisease,
)

# 테이블 보장
Base.metadata.create_all(bind=engine)

random.seed(20260824)

# ---------------------------------------------------------------- 사전 데이터
SURNAMES = list("김이박최정강조윤장임한오서신권황안송류전홍")
GIVEN_1 = list("영순정길복명춘옥금말분화자경숙미현광동종상병")
GIVEN_2 = list("자수남순희옥례식호근철수민아연진호국주현선")

REGIONS = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "경기", "강원", "충북", "전남", "경북", "제주"]

# (약품명, 성분, 카테고리, 대표 복용법)
MED_CATALOG = [
    ("아모잘탄정5/50mg", "암로디핀베실산염/로사르탄칼륨", "prescription", "1일 1회 아침 식후 30분"),
    ("노바스크정5mg", "암로디핀베실산염", "prescription", "1일 1회 아침 식후 30분"),
    ("메트포르민서방정500mg", "메트포르민염산염", "prescription", "1일 2회 아침·저녁 식후"),
    ("자누비아정100mg", "시타글립틴인산염", "prescription", "1일 1회 아침 식후"),
    ("리피토정10mg", "아토르바스타틴칼슘", "prescription", "1일 1회 저녁 식후"),
    ("크레스토정10mg", "로수바스타틴칼슘", "prescription", "1일 1회 저녁 식후"),
    ("아스피린프로텍트정100mg", "아세틸살리실산", "prescription", "1일 1회 아침 식후"),
    ("플라빅스정75mg", "클로피도그렐황산염", "prescription", "1일 1회 아침 식후"),
    ("하루날디정0.2mg", "탐스로신염산염", "prescription", "1일 1회 저녁 식후"),
    ("씬지로이드정0.1mg", "레보티록신나트륨", "prescription", "1일 1회 아침 공복"),
    ("가스터정20mg", "파모티딘", "prescription", "1일 2회 아침·저녁 식전"),
    ("타이레놀정500mg", "아세트아미노펜", "otc", "통증 시 1일 3회 식후"),
    ("이지엔6이브연질캡슐", "이부프로펜", "otc", "통증 시 1일 3회 식후"),
    ("판피린큐액", "아세트아미노펜/카페인무수물", "otc", "감기 증상 시 1일 3회"),
    ("겔포스엠현탁액", "인산알루미늄겔", "otc", "속쓰림 시 1일 3회 식간"),
    ("우루사정100mg", "우르소데옥시콜산", "otc", "1일 3회 식후"),
    ("훼스탈플러스정", "판크레아틴", "otc", "1일 3회 식후"),
    ("아로나민골드정", "푸르설티아민", "supplement", "1일 1회 아침 식후"),
    ("센트룸실버정", "종합비타민미네랄", "supplement", "1일 1회 아침 식후"),
    ("오메가3연질캡슐", "오메가3지방산", "supplement", "1일 1회 저녁 식후"),
    ("칼슘마그네슘아연", "탄산칼슘/산화마그네슘", "supplement", "1일 1회 저녁 식후"),
    ("비타민D3 2000IU", "콜레칼시페롤", "supplement", "1일 1회 아침 식후"),
    ("글루코사민정", "글루코사민황산염", "supplement", "1일 2회 아침·저녁 식후"),
    ("프로바이오틱스", "유산균", "supplement", "1일 1회 아침 공복"),
]

HOSPITALS = [
    "서울내과의원", "행복가정의학과", "튼튼정형외과", "제일신경과의원", "미소가정의학과의원",
    "한마음내과", "우리동네의원", "연세365의원", "참사랑의원", "건강한내과",
    "서울대학교병원", "삼성서울병원", "강북삼성병원", "지역보건소",
]

# 만성질환 (한글표시명, 코드, 목표치)
CHRONIC = [
    ("고혈압", "hypertension", {"systolic": 130, "diastolic": 80}),
    ("당뇨병", "diabetes", {"fasting_glucose": 130, "hba1c": 6.5}),
    ("고지혈증", "hyperlipidemia", {"ldl": 100, "total_cholesterol": 200}),
    ("골다공증", "osteoporosis", {"t_score": -2.0}),
    ("관절염", "arthritis", {"pain_score": 3}),
    ("만성신장질환", "ckd", {"egfr": 60}),
]

SYMPTOMS = [
    "무릎이 시큰거리고 아프다", "머리가 지끈지끈 아프다", "속이 더부룩하고 소화가 안 된다",
    "밤에 잠이 잘 안 온다", "어지럽고 기운이 없다", "허리가 뻐근하다",
    "손발이 저리다", "가슴이 답답하고 두근거린다", "기침이 자주 난다",
    "변비가 있어 불편하다", "눈이 침침하고 뻑뻑하다", "입맛이 없다",
    "다리가 자주 붓는다", "귀에서 소리가 난다", "어깨가 결린다",
]

VOICE_MEMOS = [
    "오늘 아침 혈압약 잘 챙겨 먹었어", "점심 먹고 산책 삼십 분 했다", "손주가 전화해서 기분이 좋다",
    "병원 예약이 다음 주 화요일이네", "밥맛이 통 없어서 죽만 조금 먹었어", "무릎이 아파서 병원 다녀왔다",
    "오늘은 컨디션이 아주 좋구먼", "약 먹는 걸 깜빡할 뻔했네", "경로당 다녀오니 피곤하다",
]

CHAT_USER = [
    "혈압약이랑 감기약 같이 먹어도 되나?", "무릎이 아픈데 어떤 약이 좋을까?",
    "당뇨에 좋은 음식이 뭐가 있어?", "오늘 약 먹었는지 기억이 안 나네",
    "타이레놀 하루에 몇 번 먹어도 되지?", "혈압이 145면 높은 건가?",
    "밤에 잠이 안 오는데 어떡하지?", "소화가 안 되는데 무슨 약 먹을까?",
    "다음 병원 예약이 언제였지?", "비타민은 언제 먹는 게 좋아?",
    "손주한테 전화 좀 걸어줘", "오늘 날씨가 어때?",
]

CHAT_ASSISTANT = [
    "네 어르신, 두 약은 함께 드셔도 괜찮지만 식후 30분에 드시는 걸 권해요.",
    "무릎 통증에는 무리한 활동을 줄이시고, 심하면 병원 진료를 받아보세요.",
    "당뇨에는 잡곡밥과 채소가 좋아요. 단 음식은 줄이시는 게 좋습니다.",
    "오늘 아침 약은 이미 드셨어요. 저녁 약은 저녁 식후에 알려드릴게요.",
    "타이레놀은 하루 3회, 최대 8시간 간격으로 드세요.",
    "혈압 145면 조금 높은 편이에요. 오늘 다시 한번 재보시겠어요?",
    "따뜻한 우유를 드시고 일찍 누워보세요. 자주 그러시면 알려주세요.",
    "속이 불편하시면 겔포스 같은 제산제가 도움이 돼요.",
    "다음 병원 예약은 다음 주 화요일 오전 10시예요.",
    "비타민은 아침 식사 후에 드시는 게 흡수에 좋아요.",
    "네, 보호자님께 연결해 드릴게요.",
    "오늘은 맑고 따뜻해요. 산책하기 좋은 날이에요.",
]

DUR_CASES = [
    ("contraindication", "high", "아스피린프로텍트정100mg", "플라빅스정75mg",
     "항혈소판제 병용으로 출혈 위험이 증가할 수 있습니다.", "복용 전 반드시 의사·약사와 상담하세요."),
    ("duplicate", "medium", "노바스크정5mg", "아모잘탄정5/50mg",
     "동일 성분(암로디핀) 중복 복용이 의심됩니다.", "중복 복용 여부를 확인하고 한 가지로 조정하세요."),
    ("overdose", "high", "타이레놀정500mg", None,
     "아세트아미노펜 일일 최대 용량 초과가 우려됩니다.", "하루 4000mg을 넘지 않도록 주의하세요."),
    ("elderly_caution", "medium", "이지엔6이브연질캡슐", None,
     "고령자에게 위장관 부작용 위험이 있는 약물입니다.", "식후 복용하고 장기 복용은 피하세요."),
    ("elderly_caution", "low", "가스터정20mg", None,
     "신기능 저하 고령자는 용량 조절이 필요할 수 있습니다.", "신장 수치를 정기적으로 확인하세요."),
]


def rand_name():
    return random.choice(SURNAMES) + random.choice(GIVEN_1) + random.choice(GIVEN_2)


def rand_phone(exist):
    while True:
        p = "010-" + f"{random.randint(1000,9999)}" + "-" + f"{random.randint(1000,9999)}"
        if p not in exist:
            exist.add(p)
            return p


def rand_date(start_days_ago, end_days_ago=0):
    d = datetime.now() - timedelta(days=random.randint(end_days_ago, start_days_ago))
    return d


def main():
    db = SessionLocal()
    phones = set(p[0] for p in db.query(User.phone).all())
    counts = {}

    # ---- 사용자: 보호자 15명 + 환자 45명 --------------------------------
    guardians = []
    for _ in range(15):
        g = User(
            name=rand_name(),
            phone=rand_phone(phones),
            birth_date=f"{random.randint(1965,1985)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
            gender=random.choice(["male", "female"]),
            role="guardian",
            created_at=rand_date(400, 200),
        )
        db.add(g)
        guardians.append(g)
    db.commit()

    patients = []
    for _ in range(45):
        birth_year = random.randint(1935, 1958)
        p = User(
            name=rand_name(),
            phone=rand_phone(phones),
            birth_date=f"{birth_year}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
            gender=random.choice(["male", "female"]),
            role="patient",
            guardian_id=random.choice(guardians).id if random.random() < 0.7 else None,
            created_at=rand_date(400, 150),
        )
        db.add(p)
        patients.append(p)
    db.commit()
    counts["users"] = len(guardians) + len(patients)

    # ---- 만성질환: 환자당 1~3개 ----------------------------------------
    n_chronic = 0
    for p in patients:
        for name, code, target in random.sample(CHRONIC, k=random.randint(1, 3)):
            latest = {}
            for key, val in target.items():
                if isinstance(val, int):
                    latest[key] = val + random.randint(-10, 25)
                else:
                    latest[key] = round(val + random.uniform(-0.5, 1.5), 1)
            status = random.choices(
                ["stable", "monitoring", "warning", "danger"], weights=[4, 4, 2, 1]
            )[0]
            db.add(ChronicDisease(
                user_id=p.id, disease_name=code, diagnosis_date=rand_date(2000, 300).strftime("%Y-%m-%d"),
                target_values=target, latest_values=latest, status=status,
                updated_at=rand_date(30, 0),
            ))
            n_chronic += 1
    db.commit()
    counts["chronic_diseases"] = n_chronic

    # ---- 복약: 환자당 2~5개 --------------------------------------------
    all_meds = []
    for p in patients:
        for med in random.sample(MED_CATALOG, k=random.randint(2, 5)):
            name, ingredient, category, freq = med
            start = rand_date(300, 30)
            active = random.random() < 0.85
            m = Medication(
                user_id=p.id, name=name, ingredient=ingredient,
                dosage="1정" if "정" in name else "1회분", frequency=freq, category=category,
                start_date=start.strftime("%Y-%m-%d"),
                end_date=None if active else (start + timedelta(days=random.randint(14, 90))).strftime("%Y-%m-%d"),
                prescribing_hospital=random.choice(HOSPITALS) if category == "prescription" else None,
                notes=random.choice([None, None, "식전 복용 주의", "물 충분히", "졸음 유발 가능"]),
                is_active=active, created_at=start,
            )
            db.add(m)
            all_meds.append(m)
    db.commit()
    counts["medications"] = len(all_meds)

    # ---- 복약 알람: 활성 약 기준 -----------------------------------------
    n_alarm = 0
    times_map = {"1일 1회": ["08:00"], "1일 2회": ["08:00", "19:00"], "1일 3회": ["08:00", "13:00", "19:00"]}
    for m in all_meds:
        if not m.is_active:
            continue
        key = next((k for k in times_map if k in m.frequency), "1일 1회")
        for t in times_map[key]:
            taken = random.random() < 0.75
            db.add(MedicationAlarm(
                user_id=m.user_id, medication_id=m.id, alarm_time=t,
                is_taken=taken,
                taken_at=(datetime.now().replace(hour=int(t[:2]), minute=int(t[3:]), second=0)
                          if taken else None),
                created_at=rand_date(60, 0),
            ))
            n_alarm += 1
    db.commit()
    counts["medication_alarms"] = n_alarm

    # ---- 건강기록: 혈압/혈당/증상/음성메모 --------------------------------
    n_health = 0
    for p in patients:
        # 최근 60일간 혈압/혈당 측정 시계열
        for _ in range(random.randint(4, 10)):
            rec_date = rand_date(60, 0)
            kind = random.random()
            if kind < 0.5:
                sys = random.randint(115, 160)
                dia = random.randint(70, 100)
                db.add(HealthRecord(
                    user_id=p.id, record_type="vital_sign",
                    content=f"혈압 {sys}/{dia} mmHg, 맥박 {random.randint(60,90)}회",
                    structured_data={"type": "blood_pressure", "systolic": sys, "diastolic": dia,
                                     "pulse": random.randint(60, 90)},
                    source="manual", created_at=rec_date,
                ))
            elif kind < 0.8:
                glu = random.randint(90, 200)
                db.add(HealthRecord(
                    user_id=p.id, record_type="vital_sign",
                    content=f"공복 혈당 {glu} mg/dL",
                    structured_data={"type": "blood_glucose", "value": glu, "timing": "fasting"},
                    source="manual", created_at=rec_date,
                ))
            else:
                db.add(HealthRecord(
                    user_id=p.id, record_type="symptom",
                    content=random.choice(SYMPTOMS),
                    structured_data={"severity": random.randint(1, 5)},
                    source=random.choice(["voice", "manual"]), created_at=rec_date,
                ))
            n_health += 1
        # 음성 메모
        for _ in range(random.randint(0, 3)):
            db.add(HealthRecord(
                user_id=p.id, record_type="voice_memo",
                content=random.choice(VOICE_MEMOS),
                structured_data=None, source="voice", created_at=rand_date(60, 0),
            ))
            n_health += 1
    db.commit()
    counts["health_records"] = n_health

    # ---- 채팅 기록: 환자당 대화 몇 턴 ------------------------------------
    n_chat = 0
    for p in patients:
        for _ in range(random.randint(2, 6)):
            base = rand_date(90, 0)
            idx = random.randrange(len(CHAT_USER))
            db.add(ChatMessage(user_id=p.id, role="user", content=CHAT_USER[idx], created_at=base))
            db.add(ChatMessage(user_id=p.id, role="assistant", content=CHAT_ASSISTANT[idx],
                               created_at=base + timedelta(seconds=random.randint(2, 8))))
            n_chat += 2
    db.commit()
    counts["chat_messages"] = n_chat

    # ---- DUR 경고: 일부 환자에게 --------------------------------------
    n_dur = 0
    for p in random.sample(patients, k=25):
        atype, sev, ma, mb, desc, rec = random.choice(DUR_CASES)
        db.add(DURAlert(
            user_id=p.id, alert_type=atype, severity=sev,
            medication_a=ma, medication_b=mb, description=desc, recommendation=rec,
            is_resolved=random.random() < 0.4, created_at=rand_date(90, 0),
        ))
        n_dur += 1
    db.commit()
    counts["dur_alerts"] = n_dur

    db.close()

    total = sum(counts.values())
    print("=" * 40)
    print(" 손주약방 테스트 데이터 생성 완료")
    print("=" * 40)
    for k, v in counts.items():
        print(f"  {k:<20} {v:>5} 건")
    print("-" * 40)
    print(f"  {'총계':<20} {total:>5} 건")


if __name__ == "__main__":
    main()
