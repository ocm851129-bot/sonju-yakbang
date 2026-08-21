# 📱 손주약방 모바일 앱 (Android / iOS)

PWA(`frontend/`)를 **Capacitor 6** 으로 감싼 네이티브 앱 프로젝트입니다. 위치: `mobile/`

- **appId**: `kr.co.metaict.sonjuyakbang`
- **appName**: 손주약방
- 웹 자산은 `mobile/www/` (= `frontend/` 복사본). `npm run cap:sync` 로 갱신.

---

## ✅ Android (APK) — Windows에서 빌드 완료

빌드된 APK: **`dist/손주약방-v1-debug.apk`** (약 3.7MB, 디버그 서명)

### 설치 방법
1. APK 파일을 안드로이드 폰으로 전송 (USB / 카톡 / 드라이브)
2. 폰에서 "출처를 알 수 없는 앱 설치" 허용 → APK 탭 → 설치

### ⚠️ 한글 경로 이슈 & 재빌드 방법
프로젝트가 한글 경로(`C:\Users\오창민\...\여성발명\...`)에 있어 **Android Gradle 빌드가 실패**합니다.
그래서 **ASCII 경로로 복사해서 빌드**했습니다. 재빌드 시:

```bash
# 1) 웹 자산 최신화 (frontend 수정 후)
cd mobile && npm run cap:sync

# 2) ASCII 경로로 복사 (PowerShell)
robocopy "C:\Users\오창민\...\sonju-yakbang\mobile" "C:\sonju-build\mobile" /MIR /XD "android\build" "android\.gradle" /MT:16

# 3) ASCII 환경에서 빌드
$env:JAVA_HOME="C:\Program Files\Eclipse Adoptium\jdk-17.0.17.10-hotspot"
$env:ANDROID_HOME="C:\android-sdk"
$env:GRADLE_USER_HOME="C:\gradle-home"
cd C:\sonju-build\mobile\android
.\gradlew.bat assembleDebug          # 디버그 APK
# 산출물: app\build\outputs\apk\debug\app-debug.apk
```

빌드 요구사항: **JDK 17**, Android SDK **platform android-34 + build-tools 34.0.0**, Gradle 8.2.1(wrapper 자동).

### 배포용 서명 APK/AAB (구글 플레이 업로드)
```bash
# 키스토어 생성 (1회)
keytool -genkey -v -keystore sonju.keystore -alias sonju -keyalg RSA -keysize 2048 -validity 10000
# android/app/build.gradle 의 signingConfigs 설정 후
.\gradlew.bat bundleRelease           # AAB (플레이스토어 권장)
.\gradlew.bat assembleRelease         # 서명 APK
```

---

## 🍎 iOS — Windows에서는 빌드 불가

iOS 프로젝트(`mobile/ios/App/`, Xcode 프로젝트)는 **생성 완료**했으나,
**`.ipa` 빌드는 macOS + Xcode 가 반드시 필요**합니다. 세 가지 선택지:

| 방법 | 설명 | Mac 필요 |
|------|------|:---:|
| **A. Mac + Xcode** | `cd mobile && npm run cap:sync && npx cap open ios` → Xcode에서 Run/Archive | ✅ |
| **B. PWABuilder** | pwabuilder.com 에 `https://sonju-yakbang.vercel.app` 입력 → iOS 패키지 생성 | ❌(웹) |
| **C. GitHub Actions (설정 완료)** | `.github/workflows/ios-build.yml` — macOS 러너에서 자동 빌드 → **서명 안 된 .ipa** 아티팩트 | ❌(클라우드) |

### ⭐ Mac 없이 iOS 만들기 — 설정 완료된 클라우드 빌드
공개 저장소라 **GitHub Actions의 macOS 러너가 무료**입니다. `mobile/**` 를 푸시하거나
GitHub → **Actions** 탭 → **iOS Build (unsigned)** → **Run workflow** 실행하면,
빌드 후 **`sonju-yakbang-ios-unsigned.ipa`** 아티팩트가 생성됩니다.

이 **서명 안 된 .ipa** 를 본인 아이폰에 설치하는 법 (Windows에서):
1. PC에 **[Sideloadly](https://sideloadly.io)** 설치 (Windows용 있음)
2. 아이폰 USB 연결 → Sideloadly에 .ipa 드래그 → **무료 Apple ID** 로그인
3. 설치 완료 (무료 계정은 **7일마다 재설치** 필요, 유료 계정은 1년)

### iOS "필요한 것" 요약
| 목적 | 필요한 것 | 비용 |
|------|-----------|------|
| 클라우드 빌드(.ipa 생성) | GitHub Actions (이미 설정) | 무료 |
| 본인 아이폰에 설치(테스트) | 무료 Apple ID + Sideloadly | 무료(7일 갱신) |
| 실기기 안정 설치 / TestFlight 배포 | **Apple Developer Program** | **$99/년** |
| App Store 정식 출시 | Apple Developer + 앱 심사 | $99/년 |
| Xcode에서 직접 빌드 | **macOS + Xcode** | Mac 기기 필요 |

> 심사·시연 목적이면 **B(PWABuilder)** 또는 **C(GitHub Actions + Sideloadly)** 로 Mac 없이 가능.
> 앱스토어 정식 배포만 Apple Developer 계정($99/년)이 반드시 필요합니다.

### Mac에서 빌드하는 경우
```bash
cd mobile
npm install
npm run cap:sync
sudo gem install cocoapods   # 최초 1회
npx cap open ios             # Xcode 실행 → 서명팀 설정 → Run
```

---

## 공통: 백엔드 연결
앱은 `www/config.js` 의 `PROD_API_ORIGIN` (기본 `https://sonju-yakbang-api.onrender.com`) 으로 API를 호출합니다.
백엔드 배포 후 이 값을 실제 URL로 바꾸고 `npm run cap:sync` → 재빌드하세요.
백엔드가 없어도 앱은 실행되며, 서버 연동 기능만 대기 상태가 됩니다.
