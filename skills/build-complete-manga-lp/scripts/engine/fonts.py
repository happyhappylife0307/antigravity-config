"""fonts.py — システムの日本語フォントを名前で解決する。

macOSは日本語フォントを /System/Library/AssetsV2/ 配下のハッシュ名ディレクトリに置く。
パスが更新で変わるので、絶対パスを直書きせずファイル名で探索してキャッシュする。

役割ごとの論理名（speech / emphasis / narration / heading）でフォントを引ける。
"""

from __future__ import annotations

import functools
import pathlib

# 探索するルート。上から順に見て最初に当たったものを使う。
SEARCH_ROOTS = [
    pathlib.Path.home() / "Library/Fonts",
    pathlib.Path("/Library/Fonts"),
    pathlib.Path("/System/Library/Fonts"),
    pathlib.Path("/System/Library/Fonts/Supplemental"),
    pathlib.Path("/System/Library/AssetsV2"),
    pathlib.Path("/usr/share/fonts"),
    pathlib.Path("/usr/local/share/fonts"),
    pathlib.Path("C:/Windows/Fonts"),
]

# 論理名 → 候補ファイル名（優先順）。先頭から順に探す。
# 追加フォント（源暎アンチック等）を ~/Library/Fonts に入れたら自動で拾う。
ROLES: dict[str, list[str]] = {
    # セリフ本文。漫画は本来アンチック体だが、無ければ丸ゴシックが最も近い印象になる
    "speech": [
        "GenEiAntiqueNv5-M.ttf",       # 源暎アンチック（任意インストール・最優先）
        "TsukushiBMaruGothic.ttc",      # 筑紫B丸ゴシック
        "TsukushiAMaruGothic.ttc",
        "Hiragino Sans GB.ttc",
        "NotoSansCJK-Regular.ttc",
        "NotoSansJP-Regular.ttf",
        "YuGothM.ttc",
    ],
    # 叫び・強調セリフ
    "emphasis": [
        "ToppanBunkyuMidashiGothicStdN-ExtraBold.otf",
        "TsukushiBMaruGothic.ttc",
        "Hiragino Sans GB.ttc",
        "NotoSansCJK-Bold.ttc",
        "NotoSansJP-Bold.ttf",
        "YuGothB.ttc",
    ],
    # ナレーション（枠外の説明）。明朝系が漫画の作法
    "narration": [
        "ToppanBunkyuMinchoPr6N-Regular.otf",
        "ToppanBunkyuMidashiMinchoStdN-ExtraBold.otf",
        "Hiragino Sans GB.ttc",
        "NotoSerifCJK-Regular.ttc",
        "NotoSerifJP-Regular.otf",
        "YuMincho.ttc",
    ],
    # LPの見出し
    "heading": [
        "ToppanBunkyuMidashiGothicStdN-ExtraBold.otf",
        "Hiragino Sans GB.ttc",
        "NotoSansCJK-Bold.ttc",
        "NotoSansJP-Bold.ttf",
        "YuGothB.ttc",
    ],
    # 手書き風（心の声・回想）
    "handwrite": [
        "Klee.ttc",
        "TsukushiBMaruGothic.ttc",
        "Hiragino Sans GB.ttc",
        "NotoSansCJK-Regular.ttc",
        "NotoSansJP-Regular.ttf",
        "YuGothM.ttc",
    ],
}

# .ttc（コレクション）は複数フォントを内包する。役割ごとに使いたい index を指定。
TTC_INDEX: dict[str, int] = {
    "TsukushiBMaruGothic.ttc": 0,
    "TsukushiAMaruGothic.ttc": 0,
    "Hiragino Sans GB.ttc": 0,
    "Klee.ttc": 1,  # Klee Medium
}


@functools.lru_cache(maxsize=None)
def _index_fonts() -> dict[str, str]:
    """システム上のフォントファイルを {ファイル名: 絶対パス} で1度だけ索引する。"""
    found: dict[str, str] = {}
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        # AssetsV2 は深いので rglob、それ以外は浅いので glob
        pattern = "**/*" if "AssetsV2" in str(root) else "*"
        try:
            for p in root.glob(pattern):
                if p.suffix.lower() in (".ttf", ".otf", ".ttc") and p.name not in found:
                    found[p.name] = str(p)
        except (PermissionError, OSError):
            continue
    return found


@functools.lru_cache(maxsize=None)
def resolve(role: str) -> tuple[str, int]:
    """論理名 → (フォント絶対パス, ttcインデックス)。

    見つからなければ RuntimeError。黙って英字フォントに落ちると
    日本語が豆腐（□）になるので、失敗は失敗として上げる。
    """
    if role not in ROLES:
        raise KeyError(f"未知のフォント役割: {role}（有効: {list(ROLES)}）")
    index = _index_fonts()
    for filename in ROLES[role]:
        if filename in index:
            return index[filename], TTC_INDEX.get(filename, 0)
    raise RuntimeError(
        f"役割 '{role}' に使えるフォントが1つも見つからんかった。候補: {ROLES[role]}"
    )


def load(role: str, size: int):
    """PIL の FreeTypeFont を返す。"""
    from PIL import ImageFont

    path, idx = resolve(role)
    return ImageFont.truetype(path, size=size, index=idx)


def report() -> str:
    """どの役割にどのフォントが割り当たったかを人間可読で返す（検証用）。"""
    lines = []
    for role in ROLES:
        try:
            path, idx = resolve(role)
            lines.append(f"  {role:10s} → {pathlib.Path(path).name} (index={idx})")
        except RuntimeError as e:
            lines.append(f"  {role:10s} → ✗ {e}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(f"索引したフォント数: {len(_index_fonts())}")
    print("役割の割り当て:")
    print(report())

    # 実際に日本語が描けるか、豆腐にならないかを画素で検証する
    from PIL import Image, ImageDraw

    probe = "あア亜｜「」…—①"
    print("\n描画テスト（豆腐チェック）:")
    for role in ROLES:
        try:
            font = load(role, 48)
            img = Image.new("L", (700, 80), 255)
            ImageDraw.Draw(img).text((5, 5), probe, font=font, fill=0)
            inked = sum(1 for px in img.getdata() if px < 128)
            # 豆腐（□）は輪郭だけなので墨量が極端に少ない。文字が出ていれば数千px以上になる
            verdict = "OK" if inked > 1500 else f"疑わしい(墨量{inked})"
            print(f"  {role:10s} 墨量={inked:6d}  {verdict}")
        except Exception as e:  # noqa: BLE001
            print(f"  {role:10s} ✗ {e}")
