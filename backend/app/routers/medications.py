"""복약 관리 - 의약품 목록, 알림, 복약 확인"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.database import get_db
from app.models import Medication, MedicationAlarm

router = APIRouter()


class MedicationCreate(BaseModel):
    name: str
    ingredient: str = ""
    dosage: str = ""
    frequency: str = ""
    category: str = "prescription"
    start_date: str = ""
    end_date: Optional[str] = None
    prescribing_hospital: Optional[str] = None
    notes: Optional[str] = None


class AlarmCreate(BaseModel):
    medication_id: int
    alarm_time: str  # HH:MM


@router.get("/list/{user_id}")
def get_medications(user_id: int, db: Session = Depends(get_db)):
    """사용자의 복용 중인 의약품 목록 조회"""
    meds = (
        db.query(Medication)
        .filter(Medication.user_id == user_id, Medication.is_active == True)
        .all()
    )
    return {
        "medications": [
            {
                "id": m.id,
                "name": m.name,
                "ingredient": m.ingredient,
                "dosage": m.dosage,
                "frequency": m.frequency,
                "category": m.category,
                "category_label": {
                    "prescription": "전문의약품",
                    "otc": "일반의약품",
                    "supplement": "건강기능식품",
                    "herbal": "한약",
                }.get(m.category, m.category),
                "start_date": m.start_date,
                "hospital": m.prescribing_hospital,
                "notes": m.notes,
            }
            for m in meds
        ],
        "total": len(meds),
    }


@router.post("/add/{user_id}")
def add_medication(user_id: int, med_data: MedicationCreate, db: Session = Depends(get_db)):
    """의약품 수동 추가"""
    medication = Medication(
        user_id=user_id,
        name=med_data.name,
        ingredient=med_data.ingredient,
        dosage=med_data.dosage,
        frequency=med_data.frequency,
        category=med_data.category,
        start_date=med_data.start_date,
        end_date=med_data.end_date,
        prescribing_hospital=med_data.prescribing_hospital,
        notes=med_data.notes,
    )
    db.add(medication)
    db.commit()
    db.refresh(medication)
    return {"message": f"{med_data.name} 추가 완료", "medication_id": medication.id}


@router.post("/alarm/create/{user_id}")
def create_alarm(user_id: int, alarm_data: AlarmCreate, db: Session = Depends(get_db)):
    """복약 알림 설정"""
    alarm = MedicationAlarm(
        user_id=user_id,
        medication_id=alarm_data.medication_id,
        alarm_time=alarm_data.alarm_time,
    )
    db.add(alarm)
    db.commit()
    return {"message": f"{alarm_data.alarm_time} 알림 설정 완료"}


@router.post("/alarm/confirm/{alarm_id}")
def confirm_medication(alarm_id: int, db: Session = Depends(get_db)):
    """복약 확인 (약 먹었음 표시)"""
    alarm = db.query(MedicationAlarm).filter(MedicationAlarm.id == alarm_id).first()
    if not alarm:
        raise HTTPException(status_code=404, detail="알림을 찾을 수 없습니다")

    alarm.is_taken = True
    alarm.taken_at = datetime.utcnow()
    db.commit()
    return {"message": "복약 확인 완료", "taken_at": str(alarm.taken_at)}


@router.get("/alarms/{user_id}")
def get_alarms(user_id: int, db: Session = Depends(get_db)):
    """오늘의 복약 알림 목록"""
    alarms = (
        db.query(MedicationAlarm)
        .filter(MedicationAlarm.user_id == user_id)
        .all()
    )
    return {
        "alarms": [
            {
                "id": a.id,
                "medication_id": a.medication_id,
                "alarm_time": a.alarm_time,
                "is_taken": a.is_taken,
                "taken_at": str(a.taken_at) if a.taken_at else None,
            }
            for a in alarms
        ]
    }
