(function () {
  'use strict';

  var lastNoteId = null;
  var timers = [];

  function stopAll() {
    timers.forEach(clearInterval);
    timers = [];
  }

  function every(ms, fn) {
    timers.push(setInterval(function () {
      if (!document.hidden) { fn(); }
    }, ms));
  }

  function getJson(url) {
    return fetch(url, { credentials: 'same-origin', headers: { 'Accept': 'application/json' } })
      .then(function (r) {
        if (r.status === 401) { stopAll(); return null; }
        if (!r.ok) { return null; }
        return r.json();
      })
      .catch(function () { return null; });
  }

  function updateBell(unread) {
    var link = document.querySelector('a.navlink[href$="/accounts/notifications/"]');
    if (!link) { return; }
    var badge = link.querySelector('.count');
    if (unread > 0) {
      if (!badge) {
        badge = document.createElement('span');
        badge.className = 'count';
        link.appendChild(badge);
      }
      badge.textContent = unread;
    } else if (badge) {
      badge.remove();
    }
  }

  function toast(message, url) {
    var box = document.createElement('div');
    box.setAttribute('role', 'status');
    box.style.cssText = 'position:fixed;right:1rem;bottom:1rem;max-width:22rem;background:#1E2A32;color:#fff;' +
      'padding:.9rem 1rem;border-radius:12px;box-shadow:0 6px 24px rgba(0,0,0,.25);z-index:50;font-size:.95rem;';
    var text = document.createElement('div');
    text.textContent = message;
    box.appendChild(text);
    if (url) {
      var link = document.createElement('a');
      link.href = url;
      link.textContent = 'Open';
      link.style.cssText = 'color:#F5A800;font-weight:600;display:inline-block;margin-top:.4rem;';
      box.appendChild(link);
    }
    document.body.appendChild(box);
    setTimeout(function () { box.remove(); }, 9000);
  }

  function showBanner() {
    var bar = document.createElement('div');
    bar.setAttribute('role', 'status');
    bar.style.cssText = 'position:fixed;left:0;right:0;bottom:0;background:#F5A800;color:#1E2A32;' +
      'padding:.75rem 1rem;z-index:50;display:flex;gap:1rem;justify-content:center;align-items:center;font-weight:600;';
    var text = document.createElement('span');
    text.textContent = 'This page has new activity.';
    var button = document.createElement('button');
    button.type = 'button';
    button.textContent = 'Refresh now';
    button.style.cssText = 'border:0;border-radius:8px;padding:.35rem .8rem;background:#1E2A32;color:#fff;font-weight:600;';
    button.addEventListener('click', function () { location.reload(); });
    bar.appendChild(text);
    bar.appendChild(button);
    document.body.appendChild(bar);
  }

  function checkNotes() {
    getJson('/accounts/live/').then(function (d) {
      if (!d || !d.ok) { return; }
      updateBell(d.unread);
      var n = d.latest;
      if (!n) {
        if (lastNoteId === null) { lastNoteId = 0; }
        return;
      }
      if (lastNoteId !== null && n.id > lastNoteId && !n.is_read) { toast(n.message, n.url); }
      lastNoteId = n.id;
    });
  }

  checkNotes();
  every(10000, checkNotes);

  var match = location.pathname.match(/^\/loads\/(\d+)\/$/);
  if (match) {
    var signature = null;
    var bannerShown = false;
    var url = '/loads/' + match[1] + '/live/';
    var checkLoad = function () {
      getJson(url).then(function (d) {
        if (!d || !d.signature) { return; }
        if (signature === null) { signature = d.signature; return; }
        if (d.signature === signature) { return; }
        var a = document.activeElement;
        var typing = a && /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName);
        if (!typing) { location.reload(); return; }
        if (!bannerShown) { bannerShown = true; showBanner(); }
      });
    };
    checkLoad();
    every(6000, checkLoad);
  }
})();