"""Export actual visible interactions from one project session, without reconstruction."""

import argparse
import hashlib
import html
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


def local_time(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')


def message_text(payload):
    return '\n'.join(part.get('text', '') for part in payload.get('content', []) if part.get('type') in {'input_text', 'output_text'})


def export(source):
    data = source.read_bytes()
    rows, incomplete = [], False
    lines = data.splitlines()
    for position, line in enumerate(lines, 1):
        try:
            rows.append((position, json.loads(line)))
        except json.JSONDecodeError:
            if position != len(lines):
                raise
            incomplete = True
    metadata = rows[0][1]
    if metadata.get('type') != 'session_meta' or Path(metadata['payload']['cwd']).resolve() != ROOT:
        raise ValueError('Only the selected project session can be exported')
    final_positions = set()
    for position, row in rows:
        if row.get('type') == 'event_msg' and row.get('payload', {}).get('type') == 'task_complete':
            final_text = row['payload'].get('last_agent_message')
            for earlier_position, earlier in reversed(rows[:position - 1]):
                payload = earlier.get('payload', {})
                if earlier.get('type') == 'response_item' and payload.get('role') == 'assistant' and message_text(payload) == final_text:
                    final_positions.add(earlier_position)
                    break
    model = '未记录'
    models, excluded, selected = set(), Counter(), []
    for position, row in rows:
        if row['type'] == 'turn_context':
            model = row['payload'].get('model', model)
            models.add(model)
        if row['type'] != 'response_item':
            excluded[row['type']] += 1
            continue
        payload = row['payload']
        kind = payload.get('type')
        visible = kind in {'function_call', 'function_call_output', 'custom_tool_call', 'custom_tool_call_output'}
        if kind == 'message':
            visible = payload.get('role') == 'user' or (payload.get('role') == 'assistant' and payload.get('channel') in {None, 'commentary', 'final'})
        if not visible:
            excluded[f'response_item:{kind}:{payload.get("role", "")}:{payload.get("channel", "")}'] += 1
            continue
        selected.append({'source_line': position, 'model': model, 'is_final': position in final_positions, 'record': row})
    if not selected:
        raise ValueError('No visible interactions found')
    human_positions = [i for i, e in enumerate(selected) if e['record']['payload'].get('role') == 'user'
                       and message_text(e['record']['payload']).strip()
                       and not message_text(e['record']['payload']).lstrip().startswith('<')]
    complete = any(e['is_final'] for e in selected[human_positions[-1] + 1:])
    created = datetime.now().astimezone().isoformat(timespec='seconds')
    start = local_time(selected[0]['record']['timestamp'])[:10].replace('-', '')
    end = local_time(selected[-1]['record']['timestamp'])[:10].replace('-', '')
    model_label = '+'.join(sorted(models)) or '未记录'
    filename = f'AI原始日志_Codex_{model_label}_{start}-{end}.json'
    destination = ROOT / '02_AI原始日志'
    destination.mkdir(exist_ok=True)
    path = destination / filename
    export_metadata = {'exported_at': created, 'session_id': metadata['payload']['id'],
                       'source_filename': source.name, 'source_sha256': hashlib.sha256(data).hexdigest(),
                       'source_bytes': len(data), 'source_lines': len(lines), 'models': sorted(models),
                       'visible_records': len(selected), 'incomplete_last_source_line': incomplete,
                       'current_interaction_complete': complete,
                       'excluded_record_counts': dict(excluded),
                       'scope': '实际可见交互字段提取；非完整内部运行文件。排除内部推理、系统/开发者提示、审批辅助会话、重复运行事件。保留可见 Prompt、回复、工具调用和结果，不事后补写。最新交互是否已记录最终回复见 current_interaction_complete。'}
    document = {'export_metadata': export_metadata, 'records': selected}
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding='utf-8')
    # HTML is a lossless display of the selected message/tool fields; JSON is authoritative.
    sections = []
    starts = []
    for index, entry in enumerate(selected):
        row, payload = entry['record'], entry['record']['payload']
        kind = payload['type']
        text = message_text(payload) if kind == 'message' else payload.get('arguments', payload.get('input', payload.get('output', '')))
        if not isinstance(text, str):
            text = json.dumps(text, ensure_ascii=False, indent=2)
        label = payload.get('role', kind)
        if kind == 'message' and payload.get('role') == 'user' and text.strip() and not text.lstrip().startswith('<'):
            starts.append((index, text))
        sections.append(f'<section id="L{entry["source_line"]}"><h2>源行 {entry["source_line"]} · {html.escape(local_time(row["timestamp"]))} · {html.escape(label)}</h2><pre>{html.escape(text)}</pre>')
        for part in payload.get('content', []):
            if part.get('type') == 'input_image':
                image_url = part.get('image_url', '')
                if isinstance(image_url, dict):
                    image_url = image_url.get('url', '')
                if image_url.startswith('data:image/'):
                    sections.append(f'<img alt="原始用户附件" src="{html.escape(image_url, quote=True)}">')
                else:
                    sections.append('<p>附件引用保留在 JSON；此预览未解析外部引用。</p>')
        sections.append('</section>')
    html_path = path.with_suffix('.html')
    status = '最新交互的最终回复已记录。' if complete else '最新交互仍进行中，后续回复尚未纳入。'
    html_path.write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>CampusBite 原始可见交互</title><style>body{max-width:1100px;margin:30px auto;padding:0 20px;font:14px/1.6 sans-serif}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f4;padding:16px}h2{font-size:16px}section{border-bottom:1px solid #ddd}img{max-width:100%;height:auto}</style><h1>校园食光：原始可见交互</h1><p>由实际本地会话字段自动提取，不是内部总结。JSON 为权威导出；源行号可用于定位。' + status + '</p>' + ''.join(sections) + '</html>', encoding='utf-8')
    index_rows = []
    notes_path = ROOT / 'docs/evidence/log_export/index_notes.json'
    notes = json.loads(notes_path.read_text(encoding='utf-8')) if notes_path.exists() else {}
    for number, (begin, prompt) in enumerate(starts, 1):
        finish = starts[number][0] if number < len(starts) else len(selected)
        chunk = selected[begin:finish]
        final_messages = [message_text(e['record']['payload']) for e in chunk if e['is_final']]
        finals = '\n'.join(final_messages)
        calls = [e['record']['payload'] for e in chunk if e['record']['payload']['type'] in {'function_call', 'custom_tool_call'}]
        call_text = '\n'.join(str(p.get('arguments', p.get('input', ''))) for p in calls)
        files = sorted(set(re.findall(r'(?:Add|Update|Delete) File: ([^\n\\]+)', call_text)))
        evidence = sorted(set(re.findall(r'docs/evidence/[A-Za-z0-9_./-]+', call_text + finals)))
        evidence = [value for value in evidence if (ROOT / value).exists()]
        files = [value.removeprefix(ROOT.as_posix() + '/') for value in files]
        index_rows.append({'轮次': f'{number:02}', '日期时间': local_time(chunk[0]['record']['timestamp']),
                           '工具与模型': 'Codex / ' + ', '.join(sorted({e['model'] for e in chunk if e['record']['payload'].get('role') != 'user'})),
                           '原始日志文件名': filename,
                           '原始日志位置': f'源行 {chunk[0]["source_line"]}-{chunk[-1]["source_line"]}；HTML #L{chunk[0]["source_line"]}',
                           '交互目标': (re.search(r'本轮主题[：:]\s*([^\n]+)', prompt).group(1) if re.search(r'本轮主题[：:]\s*([^\n]+)', prompt) else prompt.strip().splitlines()[0])[:100],
                           'Prompt摘要': prompt.strip()[:180],
                           'AI输出摘要': finals[:350] if finals else '快照中无最终回复；该次交互可能尚未结束，需人工核对。',
                           '采纳或修改内容': '见本行原始工具调用和最终回复；实际人工采纳情况待学生确认。',
                           '涉及文件': '; '.join(files) or '见原始日志；未自动提取到修改路径。',
                           '测试或截图证据': '; '.join(evidence) or '见原始工具输出；不凭摘要补写通过结论。',
                           '下一步': '人工核对日志、身份命名及提交材料。' if final_messages else '本次交互仍进行中，结束后刷新导出，不计为已完成交互。'})
        annotation = notes.get(str(number), {})
        if annotation:
            if not prompt.startswith(annotation['prompt_prefix']):
                raise ValueError(f'Index annotation does not match actual prompt {number}')
            for key in ('交互目标', 'Prompt摘要', '采纳或修改内容', '测试或截图证据', '下一步'):
                if key in annotation:
                    index_rows[-1][key] = annotation[key]
            if finals and 'AI输出摘要' in annotation:
                index_rows[-1]['AI输出摘要'] = annotation['AI输出摘要']
        index_rows[-1]['交互状态'] = '已记录最终回复' if final_messages else '快照时进行中，最终回复未纳入'
        if not files:
            index_rows[-1]['涉及文件'] = annotation.get('涉及文件', '无业务文件修改；见原始读取/检查操作。')
    import csv
    index_path = ROOT / '03_AI日志索引_学号+姓名.csv'
    with index_path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(index_rows[0]))
        writer.writeheader(); writer.writerows(index_rows)
    md_path = index_path.with_suffix('.md')
    fields = list(index_rows[0])
    def cell(value):
        return str(value).replace('|', '\\|').replace('\n', '<br>')
    markdown = ['# AI 日志索引', '',
                '本索引对应真实主会话，每行一次用户交互。日期为 Asia/Shanghai。JSON 是原始可见字段导出，HTML 使用源行锚点定位；本文件只是索引，不冒充原始日志。', '',
                '学号与姓名尚未提供，文件名保留占位。内容摘要由真实 Prompt、回复与实际工具修改整理；未声称学生做了不存在的代码审查。' + (f'当前第 {len(starts)} 次交互仍进行中，后续需刷新其最终回复。' if not complete else '最新交互的最终回复已纳入。'), '',
                '| ' + ' | '.join(fields) + ' |', '| ' + ' | '.join(['---'] * len(fields)) + ' |']
    markdown.extend('| ' + ' | '.join(cell(row[field]) for field in fields) + ' |' for row in index_rows)
    md_path.write_text('\n'.join(markdown) + '\n', encoding='utf-8')
    # Verify serialized records are identical to the selected source objects.
    saved = json.loads(path.read_text(encoding='utf-8'))
    assert saved['records'] == selected
    assert not any(e['record']['payload'].get('type') == 'reasoning' or e['record']['payload'].get('channel') == 'analysis' for e in saved['records'])
    with index_path.open(encoding='utf-8-sig', newline='') as handle:
        restored_index = list(csv.DictReader(handle))
        assert restored_index == index_rows
    for number, row in enumerate(index_rows, 1):
        assert row['轮次'] == f'{number:02}' and all(row.values())
        assert f'id="L{selected[starts[number - 1][0]]["source_line"]}"' in html_path.read_text(encoding='utf-8')
    manifest = {**export_metadata, 'files': {p.name: {'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in [path, html_path, index_path, md_path]},
                'indexed_interactions': len(starts), 'completed_interactions': sum(row['交互状态'] == '已记录最终回复' for row in index_rows),
                'verification': '源字段逐条相等、task_complete 最终回复匹配、CSV 往返、全部必填字段、连续编号及 HTML 定位校验通过'}
    evidence_dir = ROOT / 'docs/evidence/log_export'
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'saved_json': str(path), 'saved_html': str(html_path), 'index': str(index_path), 'records': len(selected), 'interactions': len(starts), 'models': sorted(models), 'verified': True, 'snapshot_at': created, 'current_interaction_complete': complete}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    export(parser.parse_args().source)
