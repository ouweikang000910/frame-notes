import csv
import io


def timestamp(seconds):
    return f'{int(seconds // 60):02d}:{seconds % 60:05.2f}'


LABELS = [('topic', '主题'), ('audience', '目标人群'), ('hook', '开头钩子'), ('structure', '内容结构'),
          ('rhythm', '节奏特点'), ('observations', '基于视频的观察'), ('takeaways', '可借鉴的创作方法'), ('uncertainties', '待核对项')]


def markdown(doc):
    lines = [f'# {doc["title"]}', '', f'视频时长：{timestamp(doc["duration"])}',
             f'来源：{doc["source_url"] or "本地上传"}', '', '## 整体分析', '']
    for key, label in LABELS:
        lines.extend([f'### {label}', '', (doc['overview'] or {}).get(key, '待核对'), ''])
    lines.extend(['## 带时间戳的文案', ''])
    for sentence in doc['transcript']:
        lines.append(f'- **{timestamp(sentence["start"])}–{timestamp(sentence["end"])}** {sentence["text"]}')
    if not doc['transcript']:
        lines.append('未识别到语音。')
    lines.extend(['', '## 分镜拆解', ''])
    for index, shot in enumerate(doc['shots']):
        lines.extend([f'### {index + 1}. {timestamp(shot["start"])}–{timestamp(shot["end"])}', '',
                      f'画面：{shot["description"]}', '', f'文案：{shot["text"] or "无语音"}', '',
                      f'段落作用：{shot["role"]}', '', f'节奏：{shot["rhythm"]}', '',
                      f'核对状态：{"待核对" if shot.get("uncertain") else "AI分析，建议对照视频核对"}', ''])
    return '\n'.join(lines).encode('utf-8')


def csv_safe(value):
    text = str(value)
    # Keep editable prose from being interpreted as a spreadsheet formula.
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) else text


def storyboard_csv(doc):
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(['序号', '开始时间', '结束时间', '开始秒数', '结束秒数', '画面描述', '对应文案', '段落作用', '节奏分析', '待核对'])
    for index, shot in enumerate(doc['shots']):
        writer.writerow([index + 1, timestamp(shot['start']), timestamp(shot['end']), shot['start'], shot['end'],
                         *(csv_safe(shot[key]) for key in ('description', 'text', 'role', 'rhythm')),
                         '是' if shot.get('uncertain') else '否'])
    return output.getvalue().encode('utf-8-sig')

