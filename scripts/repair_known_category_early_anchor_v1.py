#!/usr/bin/env python3
import hashlib
import json
import re
import sys
from pathlib import Path


def norm(text: str) -> str:
    return re.sub(r"\s+", "", str(text))


def pick(pool, seed, used, answer_chars):
    if not pool:
        return None
    size = len(pool)
    start = seed % size
    for i in range(size):
        cand = norm(pool[(start + i) % size])
        if not cand:
            continue
        if cand in used:
            continue
        if len(cand) > 5:
            continue
        if set(cand) & answer_chars:
            continue
        return cand
    return None


ANIME_SLOT_POOLS = {
    1: ["长篇连载", "虚构故事", "角色登场", "作品主线", "叙事展开", "题材表达", "群像作品", "剧情开场"],
    2: ["世界框架", "人物关系", "成长路径", "冲突起点", "主线推进", "剧情线索", "阵营分化", "情节展开"],
    3: ["团队协作", "宿命牵引", "能力设定", "章节节点", "关键抉择", "情绪拉扯", "对抗局势", "伏笔回收"],
    4: ["高光桥段", "阶段对决", "情节反转", "线索收束", "角色爆发", "命运交锋", "经典场景", "关键回合"],
    5: ["伙伴并肩", "命运牵连", "身世秘密", "阵营碰撞", "旅程转折", "宿敌交锋", "队伍同行", "成长试炼", "守护执念", "冒险升级", "立场摇摆", "秘密揭开"],
    6: ["名场面多", "主线悬念", "核心设定", "终局压力", "角色招牌", "关键对决", "世界规则", "人物执念", "作品记忆", "长线伏笔", "粉丝熟知", "力量觉醒"],
}

FOOD_SLOT_POOLS = {
    1: ["餐桌日常", "饮食选择", "入口感受", "热食场景", "口味偏好", "饭点常见", "家常餐食", "日常吃食"],
    2: ["食材处理", "做法起手", "火候变化", "口感线索", "风味铺垫", "出餐节奏", "调味方向", "香气先出"],
    3: ["咀嚼反馈", "层次变化", "味型成形", "热度状态", "口感走向", "锅中变化", "香味外扩", "主料搭配"],
    4: ["上桌时机", "回味落点", "搭配习惯", "餐后记忆", "入口留香", "熟度判断", "质地表现", "口味收束"],
    5: ["店里现做", "热气上桌", "口感分层", "蘸料习惯", "饭桌常见", "聚餐常点", "节令餐桌", "吃法讲究", "口味分流", "冷热皆宜", "外卖常点", "夜宵常见"],
    6: ["招牌吃法", "熟客会点", "一口就香", "摆盘显眼", "风味记忆", "回味明显", "节日常见", "咬开流香", "越嚼越香", "口感扎实", "餐桌主角", "上桌很快"],
}

GAME_SLOT_POOLS = {
    1: ["虚拟对局", "玩家操作", "互动规则", "胜负目标", "进度推进", "策略选择", "回合机制"],
    2: ["资源管理", "分工定位", "任务路线", "地图探索", "战局判断", "节奏把控", "风险收益"],
    3: ["冷却管理", "时机判断", "连段衔接", "局势逆转", "团队协同", "经济差距", "目标争夺"],
    4: ["关键节点", "高压博弈", "团战处理", "资源抢控", "阵容配合", "战术执行", "临场决策"],
    5: ["队内分工", "操作习惯", "常用说法", "进场时机", "局势分线", "对局流程", "资源轮转", "战斗职责", "推进方式", "配合思路", "控图节奏", "翻盘机会"],
    6: ["老玩家懂", "实战叫法", "关键职责", "功能定位", "团战配合", "局内黑话", "场内协同", "常见口令", "阶段目标", "打法招牌", "对局记忆", "临场应对"],
}

LIFE_SLOT_POOLS = {
    1: ["日常节律", "居家场景", "手边小事", "生活片刻", "时间安排", "当天事务", "起居片段", "日常步骤"],
    2: ["按序进行", "顺手处理", "场景切换", "固定习惯", "经常会做", "临时决定", "马上处理", "当天安排"],
    3: ["动作细节", "步骤衔接", "前后连贯", "习惯维持", "流程推进", "收尾动作", "状态调整", "过程衔接"],
    4: ["结果反馈", "完成状态", "场景收束", "日常闭环", "实际用途", "生活需要", "效率提升", "即时可感"],
    5: ["居家日常", "手边事务", "顺手完成", "场景切换", "日程安排", "当天节奏", "饭点更忙", "状态调整", "按序处理", "生活片段", "日常收尾", "居家安排"],
    6: ["生活节奏", "顺路处理", "手边就做", "临时安排", "场景过渡", "日常闭环", "起居变化", "习惯动作", "当天要做", "顺手解决", "忙完再说", "生活反馈"],
}

LIFE_SPECIAL = {
    "起床": ["闹铃响", "离开被窝", "睁眼清醒", "清晨微光"],
    "洗漱": ["镜前整理", "牙膏泡沫", "毛巾擦脸", "口气清新"],
    "做饭": ["下厨开火", "锅铲翻动", "灶台热气", "备菜调味"],
    "购物": ["比价挑选", "付款结算", "商场货架", "拎袋回家"],
    "逛街": ["商圈漫步", "橱窗停留", "试衣挑款", "门店连逛"],
    "通勤": ["早高峰", "地铁站", "赶点出门", "上班路上"],
    "运动": ["心率上升", "拉伸热身", "汗湿衣背", "呼吸加快"],
    "养宠": ["定时喂食", "遛弯", "清理猫砂", "陪伴互动"],
    "租房": ["看房比对", "押金合同", "房东沟通", "月付账单"],
    "搬家": ["纸箱打包", "清点物品", "新住处", "车辆装载"],
    "装修": ["量尺", "刷墙", "木工安装", "选材配色"],
    "打扫": ["除尘擦拭", "拖地", "清理角落", "收纳归位"],
    "洗衣": ["滚筒转动", "脱水声", "柔顺剂", "晾杆"],
    "晾晒": ["阳台杆", "夹子", "通风处", "太阳下"],
    "读书": ["纸页翻动", "章节推进", "安静角落", "书签定位"],
    "上网": ["浏览网页", "连线稳定", "搜索内容", "信息刷新"],
    "追剧": ["连更", "片头曲", "下一集", "弹幕讨论"],
    "做梦": ["入睡后", "潜意识", "醒来残影", "夜间幻景"],
    "护肤": ["面霜", "精华液", "保湿层", "涂抹吸收"],
    "外卖": ["餐盒保温", "懒得下厨", "到门餐食", "饭点更忙"],
    "洗碗": ["餐后清理", "去油冲净", "沥水架", "擦干收放"],
    "丢垃圾": ["分类桶", "打包袋", "下楼投放", "定点清运"],
    "取件": ["驿站", "快递柜", "编号码", "包裹签收"],
    "做家务": ["清洁收纳", "分区整理", "台面归位", "居家维护"],
    "理发": ["剪刀声", "修短刘海", "推子嗡鸣", "发型调整"],
    "淋浴": ["花洒", "热水汽", "冲净", "浴室蒸气"],
    "早起": ["晨光", "离被窝", "闹铃", "清醒更早"],
    "晚睡": ["夜深时分", "关灯后", "入眠偏迟", "次日犯困"],
    "通话": ["来电提醒", "语音时长", "扬声器", "通联记录"],
    "网购": ["购物车", "包裹物流", "评论区", "退换流程"],
    "刷牙": ["清新口气", "薄荷味", "漱口杯", "晨晚固定"],
    "泡澡": ["浴缸", "热水温度", "香氛盐", "全身放松"],
    "晒衣": ["阳台绳", "通风晾干", "日照", "夹子固定"],
    "收拾": ["台面归整", "物品分类", "抽屉归位", "空间清爽"],
    "通风": ["开窗", "空气流动", "换气", "室内清新"],
    "熬夜": ["凌晨时段", "困意上来", "夜间清醒", "次日乏力"],
    "午休": ["中午短睡", "恢复精神", "闭眼片刻", "下午提神"],
    "冲茶": ["热水壶", "茶香", "回甘", "杯中舒展"],
    "修灯": ["更换灯泡", "电笔测试", "照明恢复", "断电操作"],
    "理财": ["记账", "预算分配", "收益率", "现金流"],
}


def load_game_special(repo_root: Path):
    sys.path.append(str(repo_root / "scripts"))
    import rewrite_game_hints_v29 as rg  # pylint: disable=import-error

    return rg.GAME_SPECIAL


def repair_category(items, category, anchor_map, slot_pools, salt):
    changed = 0
    touched = 0
    for item in items:
        if norm(item.get("category", "")) != category:
            continue
        answer = norm(item.get("answer", ""))
        if not answer:
            continue
        anchors = {norm(x) for x in anchor_map.get(answer, [])}
        hints = [str(x).strip() for x in (item.get("hints") or [])[:7]]
        if len(hints) < 7:
            continue
        answer_chars = {c for c in answer if c.strip()}
        used = {norm(h) for h in hints}
        item_changed = False
        seed = int(hashlib.sha256(f"{salt}::{answer}".encode("utf-8")).hexdigest(), 16)
        for slot in range(1, 7):
            if norm(hints[slot - 1]) not in anchors:
                continue
            used.discard(norm(hints[slot - 1]))
            pool = slot_pools[slot]
            replacement = pick(pool, seed + slot * 37, used, answer_chars)
            if replacement is None:
                raise SystemExit(f"cannot_pick_replacement:{category}:{answer}:slot{slot}")
            hints[slot - 1] = replacement
            used.add(replacement)
            item_changed = True
        if item_changed:
            item["hints"] = hints
            touched += 1
            changed += 1
    return {"changed_items": changed, "touched_items": touched}


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    data_path = repo_root / "assets/puzzles.json"
    items = json.loads(data_path.read_text(encoding="utf-8"))

    anime_map = json.loads((repo_root / "data/anime_guess_master_map_v1.json").read_text(encoding="utf-8"))
    food_map = json.loads((repo_root / "data/food_hint_style_map_v2.json").read_text(encoding="utf-8"))
    game_map = load_game_special(repo_root)

    summary = {
        "动漫": repair_category(items, "动漫", anime_map, ANIME_SLOT_POOLS, "anime-early-fix"),
        "游戏": repair_category(items, "游戏", game_map, GAME_SLOT_POOLS, "game-early-fix"),
        "美食": repair_category(items, "美食", food_map, FOOD_SLOT_POOLS, "food-early-fix"),
        "生活": repair_category(items, "生活", LIFE_SPECIAL, LIFE_SLOT_POOLS, "life-early-fix"),
    }

    data_path.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
