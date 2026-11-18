import { h, setOnline, store } from './main.js';

const headers = { 'X-PhoneBox-Panel': '1' };
const panel = document.body;
setOnline(false);
const overview = document.querySelector('.ov-head');
const enabled = h('input');
enabled.type = 'checkbox';
enabled.checked = store.get('pwa-wake', false);
const wakeStatus = h('small');
const wake = h('label', 'pwa-wake', enabled, ' Keep screen on ', wakeStatus);
overview.append(wake);
wake.addEventListener('click', (event) => event.stopPropagation());

const name = h('input');
name.placeholder = 'e.g. Desk iPad';
name.maxLength = 40;
const code = h('input');
code.placeholder = 'Pairing code from the desktop agent';
code.required = true;
code.maxLength = 32;
code.autocapitalize = 'none';
code.spellcheck = false;
const submit = h('button', null, 'Pair');
submit.type = 'submit';
const message = h('p');
message.setAttribute('role', 'status');
const form = h('form', 'pwa-pair',
  h('h1', null, 'Pair PhoneBox'),
  h('p', null, 'On the computer, open PhoneBox settings and choose Web app setup. Enter the code here.'),
  h('label', null, 'Device name', name),
  h('label', null, 'Pairing code', code),
  submit, message,
  h('p', null, 'To install in Safari, choose Share → Add to Home Screen. Pair from the installed app if it asks for a code.'));
const setup = h('div', 'pwa-setup', form);
setup.hidden = true;
panel.append(setup);

function readPairingFragment() {
  const fragment = new URLSearchParams(location.hash.slice(1)).get('pair');
  if (fragment === null) return;
  history.replaceState(history.state, '', location.pathname + location.search);
  if (/^[a-f0-9]{32}$/.test(fragment)) {
    code.value = fragment;
    setup.hidden = false;
  }
}
window.addEventListener('hashchange', readPairingFragment);
readPairingFragment();

let stream;
let probing;
let screenLock;
let acquiring = false;
let foreground = true;

function closeStream() {
  if (!stream) return;
  stream.close();
  stream = null;
  window.onAgentStream('close');
}

function openStream() {
  if (stream || !foreground || document.hidden || panel.dataset.pwaSession !== 'paired') return;
  const source = new EventSource('/agent/api/stream');
  stream = source;
  source.onopen = () => { if (stream === source) window.onAgentStream('open'); };
  source.onerror = () => {
    if (stream !== source) return;
    window.onAgentStream('close');
    if (source.readyState === EventSource.CLOSED) closeStream();
    checkSession(false);
  };
  for (const type of ['state', 'event', 'work', 'spectrum']) {
    source.addEventListener(type, (event) => { if (stream === source) window.onAgentStream(type, event.data); });
  }
}

function showPairing() {
  panel.dataset.pwaSession = 'unpaired';
  setup.hidden = false;
  closeStream();
  setOnline(false);
}

function checkSession(reopen = true) {
  if (probing) return probing;
  probing = (async () => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 4000);
    try {
      const response = await fetch('/pwa/session', { headers, cache: 'no-store', signal: controller.signal });
      if (response.status === 401) { showPairing(); return; }
      if (!response.ok) return;
      setup.hidden = !code.value;
      panel.dataset.pwaSession = 'paired';
      if (reopen) openStream();
    } catch (_) {
      // The cached panel can boot while the agent is down. Foreground polling retries when it is reachable.
      if (!panel.dataset.pwaSession) setOnline(false);
    } finally { clearTimeout(timer); }
  })().finally(() => { probing = null; });
  return probing;
}

form.onsubmit = async (event) => {
  event.preventDefault();
  submit.disabled = true;
  await probing;
  message.textContent = '';
  try {
    const response = await fetch('/pwa/session', {
      method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: code.value.trim().toLowerCase(), name: name.value }),
    });
    if (!response.ok) {
      message.textContent = 'Pairing was refused. Create a fresh code on the computer and try again.';
      return;
    }
    code.value = '';
    await checkSession();
  } catch (_) {
    message.textContent = 'The computer could not be reached. Check the HTTPS address and try again.';
  } finally { submit.disabled = false; }
};

async function syncWake() {
  if (!enabled.checked || !foreground || document.hidden) {
    const lock = screenLock;
    screenLock = null;
    await lock?.release();
    return;
  }
  if (!navigator.wakeLock) { wakeStatus.textContent = 'Unavailable in this browser'; return; }
  if (screenLock || acquiring) return;
  acquiring = true;
  try {
    const lock = await navigator.wakeLock.request('screen');
    if (!enabled.checked || !foreground || document.hidden || lock.released) { await lock.release(); return; }
    screenLock = lock;
    wakeStatus.textContent = 'Active';
    lock.addEventListener('release', () => {
      if (screenLock === lock) screenLock = null;
      wakeStatus.textContent = enabled.checked ? 'Released by the system' : '';
    }, { once: true });
  } catch (_) { wakeStatus.textContent = 'Unavailable right now'; }
  finally { acquiring = false; }
}

enabled.onchange = () => {
  store.set('pwa-wake', enabled.checked);
  wakeStatus.textContent = '';
  syncWake();
};
function resume() {
  if (!foreground || document.hidden) closeStream();
  else checkSession().then(openStream);
  syncWake();
}

document.addEventListener('visibilitychange', resume);
window.addEventListener('pagehide', () => { foreground = false; resume(); });
window.addEventListener('pageshow', () => { foreground = true; resume(); });
window.addEventListener('online', resume);
window.addEventListener('phonebox-session-required', showPairing);
setInterval(() => {
  if (foreground && !document.hidden && panel.dataset.pwaSession !== 'unpaired' && !stream)
    checkSession();
}, 5000);

if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js', { updateViaCache: 'none' }).catch(() => {});
resume();
