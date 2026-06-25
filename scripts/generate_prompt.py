"""阶段二入口 · 基于模板生成新视频的 prompt。

用法:
  cd /Users/ma/WorkBuddy/my-project
  source .venv/bin/activate

  # 列出可用模板
  python scripts/generate_prompt.py --list

  # 模式 B: 同主题换形式（如 咖啡 → 奶茶）
  python scripts/generate_prompt.py --template-id xxx --mode B --theme "奶茶知识科普"

  # 模式 D: 跨主题迁移（如 咖啡 → 基金理财）
  python scripts/generate_prompt.py --template-id xxx --mode D --theme "基金理财科普"

  # 输出到文件
  python scripts/generate_prompt.py --template-id xxx --mode D --theme "基金" --output prompt.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.extract.prompt.factory import PromptGeneratorFactory
from src.extract.prompt.context import GenerateContext
from src.storage.db import get_db
from src.utils.logger import logger


def list_templates() -> None:
    """列出可用模板。"""
    db = get_db()
    with db.conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT template_id, source_platform, source_video_id,
                       category, sub_type, quality_score, usage_count
                FROM prompt_templates
                ORDER BY quality_score DESC
                LIMIT 50
                """
            )
            rows = cur.fetchall()

    print("\n" + "=" * 90)
    print(f"可用模板（共 {len(rows)} 个，按 quality_score 排序）")
    print("=" * 90)
    if not rows:
        print("暂无模板。请先跑提取: python scripts/extract_video.py --video-id xxx")
        return

    print(f"{'template_id':<40} {'分类':<12} {'子类':<12} {'score':<8} {'used':<6} {'来源'}")
    print("-" * 90)
    for tid, platform, vid, cat, sub, score, used in rows:
        print(f"{tid:<40} {cat or 'N/A':<12} {sub or 'N/A':<12} {score:<8.4f} {used:<6} {platform}/{vid}")

    print(f"\n支持的生成模式: {PromptGeneratorFactory.supported_modes()}")
    desc = PromptGeneratorFactory.mode_descriptions()
    for mode, d in desc.items():
        print(f"  {mode}: {d}")


def generate(template_id: str, mode: str, theme: str, output: str = "") -> None:
    """生成 prompt。"""
    logger.info(f"=== generate: mode={mode}, theme={theme} ===")

    # 创建生成器
    generator = PromptGeneratorFactory.create(mode)

    # 构造上下文
    ctx = GenerateContext(
        template_id=template_id,
        mode=mode,
        theme=theme,
        target_model="kling",
    )

    # 生成
    try:
        package = generator.generate(ctx)
    except Exception as e:
        logger.error(f"generate failed: {e}")
        print(f"\n❌ 生成失败: {e}")
        sys.exit(1)

    # 输出
    print("\n" + package.to_summary())

    if output:
        # 写入文件
        out_data = {
            "template_id": package.template_id,
            "mode": package.mode,
            "video_topic": package.video_topic,
            "global_prompt": package.global_prompt,
            "segments": [
                {
                    "index": s.index,
                    "duration": s.duration,
                    "shot": s.shot,
                    "dialogue": s.dialogue,
                    "action": s.action,
                    "transition": s.transition,
                }
                for s in package.segments
            ],
            "constraints": package.constraints,
            "target_model": package.target_model,
        }
        with open(output, "w", encoding="utf-8") as f:
            json.dump(out_data, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 已写入: {output}")
    else:
        print(f"\n✅ 生成完成")


def main() -> None:
    ap = argparse.ArgumentParser(description="generate video prompt from template")
    ap.add_argument("--list", action="store_true", help="list available templates")
    ap.add_argument("--template-id", help="template ID to use")
    ap.add_argument("--mode", choices=["B", "D"], help="generation mode")
    ap.add_argument("--theme", help="new theme/topic")
    ap.add_argument("--output", help="output to file (JSON)")
    args = ap.parse_args()

    if args.list:
        list_templates()
    elif args.template_id and args.mode and args.theme:
        generate(args.template_id, args.mode, args.theme, args.output)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
