const API = window.location.origin;
        let currentPage = "dashboard";

        // Theme Toggle Logic
        document.getElementById("theme-toggle")?.addEventListener("click", () => {
            if (document.body.classList.contains("dark")) {
                document.body.classList.replace("dark", "light");
            } else {
                document.body.classList.replace("light", "dark");
            }
        });

        // Mobile Menu Logic
        document.getElementById("mobile-menu-btn")?.addEventListener("click", () => {
            document.getElementById("sidebar").classList.toggle("hidden");
        });

        // TTS Counters Logic
        function updateTtsCounters() {
            const text = document.getElementById("tts-text").value;
            const chars = text.length;
            const words = text.trim() === "" ? 0 : text.trim().split(/\s+/).length;
            const estSeconds = Math.round(words / 2.5); // roughly 2.5 words per second

            document.getElementById("tts-char-count").textContent = "حروف: " + chars;
            document.getElementById("tts-word-count").textContent = "كلمات: " + words;
            document.getElementById("tts-est-duration").textContent = "المدة: ~" + estSeconds + "s";
        }

        document.getElementById("tts-text")?.addEventListener("input", updateTtsCounters);

        // TTS File Import Logic
        document.getElementById("tts-import-file")?.addEventListener("change", (e) => {
            const file = e.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = function(evt) {
                const textArea = document.getElementById("tts-text");
                textArea.value = textArea.value ? textArea.value + "\n\n" + evt.target.result : evt.target.result;
                updateTtsCounters();
            };
            reader.readAsText(file);
        });

        document.querySelectorAll(".nav-item").forEach(item => {
            item.addEventListener("click", (e) => {
                e.preventDefault();
                document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
                item.classList.add("active");
                document.querySelectorAll(".page").forEach(p => p.classList.add("hidden"));
                const page = item.dataset.page;
                const targetPage = document.getElementById("page-" + page);
                if (targetPage) targetPage.classList.remove("hidden");
                currentPage = page;
                if (page === "dashboard") loadDashboard();
                if (page === "library") loadLibrary();
                if (page === "models") loadModelsAndPlugins();
                if (page === "logs") loadLogs();
                if (page === "settings") loadSettings();
                if (page === "api-tester") { /* no init needed */ }
            });
        });

        async function runApiTest() {
            const method = document.getElementById("api-method").value;
            const url = document.getElementById("api-url").value.trim();
            let bodyText = document.getElementById("api-body").value.trim();
            const resContainer = document.getElementById("api-response");

            resContainer.textContent = "جارٍ التحميل...";

            try {
                let options = {
                    method: method,
                    headers: {}
                };

                if (method !== "GET" && method !== "HEAD" && bodyText) {
                    options.headers["Content-Type"] = "application/json";
                    options.body = bodyText;
                }

                const res = await fetch(API + url, options);
                let data;
                const contentType = res.headers.get("content-type");
                if(contentType && contentType.includes("application/json")) {
                    data = await res.json();
                } else {
                    data = await res.text();
                }

                resContainer.textContent = JSON.stringify({
                    status: res.status,
                    ok: res.ok,
                    data: data
                }, null, 2);
            } catch(e) {
                resContainer.textContent = "Error: " + e.message;
            }
        }

        async function loadLogs() {
            try {
                const logs = await apiGet("/api/logs");
                const container = document.getElementById("logs-container");
                if (logs.logs && logs.logs.length > 0) {
                    container.textContent = logs.logs.join("\n");
                } else {
                    container.textContent = logs.message || "لا توجد سجلات.";
                }
                container.scrollTop = container.scrollHeight;
            } catch (e) {
                console.error("Logs load error:", e);
                document.getElementById("logs-container").textContent = "حدث خطأ أثناء تحميل السجلات.";
            }
        }

        async function apiGet(path) {
            const res = await fetch(API + path);
            return res.json();
        }
        async function apiPost(path, data) {
            const res = await fetch(API + path, {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(data)
            });
            return res.json();
        }

        async function loadDashboard() {
            try {
                const [status, downloads, info] = await Promise.all([
                    apiGet("/status"), apiGet("/api/downloads"), apiGet("/api/info")
                ]);
                document.getElementById("stat-files").textContent = downloads.count;
                document.getElementById("stat-engines").textContent = info.engines.length;
                document.getElementById("stat-plugins").textContent = status.plugins_loaded;
                document.getElementById("stat-status").textContent = "نشط";
                const filesHtml = downloads.files.slice(0, 5).map(f =>
                    `<div class="flex justify-between items-center p-2 hover:bg-teal-900/10 rounded">
                        <span>${f.name}</span>
                        <span class="text-xs text-gray-400">${(f.size/1024).toFixed(1)} KB</span>
                    </div>`
                ).join("") || "<p class='text-gray-500'>لا توجد ملفات</p>";
                document.getElementById("recent-files").innerHTML = filesHtml;

                // Populate TTS engines dynamically
                const ttsEngineSelect = document.getElementById("tts-engine");
                ttsEngineSelect.innerHTML = "";
                let hasAvailableEngines = false;

                info.engines.forEach(e => {
                    if (e.available) {
                        const option = document.createElement("option");
                        option.value = e.name;
                        option.textContent = e.label;
                        ttsEngineSelect.appendChild(option);
                        hasAvailableEngines = true;
                    }
                });

                if (!hasAvailableEngines) {
                    const option = document.createElement("option");
                    option.value = "auto";
                    option.textContent = "الوضع الاحتياطي (Fallback)";
                    ttsEngineSelect.appendChild(option);
                }

            } catch (e) {
                console.error("Dashboard load error:", e);
            }
        }

        async function loadLibrary() {
            try {
                const [audioList, uploadsList, downloadsList] = await Promise.all([
                    apiGet("/api/audio/list"),
                    apiGet("/api/uploads"),
                    apiGet("/api/downloads")
                ]);

                // Render Outputs (Downloads)
                const outputsHtml = downloadsList.map(f => {
                    const downloadPath = `/api/downloads/${f.name}`;
                    return `<div class="p-3 hover:bg-teal-900/10 rounded-lg border-b border-gray-800 mb-2">
                        <div class="flex justify-between items-start mb-2">
                            <div>
                                <p class="font-bold break-all">${f.name}</p>
                                <p class="text-xs text-gray-400">${new Date(f.modified).toLocaleString("ar")} - ${(f.size/1024).toFixed(1)} KB</p>
                            </div>
                        </div>
                        <div class="flex flex-col gap-2">
                            <audio controls class="w-full"><source src="${downloadPath}"></audio>
                            <div class="flex gap-2">
                                <a href="${downloadPath}" download class="btn-primary px-3 py-1 rounded text-xs text-center flex-1">تحميل</a>
                                <button onclick="deleteFile('${f.name}', false)" class="bg-red-900 px-3 py-1 rounded text-xs text-white flex-1">حذف</button>
                            </div>
                        </div>
                    </div>`;
                }).join("") || "<p class='text-gray-500'>لا توجد مخرجات</p>";
                document.getElementById("outputs-manager").innerHTML = outputsHtml;

                // Render Uploads
                const uploadsHtml = uploadsList.map(f => {
                    const downloadPath = `/api/uploads/${f.name}`;
                    return `<div class="p-3 hover:bg-teal-900/10 rounded-lg border-b border-gray-800 mb-2">
                        <div class="flex justify-between items-start mb-2">
                            <div>
                                <p class="font-bold break-all">${f.name}</p>
                                <p class="text-xs text-gray-400">${new Date(f.modified).toLocaleString("ar")} - ${(f.size/1024).toFixed(1)} KB</p>
                            </div>
                        </div>
                        <div class="flex flex-col gap-2">
                            <audio controls class="w-full"><source src="${downloadPath}"></audio>
                            <div class="flex gap-2">
                                <a href="${downloadPath}" download class="btn-primary px-3 py-1 rounded text-xs text-center flex-1">تحميل</a>
                                <button onclick="deleteFile('${f.name}', true)" class="bg-red-900 px-3 py-1 rounded text-xs text-white flex-1">حذف</button>
                            </div>
                        </div>
                    </div>`;
                }).join("") || "<p class='text-gray-500'>لا توجد مرفوعات</p>";
                document.getElementById("uploads-manager").innerHTML = uploadsHtml;

            } catch (e) {
                console.error("Library load error:", e);
            }
        }

        async function renameFile(oldName) {
            const newName = prompt("أدخل الاسم الجديد:", oldName);
            if (newName && newName !== oldName) {
                try {
                    await apiPost(`/api/files/${oldName}/rename`, {new_name: newName});
                    loadLibrary();
                } catch (e) {
                    alert("فشل تغيير الاسم: " + e.message);
                }
            }
        }

        async function deleteFile(name, isUpload) {
            if (!confirm("حذف " + name + "?")) return;
            const endpoint = isUpload ? `/api/uploads/${name}` : `/api/downloads/${name}`;
            await fetch(API + endpoint, {method: "DELETE"});
            loadLibrary();
        }

        async function loadModelsAndPlugins() {
            try {
                const [models, plugins] = await Promise.all([
                    apiGet("/api/models"),
                    apiGet("/api/plugins")
                ]);

                // Render Models
                const modelsHtml = models.models.map(m =>
                    `<div class="p-3 bg-gray-800 rounded-lg flex justify-between items-center mb-2">
                        <div>
                            <p class="font-bold">${m.name}</p>
                            <p class="text-xs text-gray-400">المحرك: ${m.engine}</p>
                        </div>
                        <button onclick="deleteModel('${m.engine}', '${m.name}')" class="bg-red-900 px-3 py-1 rounded text-xs text-white">حذف</button>
                    </div>`
                ).join("") || "<p class='text-gray-500'>لا توجد نماذج محملة</p>";
                document.getElementById("models-list").innerHTML = modelsHtml;

                // Render Plugins
                const pluginsHtml = plugins.map(p =>
                    `<div class="p-3 bg-gray-800 rounded-lg flex justify-between items-center mb-2">
                        <div>
                            <p class="font-bold">${p.name}</p>
                            <p class="text-xs text-gray-400">مثبت: ${p.installed ? 'نعم' : 'لا'} | مفعل: ${p.enabled !== false ? 'نعم' : 'لا'}</p>
                        </div>
                        <div class="flex gap-2">
                            ${!p.installed ? `<button onclick="installPlugin('${p.name}')" class="bg-blue-600 px-3 py-1 rounded text-xs text-white">تثبيت</button>` : ''}
                            ${p.installed && p.enabled !== false ? `<button onclick="togglePlugin('${p.name}', 'disable')" class="bg-yellow-600 px-3 py-1 rounded text-xs text-white">تعطيل</button>` : ''}
                            ${p.installed && p.enabled === false ? `<button onclick="togglePlugin('${p.name}', 'enable')" class="bg-green-600 px-3 py-1 rounded text-xs text-white">تفعيل</button>` : ''}
                        </div>
                    </div>`
                ).join("") || "<p class='text-gray-500'>لا توجد إضافات</p>";
                document.getElementById("plugins-list").innerHTML = pluginsHtml;
            } catch (e) {
                console.error("Models/Plugins load error:", e);
            }
        }

        async function deleteModel(engine, modelName) {
            if (!confirm(`حذف النموذج ${modelName}؟`)) return;
            await fetch(`${API}/api/models/${engine}/${modelName}`, {method: "DELETE"});
            loadModelsAndPlugins();
        }

        async function installPlugin(engine) {
            if (!confirm(`تثبيت الإضافة ${engine}؟`)) return;
            await apiPost("/api/plugins/install", {engine: engine});
            loadModelsAndPlugins();
        }

        async function togglePlugin(engine, action) {
            await apiPost(`/api/plugins/${action}`, {engine: engine});
            loadModelsAndPlugins();
        }

        async function verifyModels() {
            try {
                const res = await apiPost("/api/models/verify", {});
                if(res.success) {
                    alert("تم فحص النماذج بنجاح.");
                    loadModelsAndPlugins();
                } else {
                    alert("فشل الفحص.");
                }
            } catch (e) {
                alert("خطأ أثناء الفحص: " + e.message);
            }
        }

        async function downloadModel() {
            const engine = document.getElementById("model-download-engine").value.trim();
            const modelName = document.getElementById("model-download-name").value.trim() || "default";
            if (!engine) return alert("يرجى إدخال اسم المحرك");
            try {
                const res = await apiPost("/api/models/download", {engine: engine, model_name: modelName});
                if(res.success !== false) {
                    alert("تم طلب تحميل النموذج بنجاح");
                    loadModelsAndPlugins();
                } else {
                    alert("فشل التحميل: " + (res.message || ""));
                }
            } catch(e) {
                alert("خطأ أثناء التحميل: " + e.message);
            }
        }

        async function loadSettings() {
            try {
                const [s, cacheInfo, sysInfo] = await Promise.all([
                    apiGet("/api/settings"),
                    apiGet("/api/cache"),
                    apiGet("/api/system")
                ]);
                document.getElementById("settings-status").textContent =
                    "Gemini: " + (s.gemini_api_key_set ? "مُفعّل ✓" : "غير مُفعّل ✗") +
                    " | النموذج: " + s.gemini_tts_model;
                if(s.gemini_tts_model) {
                    document.getElementById("settings-gemini-model").value = s.gemini_tts_model;
                }
                document.getElementById("cache-size").textContent = (cacheInfo.total_size / (1024 * 1024)).toFixed(2) + " MB";

                const sysHtml = `
                    <div class="bg-gray-800 p-3 rounded-lg"><p class="text-xs text-gray-400">النظام</p><p class="font-bold truncate text-sm">${sysInfo.platform}</p></div>
                    <div class="bg-gray-800 p-3 rounded-lg"><p class="text-xs text-gray-400">Python</p><p class="font-bold">${sysInfo.python}</p></div>
                    <div class="bg-gray-800 p-3 rounded-lg"><p class="text-xs text-gray-400">المساحة المتوفرة</p><p class="font-bold text-green-400">${sysInfo.disk_free_gb} GB</p></div>
                    <div class="bg-gray-800 p-3 rounded-lg"><p class="text-xs text-gray-400">عدد الأنوية</p><p class="font-bold">${sysInfo.cpu_count || '-'}</p></div>
                `;
                document.getElementById("system-info-container").innerHTML = sysHtml;
            } catch (e) {
                console.error("Settings load error:", e);
            }
        }

        async function clearCache() {
            if (!confirm("هل أنت متأكد من مسح الكاش؟")) return;
            try {
                const res = await fetch(API + "/api/cache", {method: "DELETE"});
                const data = await res.json();
                alert(data.message);
                loadSettings();
            } catch (e) {
                alert("فشل مسح الكاش");
            }
        }

        document.getElementById("settings-gemini-key")?.addEventListener("change", async (e) => {
            await apiPost("/api/settings", {gemini_api_key: e.target.value});
            loadSettings();
        });
        document.getElementById("settings-gemini-model")?.addEventListener("change", async (e) => {
            await apiPost("/api/settings", {gemini_tts_model: e.target.value});
            loadSettings();
        });

        document.getElementById("tts-generate")?.addEventListener("click", async () => {
            const btn = document.getElementById("tts-generate");
            const text = document.getElementById("tts-text").value.trim();
            if (!text) return alert("اكتب نصاً أولاً");
            btn.disabled = true;
            btn.innerHTML = '<span class="loading"></span> جارٍ التوليد...';
            try {
                const selectedEngine = document.getElementById("tts-engine").value;
                const result = await apiPost("/api/tts", {
                    text: text,
                    engine: selectedEngine || "auto",
                    language: document.getElementById("tts-language").value,
                    voice: document.getElementById("tts-voice").value,
                    speed: parseFloat(document.getElementById("tts-speed").value),
                });
                if (result.url) {
                    document.getElementById("tts-result").classList.remove("hidden");
                    document.getElementById("tts-audio").src = result.url;
                    document.getElementById("tts-download").href = result.url;
                } else {
                    alert(result.message || "فشل التوليد");
                }
            } catch (e) {
                alert("خطأ: " + e.message);
            }
            btn.disabled = false;
            btn.textContent = "توليد الصوت";
        });

        document.getElementById("stt-generate")?.addEventListener("click", async () => {
            const btn = document.getElementById("stt-generate");
            const fileInput = document.getElementById("stt-file");
            if (!fileInput.files[0]) return alert("ارفع ملفاً أولاً");
            btn.disabled = true;
            btn.innerHTML = '<span class="loading"></span> جارٍ التحويل...';
            try {
                const formData = new FormData();
                formData.append("file", fileInput.files[0]);
                formData.append("language", document.getElementById("stt-language").value);

                const res = await fetch(API + "/api/stt", {method: "POST", body: formData});
                const data = await res.json();

                if (data.text) {
                    document.getElementById("stt-result").classList.remove("hidden");
                    document.getElementById("stt-output").value = data.text;
                } else {
                    alert(data.message || data.detail || "فشل التحويل");
                }
            } catch (e) {
                alert("خطأ: " + e.message);
            }
            btn.disabled = false;
            btn.textContent = "تحويل إلى نص";
        });

        document.getElementById("clone-generate")?.addEventListener("click", async () => {
            const btn = document.getElementById("clone-generate");
            const fileInput = document.getElementById("clone-file");
            const text = document.getElementById("clone-text").value.trim();
            if (!fileInput.files[0] || !text) return alert("ارفع ملفاً واكتب نصاً");
            btn.disabled = true;
            btn.innerHTML = '<span class="loading"></span> جارٍ الاستنساخ...';
            try {
                const formData = new FormData();
                formData.append("file", fileInput.files[0]);
                const upRes = await fetch(API + "/api/uploads", {method: "POST", body: formData});
                const upData = await upRes.json();
                const result = await apiPost("/api/audio/clone", {
                    reference_audio: upData.path, text: text, engine: "xtts"
                });
                if (result.url) {
                    document.getElementById("clone-result").classList.remove("hidden");
                    document.getElementById("clone-audio").src = result.url;
                } else {
                    alert(result.message || "فشل الاستنساخ");
                }
            } catch (e) {
                alert("خطأ: " + e.message);
            }
            btn.disabled = false;
            btn.textContent = "استنساخ الصوت";
        });

        document.getElementById("religious-generate")?.addEventListener("click", async () => {
            const text = document.getElementById("religious-text").value.trim();
            if (!text) return alert("اكتب نصاً أولاً");
            document.getElementById("religious-text").value = text;
            document.querySelector('[data-page="tts"]').click();
            document.getElementById("tts-text").value = text;
        });

        document.getElementById("effects-apply")?.addEventListener("click", async () => {
            const fileInput = document.getElementById("effects-file");
            const presetSelect = document.getElementById("effects-preset");
            const btn = document.getElementById("effects-apply");

            if (!fileInput.files[0]) return alert("ارفع ملفاً أولاً");

            btn.disabled = true;
            btn.innerHTML = '<span class="loading"></span> جارٍ التطبيق...';

            const formData = new FormData();
            formData.append("file", fileInput.files[0]);
            formData.append("preset", presetSelect.value);

            try {
                const res = await fetch(API + "/api/effects/apply", {method: "POST", body: formData});
                const data = await res.json();
                if (data.url) {
                    alert("تم تطبيق المؤثرات بنجاح!");
                    // Refresh library to show the new file
                    document.querySelector('[data-page="library"]').click();
                } else {
                    alert("فشل تطبيق المؤثرات: " + (data.detail || data.message));
                }
            } catch (e) {
                alert("خطأ: " + e.message);
            }
            btn.disabled = false;
            btn.textContent = "تطبيق المؤثرات";
        });

        document.getElementById("edit-apply")?.addEventListener("click", async () => {
            const fileInput = document.getElementById("edit-file");
            const startMs = document.getElementById("edit-start").value;
            const endMs = document.getElementById("edit-end").value;
            const btn = document.getElementById("edit-apply");

            if (!fileInput.files[0]) return alert("ارفع ملفاً أولاً");

            btn.disabled = true;
            btn.innerHTML = '<span class="loading"></span> جارٍ القص...';

            const formData = new FormData();
            formData.append("file", fileInput.files[0]);
            formData.append("trim_start_ms", startMs);
            formData.append("trim_end_ms", endMs);

            try {
                const res = await fetch(API + "/api/audio/edit", {method: "POST", body: formData});
                const data = await res.json();
                if (data.url) {
                    alert("تم قص الصوت بنجاح!");
                    document.querySelector('[data-page="library"]').click();
                } else {
                    alert("فشل القص: " + (data.detail || data.message));
                }
            } catch (e) {
                alert("خطأ: " + e.message);
            }
            btn.disabled = false;
            btn.textContent = "قص الصوت";
        });

        loadDashboard();