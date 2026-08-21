/**
 * 손주약방 Service Worker
 * PWA 오프라인 지원 + 캐싱 + 푸시 알림
 */

const CACHE_NAME = 'sonju-yakbang-v2';
const STATIC_ASSETS = [
    '/',
    '/index.html',
    '/styles.css',
    '/config.js',
    '/offline-dur.js',
    '/app.js',
    '/manifest.json',
];

// 설치: 정적 리소스 캐싱
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(STATIC_ASSETS);
        })
    );
    self.skipWaiting();
});

// 활성화: 이전 캐시 정리
self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
            );
        })
    );
    self.clients.claim();
});

// 네트워크 요청 처리: Network First (API), Cache First (정적)
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // API 요청은 네트워크 우선
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(
            fetch(event.request).catch(() => {
                return new Response(JSON.stringify({ error: '오프라인 상태입니다' }), {
                    headers: { 'Content-Type': 'application/json' }
                });
            })
        );
        return;
    }

    // 정적 리소스는 캐시 우선
    event.respondWith(
        caches.match(event.request).then((cached) => {
            return cached || fetch(event.request);
        })
    );
});

// 푸시 알림 수신 (보호자 알림용)
self.addEventListener('push', (event) => {
    const data = event.data ? event.data.json() : {};
    const title = data.title || '손주약방 알림';
    const options = {
        body: data.body || '새로운 알림이 있습니다',
        icon: '/icon-192.png',
        badge: '/icon-192.png',
        vibrate: [200, 100, 200],
        data: data,
    };
    event.waitUntil(self.registration.showNotification(title, options));
});

// 알림 클릭 처리
self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    event.waitUntil(
        self.clients.openWindow('/')
    );
});
