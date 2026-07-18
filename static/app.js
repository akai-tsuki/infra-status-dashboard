(function () {
  "use strict";

  const envSelectEl = document.getElementById("env-select");
  const intervalInput = document.getElementById("interval-input");
  const toggleBtn = document.getElementById("toggle-btn");
  const refreshBtn = document.getElementById("refresh-btn");
  const lastUpdatedEl = document.getElementById("last-updated");
  const statusMsgEl = document.getElementById("status-msg");
  const summaryEl = document.getElementById("summary");
  const targetsEl = document.getElementById("targets");

  // チェックの実行間隔はサーバ側（StatusPoller）の設定。画面はキャッシュを
  // 定期的に取りに行くだけなので、固定の短い間隔でポーリングしてよい
  // （/api/statusはSSH接続を伴わず即時に返る）。
  const UI_POLL_SECONDS = 5;

  // サーバ側の最新スナップショットを反映した自動更新ON/OFF（トグル操作に使う）
  let autoRefresh = true;
  // 表示済み結果のキー（環境名+実行時刻）。同じ結果を5秒ごとに再描画して
  // スクロール位置や折りたたみ操作を毎回リセットしないための判定に使う。
  let renderedKey = null;
  // 直近に表示できたチェック実行時刻。取得失敗時に「表示中のデータが
  // いつ時点のものか」を示すために保持する。
  let lastCheckedAt = null;
  // ユーザーが手動で開閉した対象サーバの状態（キー: 環境名/対象サーバ名）。
  // 再描画時のデフォルト（異常なら開く・正常なら閉じる）より優先する。
  const manualOpenState = new Map();

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

  function checkOk(check) {
    return !check.error && check.exit_status === 0;
  }

  function targetOk(target) {
    return allStagesOk(target.stages) && target.checks.every(checkOk);
  }

  function renderStages(stages) {
    const container = document.createElement("div");
    container.className = "stage-list";
    for (const [key, stage] of Object.entries(stages)) {
      const label = STAGE_LABELS[key] || key;

      const span = document.createElement("span");
      span.className = "stage " + (stage.ok ? "stage-ok" : "stage-ng");
      let text = (stage.ok ? "✓ " : "✗ ") + label;
      if (!stage.ok && stage.message) {
        text += `: ${stage.message}`;
      }
      span.textContent = text;

      if (stage.ok) {
        // 正常なステージは1行に並ぶ小さなバッジとして表示する
        container.appendChild(span);
      } else {
        // 異常なステージはメッセージ・出力ごと1ブロックで表示する
        const item = document.createElement("div");
        item.className = "stage-item-ng";
        item.appendChild(span);
        if (stage.output) {
          const pre = document.createElement("pre");
          pre.className = "stage-output";
          pre.textContent = stage.output;
          item.appendChild(pre);
        }
        container.appendChild(item);
      }
    }
    return container;
  }

  function renderSummary(data) {
    summaryEl.innerHTML = "";

    const envSpan = document.createElement("span");
    envSpan.className = "env-name";
    envSpan.textContent = `環境: ${data.environment}`;
    summaryEl.appendChild(envSpan);

    if (!allStagesOk(data.stages)) {
      const badge = document.createElement("span");
      badge.className = "summary-badge ng";
      badge.textContent = "踏み台接続 NG";
      summaryEl.appendChild(badge);
      return;
    }

    const okCount = data.targets.filter(targetOk).length;
    const count = document.createElement("span");
    count.className = "summary-count" + (okCount === data.targets.length ? "" : " ng");
    count.textContent = `正常 ${okCount} / ${data.targets.length}`;
    summaryEl.appendChild(count);

    data.targets.forEach((target, i) => {
      const badge = document.createElement("a");
      badge.className = "summary-badge " + (targetOk(target) ? "ok" : "ng");
      badge.href = `#target-${i}`;
      badge.textContent = target.name;
      summaryEl.appendChild(badge);
    });
  }

  function renderChecksTable(target) {
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
    return table;
  }

  function render(data) {
    renderSummary(data);
    targetsEl.innerHTML = "";

    targetsEl.appendChild(renderStages(data.stages));

    if (!allStagesOk(data.stages)) {
      return;
    }

    data.targets.forEach((target, i) => {
      const details = document.createElement("details");
      details.className = "target";
      details.id = `target-${i}`;

      const ok = targetOk(target);
      const stateKey = `${data.environment}/${target.name}`;
      // 既定では異常な対象サーバだけ開く。ユーザーが手動で開閉していれば
      // その状態を優先して維持する。
      details.open = manualOpenState.has(stateKey) ? manualOpenState.get(stateKey) : !ok;

      const summary = document.createElement("summary");
      const badge = document.createElement("span");
      badge.className = "target-status-badge " + (ok ? "ok" : "ng");
      badge.textContent = ok ? "OK" : "NG";
      const title = document.createElement("span");
      title.className = "target-title";
      title.textContent = `${target.name} (${target.host}) [${target.roles.join(", ")}]`;
      summary.appendChild(badge);
      summary.appendChild(title);
      summary.addEventListener("click", () => {
        // クリック直後はopenがまだ切り替わっていないため、切り替え完了後に記録する
        setTimeout(() => manualOpenState.set(stateKey, details.open), 0);
      });
      details.appendChild(summary);

      const body = document.createElement("div");
      body.className = "target-body";
      body.appendChild(renderStages(target.stages));
      if (allStagesOk(target.stages)) {
        body.appendChild(renderChecksTable(target));
      }
      details.appendChild(body);

      targetsEl.appendChild(details);
    });
  }

  function renderNoResult(running) {
    summaryEl.innerHTML = "";
    targetsEl.innerHTML = "";
    const p = document.createElement("p");
    p.className = "no-result";
    p.textContent = running
      ? "チェックを実行しています。しばらくお待ちください..."
      : "まだチェック結果がありません。「今すぐ更新」を押してください。";
    targetsEl.appendChild(p);
  }

  // サーバのスナップショット（キャッシュ済み結果＋実行状態＋設定）を画面に反映する
  function applySnapshot(data) {
    autoRefresh = data.polling.auto_refresh;
    toggleBtn.textContent = autoRefresh ? "一時停止" : "再開";
    // チェック実行中は手動更新を受け付けない（サーバ側でも多重起動はしないが、
    // 押せてしまうと実行されたのか分かりにくいため画面側でも防ぐ）
    refreshBtn.disabled = data.running;

    // ユーザーが入力・選択の操作中の要素は上書きしない
    if (document.activeElement !== intervalInput) {
      intervalInput.value = data.polling.interval_seconds;
    }
    if (document.activeElement !== envSelectEl) {
      envSelectEl.value = data.current_environment;
    }

    setStatus(data.running ? "チェック実行中..." : "");

    if (data.result) {
      lastCheckedAt = data.checked_at;
      lastUpdatedEl.textContent = `最終更新: ${data.checked_at}`;
      // 同じ結果の再描画はスクロール位置や開閉状態を乱すだけなのでスキップする
      const key = `${data.current_environment}|${data.checked_at}`;
      if (key !== renderedKey) {
        renderedKey = key;
        render(data.result);
      }
    } else {
      lastUpdatedEl.textContent = "";
      const key = `empty|${data.running}`;
      if (key !== renderedKey) {
        renderedKey = key;
        renderNoResult(data.running);
      }
    }
  }

  // 取得失敗時：表示中の結果は残しつつ、いつ時点のデータかを明示する
  function markFetchFailed(message) {
    setStatus(message);
    if (lastCheckedAt !== null) {
      lastUpdatedEl.textContent = `最終更新: ${lastCheckedAt}（最新の取得に失敗）`;
    }
  }

  let fetching = false;

  async function fetchStatus() {
    // 応答遅延時に取得が重ならないようにする
    if (fetching) {
      return;
    }
    fetching = true;
    try {
      const res = await fetch("/api/status");
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      applySnapshot(await res.json());
    } catch (err) {
      markFetchFailed(`取得に失敗しました: ${err.message}`);
    } finally {
      fetching = false;
    }
  }

  // setIntervalではなく「完了してから次回を予約する」方式で、遅延時の重複を防ぐ
  async function pollLoop() {
    await fetchStatus();
    setTimeout(pollLoop, UI_POLL_SECONDS * 1000);
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
    refreshBtn.disabled = true;
    try {
      applySnapshot(await postJson("/api/refresh", {}));
      setStatus("チェック実行中...");
    } catch (err) {
      refreshBtn.disabled = false;
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

    pollLoop();
  }

  init();
})();
