#!/usr/bin/env python3
import collections
import json
import re
import sys
from pathlib import Path


def norm(text: str) -> str:
    return re.sub(r"\s+", "", str(text))


def visible_chars(text: str) -> int:
    return len("".join(ch for ch in str(text) if ch.strip()))


ANIME_DIMENSION_POOLS = {
    "context": {"长篇连载", "虚构故事", "角色登场", "作品主线", "叙事展开", "题材表达", "群像作品", "剧情开场", "人物出场", "故事起势", "连载作品", "动画叙事", "剧情铺垫", "作品背景", "故事开局", "角色戏份"},
    "structure": {"世界框架", "人物关系", "成长路径", "冲突起点", "主线推进", "剧情线索", "阵营分化", "目标追寻", "关系走向", "故事走线", "冲突升级", "线索铺陈", "角色立场", "事件推进", "叙事路径", "情节展开"},
    "conflict": {"团队协作", "宿命牵引", "能力设定", "章节节点", "关键抉择", "情绪拉扯", "对抗局势", "伏笔回收", "人物转折", "事件变化", "关系张力", "阶段升级", "剧情波动", "矛盾激化", "立场冲突", "群像互动"},
    "scene_turn": {"高光桥段", "阶段对决", "情节反转", "线索收束", "角色爆发", "命运交锋", "经典场景", "关键回合", "剧情翻转", "冲突焦点", "战局逆转", "阶段高潮", "关系破局", "结局铺路", "核心桥段", "节点爆发"},
    "mid_anchor": {"伙伴并肩", "命运牵连", "身世秘密", "阵营碰撞", "旅程转折", "宿敌交锋", "队伍同行", "成长试炼", "守护执念", "冒险升级", "立场摇摆", "秘密揭开"},
    "strong_anchor": {"名场面多", "主线悬念", "核心设定", "终局压力", "角色招牌", "关键对决", "世界规则", "人物执念", "作品记忆", "长线伏笔", "粉丝熟知", "力量觉醒"},
}

FOOD_DIMENSION_POOLS = {
    "meal_scene": {"餐桌日常", "饮食选择", "入口感受", "热食场景", "口味偏好", "饭点常见", "家常餐食", "日常吃食", "外卖常点"},
    "prep_process": {"食材处理", "做法起手", "火候变化", "出餐节奏", "冷热皆宜", "吃法讲究", "上桌很快"},
    "prep_setup": {"口感线索", "风味铺垫", "调味方向", "香气先出"},
    "texture_flavor": {"咀嚼反馈", "层次变化", "味型成形", "热度状态", "口感走向", "锅中变化", "香味外扩", "主料搭配", "口感分层", "风味记忆", "回味明显", "咬开流香", "越嚼越香", "口感扎实", "一口就香", "口味平衡", "味型特点", "回味长短", "入口顺滑", "谷香", "麦香"},
    "serving_finish": {"上桌时机", "回味落点", "搭配习惯", "餐后记忆", "入口留香", "熟度判断", "质地表现", "口味收束", "蘸料习惯", "口味分流", "摆盘显眼", "餐桌主角"},
    "anchor": {"招牌吃法", "熟客会点", "节日常见"},
    "food_mid_anchor": {"饭桌常见", "聚餐常点", "节令餐桌", "夜宵常见", "店里现做", "吃法讲究", "热气上桌", "茶桌常见"},
    "food_strong_anchor": {"熟客会点", "餐桌主角", "招牌吃法", "摆盘显眼", "节日常见", "上桌很快", "多人会点", "常被点单"},
    "food_form": {"手握饭", "海苔卷", "签子串", "圆模压花", "叶片包裹", "绳线捆扎", "冷食拼盘"},
    "cooking_action": {"边翻边刷", "明火现做", "酥皮包馅", "蒸煮出锅"},
}

GAME_DIMENSION_POOLS = {
    "base_rule": {"虚拟对局", "玩家操作", "互动规则", "胜负目标", "进度推进", "策略选择", "回合机制"},
    "battle_read": {"资源管理", "分工定位", "任务路线", "地图探索", "战局判断", "节奏把控", "风险收益"},
    "execution": {"冷却管理", "时机判断", "连段衔接", "局势逆转", "团队协同", "经济差距", "目标争夺"},
    "pressure_phase": {"关键节点", "高压博弈", "团战处理", "资源抢控", "阵容配合", "战术执行", "临场决策"},
    "mid_role": {"队内分工", "操作习惯", "常用说法", "进场时机", "局势分线", "对局流程", "资源轮转", "战斗职责", "推进方式", "配合思路", "控图节奏", "翻盘机会"},
    "strong_role": {"老玩家懂", "实战叫法", "关键职责", "功能定位", "团战配合", "局内黑话", "场内协同", "常见口令", "阶段目标", "打法招牌", "对局记忆", "临场应对"},
}

LIFE_DIMENSION_POOLS = {
    "daily_scene": {"日常节律", "居家场景", "手边小事", "生活片刻", "时间安排", "当天事务", "起居片段", "日常步骤", "居家日常", "手边事务", "日程安排", "当天节奏"},
    "sequence_habit": {"按序进行", "顺手处理", "场景切换", "固定习惯", "经常会做", "临时决定", "马上处理", "当天安排", "顺手完成"},
    "action_flow": {"动作细节", "步骤衔接", "前后连贯", "习惯维持", "流程推进", "收尾动作", "状态调整", "过程衔接"},
    "result_feedback": {"结果反馈", "完成状态", "场景收束", "日常闭环", "实际用途", "生活需要", "效率提升", "即时可感"},
    "life_mid_anchor": {"手边就做", "顺路处理", "当天要做", "临时安排", "忙完再说", "顺手解决", "居家安排", "手边收尾"},
    "life_strong_anchor": {"起居变化", "生活反馈", "场景过渡", "顺手收尾", "当下感受", "后续安排", "忙后状态", "生活回响"},
}

ACTION_DIMENSION_POOLS = {
    "core_power": {"核心力量", "发力技巧", "力量对抗", "上肢带动", "蓄力一击"},
    "footwork_shift": {"步伐切换", "身法灵活", "脚步移动", "方向明确"},
    "speed_gain": {"速度提升", "反应速度", "爆发力", "节奏加快", "一气呵成"},
    "game_context": {"竞技项目", "赛场表现", "需要练习", "攻防转换"},
    "skill_precision": {"关键一招", "落点控制", "姿势标准", "肌肉记忆", "身体协调", "保持平衡"},
}

STUDY_DIMENSION_POOLS = {
    "knowledge_absorb": {"知识吸收", "理解新知", "学到新东西", "书本知识", "知识点", "学科基础", "课堂理解"},
    "memory_consolidate": {"记忆巩固", "温故知新", "理解记忆", "课后复习", "死记硬背", "复习重点", "考前复盘"},
    "note_sort": {"笔记整理", "课堂笔记", "划重点", "分组讨论", "分门别类", "系统归纳"},
    "exam_prep": {"考前准备", "刷题练习", "复习计划", "考试技巧", "反复练习", "练习节奏"},
    "problem_solving": {"举一反三", "解决问题", "逻辑思维", "难点突破", "理论应用", "动手实验", "学习方法", "学习节奏", "提炼要点", "总结规律"},
}

EMOTION_DIMENSION_POOLS = {
    "emotion_exposure": {"情感的流露", "心意难藏", "情绪外露", "态度变了", "微妙感觉", "微妙的气氛"},
    "approach_signal": {"为你考虑", "有点心动", "关系靠近", "心里有对方", "关系升温", "相处很自然"},
    "distancing_signal": {"保持距离", "关系变淡", "不再联系", "忽远忽近"},
    "inner_struggle": {"内心挣扎", "左右为难", "思绪万千", "感情的考验", "需要安全感"},
    "secret_comm": {"两人秘密", "言语试探"},
}


FESTIVAL_DIMENSION_POOLS = {
    "ritual_custom": {"传统习俗", "庆祝方式", "特定活动", "仪式感", "仪式感强", "传统活动", "民俗线索", "文化传承"},
    "season_context": {"节气风物", "时令变化", "特定日子", "氛围浓厚", "节庆氛围", "时令节点"},
    "social_scene": {"阖家团圆", "热闹气氛", "家家户户", "回家看看", "人群聚集", "家人团聚", "童年回忆", "走亲访友", "街巷热闹", "现场氛围"},
    "symbol_hint": {"共同期盼", "美好祝愿", "特殊美食", "应景食物", "装饰明显"},
}

MYTH_DIMENSION_POOLS = {
    "origin_context": {"创世传说", "源自古代", "神话源流", "上古传闻"},
    "story_structure": {"神话体系", "传说故事", "故事母题", "传说场景"},
    "entity_role": {"神仙鬼怪", "英雄人物", "奇异生灵", "人物形象", "异兽传说"},
    "fate_power": {"世代相传", "法力无边", "超自然力", "流传久远", "天地日月", "神力显化", "天命牵引"},
    "ritual_scene": {"民间信仰"},
    "symbolic_mark": {"寓意深刻", "象征意味", "天地秩序"},
    "world_view": {"想象奇特", "神异色彩"},
}

UNIVERSE_DIMENSION_POOLS = {
    "sky_location": {"夜空目标", "天区分布", "星系结构", "宇宙背景", "星云尘埃", "银河系内"},
    "scale_distance": {"浩瀚无垠", "遥远光年", "空间距离"},
    "observation": {"科学探索", "肉眼可见", "望远观测", "星图定位", "观测条件", "亮度差异"},
    "motion_cycle": {"星体运动", "周期规律", "运行方向", "天象变化"},
    "signal_feature": {"星光闪烁", "引力影响"},
    "concept": {"人类想象", "太空任务", "时空概念", "未知领域", "物理定律", "天文现象", "宇宙起源"},
}

WORK_DIMENSION_POOLS = {
    "process_norm": {"流程规范", "职场规则", "项目管理"},
    "comm_feedback": {"沟通反馈", "沟通效率", "开会讨论", "工作汇报", "写邮件"},
    "phase_review": {"阶段复盘"},
    "issue_recycle": {"问题回收", "解决问题"},
    "require_confirm": {"需求确认"},
    "schedule_push": {"排期推进", "截止日期"},
    "priority_adjust": {"优先级调整"},
    "follow_track": {"过程跟进"},
    "result_accept": {"结果验收", "KPI考核"},
    "risk_predict": {"风险预判"},
    "deliver_node": {"交付节点"},
    "plan_land": {"方案落地"},
    "cross_team": {"跨组协作", "团队合作"},
    "execute_eff": {"执行效率", "加班加点"},
    "task_split": {"任务拆分", "任务分配"},
    "resource_coord": {"资源协调"},
    "progress_sync": {"进度同步"},
    "role_boundary": {"职责边界", "上下级关系", "职业技能", "办公室里"},
}

TRAVEL_DIMENSION_POOLS = {
    "route_choice": {"路线选择", "交通方式"},
    "onsite_feel": {"现场感受", "身心放松"},
    "road_condition": {"路况变化", "在路上"},
    "itinerary_plan": {"行程安排"},
    "pace_adjust": {"节奏调整"},
    "local_insight": {"异地见闻", "当地特色", "旅行见闻", "人文景观"},
    "trip_memory": {"旅途记忆", "拍照打卡"},
    "traffic_link": {"交通衔接"},
    "departure_prep": {"出发准备", "出发前准备"},
    "walk_explore": {"步行探索", "独自旅行"},
    "return_plan": {"返程计划"},
    "stay_duration": {"停留时长"},
    "weather_effect": {"天气影响", "天气晴朗"},
    "map_locate": {"地图定位"},
    "destination_arrive": {"目的地到达"},
    "route_supply": {"途中补给"},
    "team_coord": {"同行协作"},
    "spot_experience": {"景点体验", "自然风光", "山川湖海", "景色宜人", "城市景观", "旅行的意义"},
}

SCENERY_DIMENSION_POOLS = {
    "space_depth": {"空间纵深"},
    "wind_water": {"风声水声"},
    "view_reach": {"目光所及"},
    "terrain_wave": {"地势起伏", "山川湖海"},
    "weather_state": {"天气影响", "天气晴朗"},
    "dawn_dusk": {"晨昏差异"},
    "shot_switch": {"景别转换"},
    "onsite_feel": {"现场感受", "身心放松"},
    "color_shift": {"色彩转变"},
    "natural_landform": {"自然地貌", "自然风光"},
    "near_far_layer": {"远近层次"},
    "light_shadow": {"光影变化"},
    "sky_light": {"天光条件"},
    "season_delta": {"季节差异"},
    "mountain_water_line": {"山水轮廓"},
    "field_wide": {"视野开阔", "景色宜人"},
    "ambient_tone": {"环境氛围", "旅行的意义"},
    "cloud_change": {"云层变化"},
    "human_element": {"城市景观", "人文景观", "当地特色", "拍照打卡", "在路上", "旅行见闻", "交通方式", "出发前准备", "独自旅行"},
}


IDIOM_DIMENSION_POOLS = {
    "implied_meaning": {"另有深意", "不止字面", "话外之意", "转作他义", "借指别意", "含义延展", "另层意思", "言外再指", "言外之意", "有比喻义"},
    "classical_meaning": {"古义沿用", "古时沿用"},
    "conduct_reminder": {"提醒看后果", "做事要留心", "行事多警醒", "处世别大意", "进退要谨慎", "待人留分寸", "得失要权衡", "遇事先想清", "评价行为"},
    "tone_directness": {"语气明确", "褒义或贬义", "中性词"},
    "typical_usage": {"典型用法", "用法灵活", "常用语"},
    "daily_borrow": {"生活借用"},
    "reason_concise": {"道理讲得直", "说法很明白", "一句就讲透", "讲理不绕弯", "道理说得透", "听完就懂理", "说理很清楚", "要点说得明", "富有哲理"},
    "rhetoric_color": {"修辞色彩", "书面语色彩"},
    "summary_power": {"概括力强"},
    "metaphor_sense": {"比喻意味"},
    "scene_immersion": {"情景代入", "描绘情景"},
    "culture_deposit": {"文化积淀"},
    "context_common": {"语境常见"},
    "often_quoted": {"常被引用"},
    "stance_tendency": {"态度倾向"},
    "expression_condense": {"表达凝练", "四字成语"},
    "wording_brief": {"言简意赅"},
    "meaning_stable": {"含义稳定", "结构固定"},
    "usage_scene": {"使用场景"},
}

ALLUSION_DIMENSION_POOLS = {
    "historical_record": {"史书有载", "特定背景", "有据可查", "历史事件"},
    "story_proto": {"故事原型", "事出有因", "有个故事"},
    "long_origin": {"由来已久", "形成于古代", "流传至今"},
    "classic_source": {"典籍出处", "出自古籍"},
    "implicit_meaning": {"言外含义", "背后有深意"},
    "cultural_mark": {"文化印记", "文化符号"},
    "classical_visible": {"古文可见", "书面常用"},
    "transmit_path": {"流传路径"},
    "figure_related": {"人物相关", "著名人物"},
    "moral_clear": {"寓意明确", "古人智慧"},
    "symbol_meaning": {"象征含义"},
    "event_motif": {"事件母题"},
    "scene_borrow": {"情境借用"},
    "ancient_to_now": {"借古喻今"},
    "later_quote": {"后世常引", "后人常用"},
    "history_head": {"历史源头"},
    "reality_reflect": {"现实映照", "影响深远"},
    "context_common": {"语境常用"},
    "culture_map": {"文化映射"},
    "semantic_extend": {"语义引申"},
    "source_lineage": {"出处脉络"},
    "text_clue": {"文本线索"},
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

BANNED_GENERIC = {
    "关键线索", "阶段线索", "状态线索", "情境线索", "现场变化", "过程观察", "执行过程",
    "步骤推进", "方向判断", "细节变化", "常见场景", "整体节奏", "结果走向", "临场处理",
    "过程细节", "先后顺序", "处世提醒", "说理简练", "引申含义",
}


def load_policy(repo_root: Path) -> dict:
    return json.loads((repo_root / "data/final_hint_policy_v1.json").read_text(encoding="utf-8"))


def load_game_special(repo_root: Path):
    sys.path.append(str(repo_root / "scripts"))
    import rewrite_game_hints_v29 as rg  # pylint: disable=import-error

    return rg.GAME_SPECIAL


def classify_dimension(category: str, answer: str, hint: str, game_map: dict) -> str:
    hint_n = norm(hint)
    pools = {}
    if category == "动漫":
        pools = ANIME_DIMENSION_POOLS
    elif category == "美食":
        pools = FOOD_DIMENSION_POOLS
    elif category == "游戏":
        pools = GAME_DIMENSION_POOLS
    elif category == "生活":
        pools = LIFE_DIMENSION_POOLS
    elif category == "节日":
        pools = FESTIVAL_DIMENSION_POOLS
    elif category == "神话":
        pools = MYTH_DIMENSION_POOLS
    elif category == "宇宙":
        pools = UNIVERSE_DIMENSION_POOLS
    elif category == "情感":
        pools = EMOTION_DIMENSION_POOLS
    elif category == "动作":
        pools = ACTION_DIMENSION_POOLS
    elif category == "学习":
        pools = STUDY_DIMENSION_POOLS
    elif category == "工作":
        pools = WORK_DIMENSION_POOLS
    elif category == "旅游":
        pools = TRAVEL_DIMENSION_POOLS
    elif category == "风景":
        pools = SCENERY_DIMENSION_POOLS
    elif category == "成语":
        pools = IDIOM_DIMENSION_POOLS
    elif category == "典故":
        pools = ALLUSION_DIMENSION_POOLS
    for dim, terms in pools.items():
        if hint_n in terms:
            return dim
    if category == "生活" and hint_n in {norm(x) for x in LIFE_SPECIAL.get(answer, [])}:
        if any(token in hint_n for token in ["早", "夜", "晨", "午", "点", "时"]):
            return "daily_scene"
        if any(token in hint_n for token in ["整理", "打包", "清点", "安装", "翻动", "喂食", "结算", "签收", "更换"]):
            return "action_flow"
        if any(token in hint_n for token in ["门", "柜", "站", "房", "台", "箱", "袋", "缸", "壶", "角落"]):
            return "result_feedback"
        return "sequence_habit"
    if category == "游戏" and hint_n in {norm(x) for x in game_map.get(answer, [])}:
        return "game_anchor"
    if category == "美食":
        if any(token in hint_n for token in ["卷", "串", "片", "模", "绳", "握", "架"]):
            return "food_form"
        if any(token in hint_n for token in ["翻", "刷", "现做", "出锅", "包馅", "明火"]):
            return "cooking_action"
        if any(token in hint_n for token in ["店", "摊", "桌", "盘", "碗", "节令", "聚餐", "夜宵", "饭点", "茶桌", "冷食"]):
            return "meal_scene"
        if any(token in hint_n for token in ["火", "煮", "蒸", "烤", "煎", "炸", "刷", "切", "包", "捆", "卷", "握", "压", "现做", "出锅", "包裹", "炭"]):
            return "prep_process"
        if any(token in hint_n for token in ["香", "辣", "甜", "咸", "鲜", "脆", "嫩", "滑", "润", "酥", "糯", "芥末", "醋", "孜然", "口感", "回味", "味"]):
            return "texture_flavor"
        if any(token in hint_n for token in ["吃法", "上桌", "摆盘", "主食", "常见", "拼盘", "熟客", "招牌", "餐后"]):
            return "serving_finish"
    if category == "生活":
        if any(token in hint_n for token in ["家", "居家", "日常", "起居", "片刻", "节律", "晨", "夜", "午", "高峰", "场景"]):
            return "daily_scene"
        if any(token in hint_n for token in ["按序", "顺手", "临时", "马上", "安排", "习惯", "节奏", "过渡"]):
            return "sequence_habit"
        if any(token in hint_n for token in ["动作", "步骤", "流程", "收尾", "清点", "整理", "打包", "归位", "翻动", "清理", "更换", "冲净", "喂食", "修"]):
            return "action_flow"
        if any(token in hint_n for token in ["反馈", "完成", "闭环", "用途", "效率", "可感", "恢复", "清爽", "放松", "清新", "提神"]):
            return "result_feedback"
    if category == "节日":
        if any(token in hint_n for token in ["时令", "时节", "节令", "传统时节", "节庆"]):
            return "season_context"
        if any(token in hint_n for token in ["家人", "亲友", "团圆", "走亲", "假期", "行程", "人群"]):
            return "social_scene"
        if any(token in hint_n for token in ["礼俗", "民俗", "庆典", "庆祝", "传统活动", "仪式", "习俗", "节俗"]):
            return "ritual_custom"
        if any(token in hint_n for token in ["街巷", "装饰", "布置", "灯火", "陈设", "现场"]):
            return "visual_scene"
        if any(token in hint_n for token in ["应景", "时令表达", "时令提示", "符号", "食物"]):
            return "symbol_hint"
    if category == "神话":
        if hint_n in {"上古传闻", "远古背景", "口耳相传", "神话源流"}:
            return "origin_context"
        if hint_n in {"传说场景", "古老仪式"}:
            return "ritual_scene"
        if hint_n in {"神祇相关", "奇异生灵", "异兽传说"}:
            return "entity_role"
        if hint_n in {"英雄叙事", "故事母题", "天地秩序"}:
            return "story_structure"
        if hint_n in {"祭祀痕迹", "象征意味", "神异色彩"}:
            return "symbolic_mark"
        if hint_n in {"因果轮回", "天命牵引", "神力显化"}:
            return "fate_power"
    if category == "宇宙":
        if hint_n in {"夜空目标", "天区分布", "星系结构", "宇宙背景"}:
            return "sky_location"
        if hint_n in {"天体运行", "轨道变化", "运行方向", "周期规律"}:
            return "motion_cycle"
        if hint_n in {"观测窗口", "望远观测", "观测条件", "星图定位"}:
            return "observation"
        if hint_n in {"深空尺度", "空间距离"}:
            return "scale_distance"
        if hint_n in {"光谱线索", "亮度差异", "天象变化", "引力影响"}:
            return "signal_feature"
    return "unknown"


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    data = json.loads((repo_root / "assets/puzzles.json").read_text(encoding="utf-8"))
    policy = load_policy(repo_root)
    game_map = load_game_special(repo_root)
    anime_map = json.loads((repo_root / "data/anime_guess_master_map_v1.json").read_text(encoding="utf-8"))
    food_map = json.loads((repo_root / "data/food_hint_style_map_v2.json").read_text(encoding="utf-8"))
    universal = policy.get("universal_constraints", {})

    max_chars = int(universal.get("max_chars_per_hint", 5))
    forbidden_fragments = {str(x).strip() for x in ((universal.get("natural_language_guard") or {}).get("forbidden_fragments") or [])}

    repeated_sets = collections.Counter(tuple((it.get("hints") or [])[:7]) for it in data)
    repeated_full_sets = [(list(k), v) for k, v in repeated_sets.items() if v >= 2]

    banned_generic_hits = []
    long_hint_hits = []
    fragment_hits = []
    diversity_hits = []
    adjacency_hits = []
    per_dimension_cap_hits = []

    # Festival, myth, and universe use per-answer slot7 as local strong anchor, then check front-6 leakage.
    festival_anchor_map = {}
    myth_anchor_map = {}
    universe_anchor_map = {}
    emotion_anchor_map = {}
    action_anchor_map = {}
    study_anchor_map = {}
    work_anchor_map = {}
    travel_anchor_map = {}
    scenery_anchor_map = {}
    idiom_anchor_map = {}
    allusion_anchor_map = {}
    for item in data:
        category = str(item.get("category", "")).strip()
        answer = str(item.get("answer", "")).strip()
        hints = [str(x).strip() for x in (item.get("hints") or [])[:7]]
        if not answer or len(hints) < 7 or not hints[6]:
            continue
        if category == "节日":
            festival_anchor_map[answer] = [hints[6]]
        if category == "神话":
            myth_anchor_map[answer] = [hints[6]]
        if category == "宇宙":
            universe_anchor_map[answer] = [hints[6]]
        if category == "情感":
            emotion_anchor_map[answer] = [hints[6]]
        if category == "动作":
            action_anchor_map[answer] = [hints[6]]
        if category == "学习":
            study_anchor_map[answer] = [hints[6]]
        if category == "工作":
            work_anchor_map[answer] = [hints[6]]
        if category == "旅游":
            travel_anchor_map[answer] = [hints[6]]
        if category == "风景":
            scenery_anchor_map[answer] = [hints[6]]
        if category == "成语":
            idiom_anchor_map[answer] = [hints[6]]
        if category == "典故":
            allusion_anchor_map[answer] = [hints[6]]

    early_proxy_maps = {
        "动漫": anime_map,
        "美食": food_map,
        "游戏": game_map,
        "生活": LIFE_SPECIAL,
        "节日": festival_anchor_map,
        "神话": myth_anchor_map,
        "宇宙": universe_anchor_map,
        "情感": emotion_anchor_map,
        "动作": action_anchor_map,
        "学习": study_anchor_map,
        "工作": work_anchor_map,
        "旅游": travel_anchor_map,
        "风景": scenery_anchor_map,
        "成语": idiom_anchor_map,
        "典故": allusion_anchor_map,
    }
    early_hits = {k: [] for k in early_proxy_maps}

    checked_categories = {"动漫", "游戏", "美食", "生活", "节日", "神话", "宇宙", "情感", "动作", "学习", "工作", "旅游", "风景", "成语", "典故"}

    for item in data:
        category = str(item.get("category", "")).strip()
        answer = str(item.get("answer", "")).strip()
        hints = [str(x).strip() for x in (item.get("hints") or [])[:7]]
        if category not in checked_categories:
            continue

        anchors = {norm(x) for x in early_proxy_maps[category].get(answer, [])}
        dimensions = []
        dim_counts = collections.Counter()
        for idx, hint in enumerate(hints, start=1):
            if norm(hint) in BANNED_GENERIC:
                banned_generic_hits.append({"category": category, "answer": answer, "slot": idx, "hint": hint})
            if visible_chars(hint) > max_chars:
                long_hint_hits.append({"category": category, "answer": answer, "slot": idx, "hint": hint, "length": visible_chars(hint)})
            if any(frag and frag in hint for frag in forbidden_fragments):
                fragment_hits.append({"category": category, "answer": answer, "slot": idx, "hint": hint})
            if idx <= 6 and norm(hint) in anchors:
                early_hits[category].append({"answer": answer, "slot": idx, "hint": hint, "hints": hints})
            dim = classify_dimension(category, answer, hint, game_map)
            dimensions.append(dim)
            dim_counts[dim] += 1

        known_dims = [d for d in dimensions if d != "unknown"]
        unique_known = sorted(set(known_dims))
        if len(unique_known) < 3:
            print(f"Diversity fail: {category} / {answer} -> {dimensions} -> {hints}")
            diversity_hits.append({"category": category, "answer": answer, "dimensions": dimensions, "unique_known": unique_known, "hints": hints})
        for i in range(1, len(dimensions)):
            if dimensions[i] != "unknown" and dimensions[i] == dimensions[i - 1]:
                adjacency_hits.append({"category": category, "answer": answer, "slots": [i, i + 1], "dimension": dimensions[i], "hints": [hints[i - 1], hints[i]]})
        for dim, count in dim_counts.items():
            if dim != "unknown" and count > 2:
                per_dimension_cap_hits.append({"category": category, "answer": answer, "dimension": dim, "count": count, "hints": hints})

    report = {
        "items": len(data),
        "checked_categories": sorted(checked_categories),
        "repeated_full_set_count": len(repeated_full_sets),
        "repeated_full_sets": repeated_full_sets[:100],
        "banned_generic_hit_count": len(banned_generic_hits),
        "banned_generic_hits": banned_generic_hits[:200],
        "max_char_exceeded_count": len(long_hint_hits),
        "max_char_exceeded_hits": long_hint_hits[:200],
        "forbidden_fragment_hit_count": len(fragment_hits),
        "forbidden_fragment_hits": fragment_hits[:200],
        "dimension_diversity_hit_count": len(diversity_hits),
        "dimension_diversity_hits": diversity_hits[:200],
        "adjacent_same_dimension_hit_count": len(adjacency_hits),
        "adjacent_same_dimension_hits": adjacency_hits[:200],
        "per_dimension_cap_hit_count": len(per_dimension_cap_hits),
        "per_dimension_cap_hits": per_dimension_cap_hits[:200],
        "early_anchor_proxy": {
            cat: {
                "offender_count": len(early_hits[cat]),
                "offenders": early_hits[cat][:200],
            }
            for cat in sorted(early_hits)
        },
    }

    out = repo_root / "tmp/selfcheck_hint_skill_v2.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    fail = []
    if report["repeated_full_set_count"]:
        fail.append(f"repeated_full_set_count={report['repeated_full_set_count']}")
    if report["banned_generic_hit_count"]:
        fail.append(f"banned_generic_hit_count={report['banned_generic_hit_count']}")
    if report["max_char_exceeded_count"]:
        fail.append(f"max_char_exceeded_count={report['max_char_exceeded_count']}")
    if report["forbidden_fragment_hit_count"]:
        fail.append(f"forbidden_fragment_hit_count={report['forbidden_fragment_hit_count']}")
    if report["dimension_diversity_hit_count"]:
        fail.append(f"dimension_diversity_hit_count={report['dimension_diversity_hit_count']}")
    if report["adjacent_same_dimension_hit_count"]:
        fail.append(f"adjacent_same_dimension_hit_count={report['adjacent_same_dimension_hit_count']}")
    if report["per_dimension_cap_hit_count"]:
        fail.append(f"per_dimension_cap_hit_count={report['per_dimension_cap_hit_count']}")
    for cat, payload in report["early_anchor_proxy"].items():
        if payload["offender_count"]:
            fail.append(f"early_anchor_proxy_{cat}={payload['offender_count']}")

    print(f"report={out}")
    if fail:
        print("result=FAIL")
        print("reasons=" + ", ".join(fail))
        return 1
    print("result=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
