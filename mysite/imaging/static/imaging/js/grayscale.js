// mysite/imaging/static/imaging/js/grayscale.js
import { getCSRF, fetchOpts } from "./csrf.js";
import { showLoading, hideLoading } from "./loading.js";

const spinner = document.getElementById("spinnerOverlay");
const alertWrap = document.getElementById("alertArea");

document.getElementById("gsForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    const submitBtn = form.querySelector("button[type=submit]");
    const fd = new FormData(form);
    if (form.use_scipy.checked) fd.append("use_scipy", "on");

    try {
        showLoading(spinner, submitBtn);

        const r = await fetch("/api/grayscale/", {
            ...fetchOpts,
            method: "POST",
            body: fd,
            headers: { "X-CSRFToken": getCSRF() },
        });

        // job is queued
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

        // job is finished
        if (!r.ok) throw new Error("Upload failed");
        const d = await r.json();

        const wrap = document.getElementById("results");
        wrap.innerHTML = "";
        wrap.style.display = "flex";

        const addCard = (title, src) => `
            <div class="col">
                <div class="card h-100 shadow-sm">
                    <img src="${src}" class="card-img-top">
                    <div class="card-body py-2">
                        <h6 class="card-title mb-0">${title}</h6>
                    </div>
                </div>
            </div>`;

        wrap.insertAdjacentHTML("beforeend", addCard("Original", URL.createObjectURL(form.image.files[0])));
        wrap.insertAdjacentHTML("beforeend", addCard(`Hardware (${d.hw_time})`, `data:image/jpeg;base64,${d.hw_image}`));
        if (d.sw_image) {
            wrap.insertAdjacentHTML("beforeend", addCard(`SciPy (${d.sw_time})`, `data:image/jpeg;base64,${d.sw_image}`));
        }
    } catch (err) {
        alert(err.message);
    } finally {
        hideLoading(spinner, submitBtn);
    }
});
