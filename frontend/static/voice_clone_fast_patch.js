(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const provider = $('provider');
  const generateButton = $('generate');
  if (!provider || !generateButton) return;

  let fastState = null;
  let runtimeState = null;
  let runningTimer = null;
  let warmRequested = false;

  function plainFast(value) {
    if (value == null) return '';
    if (typeof value === 'string') return value;
    if (Array.isArray(value)) return value.map(plainFast).filter(Boolean).join(' | ');
    if (typeof value === 'object') {
      for (const key of ['message', 'detail', 'error', 'reason', 'last_error']) {
        if (value[key] != null) return plainFast(value[key]);
      }
      try { return JSON.stringify(value); } catch { return String(value); }
    }
    return String(value);
  }

  async function fastApi(url, options = {}, timeout = 1200000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(url, {...options, signal: controller.signal});
      let data = {};
      try { data = await response.json(); }
      catch { data = {detail: await response.text()}; }
      if (!response.ok || data.success === false) {
        const attempts = data?.detail?.attempts || data?.attempts || [];
        const attemptText = attempts.length
          ? ' | المحاولات: ' + attempts.map(x => `${x.provider}: ${plainFast(x.error)}`).join(' | ')
          : '';
        throw new Error(plainFast(data.detail || data.message || data) + attemptText);
      }
      return data;
    } catch (error) {
      if (error && error.name === 'AbortError') {
        throw new Error('انتهت المهلة. تم منع الانتظار المفتوح؛ جرّب الوضع التلقائي أو ElevenLabs، أو أعد تجهيز XTTS.');
      }
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  function installProviderOptions() {
    const remembered = localStorage.getItem('clone:fast-provider') || 'auto';
    provider.innerHTML = [
      ['auto', 'تلقائي سريع — ElevenLabs ثم Gemini المصرح ثم XTTS'],
      ['elevenlabs', 'Human Pro — ElevenLabs (أسرع عند توفر الخطة)'],
      ['gemini_vertex', 'Gemini Voice Replication — وصول Google Cloud خاص'],
      ['local', 'XTTS-v2 المحلي — مجاني بعد التجهيز الكامل'],
    ].map(([value, label]) => `<option value="${value}">${label}</option>`).join('');
    provider.value = Array.from(provider.options).some(option => option.value === remembered) ? remembered : 'auto';
    provider.addEventListener('change', () => {
      localStorage.setItem('clone:fast-provider', provider.value);
      showProviderHint();
    });

    const hint = document.createElement('div');
    hint.id = 'fastProviderHint';
    hint.className = 'mini';
    hint.style.marginTop = '7px';
    provider.parentElement.appendChild(hint);
    showProviderHint();
  }

  function showProviderHint() {
    const hint = $('fastProviderHint');
    if (!hint) return;
    const messages = {
      auto: 'يوصى به: يستخدم أسرع محرك استنساخ حقيقي متاح، ولا يستبدل صوت العينة بصوت جاهز.',
      elevenlabs: 'يتطلب مفتاحًا وخطة تسمح بـ Instant Voice Cloning.',
      gemini_vertex: 'يتطلب Google Cloud Project وقبول المشروع في Gemini Voice Replication Allowlist؛ مفتاح Gemini AI Studio العادي لا يكفي.',
      local: 'يعمل على جهازك. تُحمّل الأداة نموذج XTTS في الذاكرة بالخلفية ثم تعيد استخدامه.',
    };
    hint.textContent = messages[provider.value] || '';
  }

  function installGeminiCard() {
    const cloudChip = $('cloudChip');
    const cloudEngine = cloudChip && cloudChip.closest('.engine');
    if (!cloudEngine || $('geminiCloneChip')) return;
    const card = document.createElement('div');
    card.className = 'engine';
    card.innerHTML = `
      <div class="engineHead">
        <div class="engineTitle">Gemini Voice Replication — Vertex AI</div>
        <span id="geminiCloneChip" class="chip bad">وصول خاص</span>
      </div>
      <p id="geminiCloneReason">يتطلب مشروع Google Cloud مصرحًا له بميزة Voice Replication وبيانات حساب خدمة.</p>`;
    cloudEngine.insertAdjacentElement('afterend', card);
  }

  async function requestWarmIfNeeded(data, runtime) {
    if (!data.xtts_model_warmed || runtime?.state === 'ready' || runtime?.state === 'warming' || warmRequested) return;
    warmRequested = true;
    try {
      await fastApi('/api/voice-clone-runtime/warm', {method: 'POST'}, 20000);
    } catch (error) {
      warmRequested = false;
      console.warn('XTTS warm request:', error);
    }
  }

  async function refreshFastState() {
    try {
      const [data, runtime] = await Promise.all([
        fastApi('/api/voice-clone-fast/status', {}, 20000),
        fastApi('/api/voice-clone-runtime/status', {}, 20000).catch(() => null),
      ]);
      fastState = data;
      runtimeState = runtime;
      const modelReady = !!data.local_engine_ready && !!data.xtts_model_warmed;
      const memoryReady = runtime?.state === 'ready';
      const warming = runtime?.state === 'warming';
      $('localChip').textContent = memoryReady
        ? 'جاهز في الذاكرة'
        : warming
          ? 'تحميل في الذاكرة...'
          : modelReady
            ? 'النموذج جاهز'
            : data.local_engine_ready
              ? 'يحتاج تنزيل النموذج'
              : 'غير جاهز';
      $('localChip').className = 'chip ' + (memoryReady || modelReady ? 'ok' : 'bad');
      if (!modelReady && data.local_setup?.state === 'needs_model') {
        $('setupLocal').textContent = 'تنزيل وتجهيز نموذج XTTS الكامل';
      } else if (memoryReady) {
        $('setupLocal').textContent = 'XTTS جاهز في الذاكرة';
      } else if (modelReady) {
        $('setupLocal').textContent = warming ? 'جاري تحميل XTTS في الذاكرة...' : 'XTTS والنموذج جاهزان';
      }
      if (runtime?.state === 'failed' && runtime.error) {
        status('setupStatus', `${runtime.message || 'فشل تشغيل XTTS.'} ${runtime.error}`, 'err');
      }
      const geminiChip = $('geminiCloneChip');
      if (geminiChip) {
        geminiChip.textContent = data.gemini_vertex_ready ? 'جاهز تقنيًا' : 'غير مربوط';
        geminiChip.className = 'chip ' + (data.gemini_vertex_ready ? 'ok' : 'bad');
      }
      const reason = $('geminiCloneReason');
      if (reason) reason.textContent = data.gemini_vertex_reason || '';
      await requestWarmIfNeeded(data, runtime);
    } catch (error) {
      console.warn('Fast clone status:', error);
    }
  }

  function beginElapsed(providerName) {
    const started = Date.now();
    clearInterval(runningTimer);
    runningTimer = setInterval(() => {
      const seconds = Math.floor((Date.now() - started) / 1000);
      const minutes = Math.floor(seconds / 60);
      const rest = seconds % 60;
      status(
        'generateStatus',
        `جاري الاستنساخ عبر ${providerName} — المدة ${minutes}:${String(rest).padStart(2, '0')}. لن يبقى الطلب معلقًا بلا نهاية...`,
        'wait'
      );
    }, 1000);
  }

  function endElapsed() {
    clearInterval(runningTimer);
    runningTimer = null;
  }

  generateButton.onclick = async event => {
    event.preventDefault();
    if (!selectedProfile) return status('generateStatus', 'حدد ملف صوت من القائمة أولًا.', 'err');
    const text = $('text').value.trim();
    if (text.length < 2) return status('generateStatus', 'اكتب النص المطلوب.', 'err');

    if (provider.value === 'local' && fastState && (!fastState.local_engine_ready || !fastState.xtts_model_warmed)) {
      return status('generateStatus', 'XTTS مثبت جزئيًا فقط. وافق على الترخيص واضغط «تنزيل وتجهيز نموذج XTTS الكامل» أولًا.', 'err');
    }

    try {
      busy('generate', true);
      $('result').classList.remove('show');
      const label = provider.options[provider.selectedIndex]?.textContent || provider.value;
      const referenceMessage = 'سيستخدم البرنامج أفضل 10–30 ثانية من العينة بدل معالجة التسجيل الطويل كاملًا.';
      status('generateStatus', `بدأ الإنتاج عبر ${label}. ${referenceMessage}`, 'wait');
      beginElapsed(label);
      const data = await fastApi('/api/voice-clone-fast/generate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          profile_id: selectedProfile,
          text,
          provider: provider.value,
          language: $('language').value,
          speed: Number($('speed').value),
          style: $('style').value,
        }),
      }, 1200000);

      $('audio').src = data.url + '?t=' + Date.now();
      $('download').href = data.url;
      $('projectPath').textContent = data.desktop_project;
      lastProject = data.desktop_project;
      $('result').classList.add('show');
      const attempts = (data.attempts || []).length
        ? ` تم تجاوز ${data.attempts.length} محرك غير متاح تلقائيًا.`
        : '';
      status(
        'generateStatus',
        `${data.message} المحرك الفعلي: ${data.provider}. الجودة: ${data.quality}.${attempts}`,
        'ok'
      );
    } catch (error) {
      status('generateStatus', plainFast(error.message || error), 'err');
    } finally {
      endElapsed();
      busy('generate', false);
    }
  };

  installProviderOptions();
  installGeminiCard();
  refreshFastState();
  setInterval(refreshFastState, 5000);
})();
