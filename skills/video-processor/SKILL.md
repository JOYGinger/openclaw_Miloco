---
name: video-processor
description: 视频预处理工具。支持将 MP4 视频按指定时间间隔（如每 5 秒）提取视频帧，为后续的学生行为分析或目标检测提供图像输入。在需要处理课堂视频、提取分析样本时使用。
---

# Video Processor

本技能主要用于将视频文件预处理为一系列静态帧。

## 核心流程

1. **视频抽帧**：使用内置脚本 `scripts/extract_frames.py` 调用 FFmpeg 进行高效抽帧。
2. **输出组织**：抽取的图片将存储在指定的输出目录中，文件名为 `frame_0001.jpg` 等格式。

## 使用指南

### 1. 提取视频帧

使用 `scripts/extract_frames.py` 脚本：

```bash
python scripts/extract_frames.py <输入视频路径> <输出目录> [时间间隔(秒)]
```

- **输入视频路径**：本地 MP4 或其他 FFmpeg 支持的格式。
- **输出目录**：存放提取出的 JPG 图片。
- **时间间隔**：默认为 5 秒。

### 示例

提取 `classroom_v1.mp4` 到 `analysis/frames/`，每 5 秒一帧：

```bash
python scripts/extract_frames.py classroom_v1.mp4 analysis/frames/ 5
```

## 注意事项

- 确保系统中已安装 `ffmpeg`。
- 较大的视频文件抽帧可能需要一定处理时间。
- 建议根据分析需求调整时间间隔（例如：活跃度分析建议 1-5s）。
