/**
 * 손주약방 - 프론트엔드 애플리케이션
 * 고령자 친화 AI 건강관리 플랫폼
 */

const API_BASE = window.SONJU_API_BASE || 'http://localhost:8000/api';
let currentUser = null;
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;

// ==================== 글씨 크기 조절 (고령자 접근성) ====================
// 프로필 화면의 슬라이더(80%~150%)로 앱 전체 본문 글씨 크기를 조절한다.
// CSS 변수 --font-scale 를 바꾸면 --font-size-* 가 일괄 확대/축소된다.
const FONT_SCALE_KEY = 'sonju_font_scale';
const FONT_SCALE_MIN = 80;
const FONT_SCALE_MAX = 150;

function setFontScale(percent) {
    let p = parseInt(percent, 10);
    if (isNaN(p)) p = 100;
    p = Math.max(FONT_SCALE_MIN, Math.min(FONT_SCALE_MAX, p));
    document.documentElement.style.setProperty('--font-scale', (p / 100).toString());
    const valueEl = document.getElementById('font-size-value');
    if (valueEl) valueEl.textContent = p + '%';
    const rangeEl = document.getElementById('font-size-range');
    if (rangeEl && parseInt(rangeEl.value, 10) !== p) rangeEl.value = p;
    try { localStorage.setItem(FONT_SCALE_KEY, String(p)); } catch (e) { /* ignore */ }
}

// 헤더의 가−/가＋ 버튼: 현재 배율에서 delta(%)만큼 단계 조절.
function stepFontScale(delta) {
    const cur = Math.round(
        (parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--font-scale')) || 1) * 100
    );
    setFontScale(cur + delta);
}

// 저장된 글씨 크기를 불러와 적용(헤더 표시·배율 동기화). 페이지 로드 시 호출.
function restoreFontScale() {
    let saved = 100;
    try { saved = parseInt(localStorage.getItem(FONT_SCALE_KEY), 10) || 100; } catch (e) { saved = 100; }
    setFontScale(saved);
}

// ==================== 네비게이션 ====================

function navigate(screen) {
    document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
    const target = document.getElementById(`${screen}-screen`);
    if (target) target.classList.add('active');

    // 네비게이션 활성화 상태 업데이트
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    const navMap = { home: 0, health: 1, medications: 2, mystatus: 3, chat: 4 };
    if (navMap[screen] !== undefined) {
        document.querySelectorAll('.nav-item')[navMap[screen]]?.classList.add('active');
    }

    // 나의 건강상태 화면 진입 시 차트 초기화
    if (screen === 'mystatus') {
        setTimeout(() => initHealthChart(), 300);
    }
    // 나만의 투약정보 화면 진입 시 등록 목록 렌더링
    if (screen === 'mymeds' && typeof renderMyMedList === 'function') {
        renderMyMedList();
    }
}

// ==================== 긴급 전화 ====================

function callEmergency() {
    if (confirm('119에 전화를 걸까요?')) {
        window.location.href = 'tel:119';
    }
}

// ==================== 음성 문진 (STT) ====================

async function toggleRecording() {
    const btn = document.getElementById('btn-record');
    const icon = document.getElementById('record-icon');
    const label = document.getElementById('record-label');

    if (!isRecording) {
        // 녹음 시작
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream);
            audioChunks = [];

            mediaRecorder.ondataavailable = (e) => audioChunks.push(e.data);
            mediaRecorder.onstop = async () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                await processVoice(audioBlob);
                stream.getTracks().forEach(track => track.stop());
            };

            mediaRecorder.start();
            isRecording = true;
            btn.classList.add('recording');
            icon.textContent = '⏹️';
            label.textContent = '그만하기';
        } catch (err) {
            alert('마이크 사용을 허용해 주세요.');
        }
    } else {
        // 녹음 중지
        mediaRecorder.stop();
        isRecording = false;
        btn.classList.remove('recording');
        icon.textContent = '🎤';
        label.textContent = '누르고 말하기';
    }
}

async function processVoice(audioBlob) {
    const resultDiv = document.getElementById('voice-result');
    const textDiv = document.getElementById('transcribed-text');
    const analysisDiv = document.getElementById('analysis-result');

    resultDiv.style.display = 'block';
    textDiv.textContent = '음성을 분석하고 있습니다...';

    try {
        const formData = new FormData();
        formData.append('audio', audioBlob, 'recording.webm');
        formData.append('user_id', currentUser?.id || 1);

        const response = await fetch(`${API_BASE}/voice/transcribe?user_id=${currentUser?.id || 1}`, {
            method: 'POST',
            body: formData,
        });

        if (response.ok) {
            const data = await response.json();
            textDiv.textContent = `"${data.text}"`;
            
            if (data.analysis) {
                let html = '<div style="margin-top:12px;">';
                if (data.analysis.symptoms?.length) {
                    html += `<p><strong>증상:</strong> ${data.analysis.symptoms.join(', ')}</p>`;
                }
                if (data.analysis.summary) {
                    html += `<p><strong>요약:</strong> ${data.analysis.summary}</p>`;
                }
                if (data.analysis.urgency === 'emergency') {
                    html += '<p style="color:red;font-weight:bold;">⚠️ 위급 상황이 의심됩니다. 119에 연락하세요.</p>';
                }
                html += '</div>';
                analysisDiv.innerHTML = html;
            }
        } else {
            textDiv.textContent = '음성 인식에 실패했습니다. 다시 시도해 주세요.';
        }
    } catch (err) {
        // 데모 모드: 서버 없이도 UI 동작 확인
        textDiv.textContent = '"오늘 아침부터 머리가 좀 아프고 어지러워요"';
        analysisDiv.innerHTML = `
            <div style="margin-top:12px;">
                <p><strong>증상:</strong> 두통, 어지러움</p>
                <p><strong>요약:</strong> 아침부터 두통과 어지러움 증상</p>
                <p><strong>권고:</strong> 혈압을 측정해 보시고, 증상이 지속되면 병원에 가세요.</p>
            </div>`;
    }
}

// ==================== 처방전 OCR ====================

// 분석 진행 표시기: 서버 OCR은 한 번의 AI 호출이라 정확한 %는 알 수 없으므로,
// 단계별 안내 메시지 + 진행 바(90%까지 서서히 채움) + 경과 시간으로
// "멈춘 게 아니라 분석 중"임을 어르신이 알 수 있게 보여준다.
function startAnalyzeProgress(container, title) {
    const stages = [
        '📤 사진을 올리는 중이에요…',
        '🔍 AI가 글자를 읽는 중이에요…',
        '💊 약 정보를 확인하는 중이에요…',
        '📋 결과를 정리하는 중이에요…',
    ];
    const started = Date.now();
    let pct = 8;
    let stageIdx = -1;
    container.innerHTML =
        '<div class="analyze-progress">' +
          '<p class="analyze-title">' + title + '</p>' +
          '<div class="analyze-bar"><div class="analyze-bar-fill" id="analyze-bar-fill"></div></div>' +
          '<p class="analyze-stage" id="analyze-stage">' + stages[0] + '</p>' +
          '<p class="analyze-elapsed" id="analyze-elapsed">⏱ 0초</p>' +
          '<p class="analyze-hint">보통 5~15초 걸려요. 처음 한 번은 조금 더 걸릴 수 있어요.</p>' +
        '</div>';
    const fill = container.querySelector('#analyze-bar-fill');
    const stageEl = container.querySelector('#analyze-stage');
    const elapsedEl = container.querySelector('#analyze-elapsed');
    if (fill) fill.style.width = pct + '%';
    const timer = setInterval(() => {
        const secs = Math.floor((Date.now() - started) / 1000);
        // 90%까지 서서히(처음 빠르게, 뒤로 갈수록 천천히) 채운다. 100%는 완료 때만.
        pct = Math.min(90, pct + Math.max(0.5, (90 - pct) * 0.06));
        if (fill) fill.style.width = pct.toFixed(0) + '%';
        if (elapsedEl) elapsedEl.textContent = '⏱ ' + secs + '초';
        const idx = secs < 2 ? 0 : secs < 6 ? 1 : secs < 12 ? 2 : 3;
        if (idx !== stageIdx) { stageIdx = idx; if (stageEl) stageEl.textContent = stages[idx]; }
    }, 300);
    return {
        done() {
            clearInterval(timer);
            if (fill) fill.style.width = '100%';
        },
    };
}

async function handleImage(event) {
    const file = event.target.files[0];
    if (!file) return;

    const resultDiv = document.getElementById('ocr-result');
    const medsDiv = document.getElementById('ocr-medications');
    resultDiv.style.display = 'block';
    const progress = startAnalyzeProgress(medsDiv, '💊 처방전을 분석하고 있어요');

    // 1) 백엔드(식약처 API) 우선 시도 — 서버가 있으면 가장 정확
    try {
        const formData = new FormData();
        formData.append('image', file);
        const response = await fetch(`${API_BASE}/ocr/prescription?user_id=${currentUser?.id || 1}`, {
            method: 'POST',
            body: formData,
        });
        if (response.ok) {
            const data = await response.json();
            if (data && (data.medications || []).length > 0) {
                progress.done();
                saveRecognizedMeds(data.medications);
                renderOCRResult(data);
                return;
            }
        }
    } catch (err) {
        /* 백엔드 불가 → 아래 기기 내 OCR로 진행 */
    }

    // 2) 백엔드 불가/실패 시 → 기기 내(오프라인) OCR 실행
    progress.done();
    await clientSideOCR(file, medsDiv);
}

/** 영양제·건강기능식품(및 일반 제품) 통합 스캔.
 *  백엔드가 품목을 자동 분류(의약품/건강기능식품)해 정보를 보강한다. */
async function handleProductScan(event) {
    const file = event.target.files[0];
    if (!file) return;

    const resultDiv = document.getElementById('ocr-result');
    const medsDiv = document.getElementById('ocr-medications');
    resultDiv.style.display = 'block';
    const progress = startAnalyzeProgress(medsDiv, '🌿 제품을 분석하고 있어요');

    // 1) 백엔드(통합 스캔) 우선
    try {
        const formData = new FormData();
        formData.append('image', file);
        const response = await fetch(`${API_BASE}/ocr/product?user_id=${currentUser?.id || 1}`, {
            method: 'POST',
            body: formData,
        });
        if (response.ok) {
            const data = await response.json();
            if (data && (data.medications || []).length > 0) {
                progress.done();
                saveRecognizedMeds(data.medications);
                renderOCRResult(data);
                return;
            }
        }
    } catch (err) {
        /* 백엔드 불가 → 아래 기기 내 OCR */
    }

    // 2) 백엔드 불가/실패 시 → 기기 내(오프라인) OCR (의약품+건강기능식품 DB)
    progress.done();
    await clientSideOCR(file, medsDiv);
}

/** 브라우저에서 Tesseract.js로 이미지 글자를 직접 인식하고, 로컬 DB로 약을 찾는다. */
async function clientSideOCR(file, medsDiv) {
    if (typeof Tesseract === 'undefined') {
        // OCR 엔진 로드 실패 → 데모 데이터로 대체
        renderOCRDemo(medsDiv, '기기 내 OCR 엔진을 불러오지 못했습니다. 예시 결과를 표시합니다.');
        return;
    }
    try {
        medsDiv.innerHTML = '<p>📷 사진에서 글자를 읽고 있습니다...</p>' +
            '<div class="ocr-progress"><div class="ocr-progress-bar" id="ocr-progress-bar"></div></div>' +
            '<p class="sub-text" id="ocr-progress-text">잠시만 기다려 주세요 (최초 1회는 조금 오래 걸립니다)</p>';

        const { data } = await Tesseract.recognize(file, 'kor+eng', {
            logger: (m) => {
                if (m.status === 'recognizing text') {
                    const pct = Math.round((m.progress || 0) * 100);
                    const bar = document.getElementById('ocr-progress-bar');
                    const txt = document.getElementById('ocr-progress-text');
                    if (bar) bar.style.width = pct + '%';
                    if (txt) txt.textContent = `글자 인식 중... ${pct}%`;
                }
            },
        });

        const rawText = (data && data.text) ? data.text : '';
        const meds = findDrugsInText(rawText);

        if (meds.length > 0) {
            saveRecognizedMeds(meds);
            renderOCRResult({
                medications: meds,
                raw_text: rawText,
                confidence: (data.confidence || 0) / 100,
                drug_info_source: '기기 내 OCR + 기기 내 의약품 DB(오프라인)',
                ocr_engine: 'on-device',
            });
        } else {
            // 글자는 읽었지만 아는 약을 못 찾음 → 인식 텍스트 + 수동 검색 안내
            renderOCRNoMatch(medsDiv, rawText);
        }
    } catch (err) {
        renderOCRDemo(medsDiv, '사진 인식에 실패했습니다. 예시 결과를 표시합니다.');
    }
}

/** OCR로 인식/추가된 약을 localStorage에 저장 (오프라인 DUR 검사에 사용) */
function saveRecognizedMeds(medications) {
    try {
        const existing = JSON.parse(localStorage.getItem('my_medications') || '[]');
        const names = new Set(existing.map((m) => m.name));
        for (const m of medications) {
            if (m.name && !names.has(m.name)) {
                existing.push({ name: m.name, ingredient: m.ingredient || '', category: m.category || 'prescription' });
                names.add(m.name);
            }
        }
        localStorage.setItem('my_medications', JSON.stringify(existing));
    } catch (e) { /* ignore */ }
}

function renderOCRNoMatch(medsDiv, rawText) {
    const preview = escapeHtml((rawText || '').trim().slice(0, 300)) || '(글자를 인식하지 못했습니다)';
    medsDiv.innerHTML = `
        <p>사진에서 아래 글자를 읽었지만, 등록된 약 정보를 찾지 못했어요.</p>
        <div class="ocr-rawtext">${preview}</div>
        <p class="sub-text" style="margin-top:12px;">아래 <strong>‘약 이름으로 정보 찾기’</strong>에 약 이름을 입력해 검색해 주세요.</p>`;
}

function renderOCRDemo(medsDiv, notice) {
    const demo = {
        hospital: '서울내과의원', diagnosis: '본태성 고혈압', date: '2026-06-10',
        medications: [
            { name: '아모디핀정 5mg', ingredient: '암로디핀', dosage: '1정', frequency: '1일 1회 아침 식후', category: 'prescription' },
            { name: '메트포르민정 500mg', ingredient: '메트포르민', dosage: '1정', frequency: '1일 2회 식후', category: 'prescription' },
            { name: '아토르바스타틴정 20mg', ingredient: '아토르바스타틴', dosage: '1정', frequency: '1일 1회 취침 전', category: 'prescription' },
        ],
        confidence: 0.92,
        drug_info_source: '기기 내 의약품 DB(오프라인)',
    };
    demo.medications.forEach((m) => enrichWithLocalDrug(m));
    saveRecognizedMeds(demo.medications);
    if (notice) medsDiv.innerHTML = `<p class="sub-text">${escapeHtml(notice)}</p>`;
    renderOCRResult(demo);
}

function escapeHtml(s) {
    return String(s || '').replace(/[&<>"']/g, c => (
        { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));
}

// 식약처 허가정보를 어르신 친화 카드로 렌더링 (permit 객체 또는 drug-info 응답 공용)
function renderDrugInfoCard(info, opts) {
    opts = opts || {};
    const otc = info.etc_otc || (info.category === 'otc' ? '일반의약품' : info.category === 'supplement' ? '건강기능식품' : '전문의약품');
    const rows = [
        ['💡 효능·효과', info.easy_effect || info.effect],
        ['🕐 복용 방법', info.easy_usage || info.usage],
        ['⚠️ 주의사항', info.easy_caution || info.caution],
        ['🤒 부작용', info.easy_side_effect],
        ['📦 보관 방법', info.easy_storage || info.storage],
        ['🧪 성분', info.ingredient],
        ['👁 생김새', info.appearance],
    ].filter(r => r[1]);

    let inner = '';
    if (opts.showTitle && (info.item_name || info.company)) {
        inner += `<div class="drug-card-title">${escapeHtml(info.item_name)}</div>`;
    }
    let tags = '';
    if (otc) tags += `<span class="drug-tag">${escapeHtml(otc)}</span>`;
    if (info.class_name) tags += `<span class="drug-tag">${escapeHtml(info.class_name)}</span>`;
    if (info.company) tags += `<span class="drug-tag drug-tag-plain">${escapeHtml(info.company)}</span>`;
    if (tags) inner += `<div class="drug-tags">${tags}</div>`;

    if (info.image_url) {
        inner += `<img class="drug-pill-img" src="${escapeHtml(info.image_url)}" alt="약 사진" loading="lazy">`;
    }

    for (const [label, val] of rows) {
        inner += `<div class="drug-info-row"><div class="drug-info-label">${label}</div><div class="drug-info-val">${escapeHtml(val)}</div></div>`;
    }

    if (info.is_demo) {
        inner += `<p class="drug-demo-note">※ 예시 정보입니다. 공공데이터 인증키 연결 시 실시간 허가정보가 표시됩니다.</p>`;
    }
    return `<div class="drug-info-card">${inner}</div>`;
}

function renderOCRResult(data) {
    const medsDiv = document.getElementById('ocr-medications');
    let html = '';

    if (data.hospital) html += `<p><strong>병원:</strong> ${escapeHtml(data.hospital)}</p>`;
    if (data.diagnosis) html += `<p><strong>진단:</strong> ${escapeHtml(data.diagnosis)}</p>`;
    if (data.date) html += `<p><strong>처방일:</strong> ${escapeHtml(data.date)}</p>`;
    if (data.confidence) html += `<p><strong>인식 정확도:</strong> ${(data.confidence * 100).toFixed(0)}%</p>`;

    html += '<hr style="margin:12px 0;">';

    (data.medications || []).forEach((med, idx) => {
        // permit 정보가 없으면 기기 내 의약품 DB로 보강
        if (!med.permit && typeof enrichWithLocalDrug === 'function') enrichWithLocalDrug(med);
        const hasPermit = med.permit && (med.permit.easy_effect || med.permit.effect || med.permit.easy_caution || med.permit.caution);
        html += `
            <div class="med-item" style="border-color: var(--primary);">
                <span class="med-name"><strong>${escapeHtml(med.name)}</strong></span>
                <span style="font-size:14px;color:#555;">${escapeHtml(med.frequency || '')}</span>
            </div>`;
        if (hasPermit) {
            const merged = Object.assign({ item_name: med.name, ingredient: med.ingredient, category: med.category }, med.permit);
            const isSupp = med.category === 'supplement' || med.product_type === 'health_functional_food' || (med.permit && med.permit.kind === 'health_food');
            const detailLabel = isSupp ? '🌿 이 영양제는 어떤 제품인가요?' : '📋 이 약은 어떤 약인가요?';
            html += `
                <button class="btn-drug-detail" onclick="toggleDrugDetail(${idx})">${detailLabel}</button>`;
            html += `
                <div class="drug-detail-wrap" id="drug-detail-${idx}" style="display:none;">
                    ${renderDrugInfoCard(merged, { showTitle: false })}
                </div>`;
        }
    });

    if (data.drug_info_source) {
        html += `<p class="drug-source-line">ℹ️ 약품정보 출처: ${escapeHtml(data.drug_info_source)}</p>`;
    }

    html += `<button class="btn-take-med" style="width:100%;margin-top:16px;" onclick="alert('약 목록에 추가되었습니다!')">
        ✅ 내 약 목록에 추가하기
    </button>`;

    medsDiv.innerHTML = html;
}

function toggleDrugDetail(idx) {
    const el = document.getElementById(`drug-detail-${idx}`);
    if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none';
}

// 약 이름으로 식약처 허가정보 직접 검색
async function searchDrug() {
    const input = document.getElementById('drug-search-input');
    const resultDiv = document.getElementById('drug-search-result');
    const name = (input.value || '').trim();
    if (!name) {
        resultDiv.innerHTML = '<p class="sub-text">약 이름을 입력해주세요.</p>';
        return;
    }
    resultDiv.innerHTML = '<p class="sub-text">약품 정보를 찾고 있습니다...</p>';

    // 1) 백엔드(식약처 API) 시도
    try {
        const response = await fetch(`${API_BASE}/drug-info/search?name=${encodeURIComponent(name)}`);
        if (response.ok) {
            const info = await response.json();
            if (info && info.matched) {
                resultDiv.innerHTML = renderDrugInfoCard(info, { showTitle: true });
                if (info.easy_effect || info.effect) speak(`${info.item_name}. ${info.easy_effect || info.effect}`);
                return;
            }
        }
    } catch (err) {
        /* 백엔드 불가 → 기기 내 DB로 폴백 */
    }

    // 2) 기기 내(오프라인) 의약품 DB 폴백
    const local = (typeof lookupLocalDrug === 'function') ? lookupLocalDrug(name) : null;
    if (local) {
        resultDiv.innerHTML = renderDrugInfoCard(local, { showTitle: true });
        speak(`${local.item_name}. ${local.easy_effect}`);
    } else {
        resultDiv.innerHTML = `<p class="sub-text">'${escapeHtml(name)}'에 대한 정보를 찾지 못했습니다. 약 이름을 정확히 입력해 주세요.<br>(예: 아모디핀, 메트포르민, 타이레놀)</p>`;
    }
}

// ==================== 병용 확인 (새 제품 vs 기존 복용약) ====================

// 데모 시나리오: 평소 복용 중인 약(처방전 1·2) + 만성질환
const DEMO_CURRENT_MEDS = [
    { name: '자렐토 15mg', ingredients: ['리바록사반'] },
    { name: '콩코르 2.5mg', ingredients: ['비소프롤롤'] },
    { name: '울트라셋이알세미정', ingredients: ['아세트아미노펜', '트라마돌염산염'] },
];
const DEMO_CONDITIONS = ['고혈압', '심방세동'];

// 예시 제품의 성분(백엔드 API를 못 쓰는 오프라인에서도 동작하도록)
const EXAMPLE_INGREDIENTS = {
    '펠루비서방정': ['펠루비프로펜'],
    '판피린': ['아세트아미노펜', '클로르페니라민말레산염', 'DL-메틸에페드린염산염', '카페인무수물', '구아이페네신', '티페피딘시트르산염'],
    '은행잎추출물': ['은행엽추출물', '비타민E'],
};

const TIER_STYLE = {
    danger: { color: 'var(--danger)', bg: '#FDECEA', icon: '🔴' },
    caution: { color: 'var(--warning)', bg: '#FFF4E5', icon: '🟡' },
    info: { color: 'var(--safe)', bg: '#EAF6EC', icon: '🟢' },
    none: { color: 'var(--safe)', bg: '#EAF6EC', icon: '✅' },
};

async function checkInteraction(presetName) {
    const input = document.getElementById('interaction-input');
    const resultDiv = document.getElementById('interaction-result');
    const name = (presetName || (input && input.value) || '').trim();
    if (input && presetName) input.value = presetName;
    if (!name) {
        resultDiv.innerHTML = '<p class="sub-text">새로 드시려는 약·영양제 이름을 입력해주세요.</p>';
        return;
    }
    resultDiv.innerHTML = '<p class="sub-text">기존에 드시는 약과 비교해 확인하고 있어요...</p>';

    // 기존 복용약: 내 약(localStorage) 우선, 없으면 데모 시나리오
    let currentMeds = [];
    try { currentMeds = JSON.parse(localStorage.getItem('my_medications') || '[]'); } catch (e) { currentMeds = []; }
    if (!Array.isArray(currentMeds) || currentMeds.length === 0) currentMeds = DEMO_CURRENT_MEDS;

    const payload = {
        new_product: { name: name, ingredients: EXAMPLE_INGREDIENTS[name] || [] },
        current_medications: currentMeds,
        conditions: DEMO_CONDITIONS,
        resolve_ingredients: true,
    };

    try {
        const res = await fetch(`${API_BASE}/dur/check-interaction`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        if (res.ok) {
            renderInteractionResult(await res.json(), resultDiv);
            return;
        }
    } catch (err) { /* 오프라인 폴백 */ }

    resultDiv.innerHTML = '<p class="sub-text">지금은 확인이 어려워요. 잠시 후 다시 시도하거나, 약사·의사에게 문의하세요.</p>';
}

function renderInteractionResult(data, resultDiv) {
    const overall = TIER_STYLE[data.overall_tier] || TIER_STYLE.none;
    let html = '';

    html += `<div class="interaction-headline" style="border-color:${overall.color}">
        <div class="ix-head-title">${overall.icon} ${escapeHtml(data.summary || data.headline)}</div>
        <div class="ix-head-sub">${escapeHtml(data.intro || '')}</div>
    </div>`;

    if (!data.findings || data.findings.length === 0) {
        html += `<div class="ix-card" style="border-left-color:var(--safe);background:${TIER_STYLE.none.bg}">
            <div class="ix-what">✅ 지금 드시는 약과 함께 복용할 때 특별히 확인된 위험은 없어요.</div>
            <div class="ix-how">그래도 몸에 이상이 느껴지면 약사·의사와 상담하세요.</div>
        </div>`;
    } else {
        data.findings.forEach(f => {
            const st = TIER_STYLE[f.tier] || TIER_STYLE.info;
            html += `<div class="ix-card" style="border-left-color:${st.color};background:${st.bg}">
                <div class="ix-badge" style="background:${st.color}">${st.icon} ${escapeHtml(f.label)}</div>
                <div class="ix-title">${escapeHtml(f.title)}</div>
                <div class="ix-row"><span class="ix-key">무엇이</span><span>${escapeHtml(f.what)}</span></div>
                <div class="ix-row"><span class="ix-key">왜</span><span>${escapeHtml(f.why)}</span></div>
                <div class="ix-row"><span class="ix-key">어떻게</span><span>${escapeHtml(f.how)}</span></div>
                <div class="ix-basis">근거: ${escapeHtml(f.basis)}</div>
            </div>`;
        });
    }

    if (data.safety_notice) {
        html += `<div class="ix-safety">🛡️ ${escapeHtml(data.safety_notice)}</div>`;
    }
    if (data.disclaimer) {
        html += `<p class="drug-demo-note">※ ${escapeHtml(data.disclaimer)}</p>`;
    }
    resultDiv.innerHTML = html;

    // 어르신 친화: 가장 중요한 안내를 음성으로
    if (typeof speak === 'function' && data.findings && data.findings.length) {
        const top = data.findings[0];
        speak(`${top.what} ${top.how}`);
    }
}

// ==================== 나만의 투약정보 (등록·저장·분석) ====================

function getUserId() {
    try { return JSON.parse(localStorage.getItem('user_id')) || 1; } catch (e) { return 1; }
}

function loadMyMeds() {
    try { return JSON.parse(localStorage.getItem('my_medications') || '[]'); } catch (e) { return []; }
}

function saveMyMeds(meds) {
    localStorage.setItem('my_medications', JSON.stringify(meds));
    // 백엔드 DB에도 동기화 (온라인일 때만, 실패해도 무시)
    fetch(`${API_BASE}/medications/bulk/${getUserId()}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ medications: meds, replace: true }),
    }).catch(() => {});
}

function renderMyMedList() {
    const meds = loadMyMeds();
    const wrap = document.getElementById('mymed-list');
    const countEl = document.getElementById('mymed-count');
    if (countEl) countEl.textContent = `(${meds.length})`;
    if (!wrap) return;
    if (meds.length === 0) {
        wrap.innerHTML = '<p class="sub-text">아직 등록한 약이 없어요. 위에서 약을 추가해보세요.</p>';
        return;
    }
    const catLabel = { prescription: '전문', otc: '일반', supplement: '영양제' };
    wrap.innerHTML = meds.map((m, i) => `
        <div class="mymed-item">
            <div class="mymed-item-main">
                <span class="mymed-item-name">${escapeHtml(m.name)}</span>
                <span class="mymed-item-tag">${catLabel[m.category] || ''}</span>
            </div>
            <div class="mymed-item-sub">${escapeHtml([m.ingredient, m.frequency].filter(Boolean).join(' · '))}</div>
            <button class="mymed-del" onclick="deleteMyMed(${i})" aria-label="삭제">✕</button>
        </div>`).join('');
}

function addMyMed() {
    const name = (document.getElementById('mymed-name').value || '').trim();
    if (!name) { alert('약 이름을 입력해주세요.'); return; }
    const med = {
        name,
        ingredient: (document.getElementById('mymed-ingredient').value || '').trim(),
        frequency: (document.getElementById('mymed-frequency').value || '').trim(),
        category: document.getElementById('mymed-category').value || 'prescription',
    };
    // 성분을 입력 안 했고 예시 약이면 자동 보강
    if (!med.ingredient && typeof EXAMPLE_INGREDIENTS !== 'undefined' && EXAMPLE_INGREDIENTS[name]) {
        med.ingredient = EXAMPLE_INGREDIENTS[name].join(', ');
    }
    const meds = loadMyMeds();
    meds.push(med);
    saveMyMeds(meds);
    renderMyMedList();
    // 입력창 비우기
    ['mymed-name', 'mymed-ingredient', 'mymed-frequency'].forEach(id => document.getElementById(id).value = '');
    document.getElementById('mymed-name').focus();
}

function deleteMyMed(idx) {
    const meds = loadMyMeds();
    meds.splice(idx, 1);
    saveMyMeds(meds);
    renderMyMedList();
}

async function analyzeMyMeds() {
    const meds = loadMyMeds();
    const resultDiv = document.getElementById('mymed-analysis');
    if (meds.length < 2) {
        resultDiv.innerHTML = '<p class="sub-text">약을 2개 이상 등록하면 함께 드셔도 되는지 분석해 드려요.</p>';
        return;
    }
    resultDiv.innerHTML = '<p class="sub-text">등록하신 약들을 서로 비교해 분석하고 있어요...</p>';

    // 1) 백엔드: DB 저장 후 전체 분석
    try {
        await fetch(`${API_BASE}/medications/bulk/${getUserId()}`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ medications: meds, replace: true }),
        });
        const res = await fetch(`${API_BASE}/medications/analyze/${getUserId()}`);
        if (res.ok) {
            renderInteractionResult(await res.json(), resultDiv);
            return;
        }
    } catch (err) { /* 오프라인 폴백 */ }

    resultDiv.innerHTML = '<p class="sub-text">지금은 분석이 어려워요. 인터넷 연결을 확인하거나 잠시 후 다시 시도해주세요.</p>';
}

// ==================== DUR 분석 ====================

async function runDURCheck() {
    const resultDiv = document.getElementById('dur-result');
    resultDiv.style.display = 'block';
    resultDiv.innerHTML = '<p>🔍 약물 안전성을 검사하고 있습니다...</p>';

    // 검사 대상 약 목록 확보: localStorage(내 약) → 없으면 데모 기본값
    let localMeds = [];
    try { localMeds = JSON.parse(localStorage.getItem('my_medications') || '[]'); } catch (e) { localMeds = []; }
    if (!Array.isArray(localMeds) || localMeds.length === 0) {
        localMeds = [
            { name: '메트포르민정 500mg', ingredient: '메트포르민', category: 'prescription' },
            { name: '심바스타틴정 20mg', ingredient: '심바스타틴', category: 'prescription' },
            { name: '아스피린정 100mg', ingredient: '아스피린', category: 'otc' },
        ];
    }

    // 1) 온라인 & 백엔드 가능하면 서버 DUR 분석
    if (!isOffline()) {
        try {
            const response = await fetch(`${API_BASE}/dur/analyze/${currentUser?.id || 1}`);
            if (response.ok) {
                const data = await response.json();
                if (data && Array.isArray(data.alerts)) {
                    renderDURResult(data);
                    speak(data.summary || '검사가 완료되었습니다.');
                    return;
                }
            }
        } catch (err) {
            /* 백엔드 불가 → 기기 내 엔진으로 폴백 */
        }
    }

    // 2) 기기 내(오프라인) DUR 엔진으로 분석 — 항상 결과를 렌더링
    const result = offlineDURCheck(localMeds);
    result.summary = (isOffline() ? '📡 오프라인 검사: ' : '') + (result.summary || '검사를 완료했습니다.');
    renderDURResult(result);
    speak(result.summary);
}

function renderDURResult(data) {
    const resultDiv = document.getElementById('dur-result');
    data = data || {};
    const alerts = Array.isArray(data.alerts) ? data.alerts : [];
    const summary = data.summary || (alerts.length === 0
        ? '복용 중인 약 사이에 특별한 문제가 발견되지 않았습니다.'
        : `주의가 필요한 약물 조합이 ${alerts.length}건 있습니다.`);

    let html = `<h3 style="margin-bottom:12px;">🔍 검사 결과</h3>`;
    html += `<p style="font-size:18px;margin-bottom:16px;"><strong>${escapeHtml(summary)}</strong></p>`;

    if (alerts.length === 0) {
        html += '<div class="dur-alert low"><p class="dur-alert-title">✅ 안전합니다</p><p>현재 복용 중인 약 사이에 문제가 없습니다.</p></div>';
    } else {
        for (const alert of alerts) {
            const sev = alert.severity || 'medium';
            const a = escapeHtml(alert.medication_a || '');
            const b = escapeHtml(alert.medication_b || '');
            const pair = b ? `${a} + ${b}` : a;
            const desc = escapeHtml(alert.description || '');
            const rec = escapeHtml(alert.recommendation || '의사 또는 약사와 상담하세요.');
            html += `
                <div class="dur-alert ${sev}">
                    <p class="dur-alert-title">${sev === 'high' ? '🚨' : '⚠️'} ${pair}</p>
                    ${desc ? `<p class="dur-alert-desc">${desc}</p>` : ''}
                    <p class="dur-alert-rec">💡 ${rec}</p>
                </div>`;
        }
    }

    if (data.data_source) {
        html += `<p class="drug-source-line">ℹ️ 분석 출처: ${escapeHtml(data.data_source)}</p>`;
    }
    html += `<p style="margin-top:12px;font-size:14px;color:var(--text-secondary);">※ 이 정보는 참고용이며, 정확한 판단은 약사 또는 의사와 상담하세요.</p>`;
    resultDiv.innerHTML = html;
}

// ==================== 건강 상담 챗봇 ====================

async function sendChat() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();
    if (!message) return;

    addChatMessage('user', message);
    input.value = '';

    try {
        const response = await fetch(`${API_BASE}/chat/send`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: currentUser?.id || 1, message }),
        });

        if (response.ok) {
            const data = await response.json();
            addChatMessage('assistant', data.reply);
            speak(data.reply);  // TTS 음성 출력
            // 병용확인 결과가 함께 오면 말풍선 아래에 3단계 위험도 카드로 표시
            if (data.interaction) {
                addInteractionCard(data.interaction);
            }
            if (data.urgency === 'emergency') {
                alert('⚠️ 위급 상황이 의심됩니다. 119에 전화하시겠습니까?');
            }
        }
    } catch (err) {
        // 데모 모드
        const demoReplies = {
            default: '네, 말씀하신 내용을 확인했어요. 더 자세히 말씀해 주시면 도움을 드릴 수 있어요.\n\n※ 이 정보는 참고용이며, 정확한 판단은 의료진과 상담하세요.',
        };
        setTimeout(() => {
            addChatMessage('assistant', demoReplies.default);
            speak(demoReplies.default);  // TTS 음성 출력
        }, 1000);
    }
}

function addInteractionCard(interaction) {
    // 챗봇 대화 안에 병용확인(새 제품 vs 기존약) 결과 카드를 삽입한다.
    const container = document.getElementById('chat-messages');
    const msgDiv = document.createElement('div');
    msgDiv.className = 'msg assistant';
    const card = document.createElement('div');
    card.className = 'msg-bubble ix-chat-card';
    msgDiv.innerHTML = `<div class="msg-avatar">🧪</div>`;
    msgDiv.appendChild(card);
    renderInteractionResult(interaction, card);
    container.appendChild(msgDiv);
    container.scrollTop = container.scrollHeight;
}

function addChatMessage(role, content) {
    const container = document.getElementById('chat-messages');
    const avatar = role === 'user' ? '👤' : '👨‍⚕️';
    
    const msgDiv = document.createElement('div');
    msgDiv.className = `msg ${role}`;
    msgDiv.innerHTML = `
        <div class="msg-avatar">${avatar}</div>
        <div class="msg-bubble">${content.replace(/\n/g, '<br>')}</div>
    `;
    container.appendChild(msgDiv);
    container.scrollTop = container.scrollHeight;
}

function voiceInput() {
    // 웹 Speech API 사용
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        const recognition = new SpeechRecognition();
        recognition.lang = 'ko-KR';
        recognition.continuous = false;

        recognition.onresult = (event) => {
            const text = event.results[0][0].transcript;
            document.getElementById('chat-input').value = text;
        };

        recognition.onerror = () => {
            alert('음성 인식에 실패했습니다. 다시 시도해 주세요.');
        };

        recognition.start();
    } else {
        alert('이 브라우저에서는 음성 입력을 지원하지 않습니다.');
    }
}

// Enter 키로 채팅 전송
document.addEventListener('DOMContentLoaded', () => {
    const chatInput = document.getElementById('chat-input');
    if (chatInput) {
        chatInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendChat();
        });
    }
});

// ==================== TTS 음성 출력 (고령자 친화) ====================

const TTS_ENABLED = true;
const TTS_RATE = 0.85;  // 느리게 (고령자 배려)
const TTS_PITCH = 1.0;
const TTS_LANG = 'ko-KR';

// 자연스러운 한국어 음성 선택.
//   기존에는 첫 번째 ko 음성을 그대로 썼는데, 윈도우에선 보통 구형 기계음
//   'Microsoft Heami'가 잡혀 부자연스러웠다. 신경망(Natural)/온라인/구글 음성을
//   우선 선택하고, 구형 음성은 최후순위로 밀어낸다.
let _cachedKoVoice = null;

function pickKoreanVoice() {
    if (!('speechSynthesis' in window)) return null;
    const voices = window.speechSynthesis.getVoices() || [];
    const ko = voices.filter(v => (v.lang || '').toLowerCase().startsWith('ko'));
    if (!ko.length) return null;

    const score = (v) => {
        const n = (v.name || '').toLowerCase();
        let s = 0;
        if (n.includes('natural')) s += 100;   // Microsoft ... Online (Natural) — 가장 자연스러움
        if (n.includes('online')) s += 40;
        if (n.includes('google')) s += 80;      // 크롬의 'Google 한국의' — 자연스러움
        if (n.includes('neural')) s += 60;
        if (/(sunhi|injoon|hyunsu|jimin|bongjin|gookmin|seoyeon|yuna|kyuwon)/.test(n)) s += 30;
        if (n.includes('heami')) s -= 50;        // 구형 기계음 감점
        if (v.localService === false) s += 10;   // 클라우드 신경망 가점
        return s;
    };
    return ko.slice().sort((a, b) => score(b) - score(a))[0];
}

function refreshKoVoice() { _cachedKoVoice = pickKoreanVoice(); }

if ('speechSynthesis' in window) {
    refreshKoVoice();
    // 음성 목록은 비동기로 로드되므로 로드 완료 시 다시 고른다.
    window.speechSynthesis.addEventListener('voiceschanged', refreshKoVoice);
}

function speak(text) {
    if (!TTS_ENABLED || !('speechSynthesis' in window)) return;

    // 이전 음성 중단
    window.speechSynthesis.cancel();

    // 면책 문구 등 불필요한 부분 제거
    const cleanText = text
        .replace(/※.*$/m, '')
        .replace(/\n{2,}/g, '. ')
        .replace(/[🚨⚠️✅💊💬❤️🏠📷🎤]/g, '')
        .trim();

    if (!cleanText) return;

    const utterance = new SpeechSynthesisUtterance(cleanText);
    utterance.lang = TTS_LANG;
    utterance.rate = TTS_RATE;
    utterance.pitch = TTS_PITCH;

    // 자연스러운 한국어 음성 선택 (신경망/온라인 우선, 구형 기계음 회피)
    const koreanVoice = _cachedKoVoice || pickKoreanVoice();
    if (koreanVoice) {
        utterance.voice = koreanVoice;
        utterance.lang = koreanVoice.lang || TTS_LANG;
    }

    window.speechSynthesis.speak(utterance);
}

function speakGreeting() {
    const greetingEl = document.getElementById('greeting-text');
    if (greetingEl) speak(greetingEl.textContent);
}

function speakMedicationReminder(medName, time) {
    speak(`${time}에 ${medName} 드실 시간이에요. 약 드셨으면 확인 버튼을 눌러주세요.`);
}

function speakDURWarning(description) {
    speak(`주의사항이 있어요. ${description}. 자세한 내용은 약사님께 확인하세요.`);
}

// ==================== 복약 확인 ====================

function confirmMed(alarmId) {
    const btn = event.target;
    btn.textContent = '✅ 완료';
    btn.disabled = true;
    btn.style.background = '#388E3C';
    
    // 서버에 복약 확인 전송
    fetch(`${API_BASE}/medications/alarm/confirm/${alarmId}`, { method: 'POST' })
        .catch(() => {}); // 데모 모드에서도 UI 동작
}

// ==================== 광고 검증 ====================

async function handleAdCheck(event) {
    const file = event.target.files[0];
    if (!file) return;
    const resultDiv = document.getElementById('ad-result');
    resultDiv.style.display = 'block';
    resultDiv.innerHTML = '<p>광고를 분석하고 있습니다...</p>';

    try {
        const formData = new FormData();
        formData.append('image', file);
        const response = await fetch(`${API_BASE}/ad-filter/check-ad?user_id=${currentUser?.id || 1}`, {
            method: 'POST', body: formData,
        });
        if (response.ok) {
            const data = await response.json();
            renderAdResult(data);
        } else {
            resultDiv.innerHTML = '<p>분석에 실패했습니다. 다시 촬영해 주세요.</p>';
        }
    } catch (err) {
        renderAdResult({
            is_suspicious: true,
            risk_level: 'caution',
            detected_claims: ['암 예방 효과', '100% 천연 성분'],
            warnings: ['⚠️ "암 예방 효과" — 식약처 금지 표현에 해당할 수 있습니다'],
            recommendation: '⚠️ 일부 과장된 표현이 포함되어 있습니다. 식약처 인정 기능성을 확인하세요.',
        });
    }
}

async function handleLabelCheck(event) {
    const file = event.target.files[0];
    if (!file) return;
    const resultDiv = document.getElementById('ad-result');
    resultDiv.style.display = 'block';
    resultDiv.innerHTML = '<p>제품 라벨을 분석하고 있습니다...</p>';

    try {
        const formData = new FormData();
        formData.append('image', file);
        const response = await fetch(`${API_BASE}/ad-filter/check-product-label?user_id=${currentUser?.id || 1}`, {
            method: 'POST', body: formData,
        });
        if (response.ok) {
            const data = await response.json();
            renderAdResult(data);
        } else {
            resultDiv.innerHTML = '<p>분석에 실패했습니다. 다시 촬영해 주세요.</p>';
        }
    } catch (err) {
        renderAdResult({
            is_suspicious: false,
            risk_level: 'safe',
            detected_claims: [],
            allowed_claims: ['혈행 개선에 도움'],
            warnings: [],
            recommendation: '✅ 식약처 인증 건강기능식품으로 확인됩니다.',
        });
    }
}

function renderAdResult(data) {
    const resultDiv = document.getElementById('ad-result');
    const colorMap = { safe: 'var(--safe)', caution: 'var(--warning)', dangerous: 'var(--danger)' };
    const labelMap = { safe: '안전', caution: '주의', dangerous: '위험' };

    let html = `<div style="padding:16px; border-radius:12px; border-left:4px solid ${colorMap[data.risk_level]}; background: ${data.risk_level === 'safe' ? '#E8F5E9' : data.risk_level === 'caution' ? '#FFF3E0' : '#FFEBEE'};">`;
    html += `<h3 style="margin-bottom:8px;">${data.risk_level === 'safe' ? '✅' : data.risk_level === 'caution' ? '⚠️' : '🚨'} 판정: ${labelMap[data.risk_level]}</h3>`;
    html += `<p style="font-size:16px; margin-bottom:12px;">${data.recommendation}</p>`;

    if (data.detected_claims?.length) {
        html += '<p><strong>의심 표현:</strong></p><ul>';
        data.detected_claims.forEach(c => { html += `<li style="color:var(--danger);">${c}</li>`; });
        html += '</ul>';
    }
    if (data.allowed_claims?.length) {
        html += '<p><strong>식약처 인정 기능성:</strong></p><ul>';
        data.allowed_claims.forEach(c => { html += `<li style="color:var(--safe);">${c}</li>`; });
        html += '</ul>';
    }
    html += '</div>';
    html += '<p style="margin-top:8px;font-size:13px;color:#888;">※ AI 분석 결과이며, 최종 판단은 식약처 인증을 확인하세요.</p>';
    resultDiv.innerHTML = html;
    speak(data.recommendation);
}

// ==================== AI 캐릭터 ====================

let selectedCharacter = { type: 'grandson_warm', emoji: '👦', name: '따뜻한 손주' };

function selectCharacter(type) {
    const charMap = {
        grandson_warm: { emoji: '👦', name: '따뜻한 손주' },
        granddaughter_cheerful: { emoji: '👧', name: '밝은 손녀' },
        pharmacist_kind: { emoji: '👨‍⚕️', name: '친절한 약사' },
        friend_warm: { emoji: '🧓', name: '다정한 친구' },
    };
    selectedCharacter = { type, ...charMap[type] };
    document.getElementById('character-display').textContent = selectedCharacter.emoji;
    document.getElementById('ai-character').textContent = selectedCharacter.emoji;
    speak(`${selectedCharacter.name} 캐릭터로 변경했어요!`);

    fetch(`${API_BASE}/character/select`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: currentUser?.id || 1, character_type: type }),
    }).catch(() => {});
}

async function doMoodCheck() {
    const message = prompt('오늘 기분이 어떠세요? (자유롭게 말씀해 주세요)');
    if (!message) return;

    const resultDiv = document.getElementById('mood-result');
    resultDiv.style.display = 'block';

    try {
        const response = await fetch(`${API_BASE}/character/mood-check?user_id=${currentUser?.id || 1}&message=${encodeURIComponent(message)}`, {
            method: 'POST',
        });
        if (response.ok) {
            const data = await response.json();
            resultDiv.innerHTML = `
                <div class="greeting-card" style="margin-top:12px;">
                    <span style="font-size:40px;">${data.character_emoji}</span>
                    <p style="font-size:18px; margin-top:8px;"><strong>기분: ${data.mood} (${data.score}/10)</strong></p>
                    <p style="margin-top:8px;">${data.response}</p>
                </div>`;
            speak(data.response);
        }
    } catch (err) {
        resultDiv.innerHTML = `
            <div class="greeting-card" style="margin-top:12px;">
                <span style="font-size:40px;">${selectedCharacter.emoji}</span>
                <p style="margin-top:8px;">오늘도 좋은 하루 보내세요! 항상 응원하고 있어요.</p>
            </div>`;
        speak('오늘도 좋은 하루 보내세요! 항상 응원하고 있어요.');
    }
}

// ==================== PWA Service Worker 등록 ====================

if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js')
            .then(reg => console.log('SW 등록 완료:', reg.scope))
            .catch(err => console.log('SW 등록 실패:', err));
    });
}

// ==================== 기기 감지 및 화면 자동 조율 ====================

function detectDevice() {
    const ua = navigator.userAgent;
    const isIOS = /iPad|iPhone|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
    const isAndroid = /Android/.test(ua);
    const isMobile = isIOS || isAndroid;

    // CSS 클래스 추가 (기기별 미세 조정용)
    document.documentElement.classList.add(isIOS ? 'ios' : isAndroid ? 'android' : 'desktop');
    if (isMobile) document.documentElement.classList.add('mobile');

    // iOS 100vh 문제 해결: 실제 뷰포트 높이 설정
    if (isIOS) {
        const setVH = () => {
            document.documentElement.style.setProperty('--real-vh', `${window.innerHeight}px`);
        };
        setVH();
        window.addEventListener('resize', setVH);
        window.addEventListener('orientationchange', () => setTimeout(setVH, 100));
    }

    // Android 키보드 올라올 때 레이아웃 대응
    if (isAndroid) {
        const initialHeight = window.innerHeight;
        window.addEventListener('resize', () => {
            if (window.innerHeight < initialHeight * 0.75) {
                // 키보드 올라옴
                document.body.classList.add('keyboard-open');
            } else {
                document.body.classList.remove('keyboard-open');
            }
        });
    }

    console.log(`[Device] ${isIOS ? 'iOS' : isAndroid ? 'Android' : 'Desktop'}, ${window.innerWidth}x${window.innerHeight}`);
}

detectDevice();

// ==================== WebSocket 보호자 실시간 알림 ====================

let guardianSocket = null;

function connectGuardianWebSocket(guardianId) {
    const wsBase = window.SONJU_WS_BASE || 'ws://localhost:8000/api';
    const wsUrl = `${wsBase}/guardian/ws/${guardianId}`;
    guardianSocket = new WebSocket(wsUrl);

    guardianSocket.onopen = () => {
        console.log('보호자 WebSocket 연결됨');
        // 30초마다 ping
        setInterval(() => {
            if (guardianSocket.readyState === WebSocket.OPEN) {
                guardianSocket.send('ping');
            }
        }, 30000);
    };

    guardianSocket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data === 'pong') return;

        // 실시간 알림 처리
        handleGuardianAlert(data);
    };

    guardianSocket.onclose = () => {
        console.log('WebSocket 연결 종료. 5초 후 재연결...');
        setTimeout(() => connectGuardianWebSocket(guardianId), 5000);
    };
}

function handleGuardianAlert(data) {
    switch (data.type) {
        case 'emergency':
            alert(`🚨 긴급! ${data.patient_name}님: ${data.description}`);
            break;
        case 'medication_missed':
            showNotification(`⚠️ ${data.patient_name}님이 약 복용 시간을 놓쳤습니다.`);
            break;
        case 'medication_taken':
            showNotification(`✅ ${data.patient_name}님이 ${data.medication}을 복용했습니다.`);
            break;
        case 'dur_alert':
            showNotification(`💊 ${data.patient_name}님 약물 주의: ${data.description}`);
            break;
    }
}

function showNotification(message) {
    // 브라우저 알림
    if (Notification.permission === 'granted') {
        new Notification('손주약방', { body: message, icon: '/icon-192.png' });
    }
}

// ==================== 초기화 ====================

function init() {
    // 저장된 글씨 크기 복원 (가장 먼저: 화면이 그려지기 전에 배율 적용)
    restoreFontScale();

    // 상단 날짜/시간 표시
    updateHeaderDateTime();
    setInterval(updateHeaderDateTime, 60000); // 1분마다 업데이트

    // 저장된 사용자 정보 복원
    const savedUser = localStorage.getItem('sonju_user');
    if (savedUser) {
        currentUser = JSON.parse(savedUser);
        updateProfileUI(true);
    } else {
        currentUser = { id: 1, name: '홍길동', role: 'patient' };
        updateProfileUI(false);
    }

    // 시간대별 인사말
    const hour = new Date().getHours();
    const greetingEl = document.getElementById('greeting-text');
    const userName = currentUser?.name || '';
    
    if (hour < 9) {
        greetingEl.textContent = `좋은 아침이에요${userName ? ', ' + userName + '님' : ''}! 오늘도 건강하세요 🌅`;
    } else if (hour < 12) {
        greetingEl.textContent = `${userName ? userName + '님, ' : ''}오전 약은 드셨나요? 💊`;
    } else if (hour < 18) {
        greetingEl.textContent = `오늘도 약 잘 챙기셨어요! ☀️`;
    } else {
        greetingEl.textContent = `편안한 저녁이에요${userName ? ', ' + userName + '님' : ''}! 🌙`;
    }

    // 앱 시작 시 인사말 음성 출력 (1초 딜레이 후)
    setTimeout(() => speakGreeting(), 1500);

    // 보호자 모드인 경우 WebSocket 연결
    if (currentUser.role === 'guardian') {
        connectGuardianWebSocket(currentUser.id);
        if (Notification.permission === 'default') {
            Notification.requestPermission();
        }
    }
}

// ==================== 사용자 등록/로그인 ====================

function switchAuthTab(tab) {
    document.getElementById('tab-login').classList.toggle('active', tab === 'login');
    document.getElementById('tab-register').classList.toggle('active', tab === 'register');
    document.getElementById('auth-login').style.display = tab === 'login' ? 'block' : 'none';
    document.getElementById('auth-register').style.display = tab === 'register' ? 'block' : 'none';
    document.getElementById('auth-message').style.display = 'none';
}

async function registerUser() {
    const name = document.getElementById('reg-name').value.trim();
    const phone = document.getElementById('reg-phone').value.trim();
    const birth = document.getElementById('reg-birth').value;
    const gender = document.getElementById('reg-gender').value;
    const role = document.getElementById('reg-role').value;

    if (!name || !phone) {
        showAuthMessage('이름과 전화번호는 필수입니다.', 'error');
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/auth/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: name,
                phone: phone,
                birth_date: birth,
                gender: gender,
                role: role,
            }),
        });

        if (response.ok) {
            const data = await response.json();
            currentUser = { id: data.user_id, name: data.name, role: data.role, phone: phone, birth_date: birth, gender: gender };
            localStorage.setItem('sonju_user', JSON.stringify(currentUser));
            localStorage.setItem('sonju_token', data.access_token);
            showAuthMessage(`${name}님, 가입을 환영합니다! 🎉`, 'success');
            updateProfileUI(true);
            speak(`${name}님, 손주약방에 오신 것을 환영합니다!`);
            setTimeout(() => navigate('home'), 1500);
        } else {
            const err = await response.json();
            showAuthMessage(err.detail || '가입에 실패했습니다.', 'error');
        }
    } catch (err) {
        showAuthMessage('서버 연결에 실패했습니다. 다시 시도해주세요.', 'error');
    }
}

async function loginUser() {
    const phone = document.getElementById('login-phone').value.trim();

    if (!phone) {
        showAuthMessage('전화번호를 입력해주세요.', 'error');
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ phone: phone }),
        });

        if (response.ok) {
            const data = await response.json();
            currentUser = { id: data.user_id, name: data.name, role: data.role, phone: phone };
            localStorage.setItem('sonju_user', JSON.stringify(currentUser));
            localStorage.setItem('sonju_token', data.access_token);
            showAuthMessage(`${data.name}님, 반갑습니다! 😊`, 'success');
            updateProfileUI(true);
            speak(`${data.name}님, 다시 오셨군요! 반갑습니다.`);
            setTimeout(() => navigate('home'), 1500);
        } else {
            const err = await response.json();
            showAuthMessage(err.detail || '로그인에 실패했습니다.', 'error');
        }
    } catch (err) {
        showAuthMessage('서버 연결에 실패했습니다. 다시 시도해주세요.', 'error');
    }
}

function logoutUser() {
    if (confirm('로그아웃 하시겠습니까?')) {
        localStorage.removeItem('sonju_user');
        localStorage.removeItem('sonju_token');
        currentUser = { id: 1, name: '홍길동', role: 'patient' };
        updateProfileUI(false);
        navigate('profile');
        speak('로그아웃 되었습니다.');
    }
}

function updateProfileUI(loggedIn) {
    const loggedInDiv = document.getElementById('profile-loggedin');
    const guestDiv = document.getElementById('profile-guest');
    const profileBtn = document.getElementById('btn-profile');

    if (loggedIn && currentUser) {
        if (loggedInDiv) loggedInDiv.style.display = 'block';
        if (guestDiv) guestDiv.style.display = 'none';
        if (profileBtn) profileBtn.textContent = '👤';

        // 프로필 정보 업데이트
        const nameEl = document.getElementById('profile-name');
        const phoneEl = document.getElementById('profile-phone');
        const birthEl = document.getElementById('profile-birth');
        const genderEl = document.getElementById('profile-gender');

        if (nameEl) nameEl.textContent = currentUser.name;
        if (phoneEl) phoneEl.textContent = `📱 ${currentUser.phone || ''}`;
        if (birthEl) birthEl.textContent = currentUser.birth_date ? `🎂 ${currentUser.birth_date}` : '';
        if (genderEl) genderEl.textContent = currentUser.gender ? `${currentUser.gender === '남' ? '👨' : '👩'} ${currentUser.gender}` : '';
    } else {
        if (loggedInDiv) loggedInDiv.style.display = 'none';
        if (guestDiv) guestDiv.style.display = 'block';
    }
}

function showEditProfile() {
    // 간단한 편집 모드 (이름 변경)
    const newName = prompt('이름을 입력하세요:', currentUser.name);
    if (newName && newName.trim()) {
        currentUser.name = newName.trim();
        localStorage.setItem('sonju_user', JSON.stringify(currentUser));
        updateProfileUI(true);
        speak(`이름이 ${newName}으로 변경되었습니다.`);
    }
}

function showAuthMessage(message, type) {
    const el = document.getElementById('auth-message');
    if (el) {
        el.style.display = 'block';
        el.textContent = message;
        el.className = `auth-message ${type}`;
    }
}

// ==================== 상단 날짜/시간 표시 ====================

function updateHeaderDateTime() {
    const now = new Date();
    const days = ['일', '월', '화', '수', '목', '금', '토'];
    const month = now.getMonth() + 1;
    const date = now.getDate();
    const day = days[now.getDay()];
    const hour = now.getHours();
    const minute = now.getMinutes().toString().padStart(2, '0');
    const ampm = hour < 12 ? '오전' : '오후';
    const displayHour = hour > 12 ? hour - 12 : hour === 0 ? 12 : hour;

    const dateTimeEl = document.getElementById('header-datetime');
    if (dateTimeEl) {
        dateTimeEl.textContent = `${month}월 ${date}일 (${day}) ${ampm} ${displayHour}:${minute}`;
    }

    // 다음 약 알림 시간 (데모: 오전 8:00 기준)
    const alarmEl = document.getElementById('header-next-alarm');
    if (alarmEl) {
        if (hour < 8) {
            alarmEl.textContent = '💊 오전 8:00 약';
        } else if (hour < 12) {
            alarmEl.textContent = '✅ 오전 약 완료';
        } else if (hour < 18) {
            alarmEl.textContent = '💊 저녁 식후 약';
        } else {
            alarmEl.textContent = '✅ 오늘 복약 완료';
        }
    }
}

// ==================== 보호자 호출 ====================

function callGuardian() {
    if (confirm('보호자에게 연락할까요?')) {
        // 데모: 보호자 전화번호
        window.location.href = 'tel:01012345678';
    }
}

// ==================== 건강정보 (그림2) 기능 ====================

async function showDiseaseInfo() {
    const panel = document.getElementById('disease-detail');
    panel.style.display = 'block';
    panel.innerHTML = '<p>질환 정보를 불러오고 있습니다...</p>';

    try {
        const response = await fetch(`${API_BASE}/wellness/disease-info/${currentUser?.id || 1}`);
        if (response.ok) {
            const data = await response.json();
            let html = '<div class="detail-card">';
            html += '<h3>💓 나의 질환 정보</h3>';
            html += `<p>${data.guide}</p>`;
            if (data.diseases?.length) {
                html += '<ul>';
                data.diseases.forEach(d => {
                    html += `<li><strong>${d.name}</strong> (${d.severity || '관리중'})</li>`;
                });
                html += '</ul>';
            }
            html += '</div>';
            panel.innerHTML = html;
            // 해시태그 업데이트
            if (data.tags) updateHealthTags(data.tags);
        }
    } catch (err) {
        panel.innerHTML = `
            <div class="detail-card">
                <h3>💓 나의 질환 정보</h3>
                <p><strong>고혈압</strong> - 관리 중</p>
                <p>혈압을 꾸준히 측정하고, 저염식을 유지하세요.</p>
                <p>적정 혈압: 수축기 120~130 / 이완기 80~85 mmHg</p>
            </div>`;
    }
}

async function showDietTips() {
    const panel = document.getElementById('diet-detail');
    panel.style.display = 'block';
    panel.innerHTML = '<p>식단팁을 불러오고 있습니다...</p>';

    try {
        const response = await fetch(`${API_BASE}/wellness/diet-tips/${currentUser?.id || 1}`);
        if (response.ok) {
            const data = await response.json();
            let html = '<div class="detail-card">';
            html += `<h3>🍊 ${data.title}</h3>`;
            html += `<p>${data.description}</p>`;
            if (data.tips) {
                data.tips.forEach(tip => {
                    html += `<div class="tip-item"><strong>${tip.category}</strong>: ${tip.content}`;
                    if (tip.foods?.length) html += `<br><span class="tip-foods">추천: ${tip.foods.join(', ')}</span>`;
                    html += '</div>';
                });
            }
            if (data.avoid_foods?.length) {
                html += `<p class="avoid-note">⚠️ 피할 음식: ${data.avoid_foods.join(', ')}</p>`;
            }
            if (data.meal_suggestion) {
                html += `<p class="meal-suggestion">🍽️ ${data.meal_suggestion}</p>`;
            }
            html += `<p class="disclaimer">${data.disclaimer || ''}</p>`;
            html += '</div>';
            panel.innerHTML = html;
        }
    } catch (err) {
        panel.innerHTML = `
            <div class="detail-card">
                <h3>🍊 단백질이 풍부한 식단</h3>
                <div class="tip-item"><strong>단백질</strong>: 매 끼니 단백질을 포함하세요<br><span class="tip-foods">추천: 두부, 계란, 생선, 닭가슴살, 콩</span></div>
                <div class="tip-item"><strong>식이섬유</strong>: 채소와 과일을 충분히 드세요<br><span class="tip-foods">추천: 브로콜리, 시금치, 당근, 사과</span></div>
                <div class="tip-item"><strong>수분</strong>: 하루 6~8잔의 물을 드세요<br><span class="tip-foods">추천: 물, 보리차, 녹차</span></div>
                <p class="avoid-note">⚠️ 피할 음식: 짠 음식, 가공식품, 튀긴 음식</p>
                <p class="meal-suggestion">🍽️ 아침: 두부된장국 + 현미밥 + 나물반찬</p>
            </div>`;
    }
}

async function showSupplementRecommend() {
    const panel = document.getElementById('supplement-detail');
    panel.style.display = 'block';
    panel.innerHTML = '<p>건강기능식품 추천을 불러오고 있습니다...</p>';

    try {
        const response = await fetch(`${API_BASE}/health/supplement-recommend/${currentUser?.id || 1}`);
        if (response.ok) {
            const data = await response.json();
            let html = '<div class="detail-card">';
            html += '<h3>💊 건강기능식품 추천</h3>';
            if (data.recommendations?.length) {
                data.recommendations.forEach(rec => {
                    html += `<div class="supplement-item">
                        <strong>${rec.name}</strong>
                        <p>효과: ${rec.benefit}</p>
                        ${rec.caution ? `<p class="caution-text">주의: ${rec.caution}</p>` : ''}
                    </div>`;
                });
            }
            html += `<p class="disclaimer">${data.disclaimer || ''}</p>`;
            html += '</div>';
            panel.innerHTML = html;
        }
    } catch (err) {
        panel.innerHTML = `
            <div class="detail-card">
                <h3>💊 건강기능식품 추천</h3>
                <div class="supplement-item"><strong>오메가3</strong><p>효과: 혈행 개선, 혈중 중성지방 감소</p></div>
                <div class="supplement-item"><strong>코엔자임Q10</strong><p>효과: 항산화, 혈압 건강에 도움</p></div>
                <div class="supplement-item"><strong>프로바이오틱스</strong><p>효과: 장 건강, 면역력 증진</p></div>
                <p class="disclaimer">※ 구매 전 담당 약사와 상담하세요.</p>
            </div>`;
    }
}

async function showRelaxContent() {
    const panel = document.getElementById('relax-detail');
    panel.style.display = 'block';
    panel.innerHTML = '<p>심신안정 콘텐츠를 불러오고 있습니다...</p>';

    try {
        const response = await fetch(`${API_BASE}/wellness/relax-content/${currentUser?.id || 1}`);
        if (response.ok) {
            const data = await response.json();
            let html = '<div class="detail-card">';
            html += `<h3>🎵 심신안정에 좋은 콘텐츠</h3>`;
            html += `<p class="mood-msg">${data.mood_message}</p>`;
            
            if (data.music?.length) {
                html += '<h4>🎶 추천 음악</h4>';
                data.music.forEach(m => {
                    html += `<div class="music-item"><strong>${m.title}</strong> - ${m.artist}<br><span class="music-benefit">${m.benefit}</span></div>`;
                });
            }
            if (data.activities?.length) {
                html += '<h4>🧘 추천 활동</h4>';
                data.activities.forEach(a => {
                    html += `<div class="activity-item"><strong>${a.name}</strong> (${a.duration})<br><span class="activity-benefit">${a.benefit}</span></div>`;
                });
            }
            if (data.breathing) {
                html += `<h4>🌬️ ${data.breathing.name}</h4>`;
                html += '<ol>';
                data.breathing.steps.forEach(s => { html += `<li>${s}</li>`; });
                html += '</ol>';
            }
            html += '</div>';
            panel.innerHTML = html;
        }
    } catch (err) {
        panel.innerHTML = `
            <div class="detail-card">
                <h3>🎵 심신안정에 좋은 콘텐츠</h3>
                <p class="mood-msg">오늘도 편안한 하루 보내세요.</p>
                <h4>🎶 추천 음악</h4>
                <div class="music-item"><strong>봄날은 간다</strong> - 이미자<br><span class="music-benefit">향수와 편안함</span></div>
                <div class="music-item"><strong>Canon in D</strong> - 파헬벨<br><span class="music-benefit">심박수 안정</span></div>
                <h4>🧘 추천 활동</h4>
                <div class="activity-item"><strong>산책하기</strong> (15~20분)<br><span class="activity-benefit">기분 전환, 혈액순환</span></div>
                <h4>🌬️ 4-7-8 호흡법</h4>
                <ol><li>코로 4초간 천천히 숨을 들이쉽니다</li><li>7초간 숨을 참습니다</li><li>입으로 8초간 천천히 내쉽니다</li><li>3~4회 반복합니다</li></ol>
            </div>`;
    }
}

function updateHealthTags(tags) {
    const tagContainer = document.getElementById('health-tags');
    if (tagContainer && tags?.length) {
        tagContainer.innerHTML = tags.map(t => `<span class="health-tag">${t}</span>`).join('');
    }
}

// ==================== 의약품 주의사항 (그림3) ====================

function showMedCautions() {
    const resultDiv = document.getElementById('dur-result');
    resultDiv.style.display = 'block';
    resultDiv.innerHTML = `
        <div class="detail-card">
            <h3>📋 복용 주의사항</h3>
            <div class="caution-item">
                <strong>메트포르민 500mg</strong>
                <ul>
                    <li>식후에 복용하세요 (위장 자극 감소)</li>
                    <li>음주를 피하세요 (젖산산증 위험)</li>
                    <li>CT/MRI 촬영 전후 48시간 복용 중단</li>
                </ul>
            </div>
            <div class="caution-item">
                <strong>심바스타틴 20mg</strong>
                <ul>
                    <li>자몽/자몽주스를 피하세요</li>
                    <li>근육통이 심하면 즉시 의사에게 연락</li>
                    <li>저녁 또는 취침 전 복용 권장</li>
                </ul>
            </div>
            <p class="disclaimer">※ 이상 증상 발생 시 즉시 의사 또는 약사와 상담하세요.</p>
        </div>`;
    speak('복용 주의사항을 확인해주세요.');
}

// ==================== 건강상태 그래프 (그림4) ====================

let healthChart = null;

function initHealthChart() {
    if (typeof Chart === 'undefined') return;
    switchChart('bp');
}

function switchChart(type) {
    // 탭 활성화
    document.querySelectorAll('.chart-tab').forEach(t => t.classList.remove('active'));
    event?.target?.classList.add('active');

    const canvas = document.getElementById('health-chart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    // 기존 차트 제거
    if (healthChart) {
        healthChart.destroy();
    }

    const labels = getLast7Days();

    let config;
    if (type === 'bp') {
        config = {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: '수축기',
                        data: [128, 132, 126, 130, 124, 127, 124],
                        borderColor: '#EF5350',
                        backgroundColor: 'rgba(239, 83, 80, 0.1)',
                        tension: 0.3,
                        fill: true,
                    },
                    {
                        label: '이완기',
                        data: [85, 88, 82, 86, 83, 84, 83],
                        borderColor: '#42A5F5',
                        backgroundColor: 'rgba(66, 165, 245, 0.1)',
                        tension: 0.3,
                        fill: true,
                    },
                ],
            },
            options: getChartOptions('mmHg'),
        };
    } else if (type === 'sugar') {
        config = {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: '공복 혈당',
                        data: [102, 98, 105, 95, 100, 97, 98],
                        borderColor: '#FFA726',
                        backgroundColor: 'rgba(255, 167, 38, 0.1)',
                        tension: 0.3,
                        fill: true,
                    },
                ],
            },
            options: getChartOptions('mg/dL'),
        };
    } else if (type === 'med') {
        config = {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: '복약 이행률',
                        data: [100, 100, 50, 100, 100, 100, 100],
                        backgroundColor: labels.map((_, i) => {
                            const val = [100, 100, 50, 100, 100, 100, 100][i];
                            return val === 100 ? 'rgba(102, 187, 106, 0.7)' : 'rgba(255, 167, 38, 0.7)';
                        }),
                        borderRadius: 6,
                    },
                ],
            },
            options: {
                ...getChartOptions('%'),
                plugins: {
                    legend: { display: false },
                },
            },
        };
    }

    healthChart = new Chart(ctx, config);
}

function getChartOptions(unit) {
    return {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                position: 'bottom',
                labels: { font: { size: 12, family: 'Noto Sans KR' }, padding: 12 },
            },
        },
        scales: {
            x: {
                grid: { display: false },
                ticks: { font: { size: 11 } },
            },
            y: {
                grid: { color: 'rgba(0,0,0,0.05)' },
                ticks: {
                    font: { size: 11 },
                    callback: function(value) { return value + unit; },
                },
            },
        },
    };
}

function getLast7Days() {
    const days = [];
    const dayNames = ['일', '월', '화', '수', '목', '금', '토'];
    for (let i = 6; i >= 0; i--) {
        const d = new Date();
        d.setDate(d.getDate() - i);
        days.push(`${d.getMonth() + 1}/${d.getDate()}(${dayNames[d.getDay()]})`);
    }
    return days;
}

init();
