import json
from pathlib import Path

PUZZLES_PATH = Path('assets/puzzles.json')

OVERRIDES = {
    '相声': ['说学逗唱', '包袱', '逗哏', '捧哏', '曲艺', '语言表演', '舞台对口'],
    '评书': ['说书', '故事演述', '长篇讲述', '醒木', '口技', '曲艺', '单人表演'],
    '昆曲': ['戏曲', '唱腔', '水磨腔', '折子戏', '身段', '舞台程式', '古老戏种'],
    '戏曲': ['唱念做打', '角色行当', '脸谱', '舞台程式', '唱腔', '昆曲', '传统戏剧'],
    '京剧': ['戏曲', '国粹', '唱念做打', '净角', '脸谱', '越剧', '传统戏剧'],
    '评弹': ['说唱', '弹词', '三弦', '琵琶', '坐唱演述', '吴语', '曲艺'],
    '皮影': ['影偶', '幕后操纵', '灯光幕布', '民间戏', '剪影', '传统表演', '影子戏'],
    '木偶': ['偶戏', '提线', '杖头木偶', '舞台操偶', '角色造型', '传统表演', '民间戏'],
    '社火': ['民俗活动', '锣鼓', '节庆表演', '舞狮', '踩高跷', '巡游', '热闹场面'],
    '灯谜': ['猜谜', '元宵', '字谜', '谜面', '谜底', '民俗活动', '节庆互动'],
}


def clean_hint(answer: str, hints: list[str]) -> list[str]:
    out = []
    seen = set()
    for h in hints:
        txt = str(h).strip()
        if not txt or txt == answer:
            continue
        if txt in seen:
            continue
        seen.add(txt)
        out.append(txt)
        if len(out) >= 7:
            break
    return out


def main() -> None:
    data = json.loads(PUZZLES_PATH.read_text(encoding='utf-8'))
    changed = 0

    for item in data:
        answer = str(item.get('answer', '')).strip()
        category = str(item.get('category', '')).strip()
        if category != '文化':
            continue
        if answer in OVERRIDES:
            old_hints = item.get('hints') or []
            new_hints = clean_hint(answer, OVERRIDES[answer])
            if len(new_hints) < 7:
                # fallback from old hints
                for h in old_hints:
                    if len(new_hints) >= 7:
                        break
                    txt = str(h).strip()
                    if txt and txt != answer and txt not in new_hints:
                        new_hints.append(txt)
            if old_hints != new_hints:
                item['hints'] = new_hints
                changed += 1

    PUZZLES_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'changed={changed}')
    print(f'written={PUZZLES_PATH}')


if __name__ == '__main__':
    main()
