1. 关于“图标”的专业描述
你提到的显示在浏览器标签页上的那个图标，专业术语叫做 Favicon（网站图标/收藏夹图标）。如果你是指页面内标题旁边的那个圆圈图像，通常描述为 Logo 或 Profile Avatar（个人头像）。

2. UI 核心优化方案
为了实现白天/夜间模式自动切换并应用你的卡通头像，我们需要对 index.html 和 style.css 进行以下调整。

A. 修改 webui/templates/index.html
在 <head> 中添加 Favicon 链接，并在页面头部嵌入头像。

HTML

<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
    <link rel="icon" href="https://imagehost.qianzhu.online/api/rfile/千逐（卡通版）.jpg" type="image/jpeg">
    <title>{{ app_title }}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@500;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}" />
  </head>
  <body>
    <main class="shell">
      <header class="header">
        <div class="brand">
          <img src="https://imagehost.qianzhu.online/api/rfile/千逐（卡通版）.jpg" class="profile-avatar" alt="Qianzhu">
          <h1>Downloader by Qianzhu</h1>
        </div>
        <nav>
          <a href="https://blog.qianzhu.me/" target="_blank" class="nav-link">📖 使用教程</a>
        </nav>
      </header>

      <footer class="site-footer">
        <p>Designed with <span style="color:#e4572e;">&hearts;</span> by <a href="https://blog.qianzhu.me/" target="_blank">Qianzhu (千逐)</a></p>
      </footer>
    </main>

    <script>window.APP_CONFIG = {{ config_json | safe }};</script>
    <script src="{{ url_for('static', filename='app.js') }}"></script>
  </body>
</html>
B. 修改 webui/static/style.css
利用 CSS 变量和 prefers-color-scheme 媒体查询，实现跟随系统的黑白模式切换。

CSS

:root {
  /* 白天模式 (千竹暖纸色) */
  --bg-page: #fafaf9;
  --bg-card: #ffffff;
  --text-main: #2c2c2c;
  --text-sub: #666666;
  --accent: #2f5c3e; /* 竹青色 */
  --accent-light: #e8f5e9;
  --border: #e5e5e5;
  --radius: 12px;
  --font-serif: "Noto Serif SC", serif;
}

/* 夜间模式自动切换 */
@media (prefers-color-scheme: dark) {
  :root {
    --bg-page: #1a1a1a;
    --bg-card: #262626;
    --text-main: #e5e5e5;
    --text-sub: #a3a3a3;
    --border: #383838;
    --accent: #4a8f63;
    --accent-light: #2a352e;
  }
}

body {
  margin: 0;
  background: var(--bg-page);
  color: var(--text-main);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  transition: background 0.3s, color 0.3s;
}

/* 品牌头部样式优化 */
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 24px;
  border-bottom: 1px solid var(--border);
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand h1 {
  font-family: var(--font-serif);
  font-size: 1.5rem;
  margin: 0;
}

/* 头像图标样式 */
.profile-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: 1.5px solid var(--accent);
  object-fit: cover;
}

.shell {
  max-width: 680px;
  margin: 0 auto;
  padding: 40px 20px;
  display: flex;
  flex-direction: column;
  gap: 32px;
}

/* 卡片与表单样式 (简化版) */
.card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 24px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.03);
}

textarea, select {
  width: 100%;
  background: var(--bg-page);
  border: 1px solid var(--border);
  color: var(--text-main);
  padding: 12px;
  border-radius: 8px;
}

.btn-primary {
  background: var(--accent);
  color: white;
  width: 100%;
  padding: 12px;
  border: none;
  border-radius: 8px;
  font-weight: 600;
  cursor: pointer;
}

/* 页脚引流 */
.site-footer {
  text-align: center;
  font-size: 0.9rem;
  color: var(--text-sub);
  margin-top: 20px;
}

.site-footer a {
  color: var(--text-main);
  text-decoration: none;
  border-bottom: 1px solid var(--accent);
}