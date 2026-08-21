"""보호자·요양보호사 연동 - WebSocket 실시간 모니터링 및 위험 알림

PPT 기준: WebSocket 기반 실시간 연동
구현: REST API (대시보드 조회) + WebSocket (실시간 알림 푸시)
"""
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime
from typing import Dict, List
from app.database import get_db
from app.models import User, HealthRecord, MedicationAlarm, DURAlert

router = APIRouter()


# ==================== WebSocket 연결 관리 ====================

class ConnectionManager:
    """보호자 WebSocket 연결 관리"""

    def __init__(self):
        # guardian_id -> list of WebSocket connections
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, guardian_id: int):
        await websocket.accept()
        if guardian_id not in self.active_connections:
            self.active_connections[guardian_id] = []
        self.active_connections[guardian_id].append(websocket)

    def disconnect(self, websocket: WebSocket, guardian_id: int):
        if guardian_id in self.active_connections:
            self.active_connections[guardian_id].remove(websocket)
            if not self.active_connections[guardian_id]:
                del self.active_connections[guardian_id]

    async def send_alert(self, guardian_id: int, message: dict):
        """보호자에게 실시간 알림 전송"""
        if guardian_id in self.active_connections:
            for connection in self.active_connections[guardian_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass

    async def broadcast_emergency(self, guardian_id: int, patient_name: str, description: str):
        """긴급 알림 브로드캐스트"""
        await self.send_alert(guardian_id, {
            "type": "emergency",
            "patient_name": patient_name,
            "description": description,
            "timestamp": datetime.utcnow().isoformat(),
        })


manager = ConnectionManager()


# ==================== WebSocket 엔드포인트 ====================

@router.websocket("/ws/{guardian_id}")
async def guardian_websocket(websocket: WebSocket, guardian_id: int):
    """보호자 실시간 알림 WebSocket 연결
    
    연결 후 다음 이벤트를 실시간 수신:
    - medication_taken: 어르신 복약 확인
    - medication_missed: 복약 누락 경고
    - emergency: 위급 상황 감지
    - dur_alert: 새 DUR 경고 발생
    - vital_warning: 바이탈 사인 이상
    """
    await manager.connect(websocket, guardian_id)
    try:
        while True:
            # 클라이언트로부터 ping/메시지 대기
            data = await websocket.receive_text()
            # ping-pong 유지
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket, guardian_id)


# ==================== 알림 발송 유틸리티 (다른 모듈에서 호출) ====================

async def notify_guardian_medication_taken(guardian_id: int, patient_name: str, medication: str):
    """복약 완료 알림"""
    await manager.send_alert(guardian_id, {
        "type": "medication_taken",
        "patient_name": patient_name,
        "medication": medication,
        "timestamp": datetime.utcnow().isoformat(),
    })


async def notify_guardian_medication_missed(guardian_id: int, patient_name: str, medication: str):
    """복약 누락 경고"""
    await manager.send_alert(guardian_id, {
        "type": "medication_missed",
        "patient_name": patient_name,
        "medication": medication,
        "message": f"{patient_name}님이 {medication} 복용 시간을 놓쳤습니다.",
        "timestamp": datetime.utcnow().isoformat(),
    })


async def notify_guardian_emergency(guardian_id: int, patient_name: str, description: str):
    """위급 상황 알림"""
    await manager.broadcast_emergency(guardian_id, patient_name, description)


async def notify_guardian_dur_alert(guardian_id: int, patient_name: str, alert_desc: str):
    """DUR 경고 알림"""
    await manager.send_alert(guardian_id, {
        "type": "dur_alert",
        "patient_name": patient_name,
        "description": alert_desc,
        "timestamp": datetime.utcnow().isoformat(),
    })


# ==================== REST API (대시보드) ====================

class GuardianLink(BaseModel):
    patient_phone: str
    guardian_id: int


@router.post("/link")
def link_guardian(data: GuardianLink, db: Session = Depends(get_db)):
    """보호자-환자 연결"""
    patient = db.query(User).filter(User.phone == data.patient_phone).first()
    if not patient:
        raise HTTPException(status_code=404, detail="환자를 찾을 수 없습니다")

    patient.guardian_id = data.guardian_id
    db.commit()
    return {"message": f"{patient.name}님과 연결되었습니다", "patient_id": patient.id}


@router.get("/dashboard/{guardian_id}")
def guardian_dashboard(guardian_id: int, db: Session = Depends(get_db)):
    """보호자 대시보드 - 관리 대상 어르신 현황"""
    patients = db.query(User).filter(User.guardian_id == guardian_id).all()

    if not patients:
        return {"patients": [], "message": "연결된 어르신이 없습니다"}

    dashboards = []
    for patient in patients:
        today_alarms = (
            db.query(MedicationAlarm)
            .filter(MedicationAlarm.user_id == patient.id)
            .all()
        )
        taken = sum(1 for a in today_alarms if a.is_taken)
        total = len(today_alarms)

        alerts = (
            db.query(DURAlert)
            .filter(DURAlert.user_id == patient.id, DURAlert.is_resolved == False)
            .order_by(DURAlert.created_at.desc())
            .limit(5)
            .all()
        )

        last_record = (
            db.query(HealthRecord)
            .filter(HealthRecord.user_id == patient.id)
            .order_by(HealthRecord.created_at.desc())
            .first()
        )

        dashboards.append({
            "patient_id": patient.id,
            "patient_name": patient.name,
            "phone": patient.phone,
            "today_medication": {
                "taken": taken,
                "total": total,
                "rate": f"{(taken/total*100):.0f}%" if total > 0 else "알림 없음",
            },
            "unresolved_alerts": [
                {
                    "type": a.alert_type,
                    "severity": a.severity,
                    "description": a.description,
                    "created_at": str(a.created_at),
                }
                for a in alerts
            ],
            "last_active": str(last_record.created_at) if last_record else "기록 없음",
            "status": _determine_status(taken, total, alerts),
            "websocket_connected": guardian_id in manager.active_connections,
        })

    return {"patients": dashboards}


@router.get("/alerts/{guardian_id}")
def get_guardian_alerts(guardian_id: int, db: Session = Depends(get_db)):
    """보호자에게 전달할 위험 알림 목록"""
    patients = db.query(User).filter(User.guardian_id == guardian_id).all()
    patient_ids = [p.id for p in patients]

    if not patient_ids:
        return {"alerts": []}

    alerts = (
        db.query(DURAlert)
        .filter(DURAlert.user_id.in_(patient_ids), DURAlert.is_resolved == False)
        .order_by(DURAlert.severity.desc(), DURAlert.created_at.desc())
        .all()
    )

    patient_map = {p.id: p.name for p in patients}

    return {
        "alerts": [
            {
                "patient_name": patient_map.get(a.user_id, ""),
                "alert_type": a.alert_type,
                "severity": a.severity,
                "medication_a": a.medication_a,
                "medication_b": a.medication_b,
                "description": a.description,
                "recommendation": a.recommendation,
                "created_at": str(a.created_at),
            }
            for a in alerts
        ],
        "total_unresolved": len(alerts),
    }


def _determine_status(taken: int, total: int, alerts: list) -> str:
    """어르신 상태 판정"""
    high_alerts = [a for a in alerts if a.severity == "high"]
    if high_alerts:
        return "위험"
    if total > 0 and taken == 0:
        return "주의"
    if total > 0 and taken < total:
        return "관심"
    return "양호"
