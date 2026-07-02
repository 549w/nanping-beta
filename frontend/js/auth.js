/* ============================================================
   auth.js — 认证状态管理
   负责 JWT 令牌的存储、解析、过期检查及导航栏更新。

   导出函数同时挂载到 window.NanpingAuth 供非模块脚本访问。
   ============================================================ */

const TOKEN_KEY = "nanping_token";

// ---- Token 存储 ----

/** 获取当前存储的 JWT 令牌。 */
export function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

/** 保存 JWT 令牌。 */
export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

/** 清除 JWT 令牌。 */
export function removeToken() {
  localStorage.removeItem(TOKEN_KEY);
}

// ---- JWT 解析 ----

/**
 * 解析 JWT 负载（不上服务器验证签名，仅客户端作过期判断）。
 * @returns {object|null} 解析后的 payload，失败返回 null
 */
function parseToken() {
  const token = getToken();
  if (!token) return null;

  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    // base64url → base64
    const payload = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(payload));
  } catch {
    return null;
  }
}

/**
 * 检查用户是否已登录（令牌存在且未过期）。
 * @returns {boolean}
 */
export function isLoggedIn() {
  const payload = parseToken();
  if (!payload || !payload.exp) return false;
  return payload.exp > Date.now() / 1000;
}

/**
 * 获取当前登录用户的 user_id。
 * @returns {number|null}
 */
export function getUserId() {
  const payload = parseToken();
  if (!payload || !payload.sub) return null;
  return parseInt(payload.sub, 10) || null;
}

/**
 * 要求登录，未登录则跳转到登录页。
 * @param {string} [redirectUrl] - 登录后跳回的地址，默认当前页面
 */
export function requireAuth(redirectUrl) {
  if (isLoggedIn()) return;
  const target = redirectUrl || window.location.href;
  window.location.href = `login.html?redirect=${encodeURIComponent(target)}`;
}

/**
 * 退出登录：清除令牌，跳转到首页。
 */
export function logout() {
  removeToken();
  window.location.href = "index.html";
}

// ---- 导航栏 ----

/**
 * 根据登录状态更新导航栏链接。
 * 页面需要在 <nav> 中放置 id="nav-auth-links" 的容器。
 */
export function updateNav() {
  const container = document.getElementById("nav-auth-links");
  if (!container) return;

  if (isLoggedIn()) {
    container.innerHTML = `
      <a href="index.html">首页</a>
      <a href="me.html">我的评价</a>
      <a class="nav-logout" id="nav-logout-btn">退出</a>
    `;
    // 绑定退出事件
    const btn = document.getElementById("nav-logout-btn");
    if (btn) {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        logout();
      });
    }
  } else {
    container.innerHTML = `
      <a href="index.html">首页</a>
      <a href="login.html">登录</a>
      <a href="register.html">注册</a>
    `;
  }
}

// ---- 挂载到 window 以便非模块脚本和内联脚本访问 ----
window.NanpingAuth = {
  getToken,
  setToken,
  removeToken,
  isLoggedIn,
  getUserId,
  requireAuth,
  logout,
  updateNav,
};
