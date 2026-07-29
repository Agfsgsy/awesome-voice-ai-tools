(() => {
  "use strict";

  const ANALYZE_ENDPOINT = "/api/voice-ai/audio/reference/analyze";
  let recorder = null;
  let stream = null;
  let chunks = [];
  let timer = null;
  let startedAt = 0;

  function messageOf(value) {
    if (!value) return "خطأ غير معروف";
    if (typeof value === "string") return value;
    const detail = value.detail || value;
    return detail.message || detail.error || JSON.stringify(detail);
  }

  function appendRecordedFile(input, file) {
    if (typeof DataTransfer === "undefined") {
      throw new Error("المتصفح الحالي لا يدعم إضافة التسجيل مباشرة. احفظ التسجيل ثم ارفعه يدويًا.");
    }
    const transfer = new DataTransfer();
    Array.from(input.files || []).forEach(item => transfer.items.add(item));
    transfer.items.add(file);
    input.files = transfer.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function formatSeconds(seconds) {
    const value = Math.max(0, Math.floor(seconds));
    return `${String(Math.floor(value / 60)).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}`;
  }

  function renderAnalysis(target, payload) {
    const files = payload.files || [];
    if (!files.length) {
      target.textContent = "لم تصل نتيجة تحليل.";
      return;
    }
    target.innerHTML = files.map(item => {
      if (!item.success) {
        return `<div style="border:1px solid #8c3f49;background:#2b151a;padding:9px;border-radius:10px;margin-top:7px"><b>${item.filename}</b><br>${item.error || "ملف غير صالح"}</div>`;
      }
      const score = Number(item.quality_score || 0);
      const color = score >= 76 ? "#7fffd9" : score >= 55 ? "#ffe19a" : "#ffb4b9";
      const warnings = (item.warnings || []).map(value => `<li>${value}</li>`).join("");
      return `<div style="border:1px solid #31506e;background:#081523;padding:10px;border-radius:11px;margin-top:7px">
        <div style="display:flex;justify-content:space-between;gap:8px"><b>${item.filename}</b><b style="color:${color}">${score}/100 — ${item.quality_label || ""}</b></div>
        <div style="font-size:11px;color:#9db4ca;margin-top:5px">${item.container || ""} / ${item.codec || ""} • ${Number(item.duration || 0).toFixed(1)} ثانية • SNR ${Number(item.snr_db_estimate || 0).toFixed(1)} dB</div>
        ${warnings ? `<ul style="margin:7px 18px 0 0;color:#e6cc8d;font-size:11px">${warnings}</ul>` : ""}
      </div>`;
    }).join("");
  }

  async function analyzeFiles(input, output, button) {
    const files = Array.from(input.files || []);
    if (!files.length) {
      output.textContent = "اختر تسجيلًا أو سجّل من الميكروفون أولًا.";
      return;
    }
    const data = new FormData();
    files.forEach(file => data.append("files", file, file.name));
    button.disabled = true;
    output.textContent = "جاري فك الترميز وتحليل الكلام والضوضاء والصمت والتشويه...";
    try {
      const response = await fetch(ANALYZE_ENDPOINT, { method: "POST", body: data });
      const payload = await response.json().catch(async () => ({ detail: await response.text() }));
      if (!response.ok) throw new Error(messageOf(payload));
      renderAnalysis(output, payload);
    } catch (error) {
      output.textContent = `فشل التحليل: ${error.message}`;
    } finally {
      button.disabled = false;
    }
  }

  function install() {
    const input = document.getElementById("samples");
    if (!input || document.getElementById("precision-reference-tools")) return;

    input.accept = "audio/*,video/*,.amr,.3gp,.3g2,.webm,.weba,.opus,.ogg,.oga,.m4a,.m4b,.aac,.flac,.wav,.mp3,.wma,.aiff,.aif,.caf,.ape,.mka,.mp4,.mov,.mkv";
    const badge = document.querySelector(".hero .badge");
    if (badge) badge.textContent = "Voice Clone Pro • Precision Reference Update";

    const tools = document.createElement("div");
    tools.id = "precision-reference-tools";
    tools.style.cssText = "margin-top:10px;border:1px solid #2a5970;background:#071b2a;padding:11px;border-radius:12px";
    tools.innerHTML = `
      <div style="font-weight:900">🎙️ تسجيل وتحليل دقيق للعينة</div>
      <div style="font-size:11px;color:#93aec3;line-height:1.7;margin-top:4px">يقبل أي ملف صوت أو فيديو يستطيع FFmpeg قراءته، ثم يحوله تلقائيًا إلى WAV مناسب ويختار أفضل التسجيلات.</div>
      <div style="display:flex;flex-wrap:wrap;gap:7px;margin-top:9px">
        <button id="precision-record" type="button" class="btn">بدء التسجيل</button>
        <button id="precision-stop" type="button" class="btn danger" disabled>إيقاف وإضافة التسجيل</button>
        <button id="precision-analyze" type="button" class="btn gold">تحليل العينات قبل الحفظ</button>
        <span id="precision-timer" style="align-self:center;color:#83ead5;font-weight:900">00:00</span>
      </div>
      <div id="precision-analysis" style="margin-top:8px;color:#bed0e1;font-size:12px"></div>
    `;
    input.parentElement.appendChild(tools);

    const startButton = tools.querySelector("#precision-record");
    const stopButton = tools.querySelector("#precision-stop");
    const analyzeButton = tools.querySelector("#precision-analyze");
    const output = tools.querySelector("#precision-analysis");
    const timerText = tools.querySelector("#precision-timer");

    startButton.addEventListener("click", async () => {
      if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
        output.textContent = "التسجيل المباشر غير مدعوم في هذا المتصفح؛ ارفع ملفًا صوتيًا من الهاتف أو الكمبيوتر.";
        return;
      }
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: false, autoGainControl: false, channelCount: 1 },
        });
        const candidates = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4", "audio/webm"];
        const mimeType = candidates.find(type => MediaRecorder.isTypeSupported(type)) || "";
        recorder = mimeType ? new MediaRecorder(stream, { mimeType, audioBitsPerSecond: 128000 }) : new MediaRecorder(stream);
        chunks = [];
        recorder.ondataavailable = event => { if (event.data?.size) chunks.push(event.data); };
        recorder.onstop = () => {
          const type = recorder.mimeType || mimeType || "audio/webm";
          const extension = type.includes("ogg") ? "ogg" : type.includes("mp4") ? "m4a" : "webm";
          const blob = new Blob(chunks, { type });
          try {
            appendRecordedFile(input, new File([blob], `microphone_${Date.now()}.${extension}`, { type }));
            output.textContent = `تمت إضافة تسجيل الميكروفون (${formatSeconds((Date.now() - startedAt) / 1000)}). اضغط تحليل العينات.`;
          } catch (error) {
            output.textContent = error.message;
          }
          stream?.getTracks().forEach(track => track.stop());
          stream = null;
          recorder = null;
          chunks = [];
        };
        recorder.start(500);
        startedAt = Date.now();
        timerText.textContent = "00:00";
        timer = window.setInterval(() => { timerText.textContent = formatSeconds((Date.now() - startedAt) / 1000); }, 500);
        startButton.disabled = true;
        stopButton.disabled = false;
        output.textContent = "جاري التسجيل... تكلم طبيعيًا، من دون موسيقى أو أشخاص آخرين.";
      } catch (error) {
        output.textContent = `تعذر فتح الميكروفون: ${error.message}`;
      }
    });

    stopButton.addEventListener("click", () => {
      if (recorder && recorder.state !== "inactive") recorder.stop();
      if (timer) window.clearInterval(timer);
      timer = null;
      startButton.disabled = false;
      stopButton.disabled = true;
    });

    analyzeButton.addEventListener("click", () => analyzeFiles(input, output, analyzeButton));
  }

  document.addEventListener("DOMContentLoaded", install);
  if (document.readyState !== "loading") install();
})();
