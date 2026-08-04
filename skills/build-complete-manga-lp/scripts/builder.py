#!/usr/bin/env python3
"""漫画LP完成ビルダーの1コマンド実行入口。"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys
import zipfile

from PIL import Image, ImageDraw

SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from engine.prompts import build_jobs, write_job_files  # noqa: E402
from engine.render import file_manifest, render_outputs, safe_path, write_manifest  # noqa: E402
from engine.strategy import GOALS, PRODUCT_TYPES, SALES_STYLES, build_strategy  # noqa: E402
from engine.validate import format_report, validate_script  # noqa: E402


AUDITS = ("machine", "style", "fact", "legal")


def read_json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: pathlib.Path, payload: dict) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def job_root(value: str) -> pathlib.Path:
    return pathlib.Path(value).expanduser().resolve()


def script_path(root: pathlib.Path) -> pathlib.Path:
    return root / "script.json"


def _next_action(product: str, goal: str) -> str:
    actions = {
        "story_ip": {"awareness": "詳細を見る", "trial": "試し読みする", "conversion": "購入する"},
        "knowledge": {"awareness": "内容を見る", "trial": "無料版を試す", "conversion": "購入・申込へ進む"},
        "service": {"awareness": "支援内容を見る", "trial": "資料を請求する", "conversion": "申し込む"},
        "tool": {"awareness": "機能を見る", "trial": "無料で試す", "conversion": "導入する"},
        "physical": {"awareness": "商品を見る", "trial": "比較する", "conversion": "購入する"},
    }
    return actions[product][goal]


def _strategy_for_template(args: argparse.Namespace) -> dict:
    strategy = build_strategy(
        args.product, args.goal, args.style, args.pages,
        decision_maker_separate=args.separate_decision_maker,
        pressure=args.pressure,
    )
    strategy.update({
        "next_action": _next_action(args.product, args.goal),
        "hook_question": "主人公はこの困りごとをどう乗り越えるのか？",
        "payoff_mirror": "冒頭の困った表情と同じ構図を、最後は自信のある表情で反転",
        "achievement_ceiling": "根拠として示せる小さな成功まで",
        "cta_basis": "商品情報と実際の申込先に基づく",
    })
    if strategy["primary_style"] == "achievement_journey":
        strategy.update({
            "user": "実際に使う主人公",
            "decision_maker": "購入や申込を判断する人",
            "peer": "主人公の背中を押す友人",
            "bright_future": "成功後にやりたかった活動を楽しむ具体的な一場面",
        })
    return strategy


def _template_script(title: str, strategy: dict) -> dict:
    beats = list(strategy["required_beats"])
    page_count = int(strategy["pages"])
    if len(beats) < page_count:
        extra = [f"bridge_{index:02d}" for index in range(1, page_count - len(beats) + 1)]
        beats = beats[:-1] + extra + beats[-1:]
    panels = []
    for index, beat in enumerate(beats, 1):
        page = max(1, math.ceil(index * page_count / len(beats)))
        panel_characters = ["user"]
        if strategy["primary_style"] == "achievement_journey":
            if beat == "peer_prompt" or beat == "bright_future":
                panel_characters = ["user", "peer"]
            elif beat in {"decision_maker_pitch", "product_reveal", "objection"}:
                panel_characters = ["user", "decision_maker"]
            elif beat == "cta":
                panel_characters = ["user", "peer", "decision_maker"]
        panels.append({
            "n": index,
            "page": page,
            "section": beat,
            "characters": panel_characters,
            "art": f"{beat} の役割を果たす具体的な場面に書き換える",
            "image": f"assets/panels/p{index:03d}.png",
            "bubbles": [{
                "style": "speech", "text": f"{beat}のセリフ",
                "x": 0.76, "y": 0.25, "w": 0.35, "h": 0.28,
                "tail": [0.56, 0.62], "font_size": 0.075,
            }],
        })
    characters = {
        "user": {
            "name": "主人公", "prompt": "対象読者を代表する人物。服装と髪型を全ページで固定。",
            "ref": "assets/characters/user.png", "expression_ref": "assets/characters/user_expressions.png",
            "action_ref": "assets/characters/user_actions.png",
        }
    }
    if strategy["primary_style"] == "achievement_journey":
        characters.update({
            "peer": {
                "name": "仲間", "prompt": "主人公と同世代で、挑戦のきっかけを作る人物。",
                "ref": "assets/characters/peer.png",
            },
            "decision_maker": {
                "name": "決裁者", "prompt": "商品やサービスの購入・申込を判断する人物。",
                "ref": "assets/characters/decision_maker.png",
            },
        })
    return {
        "meta": {
            "title": title,
            "style_prompt": "親しみやすいフルカラーの日本の広告漫画。明快な表情と読みやすい構図。",
            "canvas": {"width": 720, "panel_height": 480},
            "has_minors": False,
            "demo": False,
            "strategy": strategy,
            "marketing": {
                "phase": "P0",
                "funnel_stage": "販売",
                "traffic_source": "未確定（制作前に流入元を決める）",
                "kpi": "未確定（例: CTAクリック率）",
                "target": {
                    "segment": "未確定（年齢だけでなく、望む変化で定義する）",
                    "situation": "未確定（購入を考える直前の具体的状況）",
                    "desired_progress": "未確定（本人が進めたい用事・変化）",
                    "user": "未確定（実際の利用者）",
                    "decision_maker": "未確定（購入・申込の決裁者）",
                    "payer": "未確定（代金を支払う人）",
                    "barrier": "未確定（購入を止める不安・慣性・反論）"
                },
                "transformation": {
                    "before": "未確定（購入前の認識・感情・行動）",
                    "after_immediate": "未確定（CTA後・購入直後に起こす変化）",
                    "after_experience": "未確定（商品体験後に望む具体的行動）",
                    "non_goal": "未確定（この商品・LPが保証しないこと）"
                },
                "desired_change": "未確定（誰が、何から、何になるか）",
                "hypothesis": "未確定（なぜこの漫画ストーリーでKPIが動くか）",
                "evidence": {
                    "type": "勘",
                    "source": "調査前",
                    "date": "未確定",
                    "finding": "未確定（顧客・競合・市場・実売・自分のどれで確認したか）"
                },
                "measurement": {
                    "event": "未確定（クリック・購入・申込など）",
                    "method": "未確定（計測場所・ツール）",
                    "timing": "未確定（いつ判定するか）",
                    "success_rule": "未確定（継続・修正・中止の判断基準）"
                },
                "route_decision": {
                    "presented": False,
                    "selected": strategy["primary_style"],
                    "reason": strategy.get("selection_reason", ""),
                    "alternatives": strategy.get("route_candidates", []),
                    "confirmation": "未確認"
                },
                "do_not": ["根拠のない実績・体験談・期限を作らない"],
                "inspection_plan": list(AUDITS),
            },
            "offer": {"deadline": "", "deadline_source": ""},
            "legal_notes": ["画像はイメージです。", "効果や感じ方には個人差があります。"],
            "rights": {
                "authorized_names": [title],
                "third_party_names": [],
                "third_party_logos": [],
                "third_party_characters": [],
                "reviewed": False,
                "review_evidence": "未確定（本文・吹き出し・作画指示・生成画像を確認する）",
            },
        },
        "characters": characters,
        "proof_loops": [
            {"barrier": "最初の障壁", "mechanism": "商品の仕組み", "scene": "使う場面", "result": "確認可能な結果"}
            for _ in range(max(1, int(strategy["minimum_proof_loops"])))
        ],
        "panels": panels,
        "cta": {"label": strategy["next_action"] + "（URLを差し替える）", "url": "https://example.com/"},
    }


def command_init(args: argparse.Namespace) -> int:
    root = job_root(args.job)
    if root.exists() and any(root.iterdir()):
        raise FileExistsError(f"空でないフォルダには初期化できません: {root}")
    for relative in ("assets/characters", "assets/panels", "output/pages", "output/social", "reports"):
        (root / relative).mkdir(parents=True, exist_ok=True)
    strategy = _strategy_for_template(args)
    brief = {
        "project_name": args.title,
        "product_type": args.product,
        "goal": args.goal,
        "sales_style": args.style,
        "decision_maker_separate": args.separate_decision_maker,
        "facts": [], "claims_not_allowed": [], "cta_url": "https://example.com/",
        "authorized_names": [args.title],
        "third_party_marks": [],
        "rights_reviewed": False,
    }
    write_json(root / "brief.json", brief)
    write_json(script_path(root), _template_script(args.title, strategy))
    write_json(root / "reports" / "audit.json", {
        "test_only": False,
        "audits": {name: {"status": "pending", "evidence": ""} for name in AUDITS},
    })
    write_job_files(read_json(script_path(root)), root)
    print(f"初期化: {root}")
    print(f"販売ルート: {strategy['route']} / 選択: {strategy['selection_mode']}")
    return 0


def command_prompts(args: argparse.Namespace) -> int:
    root = job_root(args.job)
    manifest, guide = write_job_files(read_json(script_path(root)), root)
    print(manifest)
    print(guide)
    return 0


def command_strategy(args: argparse.Namespace) -> int:
    strategy = build_strategy(
        args.product, args.goal, args.style, args.pages,
        decision_maker_separate=args.separate_decision_maker,
        pressure=args.pressure,
    )
    print(json.dumps(strategy, ensure_ascii=False, indent=2))
    return 0


def _asset_status(root: pathlib.Path, script: dict) -> tuple[list[dict], list[dict]]:
    present, missing = [], []
    for job in build_jobs(script):
        path = safe_path(root, job["target"])
        record = {"id": job["id"], "kind": job["kind"], "target": job["target"]}
        (present if path.is_file() and path.stat().st_size > 0 else missing).append(record)
    return present, missing


def command_status(args: argparse.Namespace) -> int:
    root = job_root(args.job)
    script = read_json(script_path(root))
    present, missing = _asset_status(root, script)
    audit = read_json(root / "reports" / "audit.json")
    manifest_path = root / "reports" / "manifest.json"
    finalized = False
    if manifest_path.is_file():
        manifest = read_json(manifest_path)
        expected = manifest.get("source_files", []) + manifest.get("files", [])
        current_paths = []
        for record in expected:
            path = safe_path(root, record["path"])
            if path.is_file():
                current_paths.append(path)
        current = {record["path"]: record["sha256"] for record in file_manifest(root, current_paths)}
        finalized = len(current) == len(expected) and all(
            current.get(record["path"]) == record["sha256"] for record in expected
        )
    result = {
        "images": {"present": len(present), "missing": len(missing), "missing_items": missing},
        "audits": audit.get("audits", {}),
        "finalized": finalized,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if missing else 0


def command_validate(args: argparse.Namespace) -> int:
    root = job_root(args.job)
    path = script_path(root)
    issues = validate_script(read_json(path), strict=True)
    report = format_report(path, issues)
    (root / "reports").mkdir(exist_ok=True)
    (root / "reports" / "validation.txt").write_text(report + "\n", encoding="utf-8")
    print(report)
    return 1 if any(issue.level == "error" for issue in issues) else 0


def _demo_image(path: pathlib.Path, label: str, size: tuple[int, int], color: tuple[int, int, int]) -> None:
    image = Image.new("RGB", size, color)
    draw = ImageDraw.Draw(image)
    draw.rectangle((12, 12, size[0] - 13, size[1] - 13), outline="white", width=5)
    draw.text((30, 30), "DEMO / NOT FOR PUBLIC", fill="white")
    draw.text((30, 70), label, fill="white")
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "PNG")


def command_demo_assets(args: argparse.Namespace) -> int:
    root = job_root(args.job)
    script = read_json(script_path(root))
    width, height = (int(script["meta"]["canvas"]["width"]), int(script["meta"]["canvas"]["panel_height"]))
    palette = ((53, 82, 148), (111, 68, 145), (41, 130, 111), (184, 97, 53))
    for index, job in enumerate(build_jobs(script)):
        size = (900, 600) if job["kind"] != "panel" else (width, height)
        _demo_image(safe_path(root, job["target"]), job["id"], size, palette[index % len(palette)])
    (root / ".demo-assets").write_text("テスト専用。販売・公開禁止。\n", encoding="utf-8")
    write_json(root / "reports" / "audit.json", {
        "test_only": True,
        "audits": {name: {"status": "pass", "evidence": "自動E2E用ダミー素材"} for name in AUDITS},
    })
    print("デモ素材を生成しました。公開物には使用できません。")
    return 0


def _audit_gate(root: pathlib.Path, *, allow_demo: bool) -> dict:
    audit_path = root / "reports" / "audit.json"
    if not audit_path.is_file():
        raise RuntimeError("reports/audit.json がありません")
    audit = read_json(audit_path)
    if audit.get("test_only") and not allow_demo:
        raise RuntimeError("テスト専用監査です。公開用の4検品へ差し替えてください")
    for name in AUDITS:
        item = audit.get("audits", {}).get(name, {})
        if item.get("status") != "pass" or not item.get("evidence"):
            raise RuntimeError(f"{name}検品が未合格、または根拠が空です")
    return audit


def _build_zip(root: pathlib.Path) -> pathlib.Path:
    target = root / "output" / "manga-lp-delivery.zip"
    include_roots = [root / "brief.json", root / "script.json", root / "reports", root / "output"]
    files: list[pathlib.Path] = []
    for source in include_roots:
        if source.is_file():
            files.append(source)
        elif source.is_dir():
            files.extend(path for path in source.rglob("*") if path.is_file() and path != target)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(set(files)):
            archive.write(path, path.relative_to(root))
    return target


def command_preview(args: argparse.Namespace) -> int:
    root = job_root(args.job)
    outputs = render_outputs(read_json(script_path(root)), root, placeholders=True)
    print(json.dumps(outputs, ensure_ascii=False, indent=2))
    print("注意: プレースホルダー入りの確認用出力です。完成品ではありません。")
    return 0


def command_finalize(args: argparse.Namespace) -> int:
    root = job_root(args.job)
    script = read_json(script_path(root))
    issues = validate_script(script, strict=True)
    if any(issue.level == "error" for issue in issues):
        raise RuntimeError(format_report(script_path(root), issues))
    _, missing = _asset_status(root, script)
    if missing:
        names = "、".join(item["target"] for item in missing[:8])
        raise RuntimeError(f"作画素材が{len(missing)}点不足: {names}")
    if (root / ".demo-assets").exists() and not args.allow_demo:
        raise RuntimeError("デモ素材を検出しました。公開用finalizeは拒否します")
    audit = _audit_gate(root, allow_demo=args.allow_demo)
    outputs = render_outputs(script, root, placeholders=False)
    write_manifest(root, outputs, demo=bool(audit.get("test_only")))
    package = _build_zip(root)
    print(json.dumps({"outputs": outputs, "package": str(package)}, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="漫画LP完成ビルダー for Gemini Spark")
    sub = parser.add_subparsers(dest="command", required=True)

    listing = sub.add_parser("list", help="商品・目的・販売スタイル一覧")
    listing.set_defaults(func=lambda _args: print(json.dumps({
        "products": PRODUCT_TYPES, "goals": GOALS, "styles": SALES_STYLES,
    }, ensure_ascii=False, indent=2)) or 0)

    strategy = sub.add_parser("strategy", help="初期化前に販売ルートを確認")
    strategy.add_argument("--product", choices=PRODUCT_TYPES, required=True)
    strategy.add_argument("--goal", choices=GOALS, required=True)
    strategy.add_argument("--style", choices=["auto", *SALES_STYLES], default="auto")
    strategy.add_argument("--pages", type=int)
    strategy.add_argument("--pressure", choices=["soft", "balanced", "direct"])
    strategy.add_argument("--separate-decision-maker", action="store_true")
    strategy.set_defaults(func=command_strategy)

    init = sub.add_parser("init", help="新規ジョブを初期化")
    init.add_argument("job")
    init.add_argument("--title", required=True)
    init.add_argument("--product", choices=PRODUCT_TYPES, required=True)
    init.add_argument("--goal", choices=GOALS, required=True)
    init.add_argument("--style", choices=["auto", *SALES_STYLES], default="auto")
    init.add_argument("--pages", type=int)
    init.add_argument("--pressure", choices=["soft", "balanced", "direct"])
    init.add_argument("--separate-decision-maker", action="store_true")
    init.set_defaults(func=command_init)

    for name, help_text, func in (
        ("prompts", "画像生成ジョブを出力", command_prompts),
        ("status", "不足素材と検品状態を確認", command_status),
        ("validate", "原稿を厳格検査", command_validate),
        ("demo-assets", "E2E試験専用のダミー画像を生成", command_demo_assets),
        ("preview", "欠落画像をプレースホルダー表示して組版確認", command_preview),
    ):
        child = sub.add_parser(name, help=help_text)
        child.add_argument("job")
        child.set_defaults(func=func)

    finalize = sub.add_parser("finalize", help="作画・検品済みジョブを完成データへ変換")
    finalize.add_argument("job")
    finalize.add_argument("--allow-demo", action="store_true", help="自動試験だけで使用")
    finalize.set_defaults(func=command_finalize)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        return int(args.func(args))
    except (FileNotFoundError, FileExistsError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
