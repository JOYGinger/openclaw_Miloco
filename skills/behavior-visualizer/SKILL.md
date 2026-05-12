---
name: behavior-visualizer
description: 课堂行为数据可视化技能。读取行为分析生成的 JSON 统计数据，自动生成抬头率排行、学生活跃度分布以及课堂全时段行为热力图，最终产出 HTML 网页报告。
---

# Behavior Visualizer - 行为可视化器

本技能用于将枯燥的行为分析 JSON 数据转化为直观、易懂的图表和网页报告。

## 📊 核心功能

1.  **抬头率排行图**：展示全班学生的专注度排名。
2.  **行为分布散点图**：分析抬头率、笔记次数与举手次数之间的关系。
3.  **活跃度时序热力图**：展示每个学生在课堂每个时间点的活跃程度（颜色越深越活跃）。
4.  **HTML 报告生成**：自动汇总所有图表，生成一个可以直接在浏览器查看的 index.html 页面。

## 🛠️ 前置依赖

```bash
pip install pandas matplotlib seaborn
```

## 🚀 使用方法

```bash
python scripts/visualize.py <student_timeline.json 路径> <输出目录>
```

### 示例

```bash
python behavior-visualizer/scripts/visualize.py \
  "F:\jhqstudy03\开源技术与应用\测试视频\行为分析_真实结果\student_timeline.json" \
  "F:\jhqstudy03\开源技术与应用\测试视频\可视化分析报告"
```

## 📂 输出结构

```
可视化报告/
├── index.html                       # 汇总报告页面（用浏览器打开）
├── classroom_focus_rank.png         # 抬头率排行图
├── student_behavior_distribution.png # 行为分布图
└── classroom_activity_heatmap.png   # 活跃度热力图
```

## 💡 设计说明

- **活跃度算法**：抬头计1分，记笔记计1分，举手计2分。
- **中文字体**：脚本已自动配置 SimHei 字体以解决图表中文乱码问题。
