// mysite/imaging/static/imaging/js/grayscale.js
import { getCSRF, fetchOpts } from "./csrf.js";

document.getElementById("gsForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const f = e.target;
    const fd = new FormData(f);
    if (f.use_scipy.checked) fd.append("use_scipy", "on");

    const r = await fetch("/api/grayscale/", {
        ...fetchOpts,
        body: fd,
        headers: { "X-CSRFToken": getCSRF() },
    });
    if (!r.ok) return alert("Upload failed");
    const data = await r.json();

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

    addCard("Original", URL.createObjectURL(f.image.files[0]));
    addCard(`Hardware (${data.hw_time})`, `data:image/jpeg;base64,${data.hw_image}`);
    if (data.sw_image) {
        addCard(`SciPy (${data.sw_time})`, `data:image/jpeg;base64,${data.sw_image}`);
    }
});
