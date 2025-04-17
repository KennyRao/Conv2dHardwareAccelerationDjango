// mysite/imaging/static/imaging/js/history.js
import { getCSRF, fetchOpts } from "./csrf.js";
const spinner = document.getElementById("spinnerOverlay");

async function loadHistory() {
    try {
        spinner.classList.replace("d-none", "d-flex");
        const r = await fetch("/api/history/", { credentials: "same-origin" });
        if (!r.ok) throw new Error("Failed to load history");

        const list = await r.json();
        const tbody = document.getElementById("history-body");
        tbody.innerHTML = "";

        for (const j of list) {
            const preview = j.image
                ? `<img src="data:image/jpeg;base64,${j.image}" style="max-width:100px;">`
                : "-";
            const actions = j.is_video
                ? `<a href="${j.video_url}" target="_blank"
              class="btn btn-sm btn-primary me-1">Play</a>
           <a href="${j.video_url}" download
              class="btn btn-sm btn-secondary">Download</a>`
                : "-";

            tbody.insertAdjacentHTML("beforeend", `
        <tr>
          <td>${j.timestamp}</td>
          <td>${j.kind}</td>
          <td>${j.kernel ?? "-"}</td>
          <td>${j.factor ?? "-"}</td>
          <td>${j.time}</td>
          <td>${preview}</td>
          <td>${actions}</td>
        </tr>`);
        }
    } catch (e) {
        alert(e.message);
    } finally {
        spinner.classList.replace("d-flex", "d-none");
    }
}

document.getElementById("clrBtn").addEventListener("click", async () => {
    if (!confirm("Clear ALL history (images + videos)?")) return;
    try {
        spinner.classList.replace("d-none", "d-flex");
        const r = await fetch("/api/history/", {
            ...fetchOpts,
            method: "DELETE",
            headers: { "X-CSRFToken": getCSRF() },
        });
        if (!r.ok) throw new Error("Failed to clear history");
        loadHistory();
    } catch (e) { alert(e.message); }
    finally { spinner.classList.replace("d-flex", "d-none"); }
});

loadHistory();
