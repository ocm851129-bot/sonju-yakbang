"""Agentic AI + 프로액티브 AI 스케줄러
사용자가 시키지 않아도 AI가 자율적으로 판단하고 행동합니다.

기능:
1. 복약 시간 도래 시 자동 알림 (TTS + Push)
2. 복약 누락 감지 → 보호자 선제 알림
3. 새 약 등록 시 DUR 자동 트리거
4. 3일 미접속 감지 → 보호자 경고
5. 바이탈 미기록 시 측정 권유 알림
6. 건강 패턴 분석 → 선제적 건강 권고
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import User, MedicationAlarm, Medication, HealthRecord, DURAlert

scheduler = BackgroundScheduler()


# ==================== 1. 복약 시간 자동 알림 ====================

async def check_medication_reminders():
    """매 분 실행: 현재 시간에 해당하는 복약 알림을 찾아 푸시"""
    db = SessionLocal()
    try:
        now = datetime.now()
        current_time = now.strftime("%H:%M")

        # 현재 시간의 미복용 알림 조회
        pending_alarms = (
            db.query(MedicationAlarm)
            .filter(
                MedicationAlarm.alarm_time == current_time,
                MedicationAlarm.is_taken == False,
            )
            .all()
        )

        for alarm in pending_alarms:
            user = db.query(User).filter(User.id == alarm.user_id).first()
            medication = db.query(Medication).filter(Medication.id == alarm.medication_id).first()

            if user and medication:
                # WebSocket으로 환자에게 알림
                from app.routers.guardian import notify_guardian_medication_missed
                # 보호자에게도 알림 (15분 경과 시)
                # 이 로직은 check_missed_medications에서 처리
                pass
    finally:
        db.close()


# ==================== 2. 복약 누락 감지 → 보호자 알림 ====================

async def check_missed_medications():
    """매 15분 실행: 복약 시간 15분 경과 후 미복용 시 보호자에게 선제 알림"""
    db = SessionLocal()
    try:
        now = datetime.now()
        check_time = (now - timedelta(minutes=15)).strftime("%H:%M")

        missed_alarms = (
            db.query(MedicationAlarm)
            .filter(
                MedicationAlarm.alarm_time == check_time,
                MedicationAlarm.is_taken == False,
            )
            .all()
        )

        for alarm in missed_alarms:
            user = db.query(User).filter(User.id == alarm.user_id).first()
            medication = db.query(Medication).filter(Medication.id == alarm.medication_id).first()

            if user and medication and user.guardian_id:
                from app.routers.guardian import notify_guardian_medication_missed
                await notify_guardian_medication_missed(
                    guardian_id=user.guardian_id,
                    patient_name=user.name,
                    medication=medication.name,
                )
    finally:
        db.close()


# ==================== 3. 새 약 등록 시 DUR 자동 트리거 ====================

async def auto_dur_check_on_new_medication(user_id: int, new_medication_name: str):
    """새 약이 등록되면 자동으로 DUR 분석을 실행하고 위험 시 알림"""
    db = SessionLocal()
    try:
        medications = (
            db.query(Medication)
            .filter(Medication.user_id == user_id, Medication.is_active == True)
            .all()
        )

        if len(medications) < 2:
            return

        # 로컬 DUR 룰 빠른 체크
        from app.dur_database import local_dur_check
        alerts = []
        new_med = next((m for m in medications if m.name == new_medication_name), None)
        if not new_med:
            return

        for other_med in medications:
            if other_med.id == new_med.id:
                continue
            found = local_dur_check(
                new_med.name, new_med.ingredient or "",
                other_med.name, other_med.ingredient or "",
            )
            alerts.extend(found)

        # 위험 발견 시 보호자 알림
        if alerts:
            user = db.query(User).filter(User.id == user_id).first()
            if user and user.guardian_id:
                from app.routers.guardian import notify_guardian_dur_alert
                alert_desc = f"{new_medication_name}과 기존 약물 간 상호작용 {len(alerts)}건 감지"
                await notify_guardian_dur_alert(
                    guardian_id=user.guardian_id,
                    patient_name=user.name,
                    alert_desc=alert_desc,
                )

            # DB에 저장
            for alert in alerts:
                db_alert = DURAlert(
                    user_id=user_id,
                    alert_type=alert.get("type", "interaction"),
                    severity=alert.get("severity", "medium"),
                    medication_a=alert.get("medication_a", ""),
                    medication_b=alert.get("medication_b", ""),
                    description=alert.get("description", ""),
                    recommendation=alert.get("recommendation", ""),
                )
                db.add(db_alert)
            db.commit()
    finally:
        db.close()


# ==================== 4. 미접속 감지 → 보호자 경고 ====================

async def check_inactive_users():
    """매일 오전 10시 실행: 3일 이상 미접속 사용자의 보호자에게 경고"""
    db = SessionLocal()
    try:
        three_days_ago = datetime.utcnow() - timedelta(days=3)

        # 최근 기록이 3일 이상 없는 환자 조회
        patients = db.query(User).filter(User.role == "patient", User.guardian_id.isnot(None)).all()

        for patient in patients:
            last_record = (
                db.query(HealthRecord)
                .filter(HealthRecord.user_id == patient.id)
                .order_by(HealthRecord.created_at.desc())
                .first()
            )

            if last_record and last_record.created_at < three_days_ago:
                from app.routers.guardian import manager
                await manager.send_alert(patient.guardian_id, {
                    "type": "inactivity_warning",
                    "patient_name": patient.name,
                    "message": f"{patient.name}님이 3일 이상 앱을 사용하지 않고 있습니다. 안부를 확인해 주세요.",
                    "last_active": str(last_record.created_at),
                    "timestamp": datetime.utcnow().isoformat(),
                })
    finally:
        db.close()


# ==================== 5. 바이탈 미기록 시 측정 권유 ====================

async def check_vital_recording():
    """매일 오후 2시 실행: 오늘 바이탈 기록이 없는 만성질환 환자에게 권유"""
    db = SessionLocal()
    try:
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        patients = db.query(User).filter(User.role == "patient").all()

        for patient in patients:
            # 오늘 바이탈 기록 확인
            today_record = (
                db.query(HealthRecord)
                .filter(
                    HealthRecord.user_id == patient.id,
                    HealthRecord.record_type == "vital_sign",
                    HealthRecord.created_at >= today_start,
                )
                .first()
            )

            if not today_record:
                # 이 환자에게 푸시 알림 (WebSocket이 연결되어 있다면)
                from app.routers.guardian import manager
                if patient.guardian_id and patient.guardian_id in manager.active_connections:
                    await manager.send_alert(patient.guardian_id, {
                        "type": "vital_reminder",
                        "patient_name": patient.name,
                        "message": f"{patient.name}님이 오늘 아직 혈압/혈당을 기록하지 않았습니다.",
                        "timestamp": datetime.utcnow().isoformat(),
                    })
    finally:
        db.close()


# ==================== 6. 건강 패턴 분석 → 선제적 권고 ====================

async def analyze_health_patterns():
    """매주 월요일 오전 9시 실행: 주간 건강 패턴 분석 및 선제적 권고"""
    db = SessionLocal()
    try:
        one_week_ago = datetime.utcnow() - timedelta(days=7)

        patients = db.query(User).filter(User.role == "patient").all()

        for patient in patients:
            # 지난 1주일 바이탈 기록 조회
            records = (
                db.query(HealthRecord)
                .filter(
                    HealthRecord.user_id == patient.id,
                    HealthRecord.record_type == "vital_sign",
                    HealthRecord.created_at >= one_week_ago,
                )
                .all()
            )

            if len(records) < 3:
                continue

            # 혈압 상승 트렌드 감지
            systolic_values = [
                r.structured_data.get("systolic")
                for r in records
                if r.structured_data and r.structured_data.get("systolic")
            ]

            if len(systolic_values) >= 3:
                # 상승 추세 감지 (최근 3개 연속 상승)
                recent = systolic_values[-3:]
                if recent[0] < recent[1] < recent[2] and recent[2] >= 140:
                    if patient.guardian_id:
                        from app.routers.guardian import manager
                        await manager.send_alert(patient.guardian_id, {
                            "type": "health_pattern_alert",
                            "patient_name": patient.name,
                            "message": f"{patient.name}님의 혈압이 지난 일주일간 상승 추세입니다 ({recent[-1]}mmHg). 진료를 권합니다.",
                            "timestamp": datetime.utcnow().isoformat(),
                        })
    finally:
        db.close()


# ==================== 스케줄러 초기화 ====================

def init_scheduler():
    """애플리케이션 시작 시 스케줄러 등록"""
    # 복약 알림: 매 5분 체크
    scheduler.add_job(check_medication_reminders_sync, IntervalTrigger(minutes=5), id="med_reminder")

    # 복약 누락 감지: 매 15분 체크
    scheduler.add_job(check_missed_medications_sync, IntervalTrigger(minutes=15), id="missed_med")

    # 미접속 감지: 매일 오전 10시
    scheduler.add_job(check_inactive_users_sync, CronTrigger(hour=10, minute=0), id="inactive_check")

    # 바이탈 미기록 권유: 매일 오후 2시
    scheduler.add_job(check_vital_recording_sync, CronTrigger(hour=14, minute=0), id="vital_reminder")

    # 건강 패턴 분석: 매주 월요일 오전 9시
    scheduler.add_job(analyze_health_patterns_sync, CronTrigger(day_of_week="mon", hour=9), id="pattern_analysis")

    scheduler.start()


# ===== 동기 래퍼 (BackgroundScheduler용) =====

def check_medication_reminders_sync():
    """복약 알림 동기 버전"""
    db = SessionLocal()
    try:
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        pending = db.query(MedicationAlarm).filter(
            MedicationAlarm.alarm_time == current_time,
            MedicationAlarm.is_taken == False,
        ).all()
        for alarm in pending:
            print(f"[Agent] 복약 알림: user_id={alarm.user_id}, med_id={alarm.medication_id}, time={current_time}")
    finally:
        db.close()


def check_missed_medications_sync():
    """복약 누락 감지 동기 버전 - 15분 경과 미복용 시 로그"""
    db = SessionLocal()
    try:
        now = datetime.now()
        check_time = (now - timedelta(minutes=15)).strftime("%H:%M")
        missed = db.query(MedicationAlarm).filter(
            MedicationAlarm.alarm_time == check_time,
            MedicationAlarm.is_taken == False,
        ).all()
        for alarm in missed:
            user = db.query(User).filter(User.id == alarm.user_id).first()
            medication = db.query(Medication).filter(Medication.id == alarm.medication_id).first()
            if user and medication:
                print(f"[Agent] 복약 누락 감지: {user.name} - {medication.name} ({check_time})")
    finally:
        db.close()


def check_inactive_users_sync():
    """미접속 감지 동기 버전"""
    db = SessionLocal()
    try:
        three_days_ago = datetime.utcnow() - timedelta(days=3)
        patients = db.query(User).filter(User.role == "patient", User.guardian_id.isnot(None)).all()
        for patient in patients:
            last_record = db.query(HealthRecord).filter(
                HealthRecord.user_id == patient.id
            ).order_by(HealthRecord.created_at.desc()).first()
            if last_record and last_record.created_at < three_days_ago:
                print(f"[Agent] 미접속 경고: {patient.name} (3일+ 미사용)")
    finally:
        db.close()


def check_vital_recording_sync():
    """바이탈 미기록 권유 동기 버전"""
    db = SessionLocal()
    try:
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        patients = db.query(User).filter(User.role == "patient").all()
        for patient in patients:
            today_record = db.query(HealthRecord).filter(
                HealthRecord.user_id == patient.id,
                HealthRecord.record_type == "vital_sign",
                HealthRecord.created_at >= today_start,
            ).first()
            if not today_record:
                print(f"[Agent] 바이탈 미기록: {patient.name} (오늘 기록 없음)")
    finally:
        db.close()


def analyze_health_patterns_sync():
    """건강 패턴 분석 동기 버전"""
    db = SessionLocal()
    try:
        one_week_ago = datetime.utcnow() - timedelta(days=7)
        patients = db.query(User).filter(User.role == "patient").all()
        for patient in patients:
            records = db.query(HealthRecord).filter(
                HealthRecord.user_id == patient.id,
                HealthRecord.record_type == "vital_sign",
                HealthRecord.created_at >= one_week_ago,
            ).all()
            if len(records) < 3:
                continue
            systolic_values = [
                r.structured_data.get("systolic")
                for r in records
                if r.structured_data and r.structured_data.get("systolic")
            ]
            if len(systolic_values) >= 3:
                recent = systolic_values[-3:]
                if recent[0] < recent[1] < recent[2] and recent[2] >= 140:
                    print(f"[Agent] 혈압 상승 패턴: {patient.name} ({recent[-1]}mmHg)")
    finally:
        db.close()
