---
name: student-detector
description: 课堂学生检测与跟踪技能。使用 YOLOv8 + BoT-SORT 检测视频帧中的学生，自动分配稳定的学生ID，并裁剪出每个学生的小图供后续行为分析。在需要从课堂视频中识别、跟踪学生位置时使用。
---

# Student Detector - 学生检测器

本技能用于从课堂视频帧中检测学生位置、跟踪身份变化，并提取每个学生的时间序列小图。

## 核心功能

1. **YOLOv8 目标检测**：识别画面中的"人"
2. **BoT-SORT 跨帧跟踪**：为同一学生分配稳定的 ID（student_01, student_02...）
3. **自动裁剪**：为每个学生生成按时间组织的裁剪图目录
4. **结果导出**：生成 JSON 格式的检测结果，包含位置和置信度

## 使用指南

### 前置依赖

```bash
pip install ultralytics opencv-python
```

### 运行检测

```bash
python scripts/detect_students.py <帧目录> <输出目录> [置信度阈值]
```

- **帧目录**：包含视频帧图片（如 frame_0001.jpg）的文件夹
- **输出目录**：存放检测结果和裁剪图的文件夹
- **置信度阈值**（可选）：检测置信度过滤，默认 0.5（50%）

### 示例

```bash
python scripts/detect_students.py \
  "F:\课堂视频\frames" \
  "F:\课堂视频\detection_results" \
  0.5
```

## 输出结构

```
输出目录/
├── detection_results.json          # 每帧检测详情
└── students/                       # 按学生组织的小图
    ├── student_01/
    │   ├── frame_0001.jpg         # 学生1在第5秒的画面
    │   ├── frame_0002.jpg         # 学生1在第10秒的画面
    │   └── ...
    ├── student_02/
    │   └── ...
    └── ...
```

### detection_results.json 格式

```json
{
  "frame_0001.jpg": [
    {
      "student_id": "student_01",
      "bbox": [100, 200, 300, 500],
      "confidence": 0.92
    },
    {
      "student_id": "student_02",
      "bbox": [400, 220, 600, 520],
      "confidence": 0.88
    }
  ]
}
```

## 工作流衔接

本技能通常与以下环节配合：

1. **前置：video-processor 技能**
   - 从视频提取帧 → 输入到本技能

2. **后置：行为分析**
   - 本技能输出的 `students/student_XX/` 目录中的图片
   - 传入视觉大模型分析学生行为（抬头/举手/记笔记）

## 注意事项

- **首次运行**：会自动下载 YOLOv8n 模型（约 6MB）
- **座位固定假设**：BoT-SORT 跟踪依赖位置连续性，适用于座位固定的课堂场景
- **ID 稳定性**：如果学生离开画面再回来，可能会分配新 ID
- **误检过滤**：可通过调整置信度阈值（0.3-0.7）平衡漏检和误检

## 完整示例流程

```bash
# 1. 视频抽帧
python video-processor/scripts/extract_frames.py \
  classroom.mp4 ./frames 5

# 2. 学生检测
python student-detector/scripts/detect_students.py \
  ./frames ./detection_output

# 3. 查看结果
# detection_output/students/student_01/ 目录下即每个学生的时序图片
```
