# 部署配置指南

回答你所有关于部署的问题。

---

## 1. 元数据从哪来?

**yt-dlp 的 `extract_info()` 一次调用就能拿到大部分元数据**:
- 标题、描述、作者、粉丝数
- 播放量、点赞数、评论数、分享数
- 时长、发布时间、标签、封面图

`VideoWorker` 在下载视频时同时提取这些字段写入 `videos` 表,不再依赖第三方数据 API。
B 站和 YouTube 的热榜还会用各自的官方/公开 API 补全。

---

## 2. 没写爬虫吧？

**没写爬虫。** 项目里只有两类外部数据来源：

| 代码 | 性质 | 文件 |
|------|------|------|
| yt-dlp 下载器 | 开源工具调用 | `src/downloaders/` |
| 官方/公开 API | HTTP 请求 | `src/apis/`, `src/discovery/` |

**完全没有**：Playwright 浏览器自动化、X-Bogus/a_bogus 签名逆向、IP 池/Cookie 池、反爬绕过逻辑。

---

## 3. 需不需要 ECS？

| 阶段 | 在哪跑 | 原因 |
|------|-------|------|
| 0-1 验证流程 | 你的 Mac | 跑通流程，几十条视频，本地够用 |
| 规模化（每天 100+） | 阿里云 ECS | 本地 IP 会被限频，需要 24/7 运行 |

**建议：先在你的 Mac 上跑通整个流程**（本地装 PostgreSQL + Redis 即可），验证 OK 后再上 ECS。

本地 Mac 需要装：
```bash
brew install postgresql redis
brew services start postgresql
brew services start redis
```

---

## 4. OSS 配置（storage1111 bucket）

你的 bucket 信息：
- **bucket 名**：`storage1111`
- **endpoint**：`oss-cn-hangzhou.aliyuncs.com`
- **region**：cn-hangzhou（杭州）

### 权限怎么配？不要开公网读写！

**正确做法：用 RAM 子账号 + AccessKey（最安全）**

1. 登录阿里云控制台 → 右上角头像 → **访问控制 (RAM)**
2. 左侧 **用户** → **创建用户**
   - 用户名：`video-collector`（随便起）
   - 勾选 **OpenAPI 调用访问**（会生成 AccessKey）
   - 创建后 **立即复制 AccessKey ID 和 Secret**（只显示一次！）
3. 给这个用户添加权限 → **自定义策略** → 新建策略：

```json
{
  "Version": "1",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["oss:PutObject", "oss:GetObject", "oss:DeleteObject", "oss:ListObjects"],
      "Resource": [
        "acs:oss:*:*:storage1111",
        "acs:oss:*:*:storage1111/*"
      ]
    }
  ]
}
```

4. 把这个策略附加给 `video-collector` 用户

5. 在 OSS 控制台，bucket `storage1111` 的权限设置：
   - 读写权限：**私有**（不要选公共读写！）
   - 防盗链：可选配置

### 我能通过项目写入 bucket 吗？

**能。** 项目用 `oss2` SDK（阿里云官方 Python SDK），只要你把 AccessKey 填入 `.env`：

```env
OSS_ACCESS_KEY_ID=LTAI5tXXXXXXXXXX
OSS_ACCESS_KEY_SECRET=XXXXXXXXXXXXXXXXXX
OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
OSS_BUCKET_NAME=storage1111
```

代码会调用 `oss2.put_object()` 写入，不需要公网读写权限。

---

## 5. 数据库怎么给？

### 用 PostgreSQL（推荐，我的代码基于 PG）

我的代码用 PostgreSQL，因为 Schema 存储需要 JSONB 类型（MySQL 的 JSON 类型也能用，但 PG 的 JSONB 查询更高效）。

**你需要给我以下信息：**

```
PG_HOST=xxx.pg.rds.aliyuncs.com    # RDS 公网连接地址
PG_PORT=5432
PG_DB=video_collector               # 数据库名
PG_USER=video_collector             # 用户名
PG_PASSWORD=xxxxxx                  # 密码
```

**怎么操作：**

1. 买/已有阿里云 RDS PostgreSQL 实例
2. RDS 控制台 → **数据库管理** → **创建数据库** → 名称填 `video_collector`
3. RDS 控制台 → **账号管理** → 创建账号 → 授权 `video_collector` 数据库
4. RDS 控制台 → **数据安全性** → **添加白名单 IP** → 加你 Mac 的公网 IP（或 ECS 内网 IP）
5. RDS 控制台 → **数据库连接** → 申请**外网地址**（从本地连需要）
6. 把以上 5 个值填入 `.env`

**代码会自动建表**（不需要你手动建）：
```bash
python scripts/init_db.py
# 自动创建 4 张表：collect_tasks, videos, interaction_snapshots, comments
```

### 本地 Mac 跑的话（0-1 阶段推荐）

不用买 RDS，本地装就行：
```bash
brew install postgresql
brew services start postgresql
createdb video_collector
```

`.env` 填：
```env
PG_HOST=localhost
PG_PORT=5432
PG_DB=video_collector
PG_USER=你的mac用户名
PG_PASSWORD=
```

---

## 6. Redis 怎么配？

Redis 用于任务队列（rq 库），存储待处理任务。

**本地 Mac：**
```bash
brew install redis
brew services start redis
```

```env
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=
```

**阿里云：** 买 Redis 实例 → 同 PG 一样配白名单 + 外网地址

---

## 总结：0-1 阶段你只需要准备

| 项目 | 来源 | 填入 .env 的值 |
|------|------|---------------|
| OSS | RAM 子账号 AccessKey | `OSS_ACCESS_KEY_ID` + `SECRET` |
| PostgreSQL | 本地 `brew install` 或 RDS | `PG_HOST/PORT/DB/USER/PASSWORD` |
| Redis | 本地 `brew install` 或阿里云 | `REDIS_HOST/PORT` |
| YOUTUBE_API_KEY | 不需要（除非采 YouTube） | 留空 |

全部配好后：
```bash
cd /Users/ma/WorkBuddy/my-project
.venv/bin/pip install -r requirements.txt
cp .env.example .env  # 填入你的配置
.venv/bin/python scripts/init_db.py  # 自动建表
.venv/bin/python scripts/submit_task.py --url "https://www.douyin.com/video/xxx"
.venv/bin/python scripts/run_worker.py --queue default
```
