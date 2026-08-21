from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False)
    phone = Column(String(20), unique=True, nullable=False)
    birth_date = Column(String(10))  # YYYY-MM-DD
    gender = Column(String(10))
    role = Column(String(20), default="patient")  # patient, guardian, caregiver
    guardian_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    medications = relationship("Medication", back_populates="user")
    health_records = relationship("HealthRecord", back_populates="user")
    chat_history = relationship("ChatMessage", back_populates="user")
    medication_alarms = relationship("MedicationAlarm", back_populates="user")


class Medication(Base):
    __tablename__ = "medications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(200), nullable=False)
    ingredient = Column(String(500))
    dosage = Column(String(100))
    frequency = Column(String(100))  # e.g., "1일 3회 식후 30분"
    category = Column(String(50))  # prescription, otc, supplement
    start_date = Column(String(10))
    end_date = Column(String(10), nullable=True)
    prescribing_hospital = Column(String(200), nullable=True)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="medications")


class HealthRecord(Base):
    __tablename__ = "health_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    record_type = Column(String(50))  # symptom, vital_sign, prescription_ocr, voice_memo
    content = Column(Text, nullable=False)
    structured_data = Column(JSON, nullable=True)
    source = Column(String(50))  # voice, camera, manual
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="health_records")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role = Column(String(20), nullable=False)  # user, assistant
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="chat_history")


class MedicationAlarm(Base):
    __tablename__ = "medication_alarms"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    medication_id = Column(Integer, ForeignKey("medications.id"), nullable=False)
    alarm_time = Column(String(5))  # HH:MM
    is_taken = Column(Boolean, default=False)
    taken_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="medication_alarms")


class DURAlert(Base):
    __tablename__ = "dur_alerts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    alert_type = Column(String(50))  # contraindication, duplicate, overdose, elderly_caution
    severity = Column(String(20))  # high, medium, low
    medication_a = Column(String(200))
    medication_b = Column(String(200), nullable=True)
    description = Column(Text)
    recommendation = Column(Text)
    is_resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class ChronicDisease(Base):
    __tablename__ = "chronic_diseases"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    disease_name = Column(String(100))  # hypertension, diabetes, hyperlipidemia
    diagnosis_date = Column(String(10), nullable=True)
    target_values = Column(JSON, nullable=True)  # e.g., {"systolic": 130, "diastolic": 80}
    latest_values = Column(JSON, nullable=True)
    status = Column(String(20), default="monitoring")  # monitoring, stable, warning, danger
    updated_at = Column(DateTime, default=datetime.utcnow)
