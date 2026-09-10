/* explain-change page script. Inline verbatim into every page; do not rewrite.
   Requires: <body data-snapshot="..."> ; cards with data-item="id" and .controls buttons
   with data-choice; .quiz blocks with data-item, .reveal buttons, .answer[hidden],
   optional .options buttons with data-correct; a .findings section with
   #findings-list, #findings-text, #copy-findings, #copy-status; and #persist-status. */
(function () {
  var snapshot = document.body.getAttribute('data-snapshot') || 'unknown';
  var key = 'explain-change:' + snapshot + ':' + location.pathname;
  var state = {};
  var storageOk = false;
  try {
    var raw = localStorage.getItem(key);
    state = raw ? JSON.parse(raw) : {};
    localStorage.setItem(key, JSON.stringify(state));
    storageOk = true;
  } catch (e) { state = {}; storageOk = false; }
  function save() {
    if (!storageOk) return;
    try { localStorage.setItem(key, JSON.stringify(state)); } catch (e) { storageOk = false; }
  }
  var ps = document.getElementById('persist-status');
  if (ps) ps.textContent = storageOk
    ? 'Your selections persist in this browser for snapshot ' + snapshot + '.'
    : 'Browser storage is unavailable; selections will not survive a reload. Copy the findings out before closing.';

  function titleOf(el) {
    var h = el.querySelector('h3, .prompt');
    return h ? h.textContent.trim() : el.getAttribute('data-item');
  }

  /* Accept / reject / discuss, with an optional note */
  var cards = document.querySelectorAll('[data-item] .controls');
  Array.prototype.forEach.call(cards, function (ctl) {
    var card = ctl.closest('[data-item]');
    var id = card.getAttribute('data-item');
    var stateEl = ctl.querySelector('.state');
    var buttons = ctl.querySelectorAll('button[data-choice]');
    var note = document.createElement('textarea');
    note.className = 'choice-note';
    note.placeholder = 'Add a note for the findings export (optional)';
    note.setAttribute('aria-label', 'Note on this decision');
    note.hidden = true;
    ctl.parentNode.insertBefore(note, ctl.nextSibling);
    function render() {
      var choice = state[id] && state[id].choice;
      Array.prototype.forEach.call(buttons, function (b) {
        b.setAttribute('aria-pressed', b.getAttribute('data-choice') === choice ? 'true' : 'false');
      });
      if (stateEl) stateEl.textContent = choice ? choice : 'not yet reviewed';
      var hasNote = state[id] && state[id].note;
      note.hidden = !(choice || hasNote);
      if (hasNote && note.value !== state[id].note) note.value = state[id].note;
    }
    Array.prototype.forEach.call(buttons, function (b) {
      b.addEventListener('click', function () {
        var c = b.getAttribute('data-choice');
        state[id] = state[id] || {};
        state[id].choice = state[id].choice === c ? null : c;
        state[id].title = titleOf(card);
        save(); render(); renderFindings();
        if (state[id].choice) note.focus();
      });
    });
    note.addEventListener('input', function () {
      state[id] = state[id] || {};
      state[id].note = note.value; state[id].title = titleOf(card);
      save(); renderFindings();
    });
    render();
  });

  /* Learning check */
  var quizzes = document.querySelectorAll('.quiz[data-item]');
  Array.prototype.forEach.call(quizzes, function (q) {
    var id = q.getAttribute('data-item');
    var answer = q.querySelector('.answer');
    var reveal = q.querySelector('.reveal');
    var options = q.querySelectorAll('.options button');
    var note = q.querySelector('textarea');
    state[id] = state[id] || {};
    function render() {
      if (answer) answer.hidden = !state[id].revealed;
      Array.prototype.forEach.call(options, function (o) {
        o.setAttribute('aria-pressed', o.getAttribute('data-option') === state[id].picked ? 'true' : 'false');
      });
      if (note && typeof state[id].note === 'string' && note.value !== state[id].note) note.value = state[id].note;
    }
    if (reveal) reveal.addEventListener('click', function () {
      state[id].revealed = !state[id].revealed; state[id].title = titleOf(q); save(); render();
    });
    Array.prototype.forEach.call(options, function (o) {
      o.addEventListener('click', function () {
        state[id].picked = o.getAttribute('data-option'); state[id].revealed = true; state[id].title = titleOf(q); save(); render();
      });
    });
    if (note) note.addEventListener('input', function () { state[id].note = note.value; save(); });
    render();
  });

  /* Findings list and export */
  var list = document.getElementById('findings-list');
  var text = document.getElementById('findings-text');
  function listed(s) { return s && (s.choice === 'reject' || s.choice === 'discuss' || (s.choice === 'accept' && s.note)); }
  function findingsMarkdown() {
    var lines = ['# Findings for ' + snapshot, ''];
    var any = false;
    Object.keys(state).forEach(function (id) {
      var s = state[id];
      if (listed(s)) {
        any = true;
        lines.push('- [' + s.choice + '] ' + (s.title || id) + ' (#' + id + ')');
        if (s.note) s.note.split('\n').forEach(function (l, i) { lines.push('  ' + (i === 0 ? 'User note: ' : '  ') + l); });
      }
    });
    if (!any) lines.push('(nothing rejected or marked for discussion)');
    return lines.join('\n');
  }
  function renderFindings() {
    if (list) {
      list.innerHTML = '';
      var any = false;
      Object.keys(state).forEach(function (id) {
        var s = state[id];
        if (listed(s)) {
          any = true;
          var li = document.createElement('li');
          var a = document.createElement('a'); a.href = '#' + id; a.textContent = s.title || id;
          li.appendChild(document.createTextNode(s.choice + ': ')); li.appendChild(a);
          if (s.note) { var n = document.createElement('div'); n.className = 'note'; n.textContent = 'User note: ' + s.note; li.appendChild(n); }
          list.appendChild(li);
        }
      });
      if (!any) { var e = document.createElement('li'); e.className = 'empty'; e.textContent = 'Nothing rejected, marked for discussion, or annotated yet.'; list.appendChild(e); }
    }
    if (text) text.value = findingsMarkdown();
  }
  var copy = document.getElementById('copy-findings');
  var status = document.getElementById('copy-status');
  if (copy) copy.addEventListener('click', function () {
    var md = findingsMarkdown();
    function done(ok) { if (status) status.textContent = ok ? 'Copied as markdown.' : 'Clipboard blocked; select the text box below and copy manually.'; }
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(md).then(function () { done(true); }, function () { done(false); });
    else done(false);
  });
  renderFindings();
})();
