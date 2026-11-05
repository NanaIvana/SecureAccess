// Empreinte d'appareil : identifiant aléatoire conservé dans le navigateur,
// accompagné du type d'appareil, du système et du navigateur.
function randomId() {
  const a = new Uint8Array(16);
  crypto.getRandomValues(a);
  return Array.from(a, (b) => b.toString(16).padStart(2, "0")).join("");
}

export function deviceInfo() {
  let id = null;
  try {
    id = localStorage.getItem("sa_device_id");
    if (!id) { id = randomId(); localStorage.setItem("sa_device_id", id); }
  } catch { id = randomId(); }
  const ua = navigator.userAgent;
  const os = /Windows NT 10/.test(ua) ? "Windows 10/11" : /Windows/.test(ua) ? "Windows"
    : /Android/.test(ua) ? "Android" : /iPhone|iPod/.test(ua) ? "iOS" : /iPad/.test(ua) ? "iPadOS"
    : /Mac OS X/.test(ua) ? "macOS" : /Linux/.test(ua) ? "Linux" : "Inconnu";
  const browser = /Edg\//.test(ua) ? "Edge" : /OPR\//.test(ua) ? "Opera" : /Firefox\//.test(ua) ? "Firefox"
    : /Chrome\//.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : "Inconnu";
  const device_type = /iPad|Tablet/.test(ua) ? "Tablette" : /Mobi|Android|iPhone/.test(ua) ? "Mobile" : "Ordinateur";
  return { fingerprint: id, os, browser, device_type };
}
