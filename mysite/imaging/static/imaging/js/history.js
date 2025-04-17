// mysite/imaging/static/imaging/js/history.js
import { getCSRF } from "./csrf.js";

async function loadHistory() {
    const r = await fetch("/api/history/");
    if (!r.ok) return alert("Failed to load history");
    const list = await r.json();
    const tbody = document.querySelector("#history-body");
    tbody.innerHTML = "";
    for (const j of list) {
        tbody.insertAdjacentHTML("beforeend", `
      <tr>
        <td>${j.timestamp}</td>
        <td>${j.kind}</td>
        <td>${j.kernel || "-"}</td>
        <td>${j.factor || "-"}</td>
        <td>${j.time}</td>
        <td><img src="data:image/jpeg;base64,${j.image}" style="max-width:100px;"></td>
      </tr>`);
    }
}

document.getElementById("clrBtn").addEventListener("click", async () => {
    if (!confirm("Clear all history?")) return;
    const r = await fetch("/api/history/", {
        method: "DELETE",
        headers: { "X-CSRFToken": getCSRF() },
    });
    if (r.ok) loadHistory();
});

loadHistory();
