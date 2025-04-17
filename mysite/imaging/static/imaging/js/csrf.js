// mysite/imaging/static/imaging/js/csrf.js
export function getCSRF() {
    return document.querySelector("[name=csrfmiddlewaretoken]").value;
}

export const fetchOpts = {
    method: "POST",
    credentials: "same-origin", // send cookies!
};
