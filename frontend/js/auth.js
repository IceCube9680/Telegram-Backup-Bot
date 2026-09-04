/**
 * Telegram Backup Bot - Authentication & Session Helper
 */

const Auth = {
  currentUser: null,

  async checkAuth() {
    try {
      const user = await window.api.get("/auth/me");
      this.currentUser = user;
      return user;
    } catch (err) {
      this.currentUser = null;
      return null;
    }
  },

  async loginWithToken(code, telegramUserId = null) {
    const payload = { code: code.trim() };
    if (telegramUserId) {
      payload.telegram_user_id = parseInt(telegramUserId, 10);
    }
    const data = await window.api.post("/auth/token", payload);
    this.currentUser = data.user;
    return data;
  },

  async loginWithDev(telegramUserId, firstName = "Test User") {
    const payload = {
      telegram_user_id: parseInt(telegramUserId, 10),
      first_name: firstName,
    };
    const data = await window.api.post("/auth/dev-login", payload);
    this.currentUser = data.user;
    return data;
  },

  async loginWithTelegram(initData = null, widgetData = null) {
    const payload = {};
    if (initData) payload.init_data = initData;
    if (widgetData) payload.widget_data = widgetData;
    const data = await window.api.post("/auth/telegram", payload);
    this.currentUser = data.user;
    return data;
  },

  async logout() {
    try {
      await window.api.post("/auth/logout");
    } catch (e) {
      console.warn("Logout error:", e);
    } finally {
      this.currentUser = null;
      window.location.href = "/login";
    }
  },
};

window.Auth = Auth;
