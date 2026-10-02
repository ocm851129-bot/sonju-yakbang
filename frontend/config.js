/**
 * 손주약방 - 환경 설정
 * 배포 환경(도메인)에 따라 백엔드 API 주소를 자동으로 선택합니다.
 * 로컬 개발 시에는 localhost:8000, 배포 시에는 아래 PROD_API_ORIGIN 을 사용합니다.
 */
(function () {
  var host = window.location.hostname;
  var isLocal =
    host === 'localhost' || host === '127.0.0.1' || host === '' || host === '0.0.0.0';

  // ▼▼▼ 백엔드 배포 후 이 값을 실제 백엔드 URL 로 교체하세요 (끝에 슬래시 없이) ▼▼▼
  //   예) 'https://sonju-yakbang-api.onrender.com'
  var PROD_API_ORIGIN = 'https://sonju-yakbang-api.onrender.com';
  // ▲▲▲ Vercel 환경변수를 쓰지 않고 정적 값으로 관리합니다 ▲▲▲

  // Capacitor 네이티브 앱(Android/iOS)은 앱 내부를 https://localhost 스킴으로
  // 서빙하므로 hostname 이 'localhost' 다. 이를 로컬 개발로 오인해 폰 안의
  // localhost:8000(존재하지 않음)으로 요청하면 모든 기능이 멈춘다.
  // → 네이티브 앱에서는 항상 배포 백엔드를 사용하고, 백엔드가 아직 없을 때는
  //    각 기능의 기기 내 오프라인 폴백(OCR·약품DB·DUR)이 동작한다.
  var isNative = !!(window.Capacitor &&
    (typeof window.Capacitor.isNativePlatform === 'function'
      ? window.Capacitor.isNativePlatform()
      : (window.Capacitor.platform && window.Capacitor.platform !== 'web')));

  var origin = (isLocal && !isNative) ? 'http://localhost:8000' : PROD_API_ORIGIN;

  window.SONJU_API_BASE = origin + '/api';
  window.SONJU_WS_BASE = origin.replace(/^http/, 'ws') + '/api';
  window.SONJU_IS_NATIVE = isNative;
})();
