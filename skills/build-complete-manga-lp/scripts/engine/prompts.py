"""画像生成ジョブと、人間向けプロンプト集を原稿JSONから作る。"""

from __future__ import annotations

import json
import pathlib


NEGATIVE = (
    "画像内に文字、数字、セリフ、吹き出し、ロゴ、透かしを描かない。"
    "文字は後工程で正確に合成する。第三者の企業名、商品・サービス名、ロゴ、既存キャラクター、特徴的な画面や意匠を描かない。"
)


def aspect_label(width: int, height: int) -> str:
    common = [("1:1", 1.0), ("4:3", 4 / 3), ("3:2", 1.5), ("16:9", 16 / 9),
              ("3:4", 0.75), ("2:3", 2 / 3), ("9:16", 9 / 16)]
    target = width / height
    return min(common, key=lambda item: abs(item[1] - target))[0]


def character_prompt(key: str, character: dict, style: str, *, expression: bool = False) -> str:
    layout = (
        "白背景に同一人物を8つ。胸から上の表情6種（平常、疑う、困る、驚く、決意、ひらめき）と、"
        "商品または主要小道具を扱う手元2種。全カットで顔、髪型、服装、体型、小道具を一致させる。"
        if expression else
        "白背景に同一人物を6つ。全身の正面、斜め45度、横向きと、胸から上の平常、困る、驚く。"
        "全カットで顔、髪型、服装、体型を一致させる。"
    )
    return "\n".join([
        style,
        "日本の広告漫画で繰り返し使うキャラクター設定シート。",
        f"人物: {character.get('name', key)}",
        character.get("prompt", ""),
        layout,
        NEGATIVE,
    ])


def action_prompt(key: str, character: dict, style: str) -> str:
    return "\n".join([
        style,
        "日本の広告漫画で繰り返し使うキャラクター動作設定シート。",
        f"人物: {character.get('name', key)}",
        character.get("prompt", ""),
        "白背景に同一人物を6つ。商品や主要小道具を持つ、見る、使う、驚く、成功する、CTAを示す。",
        "全カットで顔、髪型、服装、体型、小道具の形と色を一致させる。",
        NEGATIVE,
    ])


def panel_prompt(panel: dict, script: dict, aspect: str) -> str:
    meta = script["meta"]
    lines = [
        meta.get("style_prompt", "フルカラーの日本の広告漫画"),
        f"縦横比: {aspect}",
        f"場面: {panel.get('art', '')}",
    ]
    characters = script.get("characters", {})
    names: list[str] = []
    for key in panel.get("characters", []):
        character = characters.get(key, {})
        names.append(character.get("name", key))
        lines.append(f"登場人物 {character.get('name', key)}: {character.get('prompt', '')}")
    if names:
        lines.append("添付した設定シートと顔、髪、服、体型、小道具を一致させる。")
    areas = [f"({bubble['x']:.2f},{bubble['y']:.2f})" for bubble in panel.get("bubbles", [])]
    if areas:
        lines.append("後から吹き出しを置くため、次の座標付近は顔や重要物を避ける: " + ", ".join(areas))
    lines.append("人物がいる場合は表情が読める顔を最低1つ明確に描く。")
    lines.append(NEGATIVE)
    return "\n".join(lines)


def build_jobs(script: dict) -> list[dict]:
    canvas = script.get("meta", {}).get("canvas", {})
    aspect = aspect_label(int(canvas.get("width", 1200)), int(canvas.get("panel_height", 760)))
    style = script.get("meta", {}).get("style_prompt", "フルカラーの日本の広告漫画")
    jobs: list[dict] = []

    for key, character in script.get("characters", {}).items():
        ref = character.get("ref", f"assets/characters/{key}.png")
        jobs.append({
            "id": f"character-{key}", "kind": "character", "target": ref,
            "references": [], "aspect_ratio": "3:2",
            "prompt": character_prompt(key, character, style),
        })
        if character.get("expression_ref"):
            jobs.append({
                "id": f"expression-{key}", "kind": "expression",
                "target": character["expression_ref"], "references": [ref],
                "aspect_ratio": "3:2",
                "prompt": character_prompt(key, character, style, expression=True),
            })
        if character.get("action_ref"):
            jobs.append({
                "id": f"action-{key}", "kind": "action",
                "target": character["action_ref"], "references": [ref],
                "aspect_ratio": "3:2",
                "prompt": action_prompt(key, character, style),
            })

    for panel in script.get("panels", []):
        refs: list[str] = []
        for key in panel.get("characters", []):
            character = script.get("characters", {}).get(key, {})
            if character.get("ref"):
                refs.append(character["ref"])
            if character.get("expression_ref"):
                refs.append(character["expression_ref"])
            if character.get("action_ref"):
                refs.append(character["action_ref"])
        target = panel.get("image") or f"assets/panels/p{panel['n']:03d}.png"
        jobs.append({
            "id": f"panel-{panel['n']:03d}", "kind": "panel", "target": target,
            "references": list(dict.fromkeys(refs)), "aspect_ratio": aspect,
            "prompt": panel_prompt(panel, script, aspect),
        })
    return jobs


def build_markdown(script: dict, jobs: list[dict]) -> str:
    title = script.get("meta", {}).get("title", "漫画LP")
    lines = [f"# {title} — 画像生成ジョブ", "", "上から順に生成し、指定の保存先へ置く。", ""]
    for index, job in enumerate(jobs, 1):
        refs = "、".join(f"`{ref}`" for ref in job["references"]) or "なし"
        lines.extend([
            f"## {index}. {job['id']}",
            f"- 種別: `{job['kind']}`",
            f"- 参照: {refs}",
            f"- 保存先: `{job['target']}`",
            f"- 比率: `{job['aspect_ratio']}`",
            "",
            "```text",
            job["prompt"],
            "```",
            "",
        ])
    return "\n".join(lines)


def write_job_files(script: dict, job_root: pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
    reports = job_root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    jobs = build_jobs(script)
    manifest = reports / "image_jobs.json"
    guide = reports / "image_jobs.md"
    manifest.write_text(json.dumps({"jobs": jobs}, ensure_ascii=False, indent=2), encoding="utf-8")
    guide.write_text(build_markdown(script, jobs), encoding="utf-8")
    return manifest, guide
