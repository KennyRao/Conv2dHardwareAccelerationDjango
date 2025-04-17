// mysite/imaging/static/imaging/js/filter.js
import { getCSRF, fetchOpts } from "./csrf.js";

const templateSel = document.getElementById("templateSelect");
const filtInput = document.getElementById("filterInput");
const factorInput = document.querySelector('input[name="factor"]');

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
    if (!p) return;
    filtInput.value = p.k;
    factorInput.value = p.f;
});

document.getElementById("fltForm").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const form = ev.target;
    const coeffs = form.filter.value.trim().split(/\s+/);
    if (coeffs.length !== 9) {
        alert("Kernel must have exactly 9 numbers.");
        return;
    }

    const fd = new FormData(form);
    if (form.use_scipy.checked) fd.append("use_scipy", "on");

    const resp = await fetch("/api/filter/", {
        ...fetchOpts,
        method: "POST",
        body: fd,
        headers: { "X-CSRFToken": getCSRF() },
    });
    if (!resp.ok) return alert("Upload failed");
    const data = await resp.json();

    const wrap = document.getElementById("results");
    wrap.innerHTML = "";
    wrap.style.display = "flex";

    const addCard = (title, src) => {
        wrap.insertAdjacentHTML("beforeend", `
      <div class="col"><div class="card h-100 shadow-sm">
        <img src="${src}" class="card-img-top">
        <div class="card-body py-2"><h6 class="card-title mb-0">${title}</h6></div>
      </div></div>`);
    };

    addCard("Original", URL.createObjectURL(form.image.files[0]));
    addCard(`Hardware (${data.hw_time})`, `data:image/jpeg;base64,${data.hw_image}`);
    if (data.sw_image) {
        addCard(`SciPy (${data.sw_time})`, `data:image/jpeg;base64,${data.sw_image}`);
    }
});
