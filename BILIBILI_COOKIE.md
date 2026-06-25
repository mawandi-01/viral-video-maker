# B站 Cookie 配置指南

B站有反爬机制，直接用 yt-dlp 下载会报 `HTTP Error 412: Precondition Failed`。需要两步配置：

## 第 1 步：安装 curl_cffi（B站反爬绕过）

yt-dlp 需要 `curl_cffi` 模拟 Chrome 浏览器绕过 412 反爬。

```bash
cd /Users/ma/WorkBuddy/my-project
source .venv/bin/activate
pip install 'curl_cffi>=0.5.10,<0.14'
```

> 注意：yt-dlp 只支持 curl_cffi 0.5.10, 0.10.x ~ 0.13.x，**不支持 0.14.0+**

验证安装：
```bash
python -m yt_dlp --list-impersonate-targets
```
应该看到类似输出：
```
Client        OS           Source
------------------------------------
Chrome-131    Android-14   curl_cffi
Firefox-133   Macos-14     curl_cffi
...
```

代码已经配好 `impersonate="chrome"`，你装好 curl_cffi 就行。

## 第 2 步：导出 B站 Cookie

B站下载需要登录态（部分视频需要大会员/登录才能访问）。

### 方法 A：浏览器扩展导出（推荐）

1. Chrome/Edge 安装扩展 [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
2. 打开 [bilibili.com](https://www.bilibili.com) 并登录
3. 在 B站页面点击扩展图标 → **Export**
4. 保存文件到：
   ```
   /Users/ma/WorkBuddy/my-project/cookies/bilibili.txt
   ```

### 方法 B：从浏览器直接读取（懒人方案，不用导出文件）

如果你用 Chrome 登录了 B站，可以直接让 yt-dlp 从浏览器读 cookie：

修改 `src/downloaders/base_downloader.py` 第 101 行，把：
```python
"cookiefile": self._cookie_file(),
```
改成：
```python
"cookiesfrombrowser": ("chrome",),
```
就不用手动导出 cookie 文件了。

### 方法 C：手动构造 Cookie 文件

如果你不想装扩展，可以手动创建 `cookies/bilibili.txt`，Netscape 格式：

```
# Netscape HTTP Cookie File
.bilibili.com	TRUE	/	FALSE	1735689600	SESSDATA	你的SESSDATA值
.bilibili.com	TRUE	/	FALSE	1735689600	bili_jct	你的bili_jct值
.bilibili.com	TRUE	/	FALSE	1735689600	DedeUserID	你的DedeUserID值
```

在浏览器 F12 → Application → Cookies → bilibili.com 里找这三个值。

## 第 3 步：创建 cookies 目录

```bash
mkdir -p /Users/ma/WorkBuddy/my-project/cookies
```

## 第 4 步：验证

```bash
cd /Users/ma/WorkBuddy/my-project
source .venv/bin/activate

# 测试下载一个短视频
python -c "
import sys; sys.path.insert(0, '.')
from src.downloaders import get_downloader
from config.platforms import Platform
import tempfile

d = get_downloader(Platform.BILIBILI, download_dir=tempfile.mkdtemp(), timeout=120)
r = d.download('https://www.bilibili.com/video/BV1zb7K6bEiA', video_id='BV1zb7K6bEiA')
print(f'成功: {r.success}')
print(f'标题: {r.title}')
print(f'文件大小: {r.file_size // 1024}KB')
if r.error:
    print(f'错误: {r.error}')
"
```

成功输出：
```
成功: True
标题: 有能的阿伟
文件大小: 12345KB
```

## Cookie 有效期

- **SESSDATA / bili_jct / DedeUserID**：约 6 个月
- 提前失效的情况：手动登出、改密码、异地登录被踢
- 失效后重新导出即可

## 常见错误

### 412 Precondition Failed
→ curl_cffi 没装，或 impersonate 没启用
→ 解决：`pip install 'curl_cffi>=0.5.10,<0.14'`

### Impersonate target "chrome" is not available
→ curl_cffi 版本不对
→ 解决：检查版本 `pip show curl_cffi`

### Subtitles are only available when logged in
→ Cookie 没提供或已过期
→ 解决：重新导出 cookie 文件
