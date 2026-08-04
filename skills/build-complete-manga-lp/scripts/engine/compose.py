"""compose.py — コマ画像に吹き出しとセリフを焼き込む。

設計の要:
  座標はすべて「コマの幅・高さに対する比率(0.0〜1.0)」で持つ。
  こうしておくと、PNG合成でもHTML出力でも同じ数値がそのまま使えて、
  両方の見た目がズレない。原稿JSONが唯一の正になる。

吹き出しの種類:
  speech    … 楕円＋しっぽ（通常のセリフ）
  shout     … トゲトゲ＋しっぽ（叫び・強調）
  thought   … 雲＋泡のしっぽ（心の声）
  narration … 角丸長方形・しっぽ無し（ナレーション/枠外）
"""

from __future__ import annotations

import math
import pathlib

from PIL import Image, ImageDraw

try:
    from . import fonts
except ImportError:  # direct script execution
    import fonts

# 描画の滑らかさ。この倍率で描いてから縮小してアンチエイリアスをかける
SUPERSAMPLE = 3

# 行頭に来てはいけない文字（ぶら下げずに前行へ送る）
NO_LINE_START = "、。，．・：；？！ゝゞ々ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ）〕］｝〉》」』】〟’”»ー～"
# 行末に来てはいけない文字（次行へ送る）
NO_LINE_END = "（〔［｛〈《「『【〝‘“«"


# --------------------------------------------------------------------------
# テキスト整形
# --------------------------------------------------------------------------

def wrap_japanese(text: str, font, max_width: int) -> list[str]:
    """日本語を max_width(px) に収まるよう折り返す。簡易禁則処理つき。

    日本語は単語区切りが無いので、1文字ずつ積んで幅を見る。
    原稿側に改行(\\n)があればそれは強制改行として尊重する。
    """
    lines: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        current = ""
        for ch in paragraph:
            trial = current + ch
            width = font.getbbox(trial)[2] - font.getbbox(trial)[0]
            if width <= max_width or not current:
                current += ch
            else:
                # 折り返す直前に禁則を見る
                if ch in NO_LINE_START:
                    # 句読点などは行頭に置けない → 無理やり前行に押し込む
                    current += ch
                    lines.append(current)
                    current = ""
                elif current and current[-1] in NO_LINE_END:
                    # 開き括弧が行末に来た → 次行へ一緒に送る
                    lines.append(current[:-1])
                    current = current[-1] + ch
                else:
                    lines.append(current)
                    current = ch
        if current:
            lines.append(current)
    return lines


def balanced_wrap(text: str, font, max_width: int) -> list[str]:
    """吹き出し向けの折り返し。max_width まで目一杯詰めず、縦横比を整える。

    漫画の吹き出しは横長の帯ではなく、正円〜やや縦長の塊になる。
    1行に詰め込むと「LINEのスクショ」みたいになって漫画に見えないので、
    文字数から目標行数を決めて、その行数に割れる幅で折り返す。
    原稿に明示の改行があるときは作者の意図を優先してそのまま従う。
    """
    if "\n" in text:
        return wrap_japanese(text, font, max_width)

    n = len(text)
    if n <= 6:
        target = 1
    elif n <= 14:
        target = 2
    elif n <= 30:
        target = 3
    else:
        target = 4

    bbox = font.getbbox(text)
    full_w = bbox[2] - bbox[0]
    ideal = int(full_w / target * 1.10)          # 1割の遊びを持たせて割り切れやすくする
    width = max(min(ideal, max_width), int(font.size * 2.2))
    return wrap_japanese(text, font, width)


def measure(lines: list[str], font, line_spacing: float) -> tuple[int, int]:
    """折り返し済みの行群が占める (幅, 高さ) を px で返す。"""
    if not lines:
        return (0, 0)
    widths = [font.getbbox(ln)[2] - font.getbbox(ln)[0] for ln in lines if ln]
    ascent, descent = font.getmetrics()
    line_h = int((ascent + descent) * line_spacing)
    return (max(widths) if widths else 0, line_h * len(lines))


# --------------------------------------------------------------------------
# 吹き出しの形
# --------------------------------------------------------------------------

def _spiky_polygon(cx: float, cy: float, rx: float, ry: float, spikes: int = 18) -> list[tuple[float, float]]:
    """叫び用のトゲトゲ楕円。外側と内側の半径を交互に打つ。"""
    points = []
    for i in range(spikes * 2):
        angle = math.pi * i / spikes
        scale = 1.0 if i % 2 == 0 else 0.78
        points.append((cx + math.cos(angle) * rx * scale,
                       cy + math.sin(angle) * ry * scale))
    return points


def _tail_polygon(cx: float, cy: float, rx: float, ry: float,
                  tx: float, ty: float, width_rad: float = 0.16) -> list[tuple[float, float]]:
    """吹き出し本体から話者(tx,ty)へ伸びるしっぽ（三角形）。

    指定された話者位置が遠すぎると、しっぽが画面を横切る巨大な三角形になって
    絵を潰す。実際の漫画のしっぽは吹き出し半径の1倍程度までなので、
    「方向は話者を向くが、長さは頭打ちにする」という挙動にしてある。
    """
    angle = math.atan2(ty - cy, tx - cx)

    # 中心から楕円周までの距離（この方向における実効半径）
    edge = math.hypot(math.cos(angle) * rx, math.sin(angle) * ry)
    dist = math.hypot(tx - cx, ty - cy)
    max_len = edge + max(rx, ry) * 0.95          # 縁から伸ばしてよい上限
    tip_dist = min(dist, max_len)
    tipx, tipy = cx + math.cos(angle) * tip_dist, cy + math.sin(angle) * tip_dist

    a1, a2 = angle - width_rad, angle + width_rad
    return [
        (cx + math.cos(a1) * rx, cy + math.sin(a1) * ry),
        (tipx, tipy),
        (cx + math.cos(a2) * rx, cy + math.sin(a2) * ry),
    ]


def draw_bubble(draw: ImageDraw.ImageDraw, style: str,
                box: tuple[float, float, float, float],
                tail: tuple[float, float] | None,
                outline_w: int) -> None:
    """吹き出しの図形だけを描く（テキストは別）。box は (x0,y0,x1,y1)。"""
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    rx, ry = (x1 - x0) / 2, (y1 - y0) / 2
    fill, line = (255, 255, 255, 255), (0, 0, 0, 255)

    # しっぽを先に描く（本体の輪郭線で付け根を隠すため）
    if tail is not None and style != "narration":
        if style == "thought":
            # 泡3つで思考のしっぽを表現。本体にめり込まないよう「縁の外」から始める
            tx, ty = tail
            angle = math.atan2(ty - cy, tx - cx)
            edge = math.hypot(math.cos(angle) * rx, math.sin(angle) * ry)
            dist = min(math.hypot(tx - cx, ty - cy), edge + max(rx, ry) * 1.05)
            for i, frac in enumerate((0.30, 0.62, 0.92)):
                d = edge + (dist - edge) * frac
                bx, by = cx + math.cos(angle) * d, cy + math.sin(angle) * d
                r = max(2.0, min(rx, ry) * 0.22 * (1 - i * 0.30))
                draw.ellipse((bx - r, by - r, bx + r, by + r), fill=fill, outline=line, width=outline_w)
        else:
            draw.polygon(_tail_polygon(cx, cy, rx, ry, *tail), fill=fill, outline=line)

    # 本体
    if style == "shout":
        draw.polygon(_spiky_polygon(cx, cy, rx, ry), fill=fill, outline=line)
    elif style == "narration":
        radius = min(rx, ry) * 0.22
        draw.rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=fill, outline=line, width=outline_w)
    elif style == "thought":
        # 雲：本体の楕円のまわりに丸を並べる
        draw.ellipse((x0, y0, x1, y1), fill=fill)
        for i in range(14):
            a = 2 * math.pi * i / 14
            bx, by = cx + math.cos(a) * rx * 0.92, cy + math.sin(a) * ry * 0.92
            r = min(rx, ry) * 0.30
            draw.ellipse((bx - r, by - r, bx + r, by + r), fill=fill, outline=line, width=outline_w)
        draw.ellipse((x0, y0, x1, y1), fill=fill)  # 内側の線を消す
    else:  # speech
        draw.ellipse((x0, y0, x1, y1), fill=fill, outline=line, width=outline_w)

    # しっぽの付け根の線を消して、輪郭を描き直す
    if style == "speech" and tail is not None:
        draw.ellipse((x0, y0, x1, y1), fill=fill)
        draw.ellipse((x0, y0, x1, y1), outline=line, width=outline_w)


# --------------------------------------------------------------------------
# 吹き出しのレイアウト計算（PNG経路とHTML/SVG経路で共有する）
# --------------------------------------------------------------------------

def layout_bubble(b: dict, w: int, h: int) -> dict:
    """吹き出し1つ分の確定した幾何情報を返す。

    **PNG合成もHTML出力も必ずこの関数を通す。**
    ここを共有していないと「PNGでは2行、HTMLでは3行」のように
    2つの出力が別物になる。原稿JSONを唯一の正にするための要。
    """
    style = b.get("style", "speech")
    font_px = max(10, int(h * b.get("font_size", 0.040)))
    role = "emphasis" if style == "shout" else ("narration" if style == "narration" else "speech")
    font = fonts.load(b.get("font", role), font_px)
    line_spacing = b.get("line_spacing", 1.25)

    wrapper = wrap_japanese if style == "narration" else balanced_wrap
    lines = wrapper(b["text"], font, int(w * b.get("max_w", 0.38)))
    tw, th = measure(lines, font, line_spacing)

    if style == "shout":
        pad_x, pad_y = 1.95, 2.20
    elif style in ("speech", "thought"):
        pad_x, pad_y = 1.50, 1.70
    else:
        pad_x, pad_y = 1.18, 1.35

    bw, bh = tw * pad_x, th * pad_y
    cx, cy = w * b["x"], h * b["y"]
    box = (cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2)
    tail = (w * b["tail"][0], h * b["tail"][1]) if b.get("tail") else None

    return {
        "style": style, "font": font, "font_px": font_px, "lines": lines,
        "text_w": tw, "text_h": th, "line_spacing": line_spacing,
        "box": box, "cx": cx, "cy": cy, "tail": tail,
        "outline_w": max(1, int(h * 0.004)),
    }


# --------------------------------------------------------------------------
# コマ1枚の合成
# --------------------------------------------------------------------------

def compose_panel(image_path: str | pathlib.Path | None,
                  bubbles: list[dict],
                  size: tuple[int, int],
                  placeholder_label: str = "") -> Image.Image:
    """コマ画像に吹き出し群を焼き込んで返す。

    image_path が None または存在しない場合は、グレーのプレースホルダを描く。
    絵がまだ無くても組版を検証できるようにするため（設計上わざとそうしている）。
    """
    w, h = size
    if image_path and pathlib.Path(image_path).exists():
        base = Image.open(image_path).convert("RGBA")
        # アスペクトを保ったまま中央でクロップして枠に合わせる
        scale = max(w / base.width, h / base.height)
        base = base.resize((max(1, int(base.width * scale)), max(1, int(base.height * scale))), Image.LANCZOS)
        left, top = (base.width - w) // 2, (base.height - h) // 2
        base = base.crop((left, top, left + w, top + h))
    else:
        base = Image.new("RGBA", (w, h), (228, 228, 232, 255))
        d = ImageDraw.Draw(base)
        d.rectangle((0, 0, w - 1, h - 1), outline=(150, 150, 158, 255), width=3)
        d.line((0, 0, w, h), fill=(205, 205, 212, 255), width=2)
        d.line((0, h, w, 0), fill=(205, 205, 212, 255), width=2)
        if placeholder_label:
            f = fonts.load("narration", max(14, int(h * 0.035)))
            lines = wrap_japanese(placeholder_label, f, int(w * 0.8))
            tw, th = measure(lines, f, 1.4)
            y = (h - th) / 2
            ascent, descent = f.getmetrics()
            for ln in lines:
                lw = f.getbbox(ln)[2] - f.getbbox(ln)[0]
                d.text(((w - lw) / 2, y), ln, font=f, fill=(110, 110, 120, 255))
                y += (ascent + descent) * 1.4

    # 吹き出しは高解像度レイヤに描いてから縮小（線を滑らかに）
    s = SUPERSAMPLE
    layer = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    text_jobs = []  # テキストは等倍で描く（縮小でボケるのを避ける）

    for b in bubbles:
        L = layout_bubble(b, w, h)
        draw_bubble(
            ld, L["style"],
            tuple(v * s for v in L["box"]),
            tuple(v * s for v in L["tail"]) if L["tail"] else None,
            L["outline_w"] * s,
        )
        text_jobs.append((L["lines"], L["font"], L["cx"], L["cy"],
                          L["text_h"], L["line_spacing"], L["style"]))

    layer = layer.resize((w, h), Image.LANCZOS)
    base.alpha_composite(layer)

    # テキストを等倍で描画（中央揃え）
    bd = ImageDraw.Draw(base)
    for lines, font, cx, cy, th, line_spacing, style in text_jobs:
        ascent, descent = font.getmetrics()
        line_h = (ascent + descent) * line_spacing
        y = cy - th / 2
        for ln in lines:
            if not ln:
                y += line_h
                continue
            bbox = font.getbbox(ln)
            lw = bbox[2] - bbox[0]
            bd.text((cx - lw / 2 - bbox[0], y), ln, font=font, fill=(20, 20, 24, 255))
            y += line_h

    return base


# --------------------------------------------------------------------------
# SVG出力（HTML経路。PNGとまったく同じ layout_bubble の数値を使う）
# --------------------------------------------------------------------------

def bubble_svg(L: dict) -> str:
    """吹き出しの図形をSVG要素の文字列として返す（テキストは含まない）。

    CSSのclip-pathや擬似要素で吹き出しを描くとPNG版と形が合わなくなる。
    描画順（しっぽ→本体）もPillow版と揃えてあるので、
    しっぽの付け根が本体の白で隠れるところまで同じ絵になる。
    """
    style, (x0, y0, x1, y1) = L["style"], L["box"]
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    rx, ry = (x1 - x0) / 2, (y1 - y0) / 2
    sw = L["outline_w"]
    stroke = f'fill="#fff" stroke="#111" stroke-width="{sw}"'
    out: list[str] = []

    if L["tail"] and style != "narration":
        tx, ty = L["tail"]
        if style == "thought":
            angle = math.atan2(ty - cy, tx - cx)
            edge = math.hypot(math.cos(angle) * rx, math.sin(angle) * ry)
            dist = min(math.hypot(tx - cx, ty - cy), edge + max(rx, ry) * 1.05)
            for i, frac in enumerate((0.30, 0.62, 0.92)):
                d = edge + (dist - edge) * frac
                bx, by = cx + math.cos(angle) * d, cy + math.sin(angle) * d
                r = max(2.0, min(rx, ry) * 0.22 * (1 - i * 0.30))
                out.append(f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="{r:.1f}" {stroke}/>')
        else:
            pts = " ".join(f"{px:.1f},{py:.1f}" for px, py in
                           _tail_polygon(cx, cy, rx, ry, tx, ty))
            out.append(f'<polygon points="{pts}" {stroke}/>')

    if style == "shout":
        pts = " ".join(f"{px:.1f},{py:.1f}" for px, py in _spiky_polygon(cx, cy, rx, ry))
        out.append(f'<polygon points="{pts}" {stroke}/>')
    elif style == "narration":
        r = min(rx, ry) * 0.22
        out.append(f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{2*rx:.1f}" height="{2*ry:.1f}" '
                   f'rx="{r:.1f}" {stroke}/>')
    elif style == "thought":
        for i in range(14):
            a = 2 * math.pi * i / 14
            bx, by = cx + math.cos(a) * rx * 0.92, cy + math.sin(a) * ry * 0.92
            r = min(rx, ry) * 0.30
            out.append(f'<circle cx="{bx:.1f}" cy="{by:.1f}" r="{r:.1f}" {stroke}/>')
        out.append(f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" fill="#fff"/>')
    else:  # speech
        out.append(f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" rx="{rx:.1f}" ry="{ry:.1f}" {stroke}/>')

    return "".join(out)


def frame_panel(panel: Image.Image, border: int = 4, margin: int = 0) -> Image.Image:
    """コマ枠（黒フチ）を付ける。"""
    w, h = panel.size
    out = Image.new("RGBA", (w + (border + margin) * 2, h + (border + margin) * 2), (255, 255, 255, 255))
    out.paste(panel, (border + margin, border + margin))
    ImageDraw.Draw(out).rectangle(
        (margin, margin, out.width - margin - 1, out.height - margin - 1),
        outline=(0, 0, 0, 255), width=border,
    )
    return out
