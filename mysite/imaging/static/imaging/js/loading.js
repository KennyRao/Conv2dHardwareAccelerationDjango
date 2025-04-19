// mysite/imaging/static/imaging/js/loading.js

export function showLoading(spinnerEl, submitBtn = null) {
    if (spinnerEl) {
        spinnerEl.classList.remove("d-none");
        spinnerEl.classList.add("d-flex");
    }
    if (submitBtn) submitBtn.disabled = true;
}

export function hideLoading(spinnerEl, submitBtn = null) {
    if (spinnerEl) {
        spinnerEl.classList.remove("d-flex");
        spinnerEl.classList.add("d-none");
    }
    if (submitBtn) submitBtn.disabled = false;
}
