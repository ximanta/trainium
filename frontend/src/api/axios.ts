import axios from "axios";

export const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL,
});

// V1 has no auth. Role is inferred from the route the user is on and sent as a
// plain header so the backend stub can pick the matching dev user. When Auth0
// lands, this interceptor is the only place that changes: it will attach the
// real access token instead of this header, and the role will come from the
// token's claims rather than the URL.
api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const role = window.location.pathname.startsWith("/trainium/admin") ? "admin" : "trainer";
    config.headers["X-Trainium-Role"] = role;
  }
  return config;
});
