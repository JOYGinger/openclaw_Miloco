

# 课堂视频分析任务说明

本项目用于分析课堂视频中的学生课堂行为。

## 最终分析方案

采用已知总人数约束策略：

1. 用户提供课堂总人数，默认为 24 人。
2. YOLO 只识别画面中明显可见的学生。
3. 对明显识别出的学生，调用方舟多模态模型判断行为：
   - raise_hand：举手
   - look_up：抬头
   - look_down：低头
   - talk：交谈
   - standing_or_leaving：站立或离座
   - unclear：不明确
4. 对未被明显识别出的学生，自动补齐为 unclear。
5. 最终每分钟总人数恒定为用户指定的人数。

## OpenClaw 执行规则

当用户说“分析某个文件夹下的课堂视频”时，请在本机终端执行：

```bat
run_classroom_folder.bat "用户提供的视频文件夹路径" 24
```

如果用户提供了其他人数，请把 24 替换为用户提供的人数。

例如：

```bat
run_classroom_folder.bat "E:\classroom_behavior_analysis\videos" 24
```

## 注意事项

- 不要把视频上传到对话中。
- 不要尝试在对话里解析视频内容。
- 只需要在本机运行脚本。
- 分析完成后，请告诉用户以下结果路径：
  1. 批量总览页面：outputs_known_total\batch_index.html
  2. 每个视频的 HTML 报告：对应子文件夹下的 classroom_dashboard.html
  3. Excel 结果：classroom_behavior_result.xlsx
  4. CSV 汇总：classroom_behavior_minute_summary.csv
  5. 标注图目录：annotated
  6. YOLO 检测图目录：yolo_debug