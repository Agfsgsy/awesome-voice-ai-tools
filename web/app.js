const API = '';

function showLoading(text = 'جاري المعالجة...') {
  document.getElementById('loading').classList.remove('hidden');
  document.getElementById('loading-text').textContent = text;
}
function hideLoading() {
  document.getElementById('loading').classList.add('hidden');
}

function showResult(containerId, audioUrl, message) {
  const box = document.getElementById(containerId);
  box.classList.remove('hidden');
  box.innerHTML = `
    <p style="color:#10b981;font-weight:700;margin-bottom:10px;">✅ ${message}</p>
    <audio controls src="${audioUrl}"></audio>
    <br/><br/>
    <a href="${audioUrl}" download class="btn-primary" style="text-align:center;display:inline-block;padding:10px 24px;text-decoration:none;">⬇️ تحميل الصوت</a>
  `;
}

function showError(containerId, msg) {
  const box = document.getElementById(containerId);
  box.classList.remove('hidden');
  box.style.background = 'rgba(239,68,68,0.08)';
  box.style.borderColor = 'rgba(239,68,68,0.3)';
  box.innerHTML = `<p style="color:#f87171;">❌ ${msg}</p>`;
}

async function generateVoice() {
  const text = document.getElementById('tts-text').value.trim();
  const engine = document.getElementById('engine').value;
  const lang = document.getElementById('language').value;
  if (!text) return alert('الرجاء إدخال نص أولاً');

  showLoading('جاري توليد الصوت...');
  try {
    const res = await fetch(`${API}/api/tts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, engine, language: lang })
    });
    const data = await res.json();
    hideLoading();
    if (data.audio_url) showResult('tts-result', data.audio_url, 'تم توليد الصوت بنجاح!');
    else showError('tts-result', data.error || 'حدث خطأ غير متوقع');
  } catch (e) {
    hideLoading();
    showError('tts-result', 'تعذر الاتصال بالخادم. تأكد من تشغيل server.py');
  }
}

async function cloneVoice() {
  const text = document.getElementById('clone-text').value.trim();
  const engine = document.getElementById('clone-engine').value;
  const refFile = document.getElementById('ref-audio').files[0];
  if (!text) return alert('الرجاء إدخال النص');
  if (!refFile) return alert('الرجاء رفع عينة صوتية مرجعية');

  showLoading('جاري استنساخ الصوت...');
  const form = new FormData();
  form.append('text', text);
  form.append('engine', engine);
  form.append('reference', refFile);

  try {
    const res = await fetch(`${API}/api/clone`, { method: 'POST', body: form });
    const data = await res.json();
    hideLoading();
    if (data.audio_url) showResult('clone-result', data.audio_url, 'تم الاستنساخ بنجاح!');
    else showError('clone-result', data.error || 'حدث خطأ');
  } catch (e) {
    hideLoading();
    showError('clone-result', 'تعذر الاتصال بالخادم');
  }
}

async function applyEffects() {
  const fxFile = document.getElementById('fx-audio').files[0];
  if (!fxFile) return alert('الرجاء رفع ملف صوتي');

  const preset = document.querySelector('.preset-btn.active')?.dataset.preset || 'studio';
  const reverb = document.getElementById('reverb').value;
  const echo = document.getElementById('echo').value;
  const compress = document.getElementById('compress').value;
  const pitch = document.getElementById('pitch').value;
  const denoise = document.getElementById('denoise').checked;

  showLoading('جاري تطبيق المؤثرات...');
  const form = new FormData();
  form.append('audio', fxFile);
  form.append('preset', preset);
  form.append('reverb', reverb);
  form.append('echo', echo);
  form.append('compress', compress);
  form.append('pitch', pitch);
  form.append('denoise', denoise);

  try {
    const res = await fetch(`${API}/api/effects`, { method: 'POST', body: form });
    const data = await res.json();
    hideLoading();
    if (data.audio_url) showResult('fx-result', data.audio_url, 'تمت المعالجة بنجاح!');
    else showError('fx-result', data.error || 'حدث خطأ');
  } catch (e) {
    hideLoading();
    showError('fx-result', 'تعذر الاتصال بالخادم');
  }
}

async function generateQuran() {
  const text = document.getElementById('quran-text').value.trim();
  const style = document.getElementById('quran-style').value;
  if (!text) return alert('الرجاء إدخال النص القرآني');

  showLoading('جاري توليد التلاوة...');
  try {
    const res = await fetch(`${API}/api/islamic/quran`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, style })
    });
    const data = await res.json();
    hideLoading();
    if (data.audio_url) showResult('islamic-result', data.audio_url, 'تم توليد التلاوة!');
    else showError('islamic-result', data.error || 'حدث خطأ');
  } catch (e) {
    hideLoading();
    showError('islamic-result', 'تعذر الاتصال بالخادم');
  }
}

async function generateSheikh() {
  const text = document.getElementById('sheikh-text').value.trim();
  const preset = document.getElementById('sheikh-preset').value;
  const refFile = document.getElementById('sheikh-audio').files[0];
  if (!text) return alert('الرجاء إدخال النص');

  showLoading('جاري توليد صوت الشيخ...');
  const form = new FormData();
  form.append('text', text);
  form.append('preset', preset);
  if (refFile) form.append('reference', refFile);

  try {
    const res = await fetch(`${API}/api/islamic/sheikh`, { method: 'POST', body: form });
    const data = await res.json();
    hideLoading();
    if (data.audio_url) showResult('islamic-result', data.audio_url, 'تم توليد صوت الشيخ!');
    else showError('islamic-result', data.error || 'حدث خطأ');
  } catch (e) {
    hideLoading();
    showError('islamic-result', 'تعذر الاتصال بالخادم');
  }
}

async function generateAdhan() {
  const type = document.getElementById('adhan-type').value;
  const text = document.getElementById('adhan-text').value.trim();

  showLoading('جاري التوليد...');
  try {
    const res = await fetch(`${API}/api/islamic/adhan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type, text })
    });
    const data = await res.json();
    hideLoading();
    if (data.audio_url) showResult('islamic-result', data.audio_url, 'تم التوليد بنجاح!');
    else showError('islamic-result', data.error || 'حدث خطأ');
  } catch (e) {
    hideLoading();
    showError('islamic-result', 'تعذر الاتصال بالخادم');
  }
}

function previewAudio(input) {
  const audio = document.getElementById('ref-preview');
  audio.src = URL.createObjectURL(input.files[0]);
  audio.classList.remove('hidden');
}
function previewFxAudio(input) {
  const audio = document.getElementById('fx-preview');
  audio.src = URL.createObjectURL(input.files[0]);
  audio.classList.remove('hidden');
}
function previewSheikh(input) {
  const audio = document.getElementById('sheikh-preview');
  audio.src = URL.createObjectURL(input.files[0]);
  audio.classList.remove('hidden');
}

function selectPreset(btn, preset) {
  document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  btn.dataset.preset = preset;
  const presets = {
    studio:  { reverb:10, echo:0, compress:50, pitch:0 },
    masjid:  { reverb:45, echo:20, compress:35, pitch:-1 },
    lecture: { reverb:10, echo:5,  compress:60, pitch:0 },
    deep:    { reverb:30, echo:10, compress:45, pitch:-3 },
  };
  const p = presets[preset];
  document.getElementById('reverb').value = p.reverb;
  document.getElementById('echo').value = p.echo;
  document.getElementById('compress').value = p.compress;
  document.getElementById('pitch').value = p.pitch;
  document.getElementById('reverb-val').textContent = p.reverb + '%';
  document.getElementById('echo-val').textContent = p.echo + '%';
  document.getElementById('comp-val').textContent = p.compress + '%';
  document.getElementById('pitch-val').textContent = p.pitch;
}

function switchTab(btn, tabId) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById(tabId).classList.add('active');
}

function openTool(tool) {
  alert(`🛠️ أداة "${tool}" — سيتم إضافتها قريباً في التحديث القادم!`);
}
