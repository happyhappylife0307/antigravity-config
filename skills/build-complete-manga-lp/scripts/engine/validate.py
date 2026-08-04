"""漫画LP原稿JSONを、目的別の品質ゲートで検査する。"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import re
import urllib.parse
from dataclasses import dataclass

try:
    from .strategy import GOALS, PRODUCT_TYPES, SALES_STYLES
except ImportError:  # direct script execution
    from strategy import GOALS, PRODUCT_TYPES, SALES_STYLES


BANNED = ("完全", "絶対", "必ず", "100%", "保証", "日本初", "業界No.1", "誰でも簡単に", "劇的に", "確実に")
MINOR_RISK = ("バストアップ", "唇を噛", "顔を覆", "髪を握", "傷だらけ")
MARKETING_PLACEHOLDERS = ("未確定", "制作前に", "調査前", "対象読者", "具体的な体験場面")


@dataclass
class Issue:
    level: str
    code: str
    message: str


def _clean_len(text: str) -> int:
    return len(re.sub(r"[\s\n]", "", text))


def _strategy(script: dict) -> dict:
    return script.get("meta", {}).get("strategy") or script.get("strategy") or {}


def _marketing(script: dict) -> dict:
    return script.get("meta", {}).get("marketing") or {}


def _require_text(issues: list[Issue], value: object, code: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        issues.append(Issue("error", code, f"成果設計カードの{label} が空です"))
    elif any(word in value for word in MARKETING_PLACEHOLDERS):
        issues.append(Issue("error", code + ".placeholder", f"成果設計カードの{label} がテンプレートのままです"))


def validate_script(script: dict, strict: bool = False) -> list[Issue]:
    issues: list[Issue] = []
    meta = script.get("meta")
    panels = script.get("panels")
    if not isinstance(meta, dict):
        return [Issue("error", "schema.meta", "meta がありません")]
    if not isinstance(panels, list) or not panels:
        return [Issue("error", "schema.panels", "panels が空です")]

    strategy = _strategy(script)
    if not strategy:
        level = "error" if strict else "warning"
        issues.append(Issue(level, "strategy.missing", "meta.strategy がありません。v1互換原稿として扱います"))
        return issues + _content_checks(script)

    marketing = _marketing(script)
    for key, label in (
        ("kpi", "動かすKPI"),
        ("desired_change", "誰の・どんな変化"),
        ("hypothesis", "KPIを動かす仮説"),
    ):
        _require_text(issues, marketing.get(key), f"marketing.{key}", label)

    for key, label in (("phase", "マーケティングフェーズ"), ("funnel_stage", "ファネル上の役割"), ("traffic_source", "流入元")):
        _require_text(issues, marketing.get(key), f"marketing.{key}", label)

    target = marketing.get("target") or {}
    for key, label in (
        ("segment", "変化で定義したターゲット"),
        ("situation", "購入直前の具体的状況"),
        ("desired_progress", "ターゲットが進めたい用事"),
        ("user", "実際の利用者"),
        ("decision_maker", "購入決裁者"),
        ("payer", "支払者"),
        ("barrier", "購入障壁"),
    ):
        _require_text(issues, target.get(key), f"marketing.target.{key}", label)

    transformation = marketing.get("transformation") or {}
    for key, label in (
        ("before", "購入前の状態"),
        ("after_immediate", "購入直後の状態"),
        ("after_experience", "商品体験後の状態"),
        ("non_goal", "保証しない変化"),
    ):
        _require_text(issues, transformation.get(key), f"marketing.transformation.{key}", label)

    evidence = marketing.get("evidence") or {}
    if not isinstance(evidence, dict):
        issues.append(Issue("error", "marketing.evidence.schema", "根拠はtype/source/date/findingを持つ構造にしてください"))
    else:
        for key, label in (("type", "根拠の種類"), ("source", "根拠の出典"), ("date", "根拠の日付"), ("finding", "根拠から得た発見")):
            _require_text(issues, evidence.get(key), f"marketing.evidence.{key}", label)
        if evidence.get("type") not in {"顧客", "競合", "市場", "実売", "自分", "勘"}:
            issues.append(Issue("error", "marketing.evidence.type", "根拠の種類は顧客・競合・市場・実売・自分・勘のいずれかです"))

    measurement = marketing.get("measurement") or {}
    if not isinstance(measurement, dict):
        issues.append(Issue("error", "marketing.measurement.schema", "計測はevent/method/timing/success_ruleを持つ構造にしてください"))
    else:
        for key, label in (("event", "計測イベント"), ("method", "計測方法"), ("timing", "判定時期"), ("success_rule", "継続・修正・中止の判断基準")):
            _require_text(issues, measurement.get(key), f"marketing.measurement.{key}", label)

    route_decision = marketing.get("route_decision") or {}
    if route_decision.get("presented") is not True:
        issues.append(Issue("error", "marketing.route.presented", "ストーリー形式の候補を制作前に提示してください"))
    _require_text(issues, route_decision.get("selected"), "marketing.route.selected", "選んだストーリー形式")
    _require_text(issues, route_decision.get("reason"), "marketing.route.reason", "ストーリー形式の選定理由")
    if route_decision.get("confirmation") not in {"user_selected", "auto_recommended"}:
        issues.append(Issue("error", "marketing.route.confirmation", "ルート決定はuser_selectedまたはauto_recommendedを記録してください"))
    alternatives = route_decision.get("alternatives")
    if not isinstance(alternatives, list) or len(alternatives) < 2:
        issues.append(Issue("error", "marketing.route.alternatives", "比較したストーリー形式を2案以上記録してください"))

    do_not = marketing.get("do_not")
    if not isinstance(do_not, list) or not any(str(item).strip() for item in do_not):
        issues.append(Issue("error", "marketing.do_not", "やらないことリストを1件以上記録してください"))

    planned = set(marketing.get("inspection_plan", []))
    required_inspections = {"machine", "style", "fact", "legal"}
    if not required_inspections <= planned:
        missing = "・".join(sorted(required_inspections - planned))
        issues.append(Issue("error", "marketing.inspection_plan", f"四面品質審査の予定が不足: {missing}"))

    rights = meta.get("rights") or {}
    authorized_names = rights.get("authorized_names")
    if not isinstance(authorized_names, list) or not any(str(item).strip() for item in authorized_names):
        issues.append(Issue("error", "rights.authorized_names", "広告主が所有または使用許諾を得た名称を1件以上記録してください"))
    for key, label in (
        ("third_party_names", "第三者の企業名・商品名・サービス名"),
        ("third_party_logos", "第三者のロゴ"),
        ("third_party_characters", "第三者のキャラクター・特徴的な意匠"),
    ):
        found = rights.get(key)
        if not isinstance(found, list):
            issues.append(Issue("error", f"rights.{key}.schema", f"{label}の確認結果を配列で記録してください"))
        elif found:
            issues.append(Issue("error", f"rights.{key}", f"漫画LPに{label}を使用できません: " + "・".join(map(str, found))))
    if rights.get("reviewed") is not True:
        issues.append(Issue("error", "rights.reviewed", "本文・吹き出し・作画指示・生成画像の第三者標章審査が未完了です"))
    _require_text(issues, rights.get("review_evidence"), "rights.review_evidence", "権利審査の確認記録")

    character_refs = []
    for character in script.get("characters", {}).values():
        character_refs.extend(
            character.get(key) for key in ("ref", "expression_ref", "action_ref") if character.get(key)
        )
    if len(set(character_refs)) < 3:
        issues.append(Issue(
            "error", "assets.character_sheets",
            "作画前のキャラクター参照シートが3枚未満です（基本・表情・動作、または主要3人物）",
        ))

    product = strategy.get("product_type")
    goal = strategy.get("goal")
    if product not in PRODUCT_TYPES:
        issues.append(Issue("error", "strategy.product", f"未知の商品種別: {product}"))
    if goal not in GOALS:
        issues.append(Issue("error", "strategy.goal", f"未知のLP目的: {goal}"))
        return issues + _content_checks(script)

    primary_style = strategy.get("primary_style")
    if primary_style not in SALES_STYLES:
        issues.append(Issue("error", "strategy.style", f"未知または未指定の販売スタイル: {primary_style}"))
    else:
        if route_decision.get("selected") != primary_style:
            issues.append(Issue("error", "marketing.route.mismatch", "成果設計カードで選んだ形式とmeta.strategy.primary_styleが一致しません"))
        sections = {p.get("section") for p in panels}
        required_beats = strategy.get("required_beats") or SALES_STYLES[primary_style]["beats"]
        missing_beats = [beat for beat in required_beats if beat not in sections]
        if missing_beats:
            issues.append(Issue(
                "error", "structure.style_beats",
                "販売スタイルの必須ビートが不足: " + "・".join(missing_beats),
            ))

        if primary_style == "achievement_journey":
            missing_roles = {"user", "peer", "decision_maker"} - set(script.get("characters", {}))
            if missing_roles:
                issues.append(Issue(
                    "error", "strategy.achievement_journey.characters",
                    "成長実感型の人物定義が不足: " + "・".join(sorted(missing_roles)),
                ))
            for key, label in (
                ("user", "利用者"),
                ("decision_maker", "決裁者"),
                ("peer", "友人・同世代役"),
            ):
                if not strategy.get(key):
                    issues.append(Issue("error", f"strategy.achievement_journey.{key}", f"成長実感型の{label}が空です"))
            if not strategy.get("bright_future"):
                issues.append(Issue("error", "strategy.achievement_journey.bright_future", "明るい未来の具体像が空です"))

    if (
        target.get("user") and target.get("decision_maker")
        and target.get("user") != target.get("decision_maker")
        and not strategy.get("decision_maker_separate")
    ):
        issues.append(Issue(
            "error", "marketing.roles.separate",
            "利用者と決裁者が別なのにdecision_maker_separateがfalseです",
        ))

    for key, label in (
        ("route", "採用ルート"),
        ("next_action", "読後の一歩"),
        ("hook_question", "未解決疑問"),
    ):
        if not strategy.get(key):
            issues.append(Issue("error", f"strategy.{key}", f"{label} が空です"))

    if goal == "conversion":
        for key, label in (
            ("payoff_mirror", "冒頭と結末の鏡"),
            ("achievement_ceiling", "達成感の上限"),
            ("cta_basis", "CTA根拠"),
        ):
            if not strategy.get(key):
                issues.append(Issue("error", f"strategy.{key}", f"{label} が空です"))

    section_sequence = [p.get("section") for p in panels]
    if section_sequence[0] != "hook":
        issues.append(Issue("error", "structure.hook", "最初のコマの section は hook にしてください"))

    planned_pages = int(strategy.get("pages", 0) or 0)
    actual_pages = {int(panel.get("page", 0) or 0) for panel in panels}
    if planned_pages > 0 and actual_pages != set(range(1, planned_pages + 1)):
        issues.append(Issue(
            "error", "structure.pages",
            f"指定{planned_pages}ページに対し、実ページは{sorted(actual_pages)}です",
        ))

    reveal_indices = [i for i, section in enumerate(section_sequence) if section == "product_reveal"]
    reveal_limit = strategy.get("product_reveal_by", GOALS[goal]["product_by"])
    if reveal_limit is not None:
        if not reveal_indices:
            issues.append(Issue("error", "structure.reveal", "product_reveal がありません"))
        else:
            latest = max(0, math.ceil(len(panels) * reveal_limit) - 1)
            if reveal_indices[0] > latest:
                issues.append(Issue(
                    "error", "structure.reveal_late",
                    f"商品登場が遅いです: コマ{reveal_indices[0] + 1}/{len(panels)}（上限コマ{latest + 1}）",
                ))

    loops = script.get("proof_loops", [])
    need_loops = GOALS[goal]["proof_loops"]
    if len(loops) < need_loops:
        issues.append(Issue("error", "proof.count", f"証拠ループが{len(loops)}組。目的上は{need_loops}組必要です"))
    for i, loop in enumerate(loops, 1):
        for key in ("barrier", "mechanism", "scene", "result"):
            if not loop.get(key):
                issues.append(Issue("error", "proof.incomplete", f"証拠ループ{i}の {key} が空です"))

    if goal == "conversion" and not ({"payoff", "visible_success", "bright_future", "after"} & set(section_sequence)):
        issues.append(Issue("error", "structure.payoff", "conversion には目で分かる達成または明るい未来が必要です"))

    cta = script.get("cta", {})
    if not cta.get("label") or not cta.get("url"):
        issues.append(Issue("error", "cta.missing", "CTAの label と url が必要です"))
    elif strategy.get("next_action") and strategy["next_action"] not in cta["label"]:
        issues.append(Issue("warning", "cta.action_mismatch", "戦略カードの読後の一歩とCTA文言を確認してください"))
    if cta.get("url"):
        parsed = urllib.parse.urlparse(cta["url"])
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            issues.append(Issue("error", "cta.url", "CTA URLは有効なhttp/https URLにしてください"))
        if parsed.netloc == "example.com" and not meta.get("demo"):
            issues.append(Issue("error", "cta.placeholder", "example.com を実際のCTA URLへ差し替えてください"))

    offer = meta.get("offer", {})
    if offer.get("deadline") and not offer.get("deadline_source"):
        issues.append(Issue("error", "offer.deadline_source", "期限に根拠がありません"))

    issues.extend(_content_checks(script))
    return issues


def _content_checks(script: dict) -> list[Issue]:
    issues: list[Issue] = []
    full_text_parts = []
    for panel in script.get("panels", []):
        art = panel.get("art", "")
        full_text_parts.append(art)
        for bubble in panel.get("bubbles", []):
            text = bubble.get("text", "")
            full_text_parts.append(text)
            length = _clean_len(text)
            if length > 22:
                issues.append(Issue("error", "copy.too_long", f"コマ{panel.get('n')}のセリフが{length}字: {text!r}"))

    cta = script.get("cta", {})
    full_text_parts.extend([cta.get("label", ""), cta.get("url", "")])
    full_text = "\n".join(full_text_parts)
    if not script.get("meta", {}).get("demo"):
        placeholders = ("書き換える", "URLを差し替える", "のセリフ", "example.com")
        found = [word for word in placeholders if word in full_text]
        if found:
            issues.append(Issue(
                "error", "copy.placeholder",
                "テンプレート文が残っています: " + "・".join(found),
            ))
    for word in BANNED:
        if word in full_text:
            issues.append(Issue("error", "copy.banned", f"禁止語を検出: {word}"))
    if script.get("meta", {}).get("has_minors"):
        for word in MINOR_RISK:
            if word in full_text:
                issues.append(Issue("error", "safety.minor", f"未成年向け演出の要修正語: {word}"))
    return issues


def format_report(path: pathlib.Path, issues: list[Issue]) -> str:
    errors = sum(i.level == "error" for i in issues)
    warnings = sum(i.level == "warning" for i in issues)
    lines = [f"検査: {path.name}", f"結果: エラー {errors} / 警告 {warnings}"]
    for issue in issues:
        mark = "✗" if issue.level == "error" else "!"
        lines.append(f"{mark} [{issue.code}] {issue.message}")
    if not issues:
        lines.append("✓ 目的別ゲートをすべて通過しました")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="漫画LP原稿JSONの品質検査")
    ap.add_argument("script")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()
    path = pathlib.Path(args.script)
    script = json.loads(path.read_text(encoding="utf-8"))
    issues = validate_script(script, strict=args.strict)
    print(format_report(path, issues))
    return 1 if any(i.level == "error" for i in issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
