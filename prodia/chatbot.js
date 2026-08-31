/* Chatbot widget — El mouskito (Poseidon) — v1.0
 * Widget autonome sans backend : réponses préprogrammées + capture de leads.
 * Config : window.CHATBOT_CONFIG = { name, subtitle, accent, welcome, faqs: [{q, keywords, answer}] }
 */
(function () {
  if (window.__chatbotLoaded) return;
  window.__chatbotLoaded = true;

  var cfg = window.CHATBOT_CONFIG || {};
  var NAME = cfg.name || 'Assistant';
  var SUB = cfg.subtitle || 'Je réponds à vos questions';
  var ACCENT = cfg.accent || '#4f46e5';
  /* Couleur de texte adaptée à la luminance de l'accent (règle 16/08 — écritures lisibles partout) */
  function lum(hex) {
    var c = (hex || '').replace('#', '');
    if (c.length === 3) c = c.split('').map(function (x) { return x + x; }).join('');
    if (c.length !== 6) return 0.5;
    var r = parseInt(c.substr(0, 2), 16) / 255, g = parseInt(c.substr(2, 2), 16) / 255, b = parseInt(c.substr(4, 2), 16) / 255;
    function f(v) { return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); }
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  }
  var ACCENT_TEXT = cfg.accentText || (lum(ACCENT) > 0.183 ? '#0f172a' : '#ffffff');
  var WELCOME = cfg.welcome || 'Bonjour ! 👋 Comment puis-je vous aider ?';
  var FAQS = cfg.faqs || [];
  var QUICK = cfg.quick || [];
  if (cfg.emailjs && !window.emailjs) {
    var s = document.createElement('script');
    s.src = 'https://cdn.jsdelivr.net/npm/@emailjs/browser@4/dist/email.min.js';
    s.onload = function () { try { emailjs.init({ publicKey: cfg.emailjs.publicKey }); } catch (err) {} };
    document.head.appendChild(s);
  }

  function findAnswer(q) {
    var ql = q.toLowerCase();
    for (var i = 0; i < FAQS.length; i++) {
      var f = FAQS[i];
      for (var k = 0; k < f.keywords.length; k++) {
        if (ql.indexOf(f.keywords[k]) !== -1) return f.answer;
      }
    }
    return null;
  }

  // ---------- DOM ----------
  var btn = document.createElement('div');
  btn.id = 'cb-btn';
  btn.innerHTML = '<span class="cb-ico">💬</span>';
  btn.style.cssText = 'position:fixed;bottom:20px;right:20px;width:58px;height:58px;border-radius:50%;background:' + ACCENT + ';color:' + ACCENT_TEXT + ';display:flex;align-items:center;justify-content:center;font-size:26px;cursor:pointer;box-shadow:0 4px 16px rgba(0,0,0,.25);z-index:99999;transition:transform .15s;';
  btn.onmouseenter = function () { btn.style.transform = 'scale(1.08)'; };
  btn.onmouseleave = function () { btn.style.transform = 'scale(1)'; };

  var panel = document.createElement('div');
  panel.id = 'cb-panel';
  panel.style.cssText = 'position:fixed;bottom:90px;right:20px;width:360px;max-width:calc(100vw - 40px);height:480px;max-height:calc(100vh - 120px);background:#fff;color:#1f2937;border-radius:16px;box-shadow:0 8px 40px rgba(0,0,0,.25);display:none;flex-direction:column;overflow:hidden;z-index:99999;font-family:inherit;';
  panel.innerHTML =
    '<div style="background:' + ACCENT + ';color:' + ACCENT_TEXT + ';padding:14px 16px;display:flex;align-items:center;gap:10px;">' +
      '<div style="width:34px;height:34px;border-radius:50%;background:rgba(255,255,255,.25);display:flex;align-items:center;justify-content:center;font-size:17px;">🤖</div>' +
      '<div style="flex:1;"><div style="font-weight:700;font-size:14px;">' + NAME + '</div>' +
      '<div style="font-size:11px;opacity:.9;">' + SUB + '</div></div>' +
      '<button id="cb-close" style="background:none;border:none;color:' + ACCENT_TEXT + ';font-size:18px;cursor:pointer;">✕</button>' +
    '</div>' +
    '<div id="cb-msgs" style="flex:1;overflow-y:auto;padding:14px;background:#f7f7fa;color:#1f2937;"></div>' +
    '<div id="cb-quick" style="display:flex;flex-wrap:wrap;gap:6px;padding:0 12px 8px;background:#f7f7fa;"></div>' +
    '<div style="display:flex;gap:8px;padding:10px;border-top:1px solid #eee;background:#fff;">' +
      '<input id="cb-input" type="text" placeholder="Écrivez votre question…" style="flex:1;border:1px solid #ddd;border-radius:8px;padding:9px 12px;font-size:13px;outline:none;color:#1f2937;background:#fff;">' +
      '<button id="cb-send" style="background:' + ACCENT + ';color:#fff;border:none;border-radius:8px;padding:0 14px;cursor:pointer;font-size:15px;">➤</button>' +
    '</div>';

  document.body.appendChild(btn);
  document.body.appendChild(panel);

  var msgs = panel.querySelector('#cb-msgs');
  var input = panel.querySelector('#cb-input');
  var quickBox = panel.querySelector('#cb-quick');
  var open = false;

  function scrollBottom() { msgs.scrollTop = msgs.scrollHeight; }

  function addMsg(text, who) {
    var d = document.createElement('div');
    d.style.cssText = 'max-width:85%;padding:9px 12px;border-radius:12px;font-size:13px;line-height:1.45;margin-bottom:8px;white-space:pre-wrap;' +
      (who === 'me' ? 'margin-left:auto;background:' + ACCENT + ';color:' + ACCENT_TEXT + ';border-bottom-right-radius:3px;'
                    : 'background:#fff;border:1px solid #e8e8ee;color:#1f2937;border-bottom-left-radius:3px;');
    d.textContent = text;
    msgs.appendChild(d);
    scrollBottom();
  }

  function bot(text) { addMsg(text, 'bot'); }

  function showQuick() {
    quickBox.innerHTML = '';
    (QUICK || []).forEach(function (q) {
      var c = document.createElement('button');
      c.textContent = q;
      c.style.cssText = 'border:1px solid ' + ACCENT + ';color:' + ACCENT + ';background:#fff;border-radius:999px;padding:5px 11px;font-size:12px;cursor:pointer;';
      c.onclick = function () { input.value = q; send(); };
      quickBox.appendChild(c);
    });
  }

  // ---------- Capture de leads ----------
  function askLead(question) {
    bot(question);
    var form = document.createElement('div');
    form.style.cssText = 'background:#fff;border:1px solid ' + ACCENT + ';border-radius:12px;padding:12px;margin-bottom:8px;';
    form.innerHTML =
      '<div style="font-size:12px;color:#374151;margin-bottom:8px;">Laissez vos coordonnées, on vous recontacte :</div>' +
      '<input id="cb-lead-name" placeholder="Votre nom" style="width:100%;border:1px solid #ddd;border-radius:7px;padding:7px 10px;font-size:13px;margin-bottom:6px;box-sizing:border-box;">' +
      '<input id="cb-lead-email" type="email" placeholder="Votre email" style="width:100%;border:1px solid #ddd;border-radius:7px;padding:7px 10px;font-size:13px;margin-bottom:6px;box-sizing:border-box;">' +
      '<button id="cb-lead-go" style="width:100%;background:' + ACCENT + ';color:' + ACCENT_TEXT + ';border:none;border-radius:7px;padding:8px;font-size:13px;cursor:pointer;">Envoyer</button>';
    msgs.appendChild(form);
    scrollBottom();
    form.querySelector('#cb-lead-go').onclick = function () {
      var n = form.querySelector('#cb-lead-name').value.trim();
      var e = form.querySelector('#cb-lead-email').value.trim();
      if (!n || !e) { bot('Merci de remplir le nom et l\u2019email 😊'); return; }
      var leads = [];
      try { leads = JSON.parse(localStorage.getItem('cb_leads') || '[]'); } catch (err) {}
      leads.push({ site: NAME, name: n, email: e, date: new Date().toISOString(), question: lastQuestion });
      localStorage.setItem('cb_leads', JSON.stringify(leads));
      if (cfg.emailjs && window.emailjs) {
        try { emailjs.send(cfg.emailjs.serviceId, cfg.emailjs.templateId, { name: n, email: e, question: lastQuestion, site: NAME }); } catch (err) {}
      }
      form.remove();
      bot('Merci ' + n + ' ! 🙏 Votre demande est enregistrée, on vous répond très vite.');
    };
  }

  var lastQuestion = '';

  function send() {
    var q = input.value.trim();
    if (!q) return;
    addMsg(q, 'me');
    input.value = '';
    lastQuestion = q;
    var a = findAnswer(q);
    if (a) {
      bot(a);
    } else {
      bot('Bonne question ! Je préfère la transmettre à un conseiller pour vous répondre précisément. 🙂');
      askLead('Puis-je prendre vos coordonnées ?');
    }
  }

  btn.onclick = function () {
    open = !open;
    panel.style.display = open ? 'flex' : 'none';
    if (open) {
      if (!msgs.children.length) { bot(WELCOME); showQuick(); }
      input.focus();
    }
  };
  panel.querySelector('#cb-close').onclick = function () { open = false; panel.style.display = 'none'; };
  panel.querySelector('#cb-send').onclick = send;
  input.addEventListener('keydown', function (e) { if (e.key === 'Enter') send(); });
})();
