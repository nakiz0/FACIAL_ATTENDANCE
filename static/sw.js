self.addEventListener('install', function(e) {
  self.skipWaiting();
});
self.addEventListener('activate', function(e) {
  clients.claim();
});
self.addEventListener('fetch', function(e) {
  // Basic offline cache strategy could be added here
});
