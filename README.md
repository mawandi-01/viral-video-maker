# 🔥 爆款视频制造机 · Viral Video Maker

从爆款视频中发现灵感，AI 拆解配方，生成新视频脚本。

## 功能

- **视频采集**：支持 B站 / YouTube 自动发现热门 + 手动 URL 采集
- **多模态拆解**：AI 分析画面 + 语音转文字 + 文案结构分析
- **模板抽象**：从爆款视频提炼可复用的"配方"
- **Prompt 生成**：基于配方 + 新主题，生成新视频分镜脚本
- **Web 界面**：仿抖音/豆包风格的深色主题前端

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.13 + FastAPI |
| 前端 | 单文件 HTML（深色主题） |
| 数据库 | PostgreSQL（JSONB 存特征） |
| 队列 | Redis + rq |
| 存储 | 阿里云 OSS |
| AI | claude-sonnet-4（CLIProxyAPI 中转站，免费） |
| ASR | mlx-whisper（本地，免费） |
| 下载 | yt-dlp + curl_cffi |
| 预处理 | ffmpeg |

## 快速开始

```bash
# 1. 安装依赖
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入你的 PG/Redis/OSS 配置

# 3. 初始化数据库
python scripts/init_db.py
python scripts/add_download_columns.py
python scripts/add_extract_columns.py

# 4. 启动 Web 服务
python scripts/run_web.py
# 浏览器打开 http://localhost:8765
```

## 项目结构

```
src/
├── ai/              # AI 客户端（Claude 封装）
├── audio/           # 音频引擎（Whisper ASR）
├── discovery/       # 爆款发现（B站/YouTube 热门）
├── downloaders/     # 视频下载器（yt-dlp）
├── extract/         # 多模态提取引擎
│   ├── preprocessor.py    # ffmpeg 预处理
│   ├── visual_engine.py   # 视觉引擎（Claude 看帧）
│   ├── text_engine.py     # 文案引擎（Claude 拆文案）
│   ├── fusion_engine.py   # 融合引擎（跨模态对齐）
│   ├── template_engine.py # 模板抽象（去主题留结构）
│   └── prompt/            # Prompt 生成（策略模式）
│       ├── mode_b.py      # 同主题换形式
│       └── mode_d.py      # 跨主题迁移
├── models/          # 数据模型
├── queue/           # 任务队列
├── storage/         # PG + OSS 存储
├── workers/         # Worker（下载 + 提取）
└── web/             # FastAPI 后端 + 前端
```

## 流程

```
采集视频 → AI 拆解（画面+声音+文案）→ 融合分析 → 模板抽象
                                                        ↓
                              用户输入新主题 → Prompt 生成 → 分镜脚本
```

## License

MIT
