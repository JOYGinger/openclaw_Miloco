---
name: behavior-analyzer
description: 学生课堂行为分析技能（配置驱动）。接收 student-detector 输出的学生裁剪图，通过配置文件定义分析指标，调用视觉大模型分析学生行为，输出时间线统计和报告。支持动态扩展指标，无需修改代码即可新增分析维度。
---

# Behavior Analyzer - 行为分析器

本技能用于分析学生在课堂上的学习行为。采用**配置文件驱动**设计，可以灵活定义和扩展分析指标。

## 工作流程

1. **加载配置**：读取 `config/indicators.yaml` 中的指标定义
2. **加载裁剪图**：读取 `student-detector` 输出的学生时序图片
3. **行为分析**：调用视觉大模型，按配置的指标分析每张图片
4. **时间线汇总**：整理每个学生在不同时间点的行为数据
5. **生成报告**：输出 JSON 数据和文本报告

## 前置依赖

```bash
pip install pyyaml
```

- 已运行 `student-detector` 技能，生成学生裁剪图
- 视觉大模型 API（需用户配置）

## 配置指标

编辑 `config/indicators.yaml` 文件，定义要分析的指标：

```yaml
indicators:
  - name: head_up
    description: 学生是否抬头看前方
    prompt: "分析图片中学生是否抬头..."
    enabled: true
    
  - name: hand_raised
    description: 学生是否举手
    prompt: "分析图片中学生是否举手..."
    enabled: true
```

### 新增指标

只需在配置文件中添加：

```yaml
  - name: using_phone
    description: 学生是否在使用手机
    prompt: |
      分析图片中学生的行为。
      请判断：学生是否在看手机？
      返回JSON: {"using_phone": true/false, "confidence": 0.0-1.0}
    enabled: true
```

**无需修改代码！**

## 配置模型接入

编辑 `scripts/analyze_behavior.py`，修改 `analyze_image()` 函数，接入你的视觉大模型。

## 使用方法

```bash
python scripts/analyze_behavior.py <学生裁剪图目录> <输出目录>
```

### 示例

```bash
python behavior-analyzer/scripts/analyze_behavior.py \
  "F:\课堂视频\学生检测_v3\students" \
  "F:\课堂视频\行为分析结果"
```

## 输出结构

```
输出目录/
├── behavior_results.json      # 每张图的行为标签（包含所有指标）
├── student_timeline.json      # 每个学生的时间线统计
└── behavior_report.txt        # 文本报告
```

### student_timeline.json 格式

```json
{
  "student_01": {
    "total_frames": 6,
    "head_up_count": 5,
    "head_up_rate": 0.83,
    "hand_raised_count": 1,
    "hand_raised_rate": 0.17,
    "taking_notes_count": 4,
    "taking_notes_rate": 0.67,
    "timeline": [...]
  }
}
```

## 完整流程

```bash
# 1. 视频抽帧
python video-processor/scripts/extract_frames.py video.mp4 ./frames 5

# 2. 学生检测
python student-detector/scripts/detect_students.py ./frames ./detection_output 0.35

# 3. 配置指标（编辑 config/indicators.yaml）

# 4. 行为分析
python behavior-analyzer/scripts/analyze_behavior.py \
  ./detection_output/students \
  ./behavior_output
```

## 注意事项

- **依赖安装**：需要先 `pip install pyyaml`
- **请先配置模型**：默认脚本返回模拟数据，需要替换为实际模型调用
- **指标配置**：新增指标只需编辑 YAML 文件，无需修改代码
- **API Key 安全**：使用环境变量存储 API Key
- **调用频率限制**：注意模型的 QPS 限制
