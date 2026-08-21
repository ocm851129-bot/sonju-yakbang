"""HL7-FHIR 호환 레이어
내부 데이터 모델을 FHIR R4 리소스 형식으로 변환/내보내기합니다.
향후 의료기관·보건소 시스템과 연동 시 이 레이어를 통해 데이터 교환합니다.

참고: https://www.hl7.org/fhir/
"""
from datetime import datetime


def to_fhir_patient(user) -> dict:
    """User 모델 → FHIR Patient 리소스"""
    return {
        "resourceType": "Patient",
        "id": str(user.id),
        "meta": {
            "profile": ["http://hl7.org/fhir/StructureDefinition/Patient"]
        },
        "name": [{"use": "official", "text": user.name}],
        "telecom": [{"system": "phone", "value": user.phone, "use": "mobile"}],
        "gender": _map_gender(user.gender),
        "birthDate": user.birth_date if user.birth_date else None,
    }


def to_fhir_medication_statement(medication, user_id: int) -> dict:
    """Medication 모델 → FHIR MedicationStatement 리소스"""
    return {
        "resourceType": "MedicationStatement",
        "id": str(medication.id),
        "meta": {
            "profile": ["http://hl7.org/fhir/StructureDefinition/MedicationStatement"]
        },
        "status": "active" if medication.is_active else "stopped",
        "subject": {"reference": f"Patient/{user_id}"},
        "medicationCodeableConcept": {
            "coding": [{
                "system": "http://www.whocc.no/atc",
                "display": medication.name,
            }],
            "text": medication.name,
        },
        "dosage": [{
            "text": f"{medication.dosage} {medication.frequency}",
            "timing": {"code": {"text": medication.frequency}},
        }],
        "effectivePeriod": {
            "start": medication.start_date,
            "end": medication.end_date,
        },
        "category": {
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/medication-statement-category",
                "code": _map_category(medication.category),
            }]
        },
        "note": [{"text": medication.notes}] if medication.notes else [],
    }


def to_fhir_observation(health_record) -> dict:
    """HealthRecord (vital_sign) → FHIR Observation 리소스"""
    data = health_record.structured_data or {}
    components = []

    if data.get("systolic"):
        components.append({
            "code": {"coding": [{"system": "http://loinc.org", "code": "8480-6", "display": "Systolic BP"}]},
            "valueQuantity": {"value": data["systolic"], "unit": "mmHg", "system": "http://unitsofmeasure.org"},
        })
    if data.get("diastolic"):
        components.append({
            "code": {"coding": [{"system": "http://loinc.org", "code": "8462-4", "display": "Diastolic BP"}]},
            "valueQuantity": {"value": data["diastolic"], "unit": "mmHg", "system": "http://unitsofmeasure.org"},
        })
    if data.get("blood_sugar"):
        components.append({
            "code": {"coding": [{"system": "http://loinc.org", "code": "2339-0", "display": "Glucose"}]},
            "valueQuantity": {"value": data["blood_sugar"], "unit": "mg/dL", "system": "http://unitsofmeasure.org"},
        })

    return {
        "resourceType": "Observation",
        "id": str(health_record.id),
        "meta": {
            "profile": ["http://hl7.org/fhir/StructureDefinition/Observation"]
        },
        "status": "final",
        "category": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/observation-category", "code": "vital-signs"}]}],
        "subject": {"reference": f"Patient/{health_record.user_id}"},
        "effectiveDateTime": health_record.created_at.isoformat() if health_record.created_at else None,
        "component": components,
    }


def to_fhir_detected_issue(dur_alert, user_id: int) -> dict:
    """DURAlert → FHIR DetectedIssue 리소스 (병용금기 알림)"""
    severity_map = {"high": "high", "medium": "moderate", "low": "low"}

    return {
        "resourceType": "DetectedIssue",
        "id": str(dur_alert.id),
        "status": "preliminary" if not dur_alert.is_resolved else "final",
        "severity": severity_map.get(dur_alert.severity, "moderate"),
        "patient": {"reference": f"Patient/{user_id}"},
        "code": {
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
                "code": "DRG" if dur_alert.alert_type == "contraindication" else "DUPTHPY",
                "display": dur_alert.alert_type,
            }]
        },
        "detail": dur_alert.description,
        "implicated": [
            {"display": dur_alert.medication_a},
            {"display": dur_alert.medication_b},
        ],
        "mitigation": [{"action": {"text": dur_alert.recommendation}}],
    }


def to_fhir_bundle(resources: list) -> dict:
    """여러 FHIR 리소스를 Bundle로 묶기"""
    return {
        "resourceType": "Bundle",
        "type": "collection",
        "timestamp": datetime.utcnow().isoformat(),
        "total": len(resources),
        "entry": [{"resource": r} for r in resources],
    }


def _map_gender(gender: str) -> str:
    mapping = {"남": "male", "여": "female", "남성": "male", "여성": "female", "M": "male", "F": "female"}
    return mapping.get(gender, "unknown")


def _map_category(category: str) -> str:
    mapping = {"prescription": "inpatient", "otc": "outpatient", "supplement": "community", "herbal": "community"}
    return mapping.get(category, "community")
