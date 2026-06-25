# 本地运行指南

沙箱环境无法下载视频（网络/fork 限制），你需要在本地 Mac 终端运行。

## 第 0 步：安装 ffmpeg（B站下载必需）

B站视频用 DASH 格式存储（视频流和音频流分离），yt-dlp 需要 ffmpeg 把它们合并成单个 mp4。
不装 ffmpeg 会报错：`You have requested merging of multiple formats but ffmpeg is not installed`

```bash
cd /Users/ma/WorkBuddy/my-project
bash scripts/install_ffmpeg.sh
```

脚本会自动下载 arm64 静态二进制并安装到 `/usr/local/bin/`（需要输入 sudo 密码）。

验证：
```bash
ffmpeg -version
# 应显示 ffmpeg 6.1.1 版本信息
```

## 第 0.5 步：修复 PG schema（一次性）

如果 PG 是旧版本 schema 建的，会缺 `download_status` 等字段，导致 worker 报：
`column "download_status" of relation "videos" does not exist`

修复（幂等，可以重复跑）：
```bash
cd /Users/ma/WorkBuddy/my-project
source .venv/bin/activate
python scripts/fix_schema.py
```

> 注意：从 2026-06-25 起，`run_worker.py` 启动时也会自动跑一次 `init_schema()`，
> 所以这步主要是为了在跑 worker 前先把库修好。

## 第 1 步：B站 Cookie（B站下载需要）

B站对未登录用户返回 412。代码已配置为**自动从 Safari 读取 Cookie**，无需手动导出。

**前提条件：**
1. 用 Safari 浏览器打开 [bilibili.com](https://www.bilibili.com) 并登录
2. 给终端"完全磁盘访问"权限：
   - 系统设置 → 隐私与安全性 → 完全磁盘访问权限
   - 添加你用的终端 app（Terminal / iTerm2）

验证 Safari Cookie 能读到：
```bash
cd /Users/ma/WorkBuddy/my-project
source .venv/bin/activate
python -c "
import browser_cookie3
cj = browser_cookie3.safari()
bili_cookies = [c for c in cj if 'bilibili' in c.domain]
print(f'读取到 {len(bili_cookies)} 个 B站 cookie')
"
```

> 如果你用 Chrome 登录的 B站，可以手动导出 cookie 文件放到 `cookies/bilibili.txt`（Netscape 格式），代码会优先使用文件。

## 第 2 步：确保 Redis 运行

```bash
# 检查本地 Redis 是否运行
redis-cli ping
# 应返回 PONG

# 如果没运行，启动它：
brew services start redis
# 或
redis-server --daemonize yes
```

## 第 3 步：本地运行 Discovery + Worker

打开 Mac 终端，依次运行：

```bash
cd /Users/ma/WorkBuddy/my-project

# 激活虚拟环境
source .venv/bin/activate

# 1. 跑 discovery（B站拉热门 → 筛爆款 → 入队）
python scripts/run_discovery.py --platforms bilibili --top-n 5

# 2. 启动 worker（消费队列 → 下载视频 → 上传 OSS → 写 PG）
python scripts/run_worker.py --queue default --burst

# 3. 查看结果
python scripts/status.py
```

## 第 4 步：验证结果

```bash
# 查 PG
python -c "
import psycopg2
conn = psycopg2.connect('postgresql://mwd:Mwd123321@pgm-bp1srl790a3u2ic33o.pg.rds.aliyuncs.com:5432/video_collector')
cur = conn.cursor()
cur.execute('SELECT video_id, title, play_count, oss_key FROM videos ORDER BY collected_at DESC LIMIT 5')
for r in cur.fetchall():
    print(r)
"

# 查 OSS（在阿里云控制台看 storage1111 bucket 的 videos/raw/ 目录）
```

## 常见问题

### ffmpeg 未安装错误
`You have requested merging of multiple formats but ffmpeg is not installed`
→ 运行 `bash scripts/install_ffmpeg.sh`，见第 0 步

### B站 412 错误
→ 需要 curl_cffi + Safari Cookie，见第 1 步和 BILIBILI_COOKIE.md

### yt-dlp impersonate AssertionError
→ yt-dlp 2026+ 需要 ImpersonateTarget 对象，代码已修复，确保 curl_cffi 已安装

### macOS fork 崩溃 (objc signal 6)
→ 代码已用 SimpleWorker 代替 Worker（macOS 无 fork），无需手动处理

### Redis 连接超时
→ 本地 Redis 不应该有此问题。检查 `redis-cli ping` 是否返回 PONG

### Worker 启动后立刻退出
→ `--burst` 模式跑完队列就退出，正常行为

### 想持续运行 Worker
去掉 `--burst`，Worker 会持续监听队列：
```bash
python scripts/run_worker.py --queue default
```

### 手动提交抖音/快手 URL
```bash
python scripts/submit_task.py --url "https://www.douyin.com/video/xxx"
python scripts/run_worker.py --queue default --burst
```
