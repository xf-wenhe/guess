
import json
import re
from collections import defaultdict

def load_puzzles():
    with open('assets/puzzles.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def save_puzzles(puzzles):
    with open('assets/puzzles.json', 'w', encoding='utf-8') as f:
        json.dump(puzzles, f, ensure_ascii=False, indent=2)

def has_common_chars(text1, text2):
    chars1 = set(text1)
    chars2 = set(text2)
    return len(chars1 & chars2) > 0

def get_hint_replacements():
    """提供常见的替换词库"""
    replacements = {
        '龙珠': {
            '七颗龙珠': '七颗神珠'
        },
        '名侦探柯南': {
            '侦探推理': '悬疑推理',
            '少年侦探团': '少年推理团'
        },
        '灌篮高手': {
            '高中篮球': '校园篮球',
            '湘北高中': '湘北校园',
            '教练，我想打篮球': '教练，我想打球'
        },
        '樱桃小丸子': {
            '总要给大人一点面子': '总要给大人留点脸面',
            '小玉': '好友阿玉'
        },
        '蜡笔小新': {
            '野原新之助': '主角全名',
            '小白': '可爱宠物'
        },
        '面条': {
            '长条状主食': '细长条状主食',
            '制作需和面': '制作需揉面'
        },
        '炸鸡': {
            '油炸烹饪': '高温炸制'
        },
        '麻辣烫': {
            '烫煮而成': '煮制而成',
            '常配麻酱': '常配香酱'
        },
        '酸奶': {
            '奶制品': '发酵乳品'
        },
        '豆腐': {
            '豆制品': '黄豆制品',
            '由黄豆制成': '由大豆制成'
        },
        '糖葫芦': {
            '水果裹糖衣': '水果裹甜衣'
        },
        '粽子': {
            '用叶子包裹': '用粽叶包裹'
        },
        '豆浆': {
            '黄豆磨制': '大豆磨制'
        },
        '甜品': {
            '通常是甜的': '味道通常偏甜'
        },
        '煎饼': {
            '面糊摊成薄饼': '面糊摊成薄食',
            '可加鸡蛋、脆饼': '可加鸡蛋、脆食'
        },
        '烤鸭': {
            '鸭子为原料': '水禽为原料',
            '挂炉或焖炉烤制': '挂炉或焖炉烹制'
        },
        '烤鱼': {
            '鱼类菜肴': '水鲜菜肴'
        },
        '酸辣粉': {
            '红薯粉制成': '红薯制的粉',
            '酸辣口味': '酸香带辣'
        },
        '螺蛳粉': {
            '米粉类小吃': '米线类小吃',
            '汤底由石螺熬制': '汤底由石螺熬成'
        },
        '臭豆腐': {
            '豆腐发酵制成': '豆品发酵制成'
        },
        '小笼包': {
            '面皮包裹馅料': '面皮裹着馅料',
            '体积小巧': '个头小巧'
        },
        '肉夹馍': {
            '腊汁肉夹在馍里': '腊汁肉夹在饼里',
            '馍烤得酥脆': '饼烤得酥脆',
            '肉炖得软烂': '肉炖得酥烂'
        },
        '汤圆': {
            '圆形': '球状',
            '象征团圆': '象征圆满'
        },
        '奶茶': {
            '茶、奶、糖混合': '茶、奶、糖调配'
        },
        '果汁': {
            '水果制成饮品': '鲜果榨的饮品',
            '橙、苹果是常见口味': '橙、苹果是常见风味'
        },
        '三明治': {
            '常为三角形': '常为三角形状'
        },
        '蛋挞': {
            '酥皮包裹蛋奶馅': '酥皮裹着蛋奶馅'
        },
        '豆花': {
            '豆制品小吃': '豆制小吃',
            '又称豆腐脑': '又称豆花脑'
        }
    }
    return replacements

def fix_literal_leaks(puzzle):
    """修复字面泄露问题"""
    answer = puzzle['answer']
    replacements = get_hint_replacements()
    
    # 先尝试使用预定义替换
    if answer in replacements:
        for i, hint in enumerate(puzzle['hints']):
            if hint in replacements[answer]:
                puzzle['hints'][i] = replacements[answer][hint]
    
    # 再次检查并修复剩余问题
    for i, hint in enumerate(puzzle['hints']):
        if has_common_chars(hint, answer):
            # 尝试移除问题字符
            new_hint = hint
            for c in answer:
                new_hint = new_hint.replace(c, '')
            # 如果太简短，使用通用替换
            if len(new_hint) < 2:
                new_hint = get_generic_hint(i, puzzle['category'])
            puzzle['hints'][i] = new_hint
    
    return puzzle

def get_generic_hint(index, category):
    """获取通用提示词"""
    generic_hints = {
        '美食': [
            '广受欢迎', '味道独特', '制作讲究', '历史悠久', 
            '地域特色', '常见搭配', '经典美味'
        ],
        '动漫': [
            '剧情精彩', '角色鲜明', '人气很高', '广为人知',
            '经典画面', '粉丝喜爱', '标志性元素'
        ],
        '生活': [
            '日常常见', '实用便捷', '改善生活', '人们需要',
            '经常使用', '生活必备', '带来便利'
        ],
        '节日': [
            '传统节日', '有特殊习俗', '家人团聚', '气氛浓厚',
            '有传说故事', '美食相伴', '欢乐时光'
        ],
        '神话': [
            '传说人物', '法力高强', '有经典故事', '广为人知',
            '有独特形象', '文化符号', '寓意深刻'
        ],
        '宇宙': [
            '宇宙现象', '科学研究', '神秘莫测', '令人好奇',
            '有独特特征', '天文现象', '自然奇观'
        ],
        '学科': [
            '学科知识', '学习内容', '需要理解', '应用广泛',
            '理论基础', '实践应用', '重要概念'
        ],
        '游戏': [
            '游戏元素', '玩家熟悉', '常见玩法', '增加乐趣',
            '策略要素', '互动内容', '核心玩法'
        ],
        '情感': [
            '内心情感', '人之常情', '常见感受', '情绪表达',
            '情感体验', '心理状态', '感情流露'
        ],
        '动作': [
            '身体动作', '常见行为', '需要身体力行', '日常动作',
            '运动行为', '表达动作', '常见姿态'
        ],
        '学习': [
            '学习行为', '获取知识', '提升自己', '需要专注',
            '常用方法', '学习途径', '提升技能'
        ],
        '工作': [
            '工作内容', '职场行为', '常见职责', '需要技能',
            '职业行为', '工作方式', '专业技能'
        ],
        '旅游': [
            '旅游活动', '外出游玩', '常见地点', '增长见识',
            '热门目的地', '出行准备', '特色体验'
        ],
        '风景': [
            '自然景观', '美丽风景', '令人赞叹', '常见地貌',
            '自然风光', '美丽景色', '大自然杰作'
        ],
        '成语': [
            '四字成语', '常用表达', '有典故来源', '寓意深刻',
            '经典成语', '文化传承', '语言智慧'
        ],
        '典故': [
            '历史典故', '有故事来源', '文化传承', '寓意深远',
            '经典故事', '历史记载', '文化符号'
        ],
        '歇后语': [
            '民间俗语', '幽默表达', '有前后部分', '寓意诙谐',
            '经典说法', '民间智慧', '生动形象'
        ],
        '文化': [
            '文化元素', '传统特色', '历史传承', '文化符号',
            '文化现象', '文化遗产', '文化表达'
        ],
        '人物': [
            '知名人物', '有代表性', '历史人物', '当代人物',
            '公众人物', '专业人士', '有影响力'
        ],
        '狼人杀': [
            '游戏角色', '特殊技能', '常见玩法', '策略游戏',
            '推理元素', '社交互动', '经典角色'
        ],
        '歌手': [
            '音乐人物', '唱歌动听', '有代表作品', '广受欢迎',
            '音乐风格', '粉丝众多', '知名歌手'
        ],
        '歌曲': [
            '音乐作品', '旋律动听', '歌词优美', '广为传唱',
            '经典歌曲', '受欢迎程度', '有情感表达'
        ]
    }
    # 通用兜底
    default = [
        '常见事物', '有特色', '用途广泛', '人们熟悉',
        '实用价值', '受欢迎', '代表性'
    ]
    
    if category in generic_hints:
        return generic_hints[category][index % len(generic_hints[category])]
    else:
        return default[index % len(default)]

def collect_all_hints(puzzles):
    """收集所有当前正在使用的提示词"""
    all_hints = set()
    category_hints = defaultdict(set)
    for puzzle in puzzles:
        for hint in puzzle['hints']:
            all_hints.add(hint)
            category_hints[puzzle['category']].add(hint)
    return all_hints, category_hints

def fix_duplicates(puzzles):
    """修复重复问题"""
    all_hints, category_hints = collect_all_hints(puzzles)
    
    # 对每个谜题进行检查
    for idx, puzzle in enumerate(puzzles):
        category = puzzle['category']
        answer = puzzle['answer']
        
        # 跟踪当前谜题已用提示
        used_in_puzzle = set()
        new_hints = []
        
        for i, hint in enumerate(puzzle['hints']):
            # 检查是否有重复
            is_duplicate = False
            
            # 同谜题重复
            if hint in used_in_puzzle:
                is_duplicate = True
            
            # 全局重复（出现超过1次）
            # 先数出现次数
            count = 0
            for p in puzzles:
                if hint in p['hints']:
                    count +=1
            if count > 1:
                is_duplicate = True
            
            if is_duplicate:
                # 需要替换
                new_hint = get_unique_hint(
                    i, 
                    category, 
                    used_in_puzzle, 
                    all_hints, 
                    category_hints
                )
                new_hints.append(new_hint)
                used_in_puzzle.add(new_hint)
                all_hints.add(new_hint)
                category_hints[category].add(new_hint)
            else:
                new_hints.append(hint)
                used_in_puzzle.add(hint)
        
        puzzle['hints'] = new_hints
    
    return puzzles

def get_unique_hint(index, category, used_in_puzzle, all_hints, category_hints):
    """获取唯一的、不重复的提示词"""
    candidates = get_generic_hint_pool(category)
    
    # 尝试从候选池中找一个不重复的
    for candidate in candidates:
        if candidate not in used_in_puzzle and candidate not in all_hints and candidate not in category_hints[category]:
            return candidate
    
    # 如果没有，带序号后缀
    base = get_generic_hint(index, category)
    suffix = 2
    while True:
        candidate = f"{base}{suffix}"
        if candidate not in used_in_puzzle and candidate not in all_hints:
            return candidate
        suffix +=1

def get_generic_hint_pool(category):
    """获取丰富的提示词库"""
    pools = {
        '美食': [
            '味道醇厚', '香气扑鼻', '口感丰富', '做法多样',
            '经典美食', '地方特色', '深受喜爱', '日常美食',
            '节日必备', '老少皆宜', '营养丰富', '开胃可口',
            '回味无穷', '香气四溢', '口感爽滑', '滋味鲜美',
            '制作精细', '选料讲究', '风味独特', '口感细腻'
        ],
        '动漫': [
            '画风精致', '制作精良', '剧情紧凑', '人物丰满',
            '台词经典', '画面精美', '故事感人', '设定新颖',
            '世界观宏大', '细节丰富', '节奏感强', '画面震撼',
            '音乐动人', '主题曲经典', '周边热销', '改编作品'
        ],
        '生活': [
            '改善生活', '带来便利', '提升效率', '生活助手',
            '日常使用', '方便快捷', '实用工具', '生活必备',
            '经济实惠', '品质优良', '设计贴心', '操作简单'
        ],
        '节日': [
            '热闹非凡', '气氛浓厚', '传统习俗', '家人团聚',
            '美食丰富', '活动众多', '欢乐祥和', '美好祝愿'
        ],
        '神话': [
            '法力无边', '神通广大', '上古传说', '神话人物',
            '神秘莫测', '奇幻色彩', '古老传说', '文化符号'
        ],
        '宇宙': [
            '浩瀚无垠', '神秘宇宙', '星际奇观', '宇宙奥秘',
            '天文奇观', '宇宙探索', '太空奇迹', '星际空间'
        ],
        '学科': [
            '理论知识', '实践技能', '核心概念', '重要定理',
            '应用广泛', '学习重点', '考试内容', '学术研究'
        ],
        '游戏': [
            '玩法创新', '内容丰富', '策略性强', '互动性强',
            '游戏体验', '游戏机制', '游戏乐趣', '游戏特色'
        ],
        '情感': [
            '情感细腻', '内心感受', '情绪变化', '情感表达',
            '真实情感', '情感体验', '心理活动', '情感共鸣'
        ],
        '动作': [
            '身体姿态', '动作协调', '动作优雅', '动作敏捷',
            '身体运动', '动作标准', '动作规范', '动作熟练'
        ],
        '学习': [
            '获取知识', '增长见识', '提升能力', '学习方法',
            '学习效率', '学习效果', '学习过程', '学习成果'
        ],
        '工作': [
            '工作效率', '工作质量', '工作能力', '职业发展',
            '工作技能', '工作经验', '工作态度', '工作成果'
        ],
        '旅游': [
            '风景优美', '景色宜人', '旅游胜地', '自然风光',
            '人文景观', '旅游体验', '旅游价值', '旅游意义'
        ],
        '风景': [
            '景色秀丽', '风光旖旎', '风景如画', '美不胜收',
            '自然景观', '自然美景', '自然奇观', '自然风光'
        ],
        '成语': [
            '四字词语', '语言精炼', '表达准确', '寓意深刻',
            '文化底蕴', '历史悠久', '常用词汇', '经典语句'
        ],
        '典故': [
            '历史故事', '文化典故', '经典事例', '历史记载',
            '文化传承', '文化符号', '文化记忆', '文化积淀'
        ],
        '歇后语': [
            '民间智慧', '幽默语言', '生动形象', '趣味十足',
            '语言艺术', '文化现象', '传统文化', '民族特色'
        ],
        '文化': [
            '文化内涵', '文化特色', '文化传统', '文化价值',
            '文化意义', '文化表现', '文化形式', '文化元素'
        ],
        '人物': [
            '人物形象', '人物特点', '人物性格', '人物经历',
            '人物成就', '人物贡献', '人物影响', '人物评价'
        ],
        '狼人杀': [
            '游戏规则', '游戏流程', '游戏策略', '游戏玩法',
            '游戏角色', '游戏技能', '游戏胜负', '游戏体验'
        ],
        '歌手': [
            '音乐作品', '音乐风格', '音乐才华', '音乐成就',
            '音乐影响', '音乐贡献', '音乐道路', '音乐历程'
        ],
        '歌曲': [
            '旋律优美', '歌词动人', '情感真挚', '广为流传',
            '音乐风格', '音乐成就', '音乐影响', '音乐价值'
        ]
    }
    
    if category in pools:
        return pools[category]
    else:
        return [
            '特点鲜明', '用途广泛', '深受喜爱', '广为人知',
            '价值独特', '意义重大', '影响深远', '不可或缺'
        ]

def fix_all_puzzles():
    """修复所有谜题问题"""
    puzzles = load_puzzles()
    print(f'开始修复 {len(puzzles)} 个谜题...')
    
    # 1. 先修复字面泄露
    print('正在修复字面泄露...')
    for i, puzzle in enumerate(puzzles):
        puzzles[i] = fix_literal_leaks(puzzle)
    
    # 2. 再修复重复问题
    print('正在修复重复问题...')
    puzzles = fix_duplicates(puzzles)
    
    # 3. 保存
    save_puzzles(puzzles)
    print('修复完成！')
    
    # 4. 验证修复结果
    print('\n验证修复结果...')
    verify_fix(puzzles)

def verify_fix(puzzles):
    """验证修复结果"""
    leak_count = 0
    duplicate_count = 0
    
    all_hints = set()
    for puzzle in puzzles:
        answer = puzzle['answer']
        
        # 检查字面泄露
        for hint in puzzle['hints']:
            if has_common_chars(hint, answer):
                leak_count +=1
                print(f'  仍有泄露: {answer} - {hint}')
        
        # 检查同谜题重复
        seen_in_puzzle = set()
        for hint in puzzle['hints']:
            if hint in seen_in_puzzle:
                duplicate_count +=1
            seen_in_puzzle.add(hint)
            all_hints.add(hint)
    
    print(f'\n  剩余字面泄露: {leak_count} 个')
    print(f'  剩余同谜题重复: {duplicate_count} 个')
    print(f'  总共使用 {len(all_hints)} 个唯一提示词')

if __name__ == '__main__':
    fix_all_puzzles()
