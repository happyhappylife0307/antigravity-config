"""商品・目的・販売スタイルを独立して選ぶ漫画LPルーター。"""

from __future__ import annotations

import argparse
import json


PRODUCT_TYPES = {
    "story_ip": {"label": "物語作品", "proof": "作品の一場面・感情体験・次の謎"},
    "knowledge": {"label": "本・教材・講座", "proof": "中身・手順・ワーク・小さな理解"},
    "service": {"label": "伴走・サブスク", "proof": "利用過程・支援・複数日の変化"},
    "tool": {"label": "アプリ・業務ツール", "proof": "画面・操作・出力"},
    "physical": {"label": "道具・機器・物販", "proof": "実物・使用・比較・細部"},
}

GOALS = {
    "awareness": {
        "label": "認知・共感", "pages": [6, 8], "proof_loops": 0,
        "product_by": None, "ending": "小さな気づきと余韻",
        "cta": "詳細を見る・フォローする", "pressure": "soft",
    },
    "trial": {
        "label": "試し読み・無料導線・比較", "pages": [8, 12], "proof_loops": 1,
        "product_by": 0.35, "ending": "小さな成功",
        "cta": "試し読み・無料版・資料請求", "pressure": "balanced",
    },
    "conversion": {
        "label": "購入・申込", "pages": [9, 20], "proof_loops": 2,
        "product_by": 0.30, "ending": "冒頭を同じ象徴で反転する達成",
        "cta": "購入する・申し込む", "pressure": "direct",
    },
}

SALES_STYLES = {
    "recommendation": {
        "label": "推薦型",
        "beats": ["hook", "empathy", "recommendation", "product_reveal", "proof", "payoff", "cta"],
    },
    "testimonial": {
        "label": "体験談型",
        "beats": ["hook", "empathy", "failed_attempt", "product_reveal", "experience", "proof", "payoff", "cta"],
    },
    "developer": {
        "label": "開発者プレゼン型",
        "beats": ["hook", "problem", "product_reveal", "demo", "proof", "objection", "payoff", "cta"],
    },
    "story_intro": {
        "label": "作品紹介型",
        "beats": ["hook", "reader_empathy", "world", "character", "scene", "next_mystery", "cta"],
    },
    "story_experience": {
        "label": "作品体験型",
        "beats": ["hook", "crisis", "mechanism", "proof", "payoff", "next_mystery", "cta"],
    },
    "insight": {
        "label": "気づき型",
        "beats": ["hook", "common_belief", "contradiction", "insight", "example", "payoff", "cta"],
    },
    "documentary": {
        "label": "密着型",
        "beats": ["hook", "before", "day_one", "support", "progress", "proof", "after", "cta"],
    },
    "desire": {
        "label": "欲望回収型",
        "beats": ["hook", "desired_future", "barrier", "product_reveal", "experience", "proof", "bright_future", "cta"],
    },
    "achievement_journey": {
        "label": "成長実感型",
        "beats": [
            "hook", "problem", "peer_prompt", "decision_maker_pitch",
            "product_reveal", "experience", "proof", "visible_success",
            "bright_future", "cta",
        ],
    },
}

AUTO_ROUTES = {
    "story_ip": {
        "awareness": ("story_intro", []),
        "trial": ("story_intro", ["recommendation"]),
        "conversion": ("story_experience", ["desire"]),
    },
    "knowledge": {
        "awareness": ("insight", []),
        "trial": ("testimonial", []),
        "conversion": ("testimonial", ["desire"]),
    },
    "service": {
        "awareness": ("documentary", []),
        "trial": ("documentary", ["testimonial"]),
        "conversion": ("desire", ["objection"]),
    },
    "tool": {
        "awareness": ("insight", []),
        "trial": ("developer", []),
        "conversion": ("developer", ["proof_stack"]),
    },
    "physical": {
        "awareness": ("recommendation", []),
        "trial": ("testimonial", []),
        "conversion": ("desire", []),
    },
}

STYLE_COMPATIBILITY = {
    "achievement_journey": set(PRODUCT_TYPES),
    "story_intro": {"story_ip"},
    "story_experience": {"story_ip"},
    "developer": {"tool", "knowledge", "service"},
}


def route_candidates(product_type: str, goal: str, primary: str, decision_maker_separate: bool) -> list[dict]:
    """制作前に提示するスイッチ候補。主案を含む最大3案を理由つきで返す。"""
    alternatives = {
        "story_ip": ["story_experience", "story_intro", "desire"],
        "knowledge": ["testimonial", "insight", "desire"],
        "service": ["desire", "documentary", "testimonial"],
        "tool": ["developer", "testimonial", "desire"],
        "physical": ["desire", "testimonial", "recommendation"],
    }[product_type]
    if decision_maker_separate and goal == "conversion":
        alternatives = ["achievement_journey", *alternatives]
    ordered = []
    for style in [primary, *alternatives]:
        if style not in ordered:
            ordered.append(style)
    reasons = {
        "achievement_journey": "利用者と購入決裁者それぞれの欲望・不安を描き、相談から購入判断までつなぐ",
        "story_experience": "作品本文の危機・小さな達成・次の謎を直接体験させる",
        "story_intro": "読者に近い現実側の人物から世界観と登場人物へ案内する",
        "testimonial": "読者に近い人物のBefore→体験→Afterで自分ごと化する",
        "developer": "仕組み・操作・出力を実演して購入判断の材料を作る",
        "insight": "旧常識を反転し、商品を見る新しい判断軸を渡す",
        "documentary": "利用過程を時系列で見せ、継続できるイメージを作る",
        "desire": "購入後の具体的な生活・行動の変化から逆算する",
        "recommendation": "第三者が勧める理由を示し、初見の警戒を下げる",
    }
    return [
        {"style": style, "label": SALES_STYLES[style]["label"], "reason": reasons[style], "recommended": style == primary}
        for style in ordered[:3]
    ]


def required_beats(
    style: str, goal: str, overlays: list[str], reveal_by: float | None,
) -> list[str]:
    """主スタイルへ補助レンズと、目的上外せない商品登場・達成を統合する。"""
    beats = list(SALES_STYLES[style]["beats"])

    def add_before(target: str, items: list[str]) -> None:
        index = beats.index(target) if target in beats else len(beats)
        for item in reversed(items):
            if item not in beats:
                beats.insert(index, item)

    for overlay in overlays:
        if overlay == "recommendation":
            if "recommendation" not in beats:
                anchor = "reader_empathy" if "reader_empathy" in beats else "hook"
                beats.insert(beats.index(anchor) + 1, "recommendation")
        elif overlay == "desire":
            if "desired_future" not in beats:
                beats.insert(1, "desired_future")
            if "barrier" not in beats:
                beats.insert(2, "barrier")
            add_before("proof", ["experience"])
            add_before("cta", ["bright_future"])
        elif overlay == "testimonial":
            add_before("product_reveal", ["failed_attempt"])
            add_before("proof", ["experience"])
        elif overlay == "objection":
            add_before("cta", ["objection"])
        elif overlay == "proof_stack":
            add_before("payoff" if "payoff" in beats else "cta", ["proof_stack"])

    if goal != "awareness" and "product_reveal" not in beats:
        add_before("cta", ["product_reveal"])
    if goal != "awareness" and "proof" not in beats:
        add_before("next_mystery" if "next_mystery" in beats else "cta", ["proof"])
    achievements = {"payoff", "visible_success", "bright_future", "after"}
    if goal == "conversion" and not achievements.intersection(beats):
        add_before("cta", ["payoff"])

    # 商品登場の位置が、自分自身の目的別ゲートと矛盾しないよう前へ移す。
    if reveal_by is not None and "product_reveal" in beats and style != "achievement_journey":
        reveal = beats.pop(beats.index("product_reveal"))
        latest = max(1, int(len(beats + [reveal]) * reveal_by + 0.999999) - 1)
        beats.insert(min(latest, len(beats)), reveal)
    return beats


def build_strategy(
    product_type: str,
    goal: str,
    style: str = "auto",
    pages: int | None = None,
    *,
    decision_maker_separate: bool = False,
    pressure: str | None = None,
) -> dict:
    if product_type not in PRODUCT_TYPES:
        raise ValueError(f"未知の商品種別: {product_type}")
    if goal not in GOALS:
        raise ValueError(f"未知のLP目的: {goal}")
    if style != "auto" and style not in SALES_STYLES:
        raise ValueError(f"未知の販売スタイル: {style}")
    if pressure is not None and pressure not in {"soft", "balanced", "direct"}:
        raise ValueError(f"未知の販売圧: {pressure}")

    product = PRODUCT_TYPES[product_type]
    goal_data = GOALS[goal]
    selection_mode = "auto" if style == "auto" else "manual"
    overlays: list[str]

    if style == "auto":
        primary, overlays = AUTO_ROUTES[product_type][goal]
        if decision_maker_separate and goal == "conversion":
            primary, overlays = "achievement_journey", ["objection"]
    else:
        primary, overlays = style, []

    low, high = goal_data["pages"]
    if primary == "achievement_journey":
        low, high = max(low, 10), max(high, 16)
    if pages is None:
        pages = low

    warnings: list[str] = []
    if not low <= pages <= high:
        warnings.append(f"推奨ページは{low}〜{high}。指定は{pages}ページ")
    compatible = STYLE_COMPATIBILITY.get(primary)
    if compatible and product_type not in compatible:
        warnings.append(f"{SALES_STYLES[primary]['label']}は{product['label']}では非標準。手動指定として続行")
    if primary == "achievement_journey" and not decision_maker_separate:
        warnings.append("成長実感型は利用者と決裁者が別のとき最も強い。decision_makerを確認")

    route_labels = [SALES_STYLES[primary]["label"]]
    overlay_labels = {
        "recommendation": "推薦",
        "desire": "欲望回収",
        "testimonial": "体験談",
        "objection": "反論処理",
        "proof_stack": "証拠蓄積",
    }
    route_labels.extend(overlay_labels.get(item, item) for item in overlays)

    reveal_by = 0.50 if primary == "achievement_journey" else goal_data["product_by"]
    beats = required_beats(primary, goal, overlays, reveal_by)

    return {
        "product_type": product_type,
        "product_label": product["label"],
        "goal": goal,
        "goal_label": goal_data["label"],
        "selection_mode": selection_mode,
        "primary_style": primary,
        "primary_style_label": SALES_STYLES[primary]["label"],
        "overlays": overlays,
        "route": "＋".join(route_labels),
        "required_beats": beats,
        "pages": pages,
        "recommended_pages": [low, high],
        "proof_style": product["proof"],
        "minimum_proof_loops": goal_data["proof_loops"],
        # 成長実感型は「困りごと→仲間→決裁者への相談」を先に描くため、
        # 通常の購入LPより商品登場を少し遅らせてよい。
        "product_reveal_by": reveal_by,
        "ending": goal_data["ending"],
        "cta": goal_data["cta"],
        "sales_pressure": pressure or goal_data["pressure"],
        "decision_maker_separate": decision_maker_separate,
        "route_candidates": route_candidates(product_type, goal, primary, decision_maker_separate),
        "selection_reason": (
            "利用者と購入決裁者が別のconversion施策なので、両者の判断過程を描ける成長実感型を推奨"
            if primary == "achievement_journey" and decision_maker_separate
            else f"{product['label']}×{goal_data['label']}の標準ルートとして{SALES_STYLES[primary]['label']}を推奨"
        ),
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="商品×目的×販売スタイルから漫画LPルートを選ぶ")
    parser.add_argument("--product", choices=PRODUCT_TYPES)
    parser.add_argument("--goal", choices=GOALS)
    parser.add_argument("--style", choices=["auto", *SALES_STYLES], default="auto")
    parser.add_argument("--pages", type=int)
    parser.add_argument("--pressure", choices=["soft", "balanced", "direct"])
    parser.add_argument("--separate-decision-maker", action="store_true")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args()
    if args.list:
        print(json.dumps({
            "products": PRODUCT_TYPES,
            "goals": GOALS,
            "styles": SALES_STYLES,
        }, ensure_ascii=False, indent=2))
        return 0
    if not args.product or not args.goal:
        parser.error("--product と --goal の両方が必要です")
    print(json.dumps(build_strategy(
        args.product, args.goal, args.style, args.pages,
        decision_maker_separate=args.separate_decision_maker,
        pressure=args.pressure,
    ), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
