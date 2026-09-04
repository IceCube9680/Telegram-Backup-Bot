/**
 * Telegram Backup Bot - Centralized REST API Client
 */

class ApiClient {
  constructor(baseUrl = "/api") {
    this.baseUrl = baseUrl;
  }

  async request(endpoint, options = {}) {
    const url = endpoint.startsWith("http") ? endpoint : `${this.baseUrl}${endpoint}`;
    
    const defaultHeaders = {
      "Content-Type": "application/json",
      "Accept": "application/json",
    };

    const config = {
      ...options,
      credentials: "include", // Send session cookies
      headers: {
        ...defaultHeaders,
        ...(options.headers || {}),
      },
    };

    if (config.body && typeof config.body === "object" && !(config.body instanceof FormData)) {
      config.body = JSON.stringify(config.body);
    }

    try {
      const response = await fetch(url, config);

      // Handle 401 Unauthorized globally
      if (response.status === 401) {
        if (!window.location.pathname.includes("/login") && !url.includes("/auth/")) {
          window.location.href = "/login";
        }
      }

      // If response is not JSON (e.g. streaming download)
      const contentType = response.headers.get("content-type");
      if (contentType && !contentType.includes("application/json")) {
        if (!response.ok) {
          throw new Error(`Request failed with status ${response.status}`);
        }
        return response;
      }

      const json = await response.json();

      if (!response.ok || json.success === false) {
        const errorMsg = (json.error && json.error.message) || json.detail || "An unexpected error occurred.";
        const error = new Error(errorMsg);
        error.status = response.status;
        error.code = json.error ? json.error.code : `HTTP_${response.status}`;
        error.details = json.error ? json.error.details : null;
        throw error;
      }

      return json.data;
    } catch (err) {
      if (err.name === "TypeError" && err.message.includes("fetch")) {
        throw new Error("Unable to connect to server. Please check your network connection.");
      }
      throw err;
    }
  }

  get(endpoint, params = {}) {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null && value !== "") {
        query.append(key, value);
      }
    }
    const queryString = query.toString() ? `?${query.toString()}` : "";
    return this.request(`${endpoint}${queryString}`, { method: "GET" });
  }

  post(endpoint, body = {}) {
    return this.request(endpoint, { method: "POST", body });
  }

  delete(endpoint, body = {}) {
    return this.request(endpoint, { method: "DELETE", body });
  }
}

window.api = new ApiClient();
