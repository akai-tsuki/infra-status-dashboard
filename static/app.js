(function () {
  "use strict";

  const envSelectEl = document.getElementById("env-select");
  const intervalInput = document.getElementById("interval-input");
  const toggleBtn = document.getElementById("toggle-btn");
  const refreshBtn = document.getElementById("refresh-btn");
  const lastUpdatedEl = document.getElementById("last-updated");
  const statusMsgEl = document.getElementById("status-msg");
  const targetsEl = document.getElementById("targets");

  // チェックの実行間隔はサーバ側（StatusPoller）の設定。画面はキャッシュを
  // 定期的に取りに行くだけなので、固定の短い間隔でポーリングしてよい
  // （/api/statusはSSH接続を伴わず即時に返る）。
  const UI_POLL_SECONDS = 5;

  // サーバ側の最新スナップショットを反映した自動更新ON/OFF（トグル操作に使う）
  let autoRefresh = true;

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
    internal_error: "内部エラー",
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

  // サーバのスナップショット（キャッシュ済み結果＋実行状態＋設定）を画面に反映する
  function applySnapshot(data) {
    autoRefresh = data.polling.auto_refresh;
    toggleBtn.textContent = autoRefresh ? "一時停止" : "再開";

    // ユーザーが入力・選択の操作中の要素は上書きしない
    if (document.activeElement !== intervalInput) {
      intervalInput.value = data.polling.interval_seconds;
    }
    if (document.activeElement !== envSelectEl) {
      envSelectEl.value = data.current_environment;
    }

    setStatus(data.running ? "チェック実行中..." : "");

    if (data.result) {
      render(data.result);
      lastUpdatedEl.textContent = `最終更新: ${data.checked_at}`;
    } else {
      targetsEl.innerHTML = "";
      const p = document.createElement("p");
      p.className = "no-result";
      p.textContent = data.running
        ? "チェックを実行しています。しばらくお待ちください..."
        : "まだチェック結果がありません。「今すぐ更新」を押してください。";
      targetsEl.appendChild(p);
      lastUpdatedEl.textContent = "";
    }
  }

  async function fetchStatus() {
    try {
      const res = await fetch("/api/status");
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      applySnapshot(await res.json());
    } catch (err) {
      setStatus(`取得に失敗しました: ${err.message}`);
    }
  }

  async function postJson(url, body) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const b = await res.json().catch(() => ({}));
      throw new Error(b.error || `HTTP ${res.status}`);
    }
    return res.json();
  }

  toggleBtn.addEventListener("click", async () => {
    try {
      applySnapshot(await postJson("/api/polling", { auto_refresh: !autoRefresh }));
    } catch (err) {
      setStatus(`設定の変更に失敗しました: ${err.message}`);
    }
  });

  refreshBtn.addEventListener("click", async () => {
    try {
      applySnapshot(await postJson("/api/refresh", {}));
    } catch (err) {
      setStatus(`更新の指示に失敗しました: ${err.message}`);
    }
  });

  envSelectEl.addEventListener("change", async () => {
    try {
      applySnapshot(await postJson("/api/environment", { name: envSelectEl.value }));
    } catch (err) {
      setStatus(`環境切り替えに失敗しました: ${err.message}`);
    }
  });

  intervalInput.addEventListener("change", async () => {
    const seconds = Math.max(5, parseInt(intervalInput.value, 10) || 60);
    intervalInput.value = seconds;
    try {
      applySnapshot(await postJson("/api/polling", { interval_seconds: seconds }));
    } catch (err) {
      setStatus(`設定の変更に失敗しました: ${err.message}`);
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
    } catch (err) {
      setStatus(`設定の取得に失敗しました: ${err.message}`);
    }

    await fetchStatus();
    setInterval(fetchStatus, UI_POLL_SECONDS * 1000);
  }

  init();
})();
