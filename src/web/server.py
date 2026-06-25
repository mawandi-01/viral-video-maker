"""Web API · FastAPI 后端。

提供视频采集系统的所有功能接口:
- GET  /api/dashboard        仪表盘统计
- GET  /api/videos           视频列表
- POST /api/submit-url       提交视频 URL 采集
- POST /api/discovery        跑爆款发现
- GET  /api/videos/{id}/extract-status  提取状态
- POST /api/extract/{id}     对视频跑多模态提取
- GET  /api/templates        模板列表
- POST /api/generate-prompt  生成 prompt
- GET  /api/health           健康检查

启动:
  cd /Users/ma/WorkBuddy/my-project
  source .venv/bin/activate
  python -m src.web.server
  或
  uvicorn src.web.server:app --host 0.0.0.0 --port 8000 --reload
"""
from __future__ import annotations

import asyncio
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from loguru import logger

from config.settings import settings
from config.platforms import Platform, parse_url
from src.storage.db import get_db


# ---- 请求模型 ----

class SubmitURLRequest(BaseModel):
    url: str


class DiscoveryRequest(BaseModel):
    platforms: list[str] = ["bilibili"]
    top_n: int = 5


class ExtractRequest(BaseModel):
    platform: str
    video_id: str


class GeneratePromptRequest(BaseModel):
    template_id: str
    mode: str = "D"
    theme: str = ""
    target_model: str = "kling"


# ---- 全局状态（后台任务跟踪）----

_running_tasks: dict[str, dict] = {}  # task_id -> {type, status, message, started_at}


def _track_task(task_id: str, task_type: str) -> None:
    _running_tasks[task_id] = {
        "task_id": task_id,
        "type": task_type,
        "status": "running",
        "message": "",
        "started_at": datetime.now().isoformat(),
        "finished_at": None,
    }


def _finish_task(task_id: str, status: str, message: str = "") -> None:
    if task_id in _running_tasks:
        _running_tasks[task_id]["status"] = status
        _running_tasks[task_id]["message"] = message
        _running_tasks[task_id]["finished_at"] = datetime.now().isoformat()


# ---- 后台任务函数（在线程里跑，不阻塞 API）----

def _bg_submit_url(url: str, task_id: str) -> None:
    try:
        from src.queue.task_queue import get_queue
        q = get_queue()
        task = q.submit_url(url)
        _finish_task(task_id, "success", f"已入队: {task.task_id}")
    except Exception as e:
        _finish_task(task_id, "failed", str(e))


def _bg_discovery(platforms: list[str], top_n: int, task_id: str) -> None:
    try:
        from src.discovery.scheduler import run_discovery
        result = run_discovery(platforms=platforms, top_n=top_n)
        _finish_task(task_id, "success", f"发现 {result} 个视频")
    except Exception as e:
        _finish_task(task_id, "failed", str(e))


def _bg_extract(platform: str, video_id: str, task_id: str) -> None:
    try:
        from src.workers.extract_worker import ExtractWorker
        worker = ExtractWorker()
        ok = worker.execute(Platform(platform), video_id)
        if ok:
            _finish_task(task_id, "success", "提取完成")
        else:
            _finish_task(task_id, "failed", "提取失败，查看日志")
    except Exception as e:
        _finish_task(task_id, "failed", str(e))


# ---- FastAPI 应用 ----

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Web API starting ...")
    yield
    logger.info("Web API shutting down ...")


app = FastAPI(title="爆款视频采集系统", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- 接口 ----

@app.get("/api/health")
async def health():
    return {"status": "ok", "time": datetime.now().isoformat()}


@app.get("/api/dashboard")
async def dashboard():
    """仪表盘统计。"""
    db = get_db()
    with db.conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM videos")
            total_videos = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM videos WHERE oss_key <> ''")
            downloaded = cur.fetchone()[0]
            cur.execute(
                "SELECT COUNT(*) FROM videos WHERE template_features IS NOT NULL AND template_features != '{}'::jsonb"
            )
            extracted = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM videos WHERE is_viral = TRUE")
            viral = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM prompt_templates")
            templates = cur.fetchone()[0]
            cur.execute(
                "SELECT platform, COUNT(*) FROM videos GROUP BY platform ORDER BY COUNT(*) DESC"
            )
            by_platform = [{"platform": r[0], "count": r[1]} for r in cur.fetchall()]
            cur.execute(
                """SELECT platform, video_id, title, play_count, like_count, interaction_rate, is_viral
                   FROM videos ORDER BY interaction_rate DESC LIMIT 5"""
            )
            top_videos = [
                {
                    "platform": r[0], "video_id": r[1], "title": r[2],
                    "play_count": r[3], "like_count": r[4],
                    "interaction_rate": float(r[5] or 0), "is_viral": r[6],
                }
                for r in cur.fetchall()
            ]
    return {
        "total_videos": total_videos,
        "downloaded": downloaded,
        "extracted": extracted,
        "viral": viral,
        "templates": templates,
        "by_platform": by_platform,
        "top_videos": top_videos,
    }


@app.get("/api/videos")
async def list_videos(limit: int = 50, offset: int = 0, extracted: Optional[str] = None):
    """视频列表。extracted=true/false 过滤。"""
    db = get_db()
    where = "1=1"
    if extracted == "true":
        where += " AND template_features IS NOT NULL AND template_features != '{}'::jsonb"
    elif extracted == "false":
        where += " AND (template_features IS NULL OR template_features = '{}'::jsonb)"

    with db.conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM videos WHERE {where}")
            total = cur.fetchone()[0]
            cur.execute(
                f"""SELECT platform, video_id, url, title, author_name, duration,
                           play_count, like_count, comment_count, share_count,
                           interaction_rate, is_viral, oss_key,
                           template_features IS NOT NULL AND template_features != '{{}}'::jsonb AS extracted,
                           collected_at
                    FROM videos WHERE {where}
                    ORDER BY collected_at DESC LIMIT %s OFFSET %s""",
                (limit, offset),
            )
            rows = cur.fetchall()
    videos = []
    for r in rows:
        videos.append({
            "platform": r[0], "video_id": r[1], "url": r[2], "title": r[3],
            "author_name": r[4], "duration": r[5],
            "play_count": r[6], "like_count": r[7], "comment_count": r[8],
            "share_count": r[9], "interaction_rate": float(r[10] or 0),
            "is_viral": r[11], "has_file": bool(r[12]), "extracted": r[13],
            "collected_at": r[14].isoformat() if r[14] else None,
        })
    return {"total": total, "videos": videos}


@app.post("/api/submit-url")
async def submit_url(req: SubmitURLRequest, bg: BackgroundTasks):
    """提交视频 URL 采集。"""
    parsed = parse_url(req.url)
    if not parsed.video_id:
        raise HTTPException(400, f"无法解析 URL: {req.url}")
    task_id = str(uuid4())
    _track_task(task_id, "submit_url")
    bg.add_task(_bg_submit_url, req.url, task_id)
    return {"task_id": task_id, "platform": parsed.platform.value, "video_id": parsed.video_id}


@app.post("/api/discovery")
async def run_discovery_api(req: DiscoveryRequest, bg: BackgroundTasks):
    """跑爆款发现。"""
    task_id = str(uuid4())
    _track_task(task_id, "discovery")
    bg.add_task(_bg_discovery, req.platforms, req.top_n, task_id)
    return {"task_id": task_id, "platforms": req.platforms, "top_n": req.top_n}


@app.post("/api/extract")
async def extract_video_api(req: ExtractRequest, bg: BackgroundTasks):
    """对视频跑多模态提取（后台执行）。"""
    task_id = str(uuid4())
    _track_task(task_id, "extract")
    bg.add_task(_bg_extract, req.platform, req.video_id, task_id)
    return {"task_id": task_id, "platform": req.platform, "video_id": req.video_id}


@app.get("/api/tasks/{task_id}")
async def get_task_status(task_id: str):
    """查询后台任务状态。"""
    task = _running_tasks.get(task_id)
    if not task:
        raise HTTPException(404, "task not found")
    return task


@app.get("/api/tasks")
async def list_tasks():
    """列出所有后台任务。"""
    return {"tasks": list(_running_tasks.values())}


@app.get("/api/templates")
async def list_templates(limit: int = 50):
    """模板列表。"""
    db = get_db()
    with db.conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT template_id, source_platform, source_video_id,
                          template_schema, category, sub_type, quality_score, usage_count, created_at
                   FROM prompt_templates
                   ORDER BY quality_score DESC LIMIT %s""",
                (limit,),
            )
            rows = cur.fetchall()
    templates = []
    for r in rows:
        schema = r[3] if isinstance(r[3], dict) else {}
        templates.append({
            "template_id": r[0], "source_platform": r[1], "source_video_id": r[2],
            "category": r[4] or "", "sub_type": r[5] or "",
            "quality_score": float(r[6] or 0), "usage_count": r[7],
            "created_at": r[8].isoformat() if r[8] else None,
            "hook_recipe": schema.get("hook_recipe", ""),
            "content_recipe": schema.get("content_recipe", ""),
            "viral_factors": schema.get("viral_factors", []),
            "segment_count": len(schema.get("segments", [])),
        })
    return {"total": len(templates), "templates": templates}


@app.get("/api/templates/{template_id}")
async def get_template_detail(template_id: str):
    """模板详情（完整 schema）。"""
    db = get_db()
    with db.conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT template_id, source_platform, source_video_id,
                          template_schema, category, sub_type, quality_score, usage_count, created_at
                   FROM prompt_templates WHERE template_id = %s""",
                (template_id,),
            )
            r = cur.fetchone()
    if not r:
        raise HTTPException(404, "template not found")
    schema = r[3] if isinstance(r[3], dict) else {}
    return {
        "template_id": r[0], "source_platform": r[1], "source_video_id": r[2],
        "template_schema": schema, "category": r[4] or "", "sub_type": r[5] or "",
        "quality_score": float(r[6] or 0), "usage_count": r[7],
        "created_at": r[8].isoformat() if r[8] else None,
    }


@app.post("/api/generate-prompt")
async def generate_prompt_api(req: GeneratePromptRequest):
    """生成 prompt（同步执行，约 10-30 秒）。"""
    try:
        from src.extract.prompt.factory import PromptGeneratorFactory
        from src.extract.prompt.context import GenerateContext

        generator = PromptGeneratorFactory.create(req.mode)
        ctx = GenerateContext(
            template_id=req.template_id,
            mode=req.mode,
            theme=req.theme,
            target_model=req.target_model,
        )
        package = generator.generate(ctx)
        return {
            "success": True,
            "video_topic": package.video_topic,
            "global_prompt": package.global_prompt,
            "segments": [
                {
                    "index": s.index, "duration": s.duration,
                    "shot": s.shot, "dialogue": s.dialogue,
                    "action": s.action, "transition": s.transition,
                }
                for s in package.segments
            ],
            "constraints": package.constraints,
            "target_model": package.target_model,
        }
    except Exception as e:
        logger.error(f"generate prompt failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@app.get("/api/videos/{platform}/{video_id}/features")
async def get_video_features(platform: str, video_id: str):
    """获取视频的多模态提取结果。"""
    db = get_db()
    with db.conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT visual_features, audio_features, text_features, template_features
                   FROM videos WHERE platform = %s AND video_id = %s""",
                (platform, video_id),
            )
            r = cur.fetchone()
    if not r:
        raise HTTPException(404, "video not found")
    return {
        "visual_features": r[0] if r[0] and r[0] != {} else None,
        "audio_features": r[1] if r[1] and r[1] != {} else None,
        "text_features": r[2] if r[2] and r[2] != {} else None,
        "template_features": r[3] if r[3] and r[3] != {} else None,
    }


# ---- 前端页面 ----

@app.get("/", response_class=HTMLResponse)
async def index():
    """返回前端页面。"""
    html_path = settings_extract_html_path()
    with open(html_path, "r", encoding="utf-8") as f:
        return f.read()


def settings_extract_html_path() -> str:
    import os
    return os.path.join(os.path.dirname(__file__), "index.html")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
