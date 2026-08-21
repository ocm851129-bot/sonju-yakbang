# 🔄 손주약방 자동 배포 (CI/CD)

**소스를 수정하고 `git push` 하면 웹·Android·iOS가 자동으로 갱신됩니다.**

```
frontend/ 수정 → git push (main)
        │
        ├─ 🌐 Vercel        → 웹앱 자동 재배포        (Git 연동, 아래 1회 설정)
        └─ ⚙️ GitHub Actions → Android APK + iOS IPA 빌드 → "latest" Release 갱신
                               (build-apps.yml, 설정 완료)
```

- 웹 소스 = `frontend/` (단일 소스)
- 앱은 빌드 시 `frontend/` → `mobile/www` 를 자동 복사(`npm run cap:sync`)하므로 **따로 손댈 필요 없음**

---

## 1. 앱 빌드 — GitHub Actions (설정 완료 ✅)

`.github/workflows/build-apps.yml`:
- **트리거**: `main` 에 `frontend/**` 또는 `mobile/**` push (또는 Actions 탭에서 수동 실행)
- **Android job** (ubuntu): JDK17 + SDK34 → `gradlew assembleDebug`
- **iOS job** (macOS): pod install → `xcodebuild` (서명 없는 .ipa)
- **release job**: 두 산출물을 **`latest`** 릴리스에 업로드(clobber)

> CI는 리눅스/맥이라 로컬의 **한글 경로 빌드 문제가 없습니다.**
> 공개 저장소라 Actions(맥 러너 포함) **무료**.

### 항상 최신 다운로드 링크 (변하지 않음)
- Android: `https://github.com/ocm851129-bot/sonju-yakbang/releases/latest/download/sonju-yakbang.apk`
- iOS: `https://github.com/ocm851129-bot/sonju-yakbang/releases/latest/download/sonju-yakbang.ipa`

설치 안내 페이지(`install.html`)가 이 "latest" 링크를 쓰므로, 새로 빌드되면 **페이지 수정 없이 자동으로 최신본**을 받습니다.

---

## 2. 웹 자동 배포 — Vercel Git 연동 (1회 설정 필요 ⚙️)

지금은 CLI로 수동 배포 중입니다. **아래 1회 설정**을 하면 push 시 자동 배포됩니다.

1. https://vercel.com/ocm851129-bots-projects/sonju-yakbang/settings/git 접속
2. **Connect Git Repository** → `ocm851129-bot/sonju-yakbang` 선택
3. **Settings → General → Root Directory** = `frontend` 확인
4. 저장 → 이후 `main` push 마다 자동 배포 (+ PR 프리뷰 배포)

> 대안(토큰 방식): Vercel 토큰을 GitHub Secret `VERCEL_TOKEN` 으로 넣고 Actions에서 배포할 수도 있으나, **Git 연동이 더 간단하고 안전**합니다.

---

## 3. 앱 코드까지 바뀐 경우 (네이티브 플러그인 추가 등)
웹(`frontend/`)만 바꾼 경우는 위 자동화로 끝입니다.
네이티브 설정(플러그인/권한/아이콘)을 바꾼 경우도 push하면 CI가 다시 빌드합니다.
로컬에서 확인하려면:
```bash
cd mobile && npm run cap:sync   # frontend→www→네이티브 반영
```

---

## 요약: 무엇을 하면 되나
| 바꾼 것 | 할 일 | 반영 |
|---------|-------|------|
| 화면·기능 (`frontend/`) | `git push` | 웹+앱 자동 |
| 네이티브 설정 (`mobile/`) | `git push` | 앱 자동 |
| 웹 자동배포 켜기 | Vercel Git 연동(위 2번, 1회) | 이후 자동 |
