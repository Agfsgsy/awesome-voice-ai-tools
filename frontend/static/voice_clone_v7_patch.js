(() => {
  "use strict";

  // Documented API contracts for Voice Clone Multi-Engine Pro 7.0:
  // GET /api/voice-ai/engines
  // POST /api/voice-ai/setup/xtts
  // POST /api/voice-ai/setup/all
  // POST /api/voice-ai/audio/clone/ensemble
  // POST /api/voice-ai/song/generate
  const API = "/api/voice-ai";
  const PANEL_ID = "voice-clone-v7-engine-panel";

  function detailText(payload) {
    if (!payload) return "خطأ غير معروف";
    if (typeof payload === "string") return payload;
    const detail = payload.detail || payload;
    if (typeof detail === "string") return detail;
    return detail.message || detail.error_code || JSON.stringify(detail);
  }

  async function jsonFetch(url, options = {}) {
    const response = await fetch(url, options);
    let data = {};
    try {
      data = await response.json();
    } catch (_) {
      data = { detail: await response.text() };
    }
    if (!response.ok) {
      const error = new Error(detailText(data));
      error.status = response.status;
      error.payload = data;
      throw error;
    }
    return data;
  }

  function createPanel() {
    let panel = document.getElementById(PANEL_ID);
    if (panel) return panel;
    panel = document.createElement("section");
    panel.id = PANEL_ID;
    panel.dir = "rtl";
    panel.style.cssText = [
      "position:fixed",
      "left:18px",
      "bottom:18px",
      "z-index:99999",
      "width:min(430px,calc(100vw - 36px))",
      "background:rgba(4,20,35,.97)",
      "border:1px solid rgba(45,212,191,.5)",
      "border-radius:16px",
      "box-shadow:0 18px 50px rgba(0,0,0,.45)",
      "padding:14px",
      "font-family:Cairo,Tahoma,sans-serif",
      "color:#e5f9ff"
    ].join(";");
    panel.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between;gap:10px">
        <strong style="font-size:15px">Voice Clone Multi-Engine Pro 7.0</strong>
        <button id="v7-close" type="button" style="border:0;background:transparent;color:#9dd;cursor:pointer;font-size:18px">×</button>
      </div>
      <div id="v7-summary" style="margin-top:8px;font-size:13px;color:#c7e7ee">جارٍ فحص المحركات...</div>
      <div id="v7-engines" style="display:flex;flex-wrap:wrap;gap:6px;margin-top:10px"></div>
      <div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:12px">
        <button id="v7-setup-xtts" type="button" style="flex:1;min-width:150px;border:0;border-radius:10px;padding:9px;background:#13b8a6;color:#021b20;font-weight:700;cursor:pointer">تجهيز XTTS المحلي</button>
        <button id="v7-setup-all" type="button" style="flex:1;min-width:150px;border:1px solid #38bdf8;border-radius:10px;padding:9px;background:#082b48;color:#dff7ff;font-weight:700;cursor:pointer">تجهيز الحزمة الكاملة</button>
      </div>
      <div id="v7-message" style="margin-top:9px;font-size:12px;color:#fcd34d;white-space:pre-wrap"></div>
    `;
    document.body.appendChild(panel);
    panel.querySelector("#v7-close").addEventListener("click", () => panel.remove());
    panel.querySelector("#v7-setup-xtts").addEventListener("click", setupXTTS);
    panel.querySelector("#v7-setup-all").addEventListener("click", setupAll);
    return panel;
  }

  function badge(engine) {
    const ok = Boolean(engine.healthy);
    const text = `${ok ? "●" : "○"} ${engine.label || engine.name}`;
    return `<span title="${String(engine.detail || "").replace(/"/g, "&quot;")}" style="padding:5px 8px;border-radius:999px;font-size:11px;border:1px solid ${ok ? "#14b8a6" : "#725b28"};color:${ok ? "#80ffe5" : "#ffd978"};background:${ok ? "rgba(20,184,166,.12)" : "rgba(180,130,30,.1)"}">${text}</span>`;
  }

  async function refresh() {
    const panel = createPanel();
    const summary = panel.querySelector("#v7-summary");
    const engines = panel.querySelector("#v7-engines");
    try {
      const data = await jsonFetch(`${API}/engines`, { cache: "no-store" });
      summary.textContent = data.speech_clone_ready
        ? `الإصدار ${data.version}: يوجد محرك استنساخ جاهز.`
        : `الإصدار ${data.version}: لا يوجد محرك جاهز بعد. جهّز XTTS مرة واحدة.`;
      summary.style.color = data.speech_clone_ready ? "#7fffd9" : "#fcd34d";
      engines.innerHTML = (data.engines || []).map(badge).join("");
      const pack = data.engine_pack || {};
      if (pack.state === "installing") {
        panel.querySelector("#v7-message").textContent = `${pack.message || "جاري التثبيت"} (${pack.progress || 0}%)`;
      }
    } catch (error) {
      summary.textContent = `تعذر فحص المحركات: ${error.message}`;
      summary.style.color = "#fca5a5";
    }
  }

  async function setupXTTS() {
    const panel = createPanel();
    const message = panel.querySelector("#v7-message");
    const button = panel.querySelector("#v7-setup-xtts");
    button.disabled = true;
    message.textContent = "بدء تجهيز XTTS... اترك البرنامج مفتوحًا.";
    const form = new FormData();
    form.append("accept_model_license", "true");
    try {
      const data = await jsonFetch(`${API}/setup/xtts`, { method: "POST", body: form });
      message.textContent = data.message || "بدأ تجهيز XTTS.";
      window.setTimeout(refresh, 1500);
    } catch (error) {
      message.textContent = `فشل بدء التجهيز: ${error.message}`;
    } finally {
      button.disabled = false;
    }
  }

  async function setupAll() {
    const panel = createPanel();
    const message = panel.querySelector("#v7-message");
    const button = panel.querySelector("#v7-setup-all");
    button.disabled = true;
    message.textContent = "بدأ تجهيز الحزمة. قد يكون التنزيل كبيرًا ويستغرق وقتًا طويلًا.";
    const form = new FormData();
    form.append("accept_model_licenses", "true");
    form.append("include_music", "true");
    try {
      const data = await jsonFetch(`${API}/setup/all`, { method: "POST", body: form });
      message.textContent = data.message || "بدأ تجهيز المحركات.";
      window.setTimeout(refresh, 1500);
    } catch (error) {
      message.textContent = `فشل بدء الحزمة: ${error.message}`;
    } finally {
      button.disabled = false;
    }
  }

  window.VoiceClonePro7 = { refresh, setupXTTS, setupAll, jsonFetch };
  document.addEventListener("DOMContentLoaded", () => {
    createPanel();
    refresh();
    window.setInterval(refresh, 6000);
  });
})();
