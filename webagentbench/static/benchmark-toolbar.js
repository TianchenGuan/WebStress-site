/**
 * WebAgentBench — Human Play Evaluation Toolbar
 *
 * Self-contained JS that injects a floating toolbar into any environment SPA.
 * Activates only when ?session=... is in the URL.
 *
 * Features:
 *   - Shows task instruction (click to expand)
 *   - "Evaluate" button: calls /api/env/{env_id}/evaluate, shows score + check results
 *   - "Reset" button: reloads the page
 *   - Collapsible results panel with pass/fail per check
 */
(function () {
  const params = new URLSearchParams(window.location.search);
  const sessionId = params.get("session");
  if (!sessionId) return;
  const agentMode = params.get("agent_mode") === "1";

  const pathMatch = window.location.pathname.match(/^\/env\/([^/]+)/);
  const envId = pathMatch ? pathMatch[1] : null;
  if (!envId) return;

  if (!agentMode) {
    // --- Inject styles + HTML ---
    // Floating panel on the right edge — collapsed by default so it never
    // covers the Gmail UI. Click the tab to expand.
    const toolbar = document.createElement("div");
    toolbar.id = "wab-toolbar";
    toolbar.innerHTML = `
    <style>
      /* ── Collapsed tab (always visible, right edge) ── */
      #wab-toolbar {
        position: fixed; top: 50%; right: 0; z-index: 99999;
        transform: translateY(-50%);
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        font-size: 13px;
      }
      #wab-tab {
        position: absolute; right: 0; top: 50%; transform: translateY(-50%);
        writing-mode: vertical-rl; text-orientation: mixed;
        background: #1a1a2e; color: #e94560; border-radius: 6px 0 0 6px;
        padding: 12px 6px; font-size: 11px; font-weight: 700; letter-spacing: 1px;
        text-transform: uppercase; cursor: pointer; user-select: none;
        border: 1px solid #0f3460; border-right: none;
        box-shadow: -2px 0 8px rgba(0,0,0,0.2);
        transition: background 0.2s;
      }
      #wab-tab:hover { background: #252545; }

      /* ── Expanded panel ── */
      #wab-panel {
        position: absolute; right: 30px; top: 50%; transform: translateY(-50%);
        width: 340px; max-height: 80vh; overflow-y: auto;
        background: #1a1a2e; color: #e0e0e0; border-radius: 8px;
        border: 1px solid #0f3460; box-shadow: -4px 0 20px rgba(0,0,0,0.3);
        display: none;
      }
      #wab-panel.open { display: block; }

      #wab-panel-header {
        padding: 10px 14px; border-bottom: 1px solid #333;
        display: flex; align-items: center; justify-content: space-between;
      }
      .wab-label {
        font-weight: 600; color: #e94560; font-size: 11px;
        text-transform: uppercase; letter-spacing: 1px;
      }
      #wab-close-btn {
        background: none; border: none; color: #888; font-size: 18px;
        cursor: pointer; padding: 0 4px; line-height: 1;
      }
      #wab-close-btn:hover { color: #fff; }

      #wab-toolbar-instruction {
        padding: 10px 14px; color: #ccc; font-size: 12px; line-height: 1.5;
        border-bottom: 1px solid #333; max-height: 120px; overflow-y: auto;
      }

      #wab-toolbar-actions {
        display: flex; gap: 6px; padding: 10px 14px; flex-wrap: wrap;
      }
      #wab-toolbar button {
        padding: 6px 14px; border: none; border-radius: 4px;
        cursor: pointer; font-size: 12px; font-weight: 600; transition: opacity 0.2s;
      }
      #wab-toolbar button:hover { opacity: 0.85; }
      #wab-evaluate-btn { background: #0f3460; color: #fff; flex: 1; }
      #wab-evaluate-btn:disabled { opacity: 0.5; cursor: not-allowed; }
      #wab-record-btn { background: #333; color: #ccc; }
      #wab-record-btn.recording { background: #c62828; color: #fff; animation: wab-pulse 1.5s infinite; }
      @keyframes wab-pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.6; } }
      #wab-reset-btn { background: #333; color: #ccc; }

      #wab-results-panel {
        display: none; padding: 10px 14px; border-top: 1px solid #333;
        max-height: 250px; overflow-y: auto; font-size: 12px;
      }
      #wab-results-panel.visible { display: block; }
      .wab-check { padding: 2px 0; }
      .wab-check-pass { color: #4caf50; }
      .wab-check-fail { color: #f44336; }
      .wab-score { font-size: 22px; font-weight: 700; margin-right: 8px; }
      .wab-score-pass { color: #4caf50; }
      .wab-score-fail { color: #f44336; }
    </style>

    <div id="wab-tab">WAB</div>
    <div id="wab-panel">
      <div id="wab-panel-header">
        <span class="wab-label">WebAgentBench</span>
        <button id="wab-close-btn">&times;</button>
      </div>
      <div id="wab-toolbar-instruction">(Loading task...)</div>
      <div id="wab-toolbar-actions">
        <button id="wab-record-btn">\u23FA Record</button>
        <button id="wab-evaluate-btn">Evaluate</button>
        <button id="wab-reset-btn">Reset</button>
      </div>
      <div id="wab-results-panel"></div>
    </div>
  `;
    document.body.appendChild(toolbar);

    // Toggle panel open/close
    document.getElementById("wab-tab").addEventListener("click", function () {
      document.getElementById("wab-panel").classList.toggle("open");
    });
    document.getElementById("wab-close-btn").addEventListener("click", function () {
      document.getElementById("wab-panel").classList.remove("open");
    });

    // --- Fetch task instruction ---
    fetch("/api/env/" + envId + "/session/" + encodeURIComponent(sessionId))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var instr = data.instruction || data.title || "Task loaded";
        var el = document.getElementById("wab-toolbar-instruction");
        el.textContent = instr;
        el.title = instr;
      })
      .catch(function () {});

    // Results panel auto-opens when evaluation completes (no toggle button needed)

    // --- Evaluate ---
    document.getElementById("wab-evaluate-btn").addEventListener("click", async function () {
      this.disabled = true;
      this.textContent = "Evaluating...";

      try {
        var response = await fetch("/api/env/" + envId + "/evaluate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            session_id: sessionId,
            task_id: null,
            benchmark_state: window.__benchmarkState || {},
            trajectory: [],
          }),
        });
        var result = await response.json();

        var score = result.score != null ? result.score : (result.final_score || 0);
        var success = result.success || false;
        var checks = result.checks || [];
        var negChecks = result.negative_checks || [];

        var html = '<div style="display:flex;align-items:center;margin-bottom:8px;">';
        html += '<span class="wab-score ' + (success ? "wab-score-pass" : "wab-score-fail") + '">';
        html += score.toFixed(2) + "</span>";
        html += "<span>" + (success ? "PASSED" : "FAILED") + "</span></div>";

        if (checks.length) {
          html += '<div style="margin-top:8px;font-weight:600;">Checks:</div>';
          for (var c of checks) {
            var cls = c.passed ? "wab-check-pass" : "wab-check-fail";
            var icon = c.passed ? "\u2713" : "\u2717";
            html += '<div class="wab-check ' + cls + '">' + icon + " " + (c.desc || c.expr) + "</div>";
          }
        }

        if (negChecks.length) {
          html += '<div style="margin-top:8px;font-weight:600;">Negative Checks:</div>';
          for (var nc of negChecks) {
            var ncCls = nc.passed ? "wab-check-pass" : "wab-check-fail";
            var ncIcon = nc.passed ? "\u2713" : "\u2717 (-" + (nc.penalty || 0).toFixed(2) + ")";
            html += '<div class="wab-check ' + ncCls + '">' + ncIcon + " " + (nc.desc || nc.expr) + "</div>";
          }
        }

        if (result.reasoning) {
          html += '<div style="margin-top:8px;color:#888;white-space:pre-wrap;font-size:12px;">';
          html += result.reasoning.replace(/</g, "&lt;") + "</div>";
        }

        var panel = document.getElementById("wab-results-panel");
        panel.innerHTML = html;
        panel.classList.add("visible");
        // Ensure the panel is open so results are visible
        document.getElementById("wab-panel").classList.add("open");

        // Save trajectory if recording is active (gold if passed, regular if failed)
        var rec = window.__WAB_RECORDER;
        if (rec && rec.recording) {
          rec.stop();
          document.getElementById("wab-record-btn").textContent = "\u23FA Record";
          document.getElementById("wab-record-btn").classList.remove("recording");

          try {
            var saveResp = await fetch("/api/env/" + envId + "/trajectory", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                session_id: sessionId,
                events: rec.events,
                evaluation: result,
              }),
            });
            var saveResult = await saveResp.json();
            if (saveResult.saved) {
              var goldTag = saveResult.gold ? "Gold trajectory" : "Trajectory";
              var color = saveResult.gold ? "#4caf50" : "#ff9800";
              html += '<div style="margin-top:8px;color:' + color + ';font-weight:600;">';
              html += "\u2713 " + goldTag + " saved (" + saveResult.events + " events): " + (saveResult.filename || "OK") + "</div>";
              panel.innerHTML = html;
            }
          } catch (saveErr) {
            html += '<div style="margin-top:8px;color:#ff9800;">Trajectory save failed: ' + saveErr.message + "</div>";
            panel.innerHTML = html;
          }
        }
      } catch (err) {
        document.getElementById("wab-results-panel").innerHTML =
          '<div style="color:#f44336;">Error: ' + err.message + "</div>";
        document.getElementById("wab-results-panel").classList.add("visible");
      }

      this.disabled = false;
      this.textContent = "Evaluate";
    });

    // --- Record button ---
    (function () {
      // Load trajectory recorder script
      var script = document.createElement("script");
      script.src = "/static/trajectory-recorder.js";
      document.head.appendChild(script);

      var btn = document.getElementById("wab-record-btn");
      btn.addEventListener("click", async function () {
        if (!window.__WAB_RECORDER) {
          btn.textContent = "Loading...";
          setTimeout(function () { btn.click(); }, 500);
          return;
        }
        var rec = window.__WAB_RECORDER;
        if (rec.recording) {
          rec.stop();
          btn.textContent = "\u23FA Record";
          btn.classList.remove("recording");
          // Auto-save on stop (unevaluated trajectory)
          if (rec.events && rec.events.length > 0) {
            try {
              var saveResp = await fetch("/api/env/" + envId + "/trajectory", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  session_id: sessionId,
                  events: rec.events,
                  evaluation: {},
                }),
              });
              var saveResult = await saveResp.json();
              if (saveResult.saved) {
                btn.textContent = "\u2713 Saved (" + saveResult.events + " events)";
                setTimeout(function () { btn.textContent = "\u23FA Record"; }, 3000);
              }
            } catch (e) {}
          }
        } else {
          rec.start(sessionId, envId);
          btn.textContent = "\u23F9 Stop (" + (rec.events ? rec.events.length : 0) + ")";
          btn.classList.add("recording");
          // Update event count periodically
          var countInterval = setInterval(function () {
            if (!rec.recording) { clearInterval(countInterval); return; }
            btn.textContent = "\u23F9 Stop (" + (rec.events ? rec.events.length : 0) + ")";
          }, 2000);
        }
      });
    })();

    // --- Reset: destroy session, create a new one with same settings ---
    document.getElementById("wab-reset-btn").addEventListener("click", async function () {
      this.disabled = true;
      this.textContent = "Resetting...";
      try {
        // 1. Get current session settings (task, seed, degradation)
        var infoResp = await fetch("/api/env/" + envId + "/session/" + encodeURIComponent(sessionId));
        var info = await infoResp.json();
        var taskId = info.task_id;
        var seed = info.seed;
        var degradation = info.degradation;

        // 2. Destroy old session
        await fetch("/api/env/" + envId + "/session/" + encodeURIComponent(sessionId), { method: "DELETE" });

        // 3. Create new session with same settings
        var payload = { task_id: taskId };
        if (seed != null) payload.seed = seed;
        if (degradation && degradation.variant_filename) {
          payload.variant_filename = degradation.variant_filename;
        } else if (degradation && degradation.injections && degradation.injections.length > 0) {
          payload.degradation = degradation;
        }

        var createResp = await fetch("/api/env/" + envId + "/session", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        var newSession = await createResp.json();

        // 4. Navigate to new session
        var startPath = newSession.start_path || "/inbox";
        window.location.href = "/env/" + envId + startPath + "?session=" + encodeURIComponent(newSession.session_id);
      } catch (e) {
        this.textContent = "Reset failed: " + e.message;
        setTimeout(function () {
          document.getElementById("wab-reset-btn").disabled = false;
          document.getElementById("wab-reset-btn").textContent = "Reset";
        }, 3000);
      }
    });
  }

  // --- Client-layer degradation (DOM mutations) ---
  // Fetch and apply client injections so human browsers see the same
  // DOM degradations that Playwright agents see.
  fetch("/api/env/" + envId + "/degradation/" + encodeURIComponent(sessionId))
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var injections = data.client_injections || [];
      if (!injections.length) return;

      function applyClientInjections() {
        for (var inj of injections) {
          var p = inj.params || {};
          var action = p.action || "";

          if (action === "scramble_aria") {
            var els = document.querySelectorAll(p.selector || "[aria-label]");
            if (els.length > 1) {
              var labels = Array.from(els).map(function(e) { return e.getAttribute("aria-label"); });
              els.forEach(function(el, i) { el.setAttribute("aria-label", labels[(i + 1) % labels.length]); });
            }
          } else if (action === "hide_affordance") {
            var el = document.querySelector(p.selector);
            if (el) {
              el.style.display = "none";
              el.parentNode.addEventListener(p.trigger || "contextmenu", function() { el.style.display = ""; });
            }
          } else if (action === "false_banner") {
            var banner = document.createElement("div");
            banner.className = p.css_class || "";
            banner.textContent = p.message || "";
            banner.setAttribute("role", "alert");
            var target = document.querySelector(p.insert_before) || document.body.firstChild;
            if (target && target.parentNode) target.parentNode.insertBefore(banner, target);
          } else if (action === "swap_labels") {
            var a = document.querySelector(p.selector_a);
            var b = document.querySelector(p.selector_b);
            if (a && b) { var t = a.textContent; a.textContent = b.textContent; b.textContent = t; }
          } else if (action === "add_decoy") {
            var real = document.querySelector(p.selector);
            if (real && !real.previousElementSibling?.hasAttribute("data-decoy")) {
              var decoy = real.cloneNode(true);
              decoy.removeAttribute("onclick");
              decoy.setAttribute("data-decoy", "true");
              real.parentNode.insertBefore(decoy, real);
            }
          }
        }
      }

      // Apply immediately
      applyClientInjections();

      // Check if any injection uses persistent mode — if so, re-apply on DOM changes
      var hasPersistent = injections.some(function(inj) {
        return (inj.params.behavior || {}).mode === "persistent";
      });
      if (hasPersistent) {
        new MutationObserver(function(mutations) {
          var significant = mutations.some(function(m) { return m.type === "childList" && m.addedNodes.length > 2; });
          if (significant) applyClientInjections();
        }).observe(document.body, { childList: true, subtree: true });
      }
    })
    .catch(function () {});
})();
