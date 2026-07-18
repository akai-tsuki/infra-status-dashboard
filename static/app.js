(function () {
  "use strict";

  const envSelectEl = document.getElementById("env-select");
  const intervalInput = document.getElementById("interval-input");
  const toggleBtn = document.getElementById("toggle-btn");
  const refreshBtn = document.getElementById("refresh-btn");
  const lastUpdatedEl = document.getElementById("last-updated");
  const statusMsgEl = document.getElementById("status-msg");
  const targetsEl = document.getElementById("targets");

  let intervalSeconds = 60;
  let autoRefresh = true;
  let timerId = null;

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  function setStatus(msg) {
    statusMsgEl.textContent = msg;
  }

  const STAGE_LABELS = {
    bastion_network: "踏み台へのネットワーク到達",
    bastion_auth: "踏み台のSSH認証",
    target_connect: "対象サーバへの多段SSH接続",
    target_setup: "事前処理",
  };

  function allStagesOk(stages) {
    return Object.values(stages).every((s) => s.ok);
  }

  function renderStages(stages) {
    const container = document.createElement("div");
    container.className = "stage-list";
    for (const [key, stage] of Object.entries(stages)) {
      const label = STAGE_LABELS[key] || key;
      const item = document.createElement("div");

      const span = document.createElement("span");
      span.className = "stage " + (stage.ok ? "stage-ok" : "stage-ng");
      let text = (stage.ok ? "✓ " : "✗ ") + label;
      if (!stage.ok && stage.message) {
        text += `: ${stage.message}`;
      }
      span.textContent = text;
      item.appendChild(span);

      if (stage.output) {
        const pre = document.createElement("pre");
        pre.className = "stage-output";
        pre.textContent = stage.output;
        item.appendChild(pre);
      }

      container.appendChild(item);
    }
    return container;
  }

  function render(data) {
    targetsEl.innerHTML = "";

    targetsEl.appendChild(renderStages(data.stages));

    if (!allStagesOk(data.stages)) {
      return;
    }

    for (const target of data.targets) {
      const section = document.createElement("section");
      section.className = "target";

      const h2 = document.createElement("h2");
      h2.textContent = `${target.name} (${target.host}) [${target.roles.join(", ")}]`;
      section.appendChild(h2);
      section.appendChild(renderStages(target.stages));

      if (!allStagesOk(target.stages)) {
        targetsEl.appendChild(section);
        continue;
      }

      const table = document.createElement("table");
      table.innerHTML = "<thead><tr><th>チェック</th><th>コマンド</th><th>exit</th><th>出力</th></tr></thead>";
      const tbody = document.createElement("tbody");

      for (const check of target.checks) {
        const tr = document.createElement("tr");

        if (check.error) {
          tr.innerHTML = `
            <td>${escapeHtml(check.name)}</td>
            <td><code>${escapeHtml(check.command)}</code></td>
            <td class="exit-error" colspan="2">${escapeHtml(check.error)}</td>
          `;
        } else {
          const output = check.stdout + (check.stderr ? "\n[stderr]\n" + check.stderr : "");
          const exitClass = check.exit_status === 0 ? "exit-ok" : "exit-error";
          tr.innerHTML = `
            <td>${escapeHtml(check.name)}</td>
            <td><code>${escapeHtml(check.command)}</code></td>
            <td class="${exitClass}">${check.exit_status}</td>
            <td><pre>${escapeHtml(output)}</pre></td>
          `;
        }
        tbody.appendChild(tr);
      }

      table.appendChild(tbody);
      section.appendChild(table);
      targetsEl.appendChild(section);
    }
  }

  async function fetchAndRender() {
    setStatus("取得中...");
    try {
      const res = await fetch("/api/status");
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const data = await res.json();
      render(data);
      setStatus("");
      lastUpdatedEl.textContent = `最終更新: ${new Date().toLocaleTimeString("ja-JP")}`;
    } catch (err) {
      setStatus(`取得に失敗しました: ${err.message}`);
    }
  }

  function startPolling() {
    stopPolling();
    timerId = setInterval(fetchAndRender, intervalSeconds * 1000);
  }

  function stopPolling() {
    if (timerId !== null) {
      clearInterval(timerId);
      timerId = null;
    }
  }

  toggleBtn.addEventListener("click", () => {
    autoRefresh = !autoRefresh;
    toggleBtn.textContent = autoRefresh ? "一時停止" : "再開";
    if (autoRefresh) {
      startPolling();
    } else {
      stopPolling();
    }
  });

  refreshBtn.addEventListener("click", fetchAndRender);

  envSelectEl.addEventListener("change", async () => {
    const name = envSelectEl.value;
    setStatus("環境切り替え中...");
    try {
      const res = await fetch("/api/environment", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || `HTTP ${res.status}`);
      }
      setStatus("");
      await fetchAndRender();
    } catch (err) {
      setStatus(`環境切り替えに失敗しました: ${err.message}`);
    }
  });

  intervalInput.addEventListener("change", () => {
    intervalSeconds = Math.max(5, parseInt(intervalInput.value, 10) || 60);
    intervalInput.value = intervalSeconds;
    if (autoRefresh) {
      startPolling();
    }
  });

  async function init() {
    try {
      const res = await fetch("/api/config");
      const cfg = await res.json();

      envSelectEl.innerHTML = "";
      for (const name of cfg.environments) {
        const option = document.createElement("option");
        option.value = name;
        option.textContent = name;
        envSelectEl.appendChild(option);
      }
      envSelectEl.value = cfg.current_environment;

      intervalSeconds = cfg.polling.interval_seconds;
      autoRefresh = cfg.polling.auto_refresh;
      intervalInput.value = intervalSeconds;
      toggleBtn.textContent = autoRefresh ? "一時停止" : "再開";
    } catch (err) {
      setStatus(`設定の取得に失敗しました: ${err.message}`);
    }

    await fetchAndRender();
    if (autoRefresh) {
      startPolling();
    }
  }

  init();
})();
