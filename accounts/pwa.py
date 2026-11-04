import json

from django.http import HttpResponse
from django.shortcuts import render
from django.templatetags.static import static
from django.views.decorators.cache import never_cache

SW_JS = """
var VERSION = 'trucklink-v1';
var PRECACHE = ['/offline/', '__ICON192__', '__ICON512__', '__LIVEJS__'];

self.addEventListener('install', function (event) {
  event.waitUntil(caches.open(VERSION).then(function (cache) { return cache.addAll(PRECACHE); }));
  self.skipWaiting();
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.filter(function (k) { return k !== VERSION; })
        .map(function (k) { return caches.delete(k); }));
    }).then(function () { return self.clients.claim(); })
  );
});

// Pages are never stored, because they contain private information.
// Only the offline notice and static files are kept.
self.addEventListener('fetch', function (event) {
  var req = event.request;
  if (req.method !== 'GET') { return; }
  var url = new URL(req.url);
  if (url.origin !== self.location.origin) { return; }

  if (req.mode === 'navigate') {
    event.respondWith(fetch(req).catch(function () { return caches.match('/offline/'); }));
    return;
  }
  if (url.pathname.indexOf('/static/') === 0) {
    event.respondWith(
      fetch(req).then(function (res) {
        var copy = res.clone();
        caches.open(VERSION).then(function (cache) { cache.put(req, copy); });
        return res;
      }).catch(function () { return caches.match(req); })
    );
  }
});
"""


def manifest(request):
    data = {
        'name': 'TruckLink',
        'short_name': 'TruckLink',
        'description': 'Loads and trucks across Zimbabwe.',
        'start_url': '/',
        'scope': '/',
        'display': 'standalone',
        'background_color': '#EEF2F1',
        'theme_color': '#1C6B4A',
        'icons': [
            {'src': static('accounts/icons/icon-192.png'), 'sizes': '192x192',
             'type': 'image/png', 'purpose': 'any'},
            {'src': static('accounts/icons/icon-512.png'), 'sizes': '512x512',
             'type': 'image/png', 'purpose': 'any'},
            {'src': static('accounts/icons/icon-512.png'), 'sizes': '512x512',
             'type': 'image/png', 'purpose': 'maskable'},
        ],
    }
    return HttpResponse(json.dumps(data), content_type='application/manifest+json')


@never_cache
def service_worker(request):
    js = (SW_JS.replace('__ICON192__', static('accounts/icons/icon-192.png'))
          .replace('__ICON512__', static('accounts/icons/icon-512.png'))
          .replace('__LIVEJS__', static('accounts/live.js')))
    response = HttpResponse(js, content_type='application/javascript')
    response['Service-Worker-Allowed'] = '/'
    return response


def offline(request):
    return render(request, 'offline.html')