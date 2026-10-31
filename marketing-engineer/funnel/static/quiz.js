/* Quiz page. Order of operations, on purpose:
   1. Read utm_* and fbclid from the URL into memory only (no cookie, no storage, no request).
   2. Load the questions from /quiz/config (no PII, nothing about the visitor).
   3. Show the consent screen. NOTHING is measured until "Start": no pixel, no CAPI, no lead row.
   4. Start → POST /quiz/start (lead row, server-side QuizStart only when tracking consent);
      the Meta pixel is initialised only when tracking consent is true and a pixel id is configured,
      and it fires with the same event_id the server used, so Meta deduplicates.
   5. Questions → contact → POST /quiz (QuizComplete once) → calendar link when qualified. */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var params = new URLSearchParams(location.search);
  var client = params.get("client") || "upclicklabs";
  var utm = {};
  ["source", "medium", "campaign", "content", "term"].forEach(function (k) {
    var v = params.get("utm_" + k); if (v) { utm[k] = v.slice(0, 200); }
  });
  var fbclid = params.get("fbclid") || null;

  var state = { config: null, questions: [], index: 0, answers: {}, leadId: null, tracking: false };

  function show(id) {
    Array.prototype.forEach.call(document.querySelectorAll(".screen"), function (s) { s.hidden = s.id !== id; });
    $("quiz").dataset.state = id.replace("screen-", "");
  }
  function progress(step, total) { $("progress").style.width = Math.round(100 * step / total) + "%"; }
  function fail(id, msg) { var el = $(id); el.textContent = msg; el.hidden = false; }
  function clear(id) { $(id).hidden = true; }

  function api(method, path, body) {
    return fetch(path, {
      method: method,
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined
    }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, status: r.status, body: j }; }); });
  }

  /* --- Meta pixel: only after tracking consent, only with a configured id (FR-33). --- */
  function initPixel(pixelId) {
    if (!pixelId || window.fbq) { return; }
    /* Meta's standard snippet; not loaded before consent. */
    !function (f, b, e, v, n, t, s) {
      if (f.fbq) return; n = f.fbq = function () { n.callMethod ? n.callMethod.apply(n, arguments) : n.queue.push(arguments); };
      if (!f._fbq) f._fbq = n; n.push = n; n.loaded = !0; n.version = "2.0"; n.queue = [];
      t = b.createElement(e); t.async = !0; t.src = v; s = b.getElementsByTagName(e)[0]; s.parentNode.insertBefore(t, s);
    }(window, document, "script", "https://connect.facebook.net/en_US/fbevents.js");
    window.fbq("init", pixelId, { external_id: state.leadId });
    window.fbq("track", "PageView");
  }
  function pixelTrack(name, eventId) {
    if (state.tracking && window.fbq && eventId) { window.fbq("track", name, {}, { eventID: eventId }); }
  }

  /* --- Turnstile: tokens are single-use, so each POST has its own widget (Start on the consent screen, submit on the
         contact screen) and a POST that failed resets its widget for a fresh token. Rendered only when a site key is
         configured; in dev the token is a placeholder. --- */
  var ts = { siteKey: null, ready: null, widgets: {}, tokens: { start: null, complete: null } };
  function setupTurnstile(siteKey) {
    if (!siteKey) { ts.tokens.start = ts.tokens.complete = "dev-pass"; return; }
    ts.siteKey = siteKey;
    ts.ready = new Promise(function (resolve) {
      var s = document.createElement("script");
      s.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
      s.async = true; s.defer = true; s.onload = resolve;
      document.head.appendChild(s);
    });
    renderWidget("start", "#turnstile-box");
  }
  function renderWidget(purpose, selector) {
    if (!ts.siteKey || purpose in ts.widgets) { return; }
    ts.widgets[purpose] = null;
    ts.ready.then(function () {
      ts.widgets[purpose] = window.turnstile.render(selector, {
        sitekey: ts.siteKey,
        callback: function (t) { ts.tokens[purpose] = t; },
        "expired-callback": function () { ts.tokens[purpose] = null; }
      });
    });
  }
  function freshToken(purpose) {
    if (!ts.siteKey) { return; }
    ts.tokens[purpose] = null;
    if (ts.widgets[purpose] !== null && ts.widgets[purpose] !== undefined) { window.turnstile.reset(ts.widgets[purpose]); }
  }

  function renderQuestion() {
    var q = state.questions[state.index];
    progress(state.index + 1, state.questions.length + 2);
    $("question-count").textContent = "Question " + (state.index + 1) + " of " + state.questions.length;
    $("question-text").textContent = q.text;
    var box = $("question-options"); box.innerHTML = "";
    q.options.forEach(function (opt) {
      var b = document.createElement("button"); b.type = "button"; b.textContent = opt; b.dataset.option = opt;
      b.addEventListener("click", function () {
        state.answers[q.id] = opt;
        if (state.index + 1 < state.questions.length) { state.index += 1; renderQuestion(); }
        else {
          progress(state.questions.length + 1, state.questions.length + 2); show("screen-contact");
          renderWidget("complete", "#turnstile-box-contact"); $("contact-email").focus();
        }
      });
      box.appendChild(b);
    });
    show("screen-question");
  }

  function start() {
    clear("error-consent");
    if (!ts.tokens.start) { fail("error-consent", "Please complete the verification first."); return; }
    var btn = $("btn-start"); btn.disabled = true;
    var consent = { tracking: $("consent-tracking").checked, marketing: $("consent-marketing").checked, verbatim_use: $("consent-verbatim").checked };
    api("POST", "/quiz/start", { client: client, consent: consent, utm: utm, fbclid: fbclid, turnstile_token: ts.tokens.start })
      .then(function (r) {
        btn.disabled = false;
        if (!r.ok) { freshToken("start"); fail("error-consent", r.body.error || "Something went wrong."); return; }
        state.leadId = r.body.lead_id; state.tracking = consent.tracking;
        if (state.tracking) { initPixel(state.config.pixel_id); pixelTrack("QuizStart", r.body.event_id); }
        state.index = 0; renderQuestion();
      })
      .catch(function () { btn.disabled = false; freshToken("start"); fail("error-consent", "Network error; please try again."); });
  }

  function submit(ev) {
    ev.preventDefault(); clear("error-contact");
    if (!ts.tokens.complete) { fail("error-contact", "Please complete the verification first."); return; }
    var btn = $("btn-submit"); btn.disabled = true;
    var contact = { email: $("contact-email").value.trim(), name: $("contact-name").value.trim() || null, phone: $("contact-phone").value.trim() || null };
    api("POST", "/quiz", { client: client, lead_id: state.leadId, answers: state.answers, contact: contact, turnstile_token: ts.tokens.complete })
      .then(function (r) {
        btn.disabled = false;
        if (!r.ok) { freshToken("complete"); fail("error-contact", r.body.error || "Something went wrong."); return; }
        pixelTrack("QuizComplete", r.body.event_id);
        progress(1, 1);
        if (r.body.calendar_url) {
          $("done-title").textContent = "One more step";
          $("done-text").textContent = "Pick a time for your free 15-minute call.";
          var a = $("btn-book"); a.href = r.body.calendar_url; a.hidden = false;
        } else {
          $("done-title").textContent = "Thanks!";
          $("done-text").textContent = "We have your answers and will be in touch by email.";
        }
        show("screen-done");
      })
      .catch(function () { btn.disabled = false; freshToken("complete"); fail("error-contact", "Network error; please try again."); });
  }

  api("GET", "/quiz/config?client=" + encodeURIComponent(client)).then(function (r) {
    if (!r.ok) { $("screen-loading").textContent = r.body.error || "This quiz is not available."; return; }
    state.config = r.body; state.questions = r.body.questions || [];
    $("offer-name").textContent = r.body.offer_name || "Quiz";
    $("promise").textContent = r.body.promise || "";
    $("notice-version").textContent = r.body.notice_version || "";
    document.title = r.body.offer_name || "Quiz";
    setupTurnstile(r.body.turnstile_site_key);
    $("btn-start").addEventListener("click", start);
    $("contact-form").addEventListener("submit", submit);
    progress(0, state.questions.length + 2);
    show("screen-consent");
  }).catch(function () { $("screen-loading").textContent = "Could not load the quiz."; });
})();
