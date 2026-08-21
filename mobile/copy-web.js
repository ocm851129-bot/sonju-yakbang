/**
 * ../frontend 의 정적 웹 자산을 ./www 로 복사합니다.
 * (배포 설정 파일 .vercel/.env.local/node_modules 는 제외)
 * 프론트를 수정한 뒤 `npm run cap:sync` 로 앱에 반영하세요.
 */
const fs = require('fs');
const path = require('path');

const SRC = path.join(__dirname, '..', 'frontend');
const DST = path.join(__dirname, 'www');
const ASSETS = [
  'index.html', 'styles.css', 'app.js', 'config.js', 'offline-dur.js',
  'sw.js', 'manifest.json', 'character.svg', 'icon-192.png', 'icon-512.png',
];

fs.mkdirSync(DST, { recursive: true });
let n = 0;
for (const f of ASSETS) {
  const s = path.join(SRC, f);
  if (fs.existsSync(s)) {
    fs.copyFileSync(s, path.join(DST, f));
    n++;
  }
}
console.log(`[copy-web] ${n}개 자산을 www 로 복사했습니다.`);
