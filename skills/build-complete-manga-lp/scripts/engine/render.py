"""作画済みパネルを、漫画ページ・縦長LP・SNSカードへ組版する。"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import pathlib
from collections import defaultdict

from PIL import Image, ImageDraw

try:
    from .compose import compose_panel, frame_panel
    from . import fonts
except ImportError:  # direct script execution
    from compose import compose_panel, frame_panel
    import fonts


def safe_path(root: pathlib.Path, relative: str, *, must_exist: bool = False) -> pathlib.Path:
    """ジョブ外への読み書きを拒否して相対パスを解決する。"""
    if not relative:
        raise ValueError("空の相対パスは使えません")
    rel = pathlib.Path(relative)
    if rel.is_absolute():
        raise ValueError(f"絶対パスは禁止です: {relative}")
    root = root.resolve()
    resolved = (root / rel).resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"ジョブ外のパスは禁止です: {relative}")
    if must_exist and not resolved.is_file():
        raise FileNotFoundError(relative)
    return resolved


def _save(image: Image.Image, path: pathlib.Path) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(path, "PNG", optimize=True)
    return path


def _canvas(script: dict) -> tuple[int, int]:
    canvas = script.get("meta", {}).get("canvas", {})
    return int(canvas.get("width", 1200)), int(canvas.get("panel_height", 760))


def render_pages(script: dict, job_root: pathlib.Path, *, placeholders: bool = False) -> list[pathlib.Path]:
    """page番号ごとにパネルを縦積みした漫画ページPNGを作る。"""
    width, panel_height = _canvas(script)
    grouped: dict[int, list[dict]] = defaultdict(list)
    for panel in script.get("panels", []):
        grouped[int(panel.get("page", panel.get("n", 1)))].append(panel)

    outputs: list[pathlib.Path] = []
    for page_no in sorted(grouped):
        rendered: list[Image.Image] = []
        for panel in sorted(grouped[page_no], key=lambda item: int(item.get("n", 0))):
            image_rel = panel.get("image") or f"assets/panels/p{int(panel['n']):03d}.png"
            image_path = safe_path(job_root, image_rel)
            if not image_path.is_file() and not placeholders:
                raise FileNotFoundError(f"作画画像がありません: {image_rel}")
            composed = compose_panel(
                image_path if image_path.is_file() else None,
                panel.get("bubbles", []),
                (width, panel_height),
                placeholder_label=f"DEMO / PANEL {panel.get('n')}",
            )
            rendered.append(frame_panel(composed, border=max(2, width // 300)))

        gap = max(6, width // 100)
        page_h = sum(image.height for image in rendered) + gap * (len(rendered) + 1)
        page = Image.new("RGB", (rendered[0].width + gap * 2, page_h), "white")
        y = gap
        for image in rendered:
            page.paste(image.convert("RGB"), (gap, y))
            y += image.height + gap
        outputs.append(_save(page, job_root / "output" / "pages" / f"page_{page_no:02d}.png"))
    return outputs


def render_vertical(page_paths: list[pathlib.Path], target: pathlib.Path) -> pathlib.Path:
    pages = [Image.open(path).convert("RGB") for path in page_paths]
    gap = max(10, pages[0].width // 50)
    width = max(page.width for page in pages)
    height = sum(page.height for page in pages) + gap * (len(pages) - 1)
    output = Image.new("RGB", (width, height), "white")
    y = 0
    for page in pages:
        output.paste(page, ((width - page.width) // 2, y))
        y += page.height + gap
    return _save(output, target)


def render_social_cards(page_paths: list[pathlib.Path], output_dir: pathlib.Path) -> list[pathlib.Path]:
    """ページを切り抜かず、正方形へレターボックスして保存する。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[pathlib.Path] = []
    side = 1200
    for index, path in enumerate(page_paths, 1):
        source = Image.open(path).convert("RGB")
        scale = min((side - 80) / source.width, (side - 80) / source.height)
        resized = source.resize((max(1, int(source.width * scale)), max(1, int(source.height * scale))), Image.LANCZOS)
        card = Image.new("RGB", (side, side), (246, 247, 251))
        card.paste(resized, ((side - resized.width) // 2, (side - resized.height) // 2))
        outputs.append(_save(card, output_dir / f"card_{index:02d}.png"))
    return outputs


def _data_uri(path: pathlib.Path) -> str:
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


def render_html(script: dict, page_paths: list[pathlib.Path], target: pathlib.Path) -> pathlib.Path:
    """外部画像参照のない、単体で開けるLP HTMLを作る。"""
    meta = script.get("meta", {})
    title = html.escape(meta.get("title", "漫画LP"))
    cta = script.get("cta", {})
    label = html.escape(cta.get("label", "詳しく見る"))
    url = html.escape(cta.get("url", "#"), quote=True)
    offer = meta.get("offer", {})
    deadline = html.escape(offer.get("deadline", ""))
    notes = [html.escape(str(item)) for item in meta.get("legal_notes", [])]
    images = "\n".join(
        f'<img src="{_data_uri(path)}" alt="{title} {index}ページ目">'
        for index, path in enumerate(page_paths, 1)
    )
    deadline_html = f'<p class="deadline">{deadline}</p>' if deadline else ""
    notes_html = "".join(f"<li>{note}</li>" for note in notes)
    document = f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#eef1f7;color:#161923;font-family:-apple-system,BlinkMacSystemFont,"Noto Sans JP",sans-serif}}
main{{max-width:820px;margin:auto;background:#fff;box-shadow:0 0 32px #cad0de}}img{{display:block;width:100%;height:auto}}
.action{{padding:28px 20px 36px;text-align:center;background:#101b42;color:white;position:relative}}.action a{{display:inline-block;background:#ffcf33;color:#111;text-decoration:none;font-weight:800;font-size:1.15rem;padding:16px 28px;border-radius:999px;box-shadow:0 5px 0 #c89500}}
.deadline{{font-weight:700}}.legal{{font-size:.76rem;text-align:left;opacity:.82;max-width:680px;margin:18px auto 0}}
</style></head><body><main>{images}<section class="action"><a href="{url}">{label}</a>{deadline_html}<ul class="legal">{notes_html}</ul></section></main></body></html>"""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(document, encoding="utf-8")
    return target


def render_outputs(script: dict, job_root: pathlib.Path, *, placeholders: bool = False) -> dict[str, list[str] | str]:
    page_paths = render_pages(script, job_root, placeholders=placeholders)
    vertical = render_vertical(page_paths, job_root / "output" / "note_vertical.png")
    cards = render_social_cards(page_paths, job_root / "output" / "social")
    html_path = render_html(script, page_paths, job_root / "output" / "lp.html")
    return {
        "pages": [str(path.relative_to(job_root)) for path in page_paths],
        "vertical": str(vertical.relative_to(job_root)),
        "social": [str(path.relative_to(job_root)) for path in cards],
        "html": str(html_path.relative_to(job_root)),
    }


def file_manifest(job_root: pathlib.Path, paths: list[pathlib.Path]) -> list[dict]:
    records = []
    for path in sorted(paths):
        data = path.read_bytes()
        records.append({
            "path": str(path.relative_to(job_root)),
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        })
    return records


def write_manifest(job_root: pathlib.Path, outputs: dict, *, demo: bool) -> pathlib.Path:
    paths = [path for path in (job_root / "output").rglob("*") if path.is_file()]
    source_paths = [job_root / "brief.json", job_root / "script.json", job_root / "reports" / "audit.json"]
    source_paths.extend(path for path in (job_root / "assets").rglob("*") if path.is_file())
    source_paths = [path for path in source_paths if path.is_file()]
    payload = {
        "demo": demo,
        "outputs": outputs,
        "source_files": file_manifest(job_root, source_paths),
        "files": file_manifest(job_root, paths),
    }
    target = job_root / "reports" / "manifest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target
