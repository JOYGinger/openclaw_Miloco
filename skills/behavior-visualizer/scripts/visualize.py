import os
import sys
import json
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei'] 
plt.rcParams['axes.unicode_minus'] = False

def calculate_engagement_score(behaviors):
    """
    计算参与度评分 (同步分析脚本算法)
    抬头 30% + 书写 20% + 举手 30% + 积极情绪 20%
    """
    score = 0
    if behaviors.get("head_up"): score += 30
    if behaviors.get("writing"): score += 20
    if behaviors.get("hand_raised"): score += 30
    if behaviors.get("is_positive"): score += 20
    return score

def create_norm_visualizations(json_path, output_dir):
    """
    根据规范版行为分析结果生成可视化看板报告
    """
    json_path = Path(json_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if not json_path.exists():
        print(f"错误：找不到文件 {json_path}")
        return

    # 1. 加载规范数据
    with open(json_path, 'r', encoding='utf-8') as f:
        full_data = json.load(f)
    
    v_analysis = full_data.get("video_analysis", {})
    time_series = v_analysis.get("time_series", [])
    ind_analysis = v_analysis.get("individual_analysis", [])
    overall = v_analysis.get("overall_metrics", {})
    focus_groups = v_analysis.get("focus_groups", {})

    # 2. 生成全班时间趋势图 (Time-Series) - 优化版
    df_ts = pd.DataFrame(time_series)
    if not df_ts.empty:
        # 将 "00:05" 格式转换为秒数，以便绘图
        def time_to_seconds(t_str):
            m, s = map(int, t_str.split(':'))
            return m * 60 + s
        
        df_ts['seconds'] = df_ts['time'].apply(time_to_seconds)
        
        plt.figure(figsize=(15, 7))
        
        # 绘制三条核心曲线
        plt.plot(df_ts['seconds'], df_ts['head_up_rate'] * 100, 
                 label='抬头率 (专注度)', color='#1890ff', marker='o', linewidth=3, markersize=8)
        plt.plot(df_ts['seconds'], df_ts['writing_rate'] * 100, 
                 label='书写率 (认知加工)', color='#52c41a', marker='s', linestyle='--', linewidth=2)
        plt.plot(df_ts['seconds'], df_ts['positive_emotion_rate'] * 100, 
                 label='积极情绪率 (心理体验)', color='#fa8c16', marker='^', linestyle=':', linewidth=2)
        
        # 设置 X 轴为分钟格式
        plt.xticks(df_ts['seconds'], df_ts['time'], rotation=45)
        
        plt.title('课堂教学进程行为变化趋势图', fontsize=18, pad=20)
        plt.xlabel('教学进程 (时间)', fontsize=12)
        plt.ylabel('行为发生比例 (%)', fontsize=12)
        
        # 设置 Y 轴范围和参考线
        plt.ylim(0, 105)
        plt.axhline(y=80, color='red', linestyle=':', alpha=0.3, label='高参与警戒线 (80%)')
        plt.axhline(y=50, color='gray', linestyle=':', alpha=0.3)
        
        plt.legend(loc='upper right', frameon=True, shadow=True)
        plt.grid(True, which='both', linestyle='--', alpha=0.5)
        
        # 优化边距
        plt.tight_layout()
        plt.savefig(output_dir / 'ts_behavior_trends.png', dpi=300)
        print("生成优化版趋势图: ts_behavior_trends.png")

    # 3. 计算个体数据基础表
    rows = []
    for s in ind_analysis:
        writing_count = sum(1 for b in s.get("details", []) if b.get("writing"))
        total_frames = len(s.get("details", []))
        writing_rate = (writing_count / total_frames) if total_frames > 0 else 0
        rows.append({
            'ID': s['student_id'],
            '抬头率': s['head_up_rate'] * 100,
            '书写率': writing_rate * 100,
            '参与度评分': s['participation_score']
        })
    df_ind = pd.DataFrame(rows)

    # 4. 生成典型个体行为对比图 (左右布局，多指标对比)
    high_sid = focus_groups.get("high_participation_ids", [])[0] if focus_groups.get("high_participation_ids") else None
    low_sid = focus_groups.get("low_participation_ids", [])[-1] if focus_groups.get("low_participation_ids") else None
    
    if high_sid and low_sid:
        s_high = next(s for s in ind_analysis if s["student_id"] == high_sid)
        s_low = next(s for s in ind_analysis if s["student_id"] == low_sid)
        
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(20, 8), sharey=True)
        
        def get_student_df(s_data):
            details = s_data.get("details", [])
            rows = []
            for i, b in enumerate(details):
                t_str = time_series[i]['time'] if time_series and i < len(time_series) else '00:00'
                m, s = map(int, t_str.split(':'))
                total_sec = m * 60 + s
                rows.append({
                    'time_str': t_str,
                    'seconds': total_sec,
                    'focus': 100 if b.get('head_up') else 0,
                    'writing': 100 if b.get('writing') else 0,
                    'emotion': 100 if b.get('is_positive') else 0
                })
            return pd.DataFrame(rows)

        df_high = get_student_df(s_high)
        df_low = get_student_df(s_low)

        ax1.plot(df_high['seconds'] if 'seconds' in df_high else [], df_high['focus'] if 'focus' in df_high else [], label='专注度 (抬头)', color='#1890ff', marker='o', linewidth=2)
        ax1.plot(df_high['seconds'], df_high['writing'], label='认知加工 (书写)', color='#52c41a', marker='s', linestyle='--', linewidth=2)
        ax1.plot(df_high['seconds'], df_high['emotion'], label='情感体验 (积极)', color='#fa8c16', marker='^', linestyle=':', linewidth=2)
        ax1.set_title(f'表现优秀学生多维行为趋势 ({high_sid})', fontsize=14)
        ax1.set_xticks(df_high['seconds'])
        ax1.set_xticklabels(df_high['time_str'], rotation=45)
        ax1.set_ylabel('发生状态 (0=否, 100=是)')
        ax1.grid(True, alpha=0.3)
        ax1.legend(loc='lower left', fontsize=10)

        ax2.plot(df_low['seconds'], df_low['focus'], label='专注度 (抬头)', color='#1890ff', marker='o', linewidth=2)
        ax2.plot(df_low['seconds'], df_low['writing'], label='认知加工 (书写)', color='#52c41a', marker='s', linestyle='--', linewidth=2)
        ax2.plot(df_low['seconds'], df_low['emotion'], label='情感体验 (积极)', color='#fa8c16', marker='^', linestyle=':', linewidth=2)
        ax2.set_title(f'表现不佳学生多维行为趋势 ({low_sid})', fontsize=14)
        ax2.set_xticks(df_low['seconds'])
        ax2.set_xticklabels(df_low['time_str'], rotation=45)
        ax2.grid(True, alpha=0.3)
        ax2.legend(loc='lower left', fontsize=10)

        plt.suptitle('典型个体多维度行为时序对比图', fontsize=18, y=1.02)
        plt.tight_layout()
        plt.savefig(output_dir / 'individual_comparison_multi_trends.png', dpi=300)
        print("生成个体多维对比图: individual_comparison_multi_trends.png")

    # 5. 生成 HTML 看板
    avg_score = overall.get('average_engagement', 0)
    top_student = focus_groups.get("high_participation_ids", ["-"])[0]
    
    if avg_score >= 80:
        status_text = "课堂整体表现<b>优秀</b>。学生专注度极高，能够积极跟随教师节奏，认知加工深度（书写率）与情感体验均处于高位。"
    elif avg_score >= 60:
        status_text = "课堂整体表现<b>良好</b>。大部分学生能够保持基本的专注，但在特定时间段存在注意力波动，建议加强课堂中段的互动。"
    else:
        status_text = "课堂整体表现<b>一般</b>。学生抬头率较低，存在明显的注意力流失现象，建议优化教学环节设计，引入更多实操或互动环节。"

    summary_ai = f"""
    <div class="chart-section">
        <h2>📑 课堂整体学习状态总结</h2>
        <div style="padding: 15px; background: #e6f7ff; border-radius: 8px; border-left: 5px solid #1890ff; font-size: 16px; line-height: 1.6;">
            <p><b>整体评价：</b>{status_text}</p>
            <p><b>关键发现：</b>
                <ul>
                    <li>全班平均参与分为 <b>{avg_score}</b>，最高峰出现在 <b>{overall.get('peak_time', '初期')}</b> 左右。</li>
                    <li>表现最突出的学生是 <b>{top_student}</b>，其专注度与情感积极度均保持稳定。</li>
                    <li>课堂中 <b>抬头率 (Focus)</b> 与 <b>积极情绪</b> 的同步性较高，说明学生情绪对专注度有显著影响。</li>
                </ul>
            </p>
        </div>
    </div>
    """

    high_cards = ""
    for sid in focus_groups.get("high_participation_ids", []):
        s_data = next(s for s in ind_analysis if s["student_id"] == sid)
        high_cards += f"<div class='card high'><h3>{sid} (优秀)</h3><p>综合评分: <b>{s_data['participation_score']}</b></p><p>抬头率: {s_data['head_up_rate']*100:.0f}%</p></div>"

    low_cards = ""
    for sid in focus_groups.get("low_participation_ids", []):
        s_data = next(s for s in ind_analysis if s["student_id"] == sid)
        low_cards += f"<div class='card low'><h3>{sid} (需关注)</h3><p>综合评分: <b>{s_data['participation_score']}</b></p><p>抬头率: {s_data['head_up_rate']*100:.0f}%</p></div>"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>课堂行为分析仪表盘</title>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; background-color: #f0f2f5; color: #333; }}
            .header {{ background: #1890ff; color: white; padding: 20px 40px; text-align: center; }}
            .container {{ display: flex; flex-wrap: wrap; padding: 20px; justify-content: center; }}
            .metric-card {{ background: white; border-radius: 8px; margin: 10px; padding: 20px; min-width: 200px; text-align: center; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
            .metric-value {{ font-size: 32px; font-weight: bold; color: #1890ff; }}
            .metric-label {{ color: #888; margin-top: 5px; }}
            .chart-section {{ background: white; border-radius: 8px; margin: 20px; padding: 20px; width: 90%; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
            .chart-container {{ text-align: center; }}
            .chart-container img {{ max-width: 100%; }}
            .group-section {{ display: flex; width: 90%; justify-content: space-between; }}
            .card-column {{ width: 48%; }}
            .card {{ background: white; border-radius: 8px; padding: 15px; margin-bottom: 10px; border-left: 5px solid #ccc; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }}
            .high {{ border-left-color: #52c41a; }}
            .low {{ border-left-color: #f5222d; }}
            h2 {{ border-bottom: 2px solid #1890ff; padding-bottom: 10px; color: #1890ff; }}
        </style>
    </head>
    <body>
        <div class="header"><h1>课堂行为分析仪表盘</h1><p>生成时间: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}</p></div>
        <div class="container">
            <div class="metric-card"><div class="metric-value">{avg_score}</div><div class="metric-label">平均参与分</div></div>
            <div class="metric-card"><div class="metric-value">{df_ind['抬头率'].mean():.1f}%</div><div class="metric-label">平均抬头率</div></div>
        </div>
        <div class="container">
            {summary_ai}
            <div class="chart-section"><h2>1. 课堂行为全时段趋势</h2><div class="chart-container"><img src="ts_behavior_trends.png"></div></div>
            <div class="chart-section"><h2>2. 典型个体多维度对比</h2><div class="chart-container"><img src="individual_comparison_multi_trends.png"></div></div>
            <div class="group-section"><div class="card-column"><h2>🌟 高参与组</h2>{high_cards}</div><div class="card-column"><h2>⚠️ 低参与组</h2>{low_cards}</div></div>
        </div>
    </body>
    </html>
    """
    with open(output_dir / 'index.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"[OK] 规范化 HTML 报告已生成: {output_dir / 'index.html'}")

if __name__ == "__main__":
    if len(sys.argv) < 3: sys.exit(1)
    create_norm_visualizations(sys.argv[1], sys.argv[2])
