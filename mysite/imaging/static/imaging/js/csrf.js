// mysite/imaging/static/imaging/js/csrf.js
export function getCSRF() {
    // 1) hidden <input name="csrfmiddlewaretoken"> (forms)
    const formToken = document.querySelector("[name=csrfmiddlewaretoken]");
    if (formToken) return formToken.value;

    // 2) <meta name="csrf-token" content="..."> (in <head>)
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.getAttribute("content");

    // 3) csrftoken cookie (last‑resort – unmasked token)
    const m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    if (m) return decodeURIComponent(m[1]);

    console.warn("CSRF token not found in DOM or cookie");
    return "";
}

export const fetchOpts = {
    credentials: "same-origin",   // always send cookies
};
