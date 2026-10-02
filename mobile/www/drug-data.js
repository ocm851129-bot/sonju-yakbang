/**
 * 손주약방 - 기기 내 의약품 데이터베이스 (오프라인/백엔드 불가 시 사용)
 *
 * 백엔드(식약처 API)가 없을 때도 다음이 동작하도록 고령자 다빈도 의약품 정보를 담습니다.
 *   - 이미지 OCR 결과 텍스트에서 약 이름 찾기 (findDrugsInText)
 *   - 약 이름 검색 (lookupLocalDrug)
 *   - OCR 인식 약품 정보 보강 (enrichWithLocalDrug)
 *
 * match: OCR/검색어에서 이 약을 식별하기 위한 부분일치 키워드(제품명·성분·별칭)
 */
const LOCAL_DRUG_DB = [
    {
        display: '아모디핀정 5mg', ingredient: '암로디핀베실산염', category: 'prescription', etc_otc: '전문의약품',
        class_name: '혈압강하제', match: ['아모디핀', '암로디핀', '노바스크', 'amlodipine'],
        effect: '혈압을 낮추고 협심증(가슴 통증)을 완화합니다.',
        usage: '1일 1회 1정을 복용합니다.',
        caution: '어지러움이 있을 수 있으니 천천히 일어나세요. 자몽주스를 피하세요.',
    },
    {
        display: '메트포르민정 500mg', ingredient: '메트포르민염산염', category: 'prescription', etc_otc: '전문의약품',
        class_name: '당뇨병용제', match: ['메트포르민', '다이아벡스', '글루코파지', 'metformin'],
        effect: '제2형 당뇨병 환자의 혈당을 조절합니다.',
        usage: '1일 2~3회 식사 중 또는 식후에 복용합니다.',
        caution: '음주 시 유산산증 위험이 있으니 삼가세요. CT 조영제 촬영 전후 복용을 중단하세요.',
    },
    {
        display: '아토르바스타틴칼슘정 20mg', ingredient: '아토르바스타틴칼슘', category: 'prescription', etc_otc: '전문의약품',
        class_name: '고지혈증용제', match: ['아토르바스타틴', '리피토', 'atorvastatin'],
        effect: '나쁜 콜레스테롤을 낮춰 혈관 질환을 예방합니다.',
        usage: '1일 1회 저녁 또는 취침 전에 복용합니다.',
        caution: '근육통이 심하거나 소변색이 진해지면 병원에 방문하세요. 자몽주스를 피하세요.',
    },
    {
        display: '심바스타틴정 20mg', ingredient: '심바스타틴', category: 'prescription', etc_otc: '전문의약품',
        class_name: '고지혈증용제', match: ['심바스타틴', '조코', 'simvastatin'],
        effect: '콜레스테롤을 낮춰 심장병을 예방합니다.',
        usage: '1일 1회 저녁에 복용합니다.',
        caution: '자몽주스와 병용하지 마세요. 근육통 발생 시 상담하세요.',
    },
    {
        display: '아스피린프로텍트정 100mg', ingredient: '아스피린', category: 'otc', etc_otc: '일반의약품',
        class_name: '항혈전제', match: ['아스피린', '아스트릭스', 'aspirin'],
        effect: '피를 묽게 하여 심근경색·뇌졸중을 예방합니다.',
        usage: '1일 1회 100mg을 복용합니다.',
        caution: '위장출혈 위험이 있으니 검은 변이 보이면 병원에 방문하세요.',
    },
    {
        display: '와파린나트륨정 2mg', ingredient: '와파린나트륨', category: 'prescription', etc_otc: '전문의약품',
        class_name: '항응고제', match: ['와파린', '쿠마딘', 'warfarin'],
        effect: '혈액이 굳는 것을 막아 혈전을 예방합니다.',
        usage: '의사가 정한 용량을 매일 같은 시간에 복용합니다.',
        caution: '출혈에 주의하세요. 청국장·녹색채소·오메가3·은행잎과의 병용에 주의가 필요합니다.',
    },
    {
        display: '리시노프릴정 10mg', ingredient: '리시노프릴', category: 'prescription', etc_otc: '전문의약품',
        class_name: '혈압강하제(ACE억제제)', match: ['리시노프릴', '제스트릴', 'lisinopril', 'ace억제제'],
        effect: '혈압을 낮추고 심장을 보호합니다.',
        usage: '1일 1회 복용합니다.',
        caution: '마른기침이 있을 수 있습니다. 칼륨보충제와 병용 시 고칼륨혈증에 주의하세요.',
    },
    {
        display: '텔미사르탄정 40mg', ingredient: '텔미사르탄', category: 'prescription', etc_otc: '전문의약품',
        class_name: '혈압강하제(ARB)', match: ['텔미사르탄', '미카르디스', 'telmisartan', '사르탄'],
        effect: '혈압을 낮춰 뇌졸중·심장병을 예방합니다.',
        usage: '1일 1회 복용합니다.',
        caution: '어지러움이 있을 수 있습니다. 임신 중에는 복용하지 마세요.',
    },
    {
        display: '글리메피리드정 2mg', ingredient: '글리메피리드', category: 'prescription', etc_otc: '전문의약품',
        class_name: '당뇨병용제', match: ['글리메피리드', '아마릴', 'glimepiride'],
        effect: '인슐린 분비를 촉진하여 혈당을 낮춥니다.',
        usage: '1일 1회 아침 식사 직전 또는 식사 중에 복용합니다.',
        caution: '식사를 거르면 저혈당 위험이 있습니다. 사탕을 휴대하세요.',
    },
    {
        display: '란소프라졸캡슐 30mg', ingredient: '란소프라졸', category: 'prescription', etc_otc: '전문의약품',
        class_name: '위산분비억제제', match: ['란소프라졸', '오메프라졸', '판토프라졸', '넥시움', 'prazole'],
        effect: '위산 분비를 줄여 위·식도 질환을 치료합니다.',
        usage: '1일 1회 식전에 복용합니다.',
        caution: '장기 복용 시 의사와 상담하세요.',
    },
    {
        display: '레보티록신나트륨정 0.1mg', ingredient: '레보티록신나트륨', category: 'prescription', etc_otc: '전문의약품',
        class_name: '갑상선호르몬제', match: ['레보티록신', '씬지로이드', 'levothyroxine', '신지로이드'],
        effect: '부족한 갑상선호르몬을 보충합니다.',
        usage: '아침 공복에 물과 함께 복용하고 30분간 음식을 피합니다.',
        caution: '철분·칼슘제와 4시간 이상 간격을 두세요.',
    },
    {
        display: '푸로세미드정 40mg', ingredient: '푸로세미드', category: 'prescription', etc_otc: '전문의약품',
        class_name: '이뇨제', match: ['푸로세미드', '라식스', 'furosemide', '이뇨제'],
        effect: '몸의 과도한 수분을 소변으로 배출해 부종·혈압을 조절합니다.',
        usage: '1일 1~2회 복용합니다(오후 늦게 복용은 피함).',
        caution: '탈수·전해질 이상에 주의하세요. 어지러우면 상담하세요.',
    },
    {
        display: '아세트아미노펜정 500mg', ingredient: '아세트아미노펜', category: 'otc', etc_otc: '일반의약품',
        class_name: '해열진통제', match: ['아세트아미노펜', '타이레놀', 'acetaminophen', 'tylenol'],
        effect: '열을 내리고 통증을 줄여줍니다.',
        usage: '1회 1~2정, 4~6시간 간격으로 복용합니다(1일 4000mg 이내).',
        caution: '음주 후 복용을 피하고, 다른 감기약과 성분이 겹치지 않게 하세요.',
    },
    {
        display: '이부프로펜정 200mg', ingredient: '이부프로펜', category: 'otc', etc_otc: '일반의약품',
        class_name: '소염진통제', match: ['이부프로펜', '부루펜', 'ibuprofen', '진통소염제'],
        effect: '염증과 통증, 열을 줄여줍니다.',
        usage: '식후에 복용합니다.',
        caution: '위장장애·신장에 주의. 혈압약·와파린·리튬과 병용 시 상담하세요.',
    },
    {
        display: '클로피도그렐정 75mg', ingredient: '클로피도그렐', category: 'prescription', etc_otc: '전문의약품',
        class_name: '항혈소판제', match: ['클로피도그렐', '플라빅스', 'clopidogrel'],
        effect: '혈소판이 뭉치는 것을 막아 혈전을 예방합니다.',
        usage: '1일 1회 복용합니다.',
        caution: '출혈에 주의. 오메프라졸과 병용 시 효과가 줄 수 있어 상담이 필요합니다.',
    },
    {
        display: '디곡신정 0.25mg', ingredient: '디곡신', category: 'prescription', etc_otc: '전문의약품',
        class_name: '강심제', match: ['디곡신', 'digoxin'],
        effect: '심장 수축력을 높여 심부전·부정맥을 치료합니다.',
        usage: '의사가 정한 용량을 매일 복용합니다.',
        caution: '메스꺼움·시야 이상 등 중독 증상 시 즉시 병원. 아미오다론과 병용 주의.',
    },
];

/** 텍스트 정규화(공백·특수문자 제거, 소문자) */
function _normalize(s) {
    return String(s || '').toLowerCase().replace(/[\s()\[\]{}·.,/\-_]+/g, '');
}

/** 로컬 DB에서 한 약을 표준 정보 객체로 변환 */
function _toDrugInfo(drug, matchedName) {
    return {
        matched: true,
        item_name: matchedName || drug.display,
        company: '',
        category: drug.category,
        etc_otc: drug.etc_otc,
        class_name: drug.class_name,
        ingredient: drug.ingredient,
        appearance: '',
        storage: '',
        effect: drug.effect,
        usage: drug.usage,
        caution: drug.caution,
        easy_effect: drug.effect,
        easy_usage: drug.usage,
        easy_caution: drug.caution,
        easy_side_effect: '',
        easy_storage: '',
        image_url: '',
        sources: ['기기 내 의약품 DB(오프라인)'],
        is_demo: true,
    };
}

/** 검색어로 로컬 약 정보 조회 (searchDrug 백엔드 폴백) */
function lookupLocalDrug(query) {
    const q = _normalize(query);
    if (!q) return null;
    for (const drug of LOCAL_DRUG_DB) {
        for (const m of drug.match) {
            const nm = _normalize(m);
            if (q.includes(nm) || nm.includes(q)) return _toDrugInfo(drug, query.trim());
        }
        if (_normalize(drug.display).includes(q)) return _toDrugInfo(drug, drug.display);
    }
    return null;
}

/** OCR로 추출된 전체 텍스트에서 약 이름들을 찾아 medications 배열로 반환 */
function findDrugsInText(rawText) {
    const norm = _normalize(rawText);
    const found = [];
    const seen = new Set();
    for (const drug of LOCAL_DRUG_DB) {
        for (const m of drug.match) {
            if (norm.includes(_normalize(m))) {
                if (!seen.has(drug.display)) {
                    seen.add(drug.display);
                    found.push({
                        name: drug.display,
                        ingredient: drug.ingredient,
                        dosage: '1정',
                        frequency: '',
                        category: drug.category,
                        permit: {
                            company: '', etc_otc: drug.etc_otc, class_name: drug.class_name,
                            appearance: '', storage: '',
                            effect: drug.effect, usage: drug.usage, caution: drug.caution,
                            easy_effect: drug.effect, easy_caution: drug.caution,
                            easy_side_effect: '', image_url: '', is_demo: true,
                        },
                    });
                }
                break;
            }
        }
    }
    return found;
}

/** 이미 인식된 약(med)에 로컬 DB 정보를 permit로 보강 */
function enrichWithLocalDrug(med) {
    if (med.permit) return med;
    const info = lookupLocalDrug(med.name || med.ingredient || '');
    if (info) {
        med.ingredient = med.ingredient || info.ingredient;
        med.category = med.category || info.category;
        med.permit = {
            company: '', etc_otc: info.etc_otc, class_name: info.class_name,
            appearance: '', storage: '', effect: info.effect, usage: info.usage, caution: info.caution,
            easy_effect: info.easy_effect, easy_caution: info.easy_caution,
            easy_side_effect: '', image_url: '', is_demo: true,
        };
    }
    return med;
}
