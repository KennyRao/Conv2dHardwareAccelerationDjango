// mysite/imaging/static/imaging/js/filter.js
import { getCSRF, fetchOpts } from "./csrf.js";

const templateSel = document.getElementById("templateSelect");
const filtInput = document.getElementById("filterInput");
templateSel.addEventListener("change", () => {
    if (templateSel.value) filtInput.value = templateSel.value;
});

document.getElementById("fltForm").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const form = ev.target;

    const fd = new FormData(form);
    if (form.use_scipy.checked) fd.append("use_scipy", "on");

    const resp = await fetch("/api/filter/", {
        ...fetchOpts,
        body: fd,
        headers: { "X-CSRFToken": getCSRF() },
    });
    if (!resp.ok) return alert("Upload failed");

    const data = await resp.json();

    const wrap = document.getElementById("results");
    wrap.innerHTML = "";
    wrap.style.display = "flex";

    const addCard = (title, src) => {
        wrap.insertAdjacentHTML(
            "beforeend",
            `<div class="col"><div class="card h-100 shadow-sm">
        <img src="${src}" class="card-img-top">
        <div class="card-body py-2"><h6 class="card-title mb-0">${title}</h6></div>
      </div></div>`
        );
    };

    addCard("Original", URL.createObjectURL(form.image.files[0]));
    addCard(`Hardware (${data.hw_time})`, `data:image/jpeg;base64,${data.hw_image}`);
    if (data.sw_image) {
        addCard(`SciPy (${data.sw_time})`, `data:image/jpeg;base64,${data.sw_image}`);
    }
});
