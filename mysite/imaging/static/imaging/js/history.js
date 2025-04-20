// mysite/imaging/static/imaging/js/history.js
import { getCSRF, fetchOpts } from "./csrf.js";
import { showLoading, hideLoading } from "./loading.js";

const spinner = document.getElementById("spinnerOverlay");
const refreshBtn = document.getElementById("refreshBtn");
const clearBtn = document.getElementById("clrBtn");
const tbody = document.getElementById("history-body");

/**
 * Fetch history JSON and rebuild the table.
 * @param {boolean} useOverlay  ‑‑ true → show/hide the full‑screen spinner;
 *                               false → silent background refresh.
 */
export async function loadHistory(useOverlay = false) {
    try {
        if (useOverlay) showLoading(spinner);

        const r = await fetch("/api/history/", { credentials: "same-origin" });
        if (!r.ok) throw new Error("Failed to fetch history");
        const list = await r.json();

        tbody.innerHTML = "";

        for (const j of list) {
            const preview = j.image
                ? `<img src="data:image/jpeg;base64,${j.image}" style="max-width:100px;">`
                : "-";

            const actions = j.is_video && j.status === "finished"
                ? `<a href="${j.video_url}" target="_blank"
               class="btn btn-sm btn-primary me-1">Play</a>
           <a href="${j.video_url}" download
               class="btn btn-sm btn-secondary">Download</a>`
                : "-";

            const progBar = j.progress
                ? `<div class="progress" style="height:18px;">
             <div class="progress-bar ${j.status === "error" ? "bg-danger" : ""}"
                  role="progressbar"
                  style="width:${j.progress}%;"
                  aria-valuenow="${j.progress}" aria-valuemin="0" aria-valuemax="100">
               ${j.progress}%
             </div>
           </div>` : "-";

            tbody.insertAdjacentHTML("beforeend", `
        <tr>
          <td>${j.timestamp}</td>
          <td>${j.kind}</td>
          <td>${j.status}</td>
          <td>${progBar}</td>
          <td>${j.kernel ?? "-"}</td>
          <td>${j.factor ?? "-"}</td>
          <td>${j.time}</td>
          <td>${preview}</td>
          <td>${actions}</td>
        </tr>`);
        }
    } catch (err) {
        alert(err.message);
    } finally {
        if (useOverlay) hideLoading(spinner);
    }
}

// manual refresh button
refreshBtn.addEventListener("click", () => loadHistory(true));

// clear‑all button
clearBtn.addEventListener("click", async () => {
    if (!confirm("Clear ALL history (images + videos)?")) return;
    try {
        showLoading(spinner);
        const r = await fetch("/api/history/", {
            ...fetchOpts,
            method: "DELETE",
            headers: { "X-CSRFToken": getCSRF() },
        });
        if (!r.ok) throw new Error("Failed to clear history");
        // Rebuild table with overlay once DELETE finishes
        await loadHistory(true);
    } catch (err) {
        alert(err.message);
    } finally {
        hideLoading(spinner);
    }
});

loadHistory(true);
