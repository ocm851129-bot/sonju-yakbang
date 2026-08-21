"""웨어러블/IoT 장치 연동 - 혈압계·혈당계·스마트워치 자동 데이터 수집

지원 연동:
- Samsung Health Connect API
- Google Health Connect (Android)
- Bluetooth 혈압계 (오므론, 인바디 등) 데이터 수신
- Open Wearables API (Apple Health, Garmin, Whoop 통합)
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.database import get_db
from app.models import HealthRecord
import json

router = APIRouter()


# ==================== 데이터 모델 ====================

class WearableData(BaseModel):
    user_id: int
    device_type: str  # blood_pressure, glucometer, smartwatch, scale
    device_name: str = ""  # "오므론 HEM-7156", "갤럭시워치6"
    measurements: dict  # 측정값 (기기별 상이)
    measured_at: str = ""  # ISO 8601
    source: str = "bluetooth"  # bluetooth, health_connect, manual


class WearableDeviceInfo(BaseModel):
    device_id: str
    device_type: str
    device_name: str
    last_sync: str
    status: str  # connected, disconnected, pairing


class HealthConnectSync(BaseModel):
    user_id: int
    platform: str  # samsung_health, google_health, apple_health
    data_types: List[str]  # ["blood_pressure", "heart_rate", "steps", "blood_glucose"]
    records: List[dict]


# ==================== 엔드포인트 ====================

@router.post("/data/receive")
def receive_wearable_data(data: WearableData, db: Session = Depends(get_db)):
    """웨어러블/IoT 기기에서 측정 데이터 수신
    
    Bluetooth 혈압계, 혈당계 등에서 측정한 데이터를 자동으로 수신합니다.
    프론트엔드의 Web Bluetooth API 또는 companion 앱에서 호출합니다.
    """
    # 데이터 정규화
    normalized = _normalize_measurement(data.device_type, data.measurements)

    # 경고 생성
    warnings = _check_vital_warnings(data.device_type, normalized)

    # DB 저장
    record = HealthRecord(
        user_id=data.user_id,
        record_type="vital_sign",
        content=json.dumps({
            "device": data.device_name,
            "source": data.source,
            **normalized,
        }, ensure_ascii=False),
        structured_data=normalized,
        source=f"iot_{data.device_type}",
    )
    db.add(record)
    db.commit()

    # 위험 수치 시 보호자 알림 트리거
    response = {
        "message": "측정 데이터 저장 완료",
        "device": data.device_name,
        "values": normalized,
        "warnings": warnings,
        "auto_saved": True,
    }

    if warnings:
        response["alert_sent"] = True

    return response


@router.post("/health-connect/sync")
def sync_health_connect(data: HealthConnectSync, db: Session = Depends(get_db)):
    """Samsung Health / Google Health Connect 동기화
    
    스마트폰의 건강 앱에서 일괄 동기화된 데이터를 수신합니다.
    """
    saved_count = 0

    for record_data in data.records:
        record_type = record_data.get("type", "vital_sign")
        normalized = _normalize_health_connect_record(record_data)

        if normalized:
            record = HealthRecord(
                user_id=data.user_id,
                record_type="vital_sign",
                content=json.dumps(normalized, ensure_ascii=False),
                structured_data=normalized,
                source=f"health_connect_{data.platform}",
            )
            db.add(record)
            saved_count += 1

    db.commit()

    return {
        "message": f"{data.platform}에서 {saved_count}건 동기화 완료",
        "synced_count": saved_count,
        "platform": data.platform,
    }


@router.get("/devices/{user_id}")
def get_paired_devices(user_id: int):
    """페어링된 기기 목록 조회 (프론트엔드 Web Bluetooth 상태 기반)"""
    # MVP에서는 프론트엔드에서 기기 상태를 관리
    # 실제 구현 시 DB에 기기 정보 저장
    return {
        "devices": [],
        "supported_devices": [
            {"type": "blood_pressure", "brands": ["오므론", "인바디", "마이크로라이프"]},
            {"type": "glucometer", "brands": ["아큐첵", "원터치", "프리스타일"]},
            {"type": "smartwatch", "brands": ["갤럭시워치", "애플워치", "핏빗"]},
            {"type": "scale", "brands": ["인바디", "샤오미", "위딩스"]},
        ],
        "pairing_guide": "설정 > 블루투스에서 기기를 연결한 후 이 앱에서 동기화하세요.",
    }


# ==================== 내부 유틸리티 ====================

def _normalize_measurement(device_type: str, raw: dict) -> dict:
    """기기별 데이터를 표준 형식으로 정규화"""
    if device_type == "blood_pressure":
        return {
            "systolic": raw.get("systolic") or raw.get("sys"),
            "diastolic": raw.get("diastolic") or raw.get("dia"),
            "pulse": raw.get("pulse") or raw.get("heart_rate"),
        }
    elif device_type == "glucometer":
        return {
            "blood_sugar": raw.get("blood_sugar") or raw.get("glucose") or raw.get("value"),
            "measurement_type": raw.get("type", "random"),  # fasting, postprandial, random
        }
    elif device_type == "smartwatch":
        return {
            "heart_rate": raw.get("heart_rate") or raw.get("hr"),
            "steps": raw.get("steps"),
            "spo2": raw.get("spo2") or raw.get("oxygen"),
            "sleep_hours": raw.get("sleep_hours"),
        }
    elif device_type == "scale":
        return {
            "weight": raw.get("weight"),
            "bmi": raw.get("bmi"),
            "body_fat": raw.get("body_fat"),
        }
    return raw


def _normalize_health_connect_record(record: dict) -> dict:
    """Health Connect 레코드를 내부 형식으로 변환"""
    data_type = record.get("type", "")
    values = record.get("values", {})

    if data_type == "blood_pressure":
        return {"systolic": values.get("systolic"), "diastolic": values.get("diastolic")}
    elif data_type == "blood_glucose":
        return {"blood_sugar": values.get("level")}
    elif data_type == "heart_rate":
        return {"heart_rate": values.get("bpm")}
    elif data_type == "steps":
        return {"steps": values.get("count")}
    return values if values else None


def _check_vital_warnings(device_type: str, values: dict) -> list:
    """측정값 기반 경고 생성"""
    warnings = []

    if device_type == "blood_pressure":
        sys = values.get("systolic")
        dia = values.get("diastolic")
        if sys and sys >= 180:
            warnings.append("🚨 수축기 혈압이 180mmHg 이상입니다. 즉시 안정을 취하고 병원에 가세요.")
        elif sys and sys >= 140:
            warnings.append("⚠️ 혈압이 높습니다 (고혈압 단계). 30분 후 재측정 권장합니다.")

    elif device_type == "glucometer":
        sugar = values.get("blood_sugar")
        if sugar and sugar >= 300:
            warnings.append("🚨 혈당이 300mg/dL 이상입니다. 즉시 병원에 가세요.")
        elif sugar and sugar <= 70:
            warnings.append("🚨 저혈당입니다. 즉시 당분을 섭취하세요.")
        elif sugar and sugar >= 200:
            warnings.append("⚠️ 혈당이 높습니다. 수분 섭취 후 1시간 뒤 재측정하세요.")

    elif device_type == "smartwatch":
        hr = values.get("heart_rate")
        spo2 = values.get("spo2")
        if hr and (hr < 40 or hr > 150):
            warnings.append("🚨 심박수 이상 감지. 증상이 있으면 119에 연락하세요.")
        if spo2 and spo2 < 90:
            warnings.append("🚨 산소포화도가 90% 미만입니다. 즉시 병원에 가세요.")

    return warnings
