// mysite/imaging/static/imaging/js/video_grayscale.js
import { getCSRF, fetchOpts } from "./csrf.js";
import { showLoading, hideLoading } from "./loading.js";

const spinner = document.getElementById("spinnerOverlay");
const alertWrap = document.getElementById("alertArea");

document.getElementById("vgForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    const submitBtn = form.querySelector("button[type=submit]");
    const fd = new FormData(form);

    try {
        showLoading(spinner, submitBtn);

        const r = await fetch("/api/video/grayscale/", {
            ...fetchOpts,
            method: "POST",
            body: fd,
            headers: { "X-CSRFToken": getCSRF() },
        });

        // job queued - always true for videos
        if (r.status === 202) {
            const d = await r.json();
            hideLoading(spinner, submitBtn);
            alertWrap.innerHTML = `
                <div class="alert alert-info d-flex justify-content-between" role="alert">
                    <span>${d.message}</span>
                    <a class="btn btn-sm btn-outline-primary" href="/history/">Go to history ↗</a>
                </div>`;
            return;
        }
    } catch (err) {
        alert(err.message);
    } finally {
        hideLoading(spinner, submitBtn);
    }
});
