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
    const blob = await r.blob();

    const wrap = document.getElementById("results");
    wrap.style.display = "flex";
    wrap.innerHTML = `
    <div class="col">
      <div class="card"><img src="${URL.createObjectURL(blob)}" class="card-img-top">
        <div class="card-body"><h5 class="card-title">Hardware</h5></div>
      </div>
    </div>`;
});
