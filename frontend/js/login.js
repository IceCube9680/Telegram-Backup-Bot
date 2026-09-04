/**
 * Login page handler for Telegram Backup Bot.
 */

document.addEventListener("DOMContentLoaded", async () => {
  // 1. Check if user is already authenticated
  try {
    const existingUser = await window.Auth.checkAuth();
    if (existingUser) {
      window.location.href = "/";
      return;
    }
  } catch (e) {
    console.debug("Not authenticated:", e);
  }

  // 2. Check for Telegram WebApp environment
  if (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.initData) {
    try {
      await window.Auth.loginWithTelegram(window.Telegram.WebApp.initData);
      window.location.href = "/";
      return;
    } catch (e) {
      console.warn("Telegram WebApp auto-login failed:", e);
    }
  }

  // 3. Show dev login button if running on localhost or non-production
  if (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") {
    const devSec = document.getElementById("dev-login-section");
    if (devSec) devSec.style.display = "block";
  }

  // 4. Form submission handler
  const form = document.getElementById("token-login-form");
  const codeInput = document.getElementById("login-code-input");
  const submitBtn = document.getElementById("btn-submit-code");

  if (form && codeInput && submitBtn) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const code = codeInput.value.trim();
      if (!code) return;

      submitBtn.disabled = true;
      submitBtn.textContent = "Verifying...";

      try {
        await window.Auth.loginWithToken(code);
        window.location.href = "/";
      } catch (err) {
        alert(err.message || "Invalid or expired login code.");
        submitBtn.disabled = false;
        submitBtn.textContent = "🔐 Sign In";
        codeInput.focus();
      }
    });
  }

  // 5. Dev login handler
  const devBtn = document.getElementById("btn-dev-login");
  if (devBtn) {
    devBtn.addEventListener("click", async () => {
      try {
        await window.Auth.loginWithDev(123456789, "Dev User");
        window.location.href = "/";
      } catch (err) {
        alert(`Dev login error: ${err.message}`);
      }
    });
  }
});
