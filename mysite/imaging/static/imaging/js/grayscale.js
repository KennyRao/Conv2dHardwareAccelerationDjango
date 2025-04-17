// mysite/imaging/static/imaging/js/grayscale.js
import { getCSRF, fetchOpts } from "./csrf.js";

const spinner = document.getElementById("spinner");

document.getElementById("gsForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.target;
    const fd = new FormData(form);
    if (form.use_scipy.checked) fd.append("use_scipy", "on");

    try {
        spinner.style.display = "block";
        const r = await fetch("/api/grayscale/", {
            ...fetchOpts,
            method: "POST",
            body: fd,
            headers: { "X-CSRFToken": getCSRF() },
        });
        if (!r.ok) throw new Error("Upload failed");
        const d = await r.json();

        const wrap = document.getElementById("results");
        wrap.innerHTML = ""; wrap.style.display = "flex";
        const addCard = (title, src) => `
            <div class="col">
                <div class="card h-100 shadow-sm">
                <img src="${src}" class="card-img-top">
                <div class="card-body py-2"><h6 class="card-title mb-0">${title}</h6></div>
                </div>
            </div>`;
        wrap.insertAdjacentHTML("beforeend", addCard("Original",
            URL.createObjectURL(form.image.files[0])));
        wrap.insertAdjacentHTML("beforeend", addCard(`Hardware (${d.hw_time})`,
            `data:image/jpeg;base64,${d.hw_image}`));
        if (d.sw_image)
            wrap.insertAdjacentHTML("beforeend", addCard(`SciPy (${d.sw_time})`,
                `data:image/jpeg;base64,${d.sw_image}`));
    } catch (e) { alert(e.message); }
    finally { spinner.style.display = "none"; }
});
