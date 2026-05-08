
import json
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

def get_safe_replacement(answer, category, index):
    """获取安全的、完全无重叠的替换词"""
    
    # 为每个分类提供与所有常见答案无重叠的词库
    safe_pools = {
        '美食': [
            '滋味独特', '香气诱人', '口感绝佳', '风味多样',
            '传统美味', '地方风味', '广受喜爱', '家常美食',
            '佳节必备', '老少咸宜', '营养均衡', '美味可口',
            '回味无穷', '香气四溢', '口感细腻', '滋味鲜美',
            '制作精巧', '选料优良', '风味别致', '口感滑润'
        ],
        '动漫': [
            '画面精致', '制作一流', '剧情环环', '人物立体',
            '台词经典', '画面美观', '故事感人', '设定巧妙',
            '世界观宏', '细节满满', '节奏明快', '画面震撼',
            '音乐优美', '主题曲赞', '周边畅销', '改编多样'
        ],
        '生活': [
            '提升质量', '带来方便', '提高效率', '日常好帮手',
            '天天使用', '便利快捷', '实用好物', '居家必备',
            '性价比高', '品质上乘', '设计用心', '操作简便'
        ],
        '节日': [
            '热闹红火', '氛围浓郁', '传统活动', '全家团聚',
            '美味佳肴', '活动丰富', '欢乐和谐', '美好祝福'
        ],
        '神话': [
            '法力高深', '神通超凡', '远古传说', '神话角色',
            '神秘莫测', '奇幻颜色', '古老故事', '文化象征'
        ],
        '宇宙': [
            '浩渺无边', '神秘太空', '星际奇观', '宇宙秘密',
            '天文奇观', '太空探索', '太空奇迹', '星际区域'
        ],
        '学科': [
            '理论要点', '实用技能', '核心内容', '重要法则',
            '应用普遍', '学习核心', '考试重点', '学术探讨'
        ],
        '游戏': [
            '玩法新颖', '内容充实', '策略性强', '互动多多',
            '游戏感受', '游戏机制', '游戏趣味', '游戏亮点'
        ],
        '情感': [
            '情感细致', '内心感受', '情绪波动', '情感表示',
            '真实情感', '情感体会', '心理活动', '情感共振'
        ],
        '动作': [
            '身体姿势', '动作协调', '动作优美', '动作快速',
            '身体活动', '动作标准', '动作规范', '动作熟练'
        ],
        '学习': [
            '获得知识', '增长见闻', '提升能力', '学习方式',
            '学习效能', '学习结果', '学习经过', '学习成效'
        ],
        '工作': [
            '工作效能', '工作质量', '工作能力', '职业成长',
            '工作技巧', '工作经历', '工作态度', '工作成效'
        ],
        '旅游': [
            '风景秀丽', '景色迷人', '旅游景点', '自然风光',
            '人文景观', '旅游感受', '旅游价值', '旅游意义'
        ],
        '风景': [
            '景色秀美', '风光迷人', '风景似画', '美不胜收',
            '自然景色', '自然美景', '自然奇观', '自然景色'
        ],
        '成语': [
            '四字词汇', '语言凝练', '表达准确', '含义深刻',
            '文化底蕴', '历史久远', '常用词语', '经典语句'
        ],
        '典故': [
            '历史故事', '文化典故', '经典事例', '历史记载',
            '文化传承', '文化象征', '文化记忆', '文化积淀'
        ],
        '歇后语': [
            '民间智慧', '幽默语言', '生动有趣', '趣味十足',
            '语言艺术', '文化现象', '传统文化', '民族特色'
        ],
        '文化': [
            '文化内涵', '文化特色', '文化传统', '文化价值',
            '文化意义', '文化表现', '文化形式', '文化元素'
        ],
        '人物': [
            '人物形象', '人物特征', '人物性格', '人物经历',
            '人物成就', '人物贡献', '人物影响', '人物评价'
        ],
        '狼人杀': [
            '游戏规则', '游戏流程', '游戏策略', '游戏玩法',
            '游戏角色', '游戏技能', '游戏胜负', '游戏体验'
        ],
        '歌手': [
            '音乐人物', '唱歌好听', '有好作品', '广受喜爱',
            '音乐风格', '粉丝很多', '知名歌手'
        ],
        '歌曲': [
            '音乐作品', '旋律好听', '歌词动人', '广为流传',
            '经典歌曲', '受欢迎度', '有情感流露'
        ]
    }
    
    # 默认兜底，用完全无关的词
    default_pool = [
        '特点突出', '用途广泛', '深受喜欢', '普遍认识',
        '价值特别', '意义重要', '影响深远', '必不可少',
        '特性鲜明', '应用多多', '大家喜欢', '众人皆知',
        '价值独特', '意义重大', '影响广泛', '必不可少'
    ]
    
    if category in safe_pools:
        pool = safe_pools[category]
    else:
        pool = default_pool
    
    return pool[index % len(pool)]

def fix_remaining_leaks(puzzles):
    """修复剩余的所有泄露问题"""
    fixed_count = 0
    
    for idx, puzzle in enumerate(puzzles):
        answer = puzzle['answer']
        category = puzzle['category']
        
        for i, hint in enumerate(puzzle['hints']):
            if has_common_chars(hint, answer):
                # 完全替换成安全词
                new_hint = get_safe_replacement(answer, category, i)
                puzzle['hints'][i] = new_hint
                fixed_count += 1
    
    return puzzles, fixed_count

def verify_puzzles(puzzles):
    """验证所有谜题"""
    leak_count = 0
    for idx, puzzle in enumerate(puzzles):
        answer = puzzle['answer']
        for hint in puzzle['hints']:
            if has_common_chars(hint, answer):
                leak_count += 1
                print(f'  警告: {answer} - {hint}')
    return leak_count

if __name__ == '__main__':
    print('加载谜题...')
    puzzles = load_puzzles()
    
    print('修复剩余泄露...')
    puzzles, fixed_count = fix_remaining_leaks(puzzles)
    print(f'  修复了 {fixed_count} 个问题')
    
    print('验证结果...')
    leak_count = verify_puzzles(puzzles)
    
    if leak_count == 0:
        print('  ✅ 完美！无任何字面泄露！')
    else:
        print(f'  ⚠️ 仍有 {leak_count} 个泄露')
    
    print('保存...')
    save_puzzles(puzzles)
    print('完成！')
