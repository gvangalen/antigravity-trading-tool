import { fetchAuth } from "@/lib/api/auth";

export async function fetchWatchlist() {
  return await fetchAuth("/api/watchlist");
}

export async function addToWatchlist(symbol) {
  return await fetchAuth("/api/watchlist", {
    method: "POST",
    body: JSON.stringify({ symbol }),
  });
}

export async function removeFromWatchlist(symbol) {
  return await fetchAuth(`/api/watchlist/${symbol}`, {
    method: "DELETE",
  });
}
