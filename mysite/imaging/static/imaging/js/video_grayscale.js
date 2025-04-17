// mysite/imaging/static/imaging/js/video_grayscale.js
import { getCSRF, fetchOpts } from "./csrf.js";

const spinner = document.getElementById("spinnerOverlay");

document.getElementById("vgForm").addEventListener("submit", async e => {
    e.preventDefault();
    const form = e.target, fd = new FormData(form);

    try {
        spinner.style.display = "block";
        const r = await fetch("/api/video/grayscale/", {
            ...fetchOpts,
            method: "POST",
            body: fd,
            headers: { "X-CSRFToken": getCSRF() },
        });
        if (!r.ok) {
            const msg = await r.json().catch(() => ({}));
            throw new Error(msg.error || "Upload failed");
        }
        const d = await r.json();
        const wrap = document.getElementById("results");
        wrap.innerHTML = ""; wrap.style.display = "flex";
        wrap.insertAdjacentHTML("beforeend", `
            <div class="col">
                <div class="card h-100 shadow-sm">
                <video src="${d.video_url}" controls class="card-img-top"></video>
                <div class="card-body py-2"><h6 class="card-title mb-0">
                    Hardware (${d.hw_time})
                </h6></div>
                </div>
            </div>`);
    } catch (err) { alert(err.message); }
    finally { spinner.style.display = "none"; }
});
