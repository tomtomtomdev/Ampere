// Ampere shell — navigation only (M0). No business logic here.
// In M4 each screen fetches from the FastAPI backend (/dashboard, /listings, /catalog,
// /changes, /settings) and renders the data. Scoring/dedup/frontier stay server-side in the
// Python domain layer. The full interactive prototype is design/Ampere.dc.html (reference only).

const TITLES = {
  dashboard: "Pareto frontier — capability vs effective price",
  listings: "Listings — deduped SKUs",
  catalog: "Catalog — reference DB",
  changes: "Watchlist — price drops / new arrivals",
  settings: "Settings",
};

const nav = document.getElementById("nav");
const title = document.getElementById("screen-title");

nav.addEventListener("click", (e) => {
  const btn = e.target.closest(".nav-item");
  if (!btn) return;
  for (const item of nav.querySelectorAll(".nav-item")) item.classList.remove("active");
  btn.classList.add("active");
  const screen = btn.dataset.screen;
  title.textContent = TITLES[screen] || screen;
});
