(function () {
  var $ = function (s) { return document.querySelector(s); };
  var $$ = function (s) { return Array.prototype.slice.call(document.querySelectorAll(s)); };
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  // ---------- illustrations (used until real photos are uploaded)
  $$('[data-art]').forEach(function (el) { el.innerHTML = window.SF_art(el.dataset.art, parseInt(el.dataset.seed, 10) || 0); });
  $$('[data-hero]').forEach(function (el) { el.innerHTML = window.SF_hero(); });

  // ---------- cart (kept in the browser until the order is placed)
  var cart = [];
  try { cart = JSON.parse(localStorage.getItem('sf_cart') || '[]') || []; } catch (e) { cart = []; }
  function save() {
    try { localStorage.setItem('sf_cart', JSON.stringify(cart)); } catch (e) {}
    var c = $('#cnt'); if (c) c.textContent = cart.reduce(function (a, b) { return a + b.qty; }, 0);
  }
  function add(id, name, cat, keepQty) {
    var ex = cart.filter(function (x) { return x.id === id; })[0];
    if (ex) { if (!keepQty) ex.qty++; } else cart.push({ id: id, name: name, cat: cat, qty: 1, note: '' });
    save();
  }
  var toastT;
  function toast(m) {
    var t = $('#toast'); if (!t) return;
    t.textContent = m; t.classList.add('show'); clearTimeout(toastT);
    toastT = setTimeout(function () { t.classList.remove('show'); }, 1800);
  }

  function renderCart() {
    var box = $('#cartlist'); if (!box) return;
    if (!cart.length) {
      box.innerHTML = '<div class="notice">Your order is empty. <a href="/products">Browse products</a> and tap “Add to order”, or describe what you need in the “anything else” box.</div>';
      return;
    }
    box.innerHTML = cart.map(function (it) {
      return '<div class="line"><div class="nm"><b>' + esc(it.name) + '</b><span>' + esc(it.cat) + '</span></div>' +
        '<div class="qty"><button type="button" data-action="qty" data-id="' + esc(it.id) + '" data-d="-1" aria-label="Less">−</button><b>' + it.qty +
        '</b><button type="button" data-action="qty" data-id="' + esc(it.id) + '" data-d="1" aria-label="More">+</button>' +
        '<button type="button" class="rm" data-action="rm" data-id="' + esc(it.id) + '">Remove</button></div>' +
        '<input data-note="' + esc(it.id) + '" value="' + esc(it.note) + '" maxlength="200" placeholder="Size, colour or other details (e.g. 6m × 12m, green)"></div>';
    }).join('');
  }

  document.addEventListener('click', function (e) {
    if (e.target.id === 'burger') { $('#nav').classList.toggle('open'); return; }
    var el = e.target.closest('[data-action]'); if (!el) return;
    var a = el.dataset.action, id = el.dataset.id;
    if (a === 'add') { add(id, el.dataset.name, el.dataset.cat); toast('Added to your order'); }
    else if (a === 'order') { add(id, el.dataset.name, el.dataset.cat, true); window.location.href = '/order'; }
    else if (a === 'qty') {
      var it = cart.filter(function (x) { return x.id === id; })[0];
      if (it) { it.qty = Math.max(1, Math.min(1000, it.qty + Number(el.dataset.d))); save(); renderCart(); }
    }
    else if (a === 'rm') { cart = cart.filter(function (x) { return x.id !== id; }); save(); renderCart(); }
    else if (a === 'gfilter') {
      var f = el.dataset.f;
      $$('#chips .chip').forEach(function (c) { c.classList.toggle('on', c.dataset.f === f); });
      $$('.grid > .card[data-cat]').forEach(function (c) { c.style.display = (f === 'all' || c.dataset.cat === f) ? '' : 'none'; });
    }
    else if (a === 'apply') { var s = $('#jobrole'); if (s) s.value = el.dataset.role; $('#apply').scrollIntoView({ behavior: 'smooth' }); }
    else if (a === 'copy') {
      try { navigator.clipboard.writeText(el.dataset.text).then(function () { toast('Copied'); }, function () { toast('Copy not available'); }); }
      catch (err) { toast('Copy not available'); }
    }
  });

  document.addEventListener('input', function (e) {
    var n = e.target.getAttribute && e.target.getAttribute('data-note');
    if (n) { var it = cart.filter(function (x) { return x.id === n; })[0]; if (it) { it.note = e.target.value; save(); } }
  });

  // ---------- place order (saved on the server)
  var form = $('#orderform');
  if (form) {
    renderCart();
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var err = $('#orderr'), btn = $('#ordersubmit');
      err.textContent = '';
      var payload = {
        items: cart.map(function (c) { return { id: c.id, qty: c.qty, note: c.note }; }),
        location: form.location.value, date: form.date.value, extra: form.extra.value, ref: form.ref.value
      };
      if (!payload.items.length && !payload.extra.trim()) {
        err.textContent = 'Please add at least one product, or describe what you need.'; return;
      }
      btn.disabled = true; btn.textContent = 'Sending…';
      fetch('/api/order', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': $('meta[name="csrf"]').content },
        body: JSON.stringify(payload)
      }).then(function (r) {
        if (r.status === 401) { window.location.href = '/login?next=/order'; return null; }
        return r.json();
      }).then(function (j) {
        if (!j) return;
        if (j.ok) { cart = []; save(); window.location.href = '/account?placed=' + encodeURIComponent(j.ref); }
        else { err.textContent = j.error || 'Could not place your order. Please try again.'; btn.disabled = false; btn.textContent = 'Place order'; }
      }).catch(function () {
        err.textContent = 'Network problem — please check your connection and try again.';
        btn.disabled = false; btn.textContent = 'Place order';
      });
    });
  }

  save();
})();
