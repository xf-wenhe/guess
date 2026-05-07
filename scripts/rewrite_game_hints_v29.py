from __future__ import annotations

import argparse
import json
from pathlib import Path

BASE_LEVELS = ["互动娱乐", "虚拟场景", "玩家操作"]

GAME_SPECIAL = {
    "公会": ["多人组织", "成员协作", "集体活动", "长期经营"],
    "刷本": ["重复挑战", "获取资源", "效率循环", "副本收益"],
    "副本": ["独立关卡", "组队挑战", "机制目标", "通关奖励"],
    "匹配": ["自动组局", "队伍分配", "对手筛选", "进入对局"],
    "升级": ["经验积累", "等级提升", "属性增强", "成长路径"],
    "单机": ["离线体验", "本地运行", "无网络依赖", "个人游玩"],
    "卡关": ["难点阻塞", "反复尝试", "策略调整", "关卡突破"],
    "合成": ["材料组合", "配方规则", "产出装备", "资源转化"],
    "塔防": ["路径防守", "部署单位", "波次进攻", "据点守护"],
    "复活": ["角色重返", "失败后恢复", "状态重置", "继续作战"],
    "存档": ["进度保存", "关键节点", "本地记录", "后续读取"],
    "开荒": ["首次探索", "未知机制", "资源紧缺", "建立优势"],
    "战绩": ["对局统计", "击败记录", "胜率表现", "历史结果"],
    "手柄": ["外接控制", "摇杆按键", "震动反馈", "主机操作"],
    "打野": ["野区资源", "游走支援", "节奏带动", "控图反蹲"],
    "技能": ["主动释放", "冷却时间", "效果判定", "连招衔接"],
    "抽卡": ["随机获取", "稀有概率", "角色招募", "保底机制"],
    "拉怪": ["仇恨吸引", "聚集敌人", "站位引导", "范围输出"],
    "掉线": ["网络中断", "连接丢失", "退出对局", "重连恢复"],
    "掉落": ["击败产出", "随机奖励", "道具获取", "战利品系统"],
    "排位": ["段位竞争", "积分增减", "实力分层", "赛季排名"],
    "探图": ["地图探索", "视野开启", "区域解锁", "隐藏发现"],
    "控蓝": ["法力管理", "消耗控制", "技能节省", "续航作战"],
    "教程": ["新手引导", "基础教学", "操作说明", "机制演示"],
    "新手": ["入门阶段", "基础认知", "学习曲线", "早期保护"],
    "暴击": ["瞬时高伤", "概率触发", "伤害倍率", "输出爆发"],
    "沙盒": ["开放世界", "自由建造", "规则可改", "创意玩法"],
    "皮肤": ["外观替换", "视觉展示", "角色装扮", "个性化内容"],
    "策略": ["决策规划", "资源分配", "阵容搭配", "局势博弈"],
    "组队": ["多人协作", "职责分工", "配合推进", "团队目标"],
    "联机": ["在线连接", "多人同玩", "实时同步", "跨端协同"],
    "视角": ["观察方式", "镜头控制", "第一第三人称", "信息获取"],
    "解谜": ["线索推理", "机关破解", "逻辑关联", "逐步还原"],
    "读档": ["加载进度", "恢复节点", "回到存档", "重新尝试"],
    "走位": ["移动规避", "站位选择", "躲避技能", "输出空间"],
    "过图": ["跨区推进", "清理阻碍", "到达终点", "阶段转换"],
    "连击": ["连续命中", "节奏衔接", "伤害叠加", "操作连贯"],
    "连麦": ["语音沟通", "实时交流", "指令同步", "团队协调"],
    "闯关": ["逐关挑战", "难度提升", "目标达成", "连续通关"],
    "首领": ["高强敌人", "阶段机制", "团队集火", "击败奖励"],
}


def build_hints(answer: str) -> list[str]:
    tail = GAME_SPECIAL.get(answer)
    if not tail:
        tail = ["玩法机制", "对局推进", "目标达成", "胜负反馈"]
    return BASE_LEVELS + tail


def run_rewrite(input_path: Path, out_dir: Path, apply: bool) -> dict:
    data = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("invalid puzzles json: root must be list")

    changed = 0
    touched_answers = []

    rewritten = []
    for item in data:
        category = str(item.get("category", "")).strip()
        answer = str(item.get("answer", "")).strip()
        new_item = dict(item)
        if category == "游戏" and answer:
            new_hints = build_hints(answer)
            old_hints = [str(h).strip() for h in (item.get("hints") or [])][:7]
            new_item["hints"] = new_hints
            if old_hints != new_hints:
                changed += 1
                touched_answers.append(answer)
        rewritten.append(new_item)

    output_text = json.dumps(rewritten, ensure_ascii=False, indent=2) + "\n"

    out_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = out_dir / "puzzles.game_rewrite.v29.json"
    report_path = out_dir / "hints_game_rewrite_v29_report.json"

    snapshot_path.write_text(output_text, encoding="utf-8")
    if apply:
        input_path.write_text(output_text, encoding="utf-8")

    report = {
        "input": str(input_path),
        "snapshot": str(snapshot_path),
        "apply": apply,
        "changed_items": changed,
        "touched_answers": sorted(set(touched_answers)),
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "report": report,
        "report_path": str(report_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Rewrite game hints sample v29")
    parser.add_argument("--input", default="assets/puzzles.json")
    parser.add_argument("--out-dir", default="tmp")
    parser.add_argument("--apply", action="store_true", help="overwrite input file")
    args = parser.parse_args()

    result = run_rewrite(Path(args.input), Path(args.out_dir), apply=args.apply)
    report = result["report"]
    print(
        "changed_items={changed_items} apply={apply} snapshot={snapshot}".format(
            **report
        )
    )
    print(f"report={result['report_path']}")


if __name__ == "__main__":
    main()
