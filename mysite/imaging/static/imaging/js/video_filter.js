// mysite/imaging/static/imaging/js/video_filter.js
import { getCSRF, fetchOpts } from "./csrf.js";
import { showLoading, hideLoading } from "./loading.js";

const templateSel = document.getElementById("templateSelect");
const filtInput = document.getElementById("filterInput");
const factorInput = document.querySelector('input[name="factor"]');
const spinner = document.getElementById("spinnerOverlay");
const alertWrap = document.getElementById("alertArea");

const presets = {
    "": { k: "", f: 1 },
    "edge": { k: "-1 -1 -1 -1 8 -1 -1 -1 -1", f: 1 },
    "sharpen": { k: "0 -1 0 -1 5 -1 0 -1 0", f: 1 },
    "box": { k: "1 1 1 1 1 1 1 1 1", f: 9 },
    "gauss": { k: "1 2 1 2 4 2 1 2 1", f: 16 },
    "boxstrong": { k: "2 2 2 2 4 2 2 2 2", f: 20 },
    "emboss": { k: "-2 -1 0 -1 1 1 0 1 2", f: 1 },
    "identity": { k: "0 0 0 0 1 0 0 0 0", f: 1 },
};

templateSel.addEventListener("change", () => {
    const p = presets[templateSel.value];
    if (p) {
        filtInput.value = p.k;
        factorInput.value = p.f;
    }
});

document.getElementById("vfForm").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const form = ev.target;
    const submitBtn = form.querySelector("button[type=submit]");
    const coeffs = form.filter.value.trim().split(/\s+/);
    if (coeffs.length !== 9) {
        alert("Kernel must have exactly 9 numbers.");
        return;
    }

    const fd = new FormData(form);

    try {
        showLoading(spinner, submitBtn);

        const r = await fetch("/api/video/filter/", {
            ...fetchOpts,
            method: "POST",
            body: fd,
            headers: { "X-CSRFToken": getCSRF() },
        });

        // job queued – always true for videos
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
