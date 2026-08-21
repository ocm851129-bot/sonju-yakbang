/**
 * Edge AI / 오프라인 DUR 분석 엔진
 * 네트워크 없이도 기본적인 병용금기 검사가 가능합니다.
 * 서버 불가 시 로컬에서 Rule Engine을 실행합니다.
 */

const OFFLINE_DUR_RULES = [
    { drugA: "와파린", drugB: "아스피린", severity: "high", desc: "출혈 위험이 크게 증가합니다", rec: "의사와 상담하세요" },
    { drugA: "와파린", drugB: "오메가3", severity: "medium", desc: "출혈 경향이 증가할 수 있습니다", rec: "출혈 징후를 관찰하세요" },
    { drugA: "와파린", drugB: "은행잎", severity: "high", desc: "항응고 작용이 강화됩니다", rec: "병용을 피하세요" },
    { drugA: "메트포르민", drugB: "알코올", severity: "high", desc: "유산산증 위험이 증가합니다", rec: "음주를 삼가세요" },
    { drugA: "스타틴", drugB: "자몽", severity: "medium", desc: "약물 대사를 방해합니다", rec: "자몽 섭취를 피하세요" },
    { drugA: "혈압약", drugB: "진통소염제", severity: "medium", desc: "혈압약 효과가 감소합니다", rec: "아세트아미노펜으로 대체 고려" },
    { drugA: "당뇨약", drugB: "스테로이드", severity: "high", desc: "혈당을 높여 당뇨약 효과를 감소시킵니다", rec: "혈당 모니터링 강화" },
    { drugA: "디곡신", drugB: "아미오다론", severity: "high", desc: "디곡신 혈중농도 상승 위험", rec: "용량 감량 필요" },
    { drugA: "씨프로플록사신", drugB: "제산제", severity: "medium", desc: "항생제 흡수를 방해합니다", rec: "2시간 이상 간격 복용" },
    { drugA: "클로피도그렐", drugB: "오메프라졸", severity: "medium", desc: "항혈소판 효과 감소 가능", rec: "다른 위산억제제 고려" },
    { drugA: "리튬", drugB: "이부프로펜", severity: "high", desc: "리튬 독성 위험", rec: "리튬 농도 모니터링 필요" },
    { drugA: "ACE억제제", drugB: "칼륨보충제", severity: "high", desc: "고칼륨혈증 위험", rec: "칼륨 수치 확인" },
];

// 오프라인 바이탈 경고 룰
const VITAL_RULES = {
    systolic: [
        { min: 180, severity: "emergency", msg: "혈압이 매우 높습니다. 즉시 병원에 가세요." },
        { min: 140, severity: "warning", msg: "혈압이 높습니다. 안정 후 30분 뒤 재측정하세요." },
    ],
    diastolic: [
        { min: 120, severity: "emergency", msg: "이완기 혈압이 위험 수준입니다." },
    ],
    blood_sugar: [
        { min: 300, severity: "emergency", msg: "혈당이 매우 높습니다. 즉시 병원에 가세요." },
        { min: 200, severity: "warning", msg: "혈당이 높습니다. 수분 섭취 후 재측정하세요." },
        { max: 70, severity: "emergency", msg: "저혈당입니다. 당분을 섭취하세요." },
    ],
    heart_rate: [
        { min: 150, severity: "emergency", msg: "심박수가 매우 높습니다." },
        { max: 40, severity: "emergency", msg: "심박수가 매우 낮습니다." },
    ],
    spo2: [
        { max: 90, severity: "emergency", msg: "산소포화도가 낮습니다. 즉시 병원에 가세요." },
    ],
};

/**
 * 오프라인 DUR 분석 (서버 불가 시 로컬 실행)
 */
function offlineDURCheck(medications) {
    const alerts = [];

    for (let i = 0; i < medications.length; i++) {
        for (let j = i + 1; j < medications.length; j++) {
            const medA = medications[i].name?.toLowerCase() || '';
            const medB = medications[j].name?.toLowerCase() || '';
            const ingA = medications[i].ingredient?.toLowerCase() || '';
            const ingB = medications[j].ingredient?.toLowerCase() || '';

            for (const rule of OFFLINE_DUR_RULES) {
                const aMatch = medA.includes(rule.drugA) || ingA.includes(rule.drugA);
                const bMatch = medB.includes(rule.drugB) || ingB.includes(rule.drugB);
                const aMatchReverse = medA.includes(rule.drugB) || ingA.includes(rule.drugB);
                const bMatchReverse = medB.includes(rule.drugA) || ingB.includes(rule.drugA);

                if ((aMatch && bMatch) || (aMatchReverse && bMatchReverse)) {
                    alerts.push({
                        severity: rule.severity,
                        medication_a: medications[i].name,
                        medication_b: medications[j].name,
                        description: rule.desc,
                        recommendation: rule.rec,
                        source: "offline_edge_ai",
                    });
                }
            }
        }
    }

    return {
        alerts,
        total_risk_score: alerts.reduce((sum, a) => sum + (a.severity === 'high' ? 30 : 15), 0),
        summary: alerts.length === 0
            ? "오프라인 검사: 특별한 문제가 발견되지 않았습니다."
            : `오프라인 검사: 주의 필요 ${alerts.length}건`,
        data_source: "offline_edge_ai",
    };
}

/**
 * 오프라인 바이탈 사인 경고
 */
function offlineVitalCheck(type, value) {
    const rules = VITAL_RULES[type] || [];
    for (const rule of rules) {
        if (rule.min && value >= rule.min) return { severity: rule.severity, message: rule.msg };
        if (rule.max && value <= rule.max) return { severity: rule.severity, message: rule.msg };
    }
    return null;
}

/**
 * 네트워크 상태 확인
 */
function isOffline() {
    return !navigator.onLine;
}
