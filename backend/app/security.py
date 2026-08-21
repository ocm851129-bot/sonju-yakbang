"""보안 모듈 - AES-256 암호화 + 데이터 보호

기능:
- 민감 필드 AES-256-GCM 암호화/복호화
- 개인정보(이름, 전화번호)와 건강정보(바이탈) 분리 암호화
- API 통신 보안 헤더 검증
- 감사 로그 (접근 기록)
"""
import os
import base64
import hashlib
import json
from datetime import datetime
from typing import Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.config import SECRET_KEY

# AES-256 키 생성 (SECRET_KEY 기반)
_AES_KEY = hashlib.sha256(SECRET_KEY.encode()).digest()  # 32 bytes = 256 bits
_aesgcm = AESGCM(_AES_KEY)


def encrypt_field(plaintext: str) -> str:
    """민감 필드 AES-256-GCM 암호화
    
    Args:
        plaintext: 암호화할 원본 텍스트
        
    Returns:
        Base64 인코딩된 암호문 (nonce + ciphertext)
    """
    if not plaintext:
        return ""

    nonce = os.urandom(12)  # 96-bit nonce
    ciphertext = _aesgcm.encrypt(nonce, plaintext.encode('utf-8'), None)

    # nonce + ciphertext를 합쳐서 Base64로 인코딩
    encrypted = base64.b64encode(nonce + ciphertext).decode('utf-8')
    return encrypted


def decrypt_field(encrypted: str) -> str:
    """AES-256-GCM 복호화
    
    Args:
        encrypted: Base64 인코딩된 암호문
        
    Returns:
        복호화된 원본 텍스트
    """
    if not encrypted:
        return ""

    try:
        raw = base64.b64decode(encrypted.encode('utf-8'))
        nonce = raw[:12]
        ciphertext = raw[12:]
        plaintext = _aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode('utf-8')
    except Exception:
        return "[복호화 실패]"


def encrypt_health_data(data: dict) -> str:
    """건강 데이터(바이탈, 증상 등) 전체 암호화"""
    json_str = json.dumps(data, ensure_ascii=False)
    return encrypt_field(json_str)


def decrypt_health_data(encrypted: str) -> dict:
    """암호화된 건강 데이터 복호화"""
    decrypted = decrypt_field(encrypted)
    try:
        return json.loads(decrypted)
    except Exception:
        return {}


# ==================== 감사 로그 ====================

_audit_log = []  # MVP: 인메모리. 프로덕션에서는 DB/파일


def log_access(user_id: int, action: str, resource: str, ip: str = ""):
    """데이터 접근 감사 로그 기록"""
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "user_id": user_id,
        "action": action,  # read, write, delete, export
        "resource": resource,  # patient_data, medication, vital_sign
        "ip": ip,
    }
    _audit_log.append(entry)

    # 최근 1000건만 유지 (MVP)
    if len(_audit_log) > 1000:
        _audit_log.pop(0)


def get_audit_log(user_id: Optional[int] = None, limit: int = 50) -> list:
    """감사 로그 조회"""
    if user_id:
        filtered = [e for e in _audit_log if e["user_id"] == user_id]
    else:
        filtered = _audit_log

    return filtered[-limit:]


# ==================== 데이터 마스킹 ====================

def mask_phone(phone: str) -> str:
    """전화번호 마스킹: 010-1234-5678 → 010-****-5678"""
    if len(phone) >= 8:
        return phone[:3] + "-****-" + phone[-4:]
    return "***"


def mask_name(name: str) -> str:
    """이름 마스킹: 홍길동 → 홍*동"""
    if len(name) >= 3:
        return name[0] + "*" * (len(name) - 2) + name[-1]
    elif len(name) == 2:
        return name[0] + "*"
    return "*"
