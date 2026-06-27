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

# 初始化日志（stderr + 文件 + SLS）
import src.utils.logger  # noqa: F401 — 触发 loguru 全局配置

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
    template_id: str = ""
    mode: str = "1"               # V2: scene 1/2/3, 兼容旧 B/D
    theme: str = ""
    target_model: str = "kling"
    selected_factors: list[str] = []
    user_input: dict = {}         # 场景2: {title, content, style}; 场景3: {prompt}
    video_type: str = ""          # 场景3: 用户手选类型


class FeedbackRequest(BaseModel):
    record_id: str
    feedback: str = ""            # 👍 / 👎
    published_url: str = ""
    published_platform: str = ""


class CollectMetricsRequest(BaseModel):
    record_id: str


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
                          template_schema, category, sub_type, quality_score, usage_count,
                          video_type, attribution_id, created_at
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
            "video_type": r[8] or "", "attribution_id": r[9] or "",
            "created_at": r[10].isoformat() if r[10] else None,
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
    """生成 prompt（V2: 支持 3 种场景 + 爆款因子勾选）。同步执行，约 10-30 秒。"""
    try:
        from src.extract.prompt.factory import PromptGeneratorFactory
        from src.extract.prompt.context import GenerateContext
        from src.extract.quality_loop import get_loop

        generator = PromptGeneratorFactory.create(req.mode)
        ctx = GenerateContext(
            template_id=req.template_id,
            mode=req.mode,
            scene=req.mode,
            theme=req.theme,
            selected_factors=req.selected_factors,
            user_input=req.user_input,
            video_type=req.video_type,
            target_model=req.target_model,
        )
        package = generator.generate(ctx)

        # 记录生成（质量闭环）
        try:
            loop = get_loop()
            record_id = loop.record_generation(
                template_id=req.template_id,
                scene_type=req.mode,
                video_type=package.raw_claude_response.get("video_type", req.video_type),
                user_theme=req.theme,
                user_input=req.user_input,
                selected_factors=req.selected_factors,
                prompt_package={
                    "video_topic": package.video_topic,
                    "global_prompt": package.global_prompt,
                    "segments": [{"duration": s.duration, "shot": s.shot, "dialogue": s.dialogue} for s in package.segments],
                },
            )
        except Exception as e:
            record_id = ""
            logger.warning(f"quality loop record failed (non-fatal): {e}")

        return {
            "success": True,
            "record_id": record_id,
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
            "used_factors": package.used_factors,
            "enhancement_notes": package.enhancement_notes,
            "constraints": package.constraints,
            "target_model": package.target_model,
        }
    except Exception as e:
        logger.error(f"generate prompt failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


@app.get("/api/templates/{template_id}/attribution")
async def get_template_attribution(template_id: str):
    """获取模板的爆款归因详情。"""
    db = get_db()
    with db.conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT attribution_id FROM prompt_templates WHERE template_id = %s",
                (template_id,),
            )
            r = cur.fetchone()
            if not r or not r[0]:
                raise HTTPException(404, "no attribution for this template")
            attribution_id = r[0]
            cur.execute(
                """SELECT attribution_id, video_type, primary_factor, primary_weight,
                          factors, critical_factors, removable_factors, migration_guide
                   FROM viral_attributions WHERE attribution_id = %s""",
                (attribution_id,),
            )
            a = cur.fetchone()
            if not a:
                raise HTTPException(404, "attribution not found")
            import json
            return {
                "attribution_id": a[0],
                "video_type": a[1] or "",
                "primary_factor": a[2] or "",
                "primary_weight": float(a[3] or 0),
                "factors": a[4] if isinstance(a[4], list) else json.loads(a[4] or "[]"),
                "critical_factors": a[5] if isinstance(a[5], list) else json.loads(a[5] or "[]"),
                "removable_factors": a[6] if isinstance(a[6], list) else json.loads(a[6] or "[]"),
                "migration_guide": a[7] if isinstance(a[7], dict) else json.loads(a[7] or "{}"),
            }


@app.get("/api/video-types")
async def list_video_types():
    """返回 10 种视频类型。"""
    from src.extract.classifier import VIDEO_TYPES
    return {"types": VIDEO_TYPES}


@app.post("/api/feedback")
async def submit_feedback(req: FeedbackRequest):
    """用户反馈（质量闭环）。"""
    try:
        from src.extract.quality_loop import get_loop
        loop = get_loop()
        loop.update_feedback(req.record_id, req.feedback, req.published_url, req.published_platform)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/collect-metrics")
async def collect_metrics(req: CollectMetricsRequest):
    """回采发布视频的实际数据。"""
    try:
        from src.extract.quality_loop import get_loop
        from src.storage.db import get_db
        db = get_db()
        with db.conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT published_url, published_platform FROM generation_records WHERE record_id = %s",
                    (req.record_id,),
                )
                r = cur.fetchone()
                if not r or not r[0]:
                    raise HTTPException(404, "no published URL")
                url = r[0]
        # 用 yt-dlp 回采数据
        import yt_dlp
        opts = {"quiet": True, "no_warnings": True, "skip_download": True}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        play = int(info.get("view_count", 0) or 0)
        like = int(info.get("like_count", 0) or 0)
        rate = round(like / play, 4) if play > 0 else 0
        loop = get_loop()
        loop.update_actual_metrics(req.record_id, play, like, rate)
        return {"success": True, "play_count": play, "like_count": like, "interaction_rate": rate}
    except Exception as e:
        logger.error(f"collect metrics failed: {e}")
        return {"success": False, "error": str(e)}


@app.get("/api/generation-records")
async def list_generation_records(limit: int = 50):
    """生成记录列表（质量闭环）。"""
    from src.extract.quality_loop import get_loop
    loop = get_loop()
    return {"records": loop.list_records(limit)}


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


@app.get("/api/videos/{platform}/{video_id}/report")
async def get_video_report(platform: str, video_id: str):
    """拆解报告 · 聚合所有数据，返回用户友好的结构。

    返回 5 个部分:
    1. video_info: 视频基本信息
    2. content_summary: 这个视频讲了什么
    3. timeline: 分镜时间线（每段配关键帧 URL）
    4. attribution: 为什么能火（爆款归因）
    5. recipe: 提炼出的配方
    """
    import json
    db = get_db()

    with db.conn() as conn:
        with conn.cursor() as cur:
            # 1. 视频基本信息 + features
            cur.execute(
                """SELECT platform, video_id, url, title, author_name, duration,
                          play_count, like_count, comment_count, share_count,
                          interaction_rate, is_viral, oss_key, cover_oss_key,
                          visual_features, audio_features, text_features, template_features
                   FROM videos WHERE platform = %s AND video_id = %s""",
                (platform, video_id),
            )
            v = cur.fetchone()
            if not v:
                raise HTTPException(404, "video not found")

            visual = v[14] if isinstance(v[14], dict) else json.loads(v[14] or "{}")
            audio = v[15] if isinstance(v[15], dict) else json.loads(v[15] or "{}")
            text = v[16] if isinstance(v[16], dict) else json.loads(v[16] or "{}")
            template = v[17] if isinstance(v[17], dict) else json.loads(v[17] or "{}")

            # 2. 关联的配方
            cur.execute(
                """SELECT template_id, template_schema, category, sub_type,
                          quality_score, video_type, attribution_id
                   FROM prompt_templates
                   WHERE source_platform = %s AND source_video_id = %s
                   ORDER BY created_at DESC LIMIT 1""",
                (platform, video_id),
            )
            t = cur.fetchone()
            template_id = ""
            template_schema = {}
            attribution_id = ""
            video_type = ""
            if t:
                template_id = t[0]
                template_schema = t[1] if isinstance(t[1], dict) else json.loads(t[1] or "{}")
                video_type = t[5] or template_schema.get("video_type", "")
                attribution_id = t[6] or ""

            # 3. 归因数据
            attribution = None
            if attribution_id:
                cur.execute(
                    """SELECT video_type, primary_factor, primary_weight,
                              factors, critical_factors, removable_factors, migration_guide
                       FROM viral_attributions WHERE attribution_id = %s""",
                    (attribution_id,),
                )
                a = cur.fetchone()
                if a:
                    factors = a[3] if isinstance(a[3], list) else json.loads(a[3] or "[]")
                    attribution = {
                        "video_type": a[0] or "",
                        "primary_factor": a[1] or "",
                        "primary_weight": float(a[2] or 0),
                        "factors": factors,
                        "critical_factors": a[4] if isinstance(a[4], list) else json.loads(a[4] or "[]"),
                        "removable_factors": a[5] if isinstance(a[5], list) else json.loads(a[5] or "[]"),
                        "migration_guide": a[6] if isinstance(a[6], dict) else json.loads(a[6] or "{}"),
                    }
                    if not video_type:
                        video_type = a[0] or ""

    # 3.5 归因兜底：没有 V2 归因时，从 template_schema 的 viral_factors 合成一个轻量版
    #      这样前端「为什么能火」永远有内容，不至于空白
    attribution_source = "v2"
    if attribution is None:
        v1_factors_raw = (
            template_schema.get("viral_factors", [])
            or template.get("viral_factors", [])
            or []
        )
        if v1_factors_raw:
            # 把字符串列表转成统一的 factor 对象
            v1_factors = []
            for i, f in enumerate(v1_factors_raw):
                if isinstance(f, str):
                    # 第一个因子权重高，后面递减
                    w = round(0.5 / (i + 1), 2) if i > 0 else 0.5
                    v1_factors.append({
                        "name": f,
                        "weight": w,
                        "evidence": "",
                        "applicable": True,
                    })
                elif isinstance(f, dict):
                    v1_factors.append(f)
            # 归一化权重
            total = sum(f.get("weight", 0) for f in v1_factors) or 1
            for f in v1_factors:
                f["weight"] = round(f.get("weight", 0) / total, 2)
            if v1_factors:
                attribution = {
                    "video_type": video_type or template_schema.get("category", ""),
                    "primary_factor": v1_factors[0].get("name", ""),
                    "primary_weight": v1_factors[0].get("weight", 0),
                    "factors": v1_factors,
                    "critical_factors": [v1_factors[0].get("name", "")] if v1_factors else [],
                    "removable_factors": [],
                    "migration_guide": {},
                }
                attribution_source = "v1"

    # 4. 构造时间线（从 template_features.segments）
    timeline = []
    segments = template.get("segments", [])
    visual_frames = visual.get("frames", [])
    for i, seg in enumerate(segments):
        # 尝试匹配关键帧
        frame_url = ""
        frame_idx = i + 1
        if frame_idx <= len(visual_frames):
            frame_url = f"/api/videos/{platform}/{video_id}/frame/{frame_idx}"
        timeline.append({
            "index": i + 1,
            "time": seg.get("time", ""),
            "shot": seg.get("shot", ""),
            "dialogue": seg.get("dialogue", ""),
            "purpose": seg.get("purpose", ""),
            "technique": seg.get("technique", ""),
            "content_summary": seg.get("content_summary", ""),
            "emotion": seg.get("emotion", ""),
            "frame_url": frame_url,
        })

    # 5. 内容摘要
    content_summary = template.get("video_topic", "") or text.get("content_summary", "")
    if not content_summary:
        # 从标题推断
        content_summary = v[3] or ""

    # 6. 封面图 URL
    cover_url = ""
    if v[13]:  # cover_oss_key
        try:
            from src.storage.oss_storage import get_oss
            cover_url = get_oss().sign_url(v[13], expires=3600)
        except Exception:
            pass

    return {
        "video_info": {
            "platform": v[0], "video_id": v[1], "url": v[2], "title": v[3],
            "author_name": v[4], "duration": v[5],
            "play_count": v[6], "like_count": v[7], "comment_count": v[8],
            "share_count": v[9], "interaction_rate": float(v[10] or 0),
            "is_viral": v[11], "cover_url": cover_url,
        },
        "content_summary": content_summary,
        "video_type": video_type or (attribution.get("video_type", "") if attribution else ""),
        "timeline": timeline,
        "attribution": attribution,
        "attribution_source": attribution_source,
        "recipe": {
            "template_id": template_id,
            "category": template_schema.get("category", ""),
            "sub_type": template_schema.get("sub_type", ""),
            "hook_recipe": template_schema.get("hook_recipe", ""),
            "content_recipe": template_schema.get("content_recipe", ""),
            "viral_factors": template_schema.get("viral_factors", []),
            "quality_score": float(t[4] if t else 0),
        } if t else None,
    }


@app.get("/api/videos/{platform}/{video_id}/frame/{frame_idx}")
async def get_video_frame(platform: str, video_id: str, frame_idx: int):
    """获取视频关键帧图片（从 OSS 读取）。"""
    # 帧图存储路径: frames/{platform}/{video_id}/frame_{idx:04d}.jpg
    oss_key = f"frames/{platform}/{video_id}/frame_{frame_idx:04d}.jpg"
    try:
        from src.storage.oss_storage import get_oss
        url = get_oss().sign_url(oss_key, expires=3600)
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url)
    except Exception:
        raise HTTPException(404, "frame not found")


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
