import csv
import random
from pathlib import Path

FIELDNAMES = ['id', 'answer', 'user_input', 'score_0_100', 'relation_tag', 'reason']
OUTPUT = Path('data/function_word_pairs_v28.csv')

def main():
    seen = set()
    rows = []

    def push(a, b, score, tag, reason):
        for ans, inp in [(a, b), (b, a)]:
            key = (ans, inp)
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                'answer': ans, 'user_input': inp,
                'score_0_100': str(score),
                'relation_tag': tag, 'reason': reason,
            })

    # === 助词互相配对 ===
    particles = ['的', '了', '吗', '呢', '吧', '啊', '呀', '哦', '嘛', '呗']
    for i, a in enumerate(particles):
        for j, b in enumerate(particles):
            if i < j:
                push(a, b, 5, 'function_word_low', '虚词之间无语义关联')

    # === 代词互相配对 ===
    pronouns = ['我', '你', '他', '她', '它', '这', '那', '谁', '什', '哪']
    for i, a in enumerate(pronouns):
        for j, b in enumerate(pronouns):
            if i < j:
                push(a, b, 5, 'function_word_low', '代词之间无语义关联')

    # === 数词互相配对 ===
    numbers = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十', '百', '千', '万']
    for i, a in enumerate(numbers):
        for j, b in enumerate(numbers):
            if i < j:
                push(a, b, 5, 'function_word_low', '数词之间无语义关联')

    # === 量词互相配对 ===
    classifiers = ['个', '只', '条', '本', '张', '把', '块', '片', '朵', '颗', '粒', '件', '双', '对', '批']
    for i, a in enumerate(classifiers):
        for j, b in enumerate(classifiers):
            if i < j:
                push(a, b, 5, 'function_word_low', '量词之间无语义关联')

    # === 连词/介词互相配对 ===
    conj_prep = ['和', '与', '或', '但', '而', '因', '所', '从', '在', '到', '向', '为', '被', '把', '给', '比']
    for i, a in enumerate(conj_prep):
        for j, b in enumerate(conj_prep):
            if i < j:
                push(a, b, 5, 'function_word_low', '连词/介词之间无语义关联')

    # === 虚词 vs 实词 ===
    real_words = ['猫', '狗', '火锅', '学校', '开心', '医生', '苹果', '足球',
                  '月亮', '春天', '雷电', '森林', '大海', '山脉', '天空',
                  '唱歌', '跑步', '跳舞', '游泳', '飞', '吃', '喝', '睡']
    all_func = particles + pronouns + numbers[:5] + classifiers[:5]
    for fw in all_func:
        for rw in real_words:
            push(fw, rw, 3, 'function_word_vs_real_low', '虚词vs实词语义无关')

    # === 双字虚词 ===
    func_2char = [
        ('什么', '怎么', 5, 'function_word_low', '疑问代词之间'),
        ('哪里', '什么', 5, 'function_word_low', '疑问代词之间'),
        ('怎么', '为什么', 5, 'function_word_low', '疑问代词之间'),
        ('这个', '那个', 8, 'function_word_low', '指示代词之间'),
        ('他们', '我们', 5, 'function_word_low', '人称代词复数之间'),
        ('自己', '别人', 8, 'function_word_low', '反身代词vs他人'),
        ('可以', '应该', 8, 'function_word_low', '情态动词之间'),
        ('如果', '因为', 5, 'function_word_low', '连词之间'),
        ('但是', '所以', 5, 'function_word_low', '连词之间'),
        ('然后', '接着', 10, 'function_word_low', '连接副词之间'),
        ('已经', '正在', 10, 'function_word_low', '时间副词之间'),
        ('非常', '特别', 15, 'function_word_low', '程度副词之间(弱关联)'),
        ('真的', '假的', 10, 'function_word_low', '肯定/否定副词'),
        ('不是', '没有', 5, 'function_word_low', '否定词之间'),
        ('可以', '不能', 8, 'function_word_low', '能愿动词对比'),
        ('知道', '觉得', 10, 'function_word_low', '认知动词(弱关联)'),
        ('还是', '或者', 8, 'function_word_low', '选择连词之间'),
        ('虽然', '但是', 8, 'function_word_low', '转折连词之间'),
        ('因为', '所以', 8, 'function_word_low', '因果连词之间'),
    ]
    for a, b, score, tag, reason in func_2char:
        push(a, b, score, tag, reason)

    # === 双字虚词 vs 实词 ===
    func_2char_words = ['什么', '怎么', '哪里', '为什么', '这个', '那个',
                        '他们', '我们', '自己', '可以', '应该', '如果',
                        '因为', '但是', '所以', '然后', '已经', '正在']
    real_2char = ['火锅', '学校', '开心', '医生', '苹果', '足球',
                  '月亮', '春天', '森林', '大海', '唱歌', '跑步']
    for fw in func_2char_words:
        for rw in real_2char[:4]:
            push(fw, rw, 3, 'function_word_vs_real_low', '虚词vs实词语义无关')

    random.seed(20260515)
    random.shuffle(rows)
    for i, row in enumerate(rows, 1):
        row['id'] = str(i)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f'function_word_pairs_v28: {len(rows)} rows')

if __name__ == '__main__':
    main()
