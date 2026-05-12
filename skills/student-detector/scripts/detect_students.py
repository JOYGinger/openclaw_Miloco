"""
学生检测脚本
使用 YOLOv8 + BoT-SORT 跟踪检测学生，自动裁剪小图
"""
import os
import sys
import json
import cv2
from pathlib import Path

def detect_students(frames_dir, output_dir, conf_threshold=0.5):
    """
    检测并跟踪学生，裁剪小图
    """
    try:
        from ultralytics import YOLO
    except ImportError:
        print("错误：未安装 ultralytics")
        print("请先运行: pip install ultralytics opencv-python")
        sys.exit(1)
    
    # 加载 YOLOv8 模型
    print("加载 YOLOv8 模型...")
    model = YOLO("yolov8s.pt")
    
    frames_dir = Path(frames_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建学生裁剪图目录
    students_dir = output_dir / "students"
    students_dir.mkdir(exist_ok=True)
    
    # 获取所有帧图片
    frame_files = sorted(frames_dir.glob("*.jpg"))
    if not frame_files:
        print(f"错误：在 {frames_dir} 中没有找到 jpg 图片")
        return
    
    print(f"找到 {len(frame_files)} 帧图片")
    
    # 存储检测结果
    detection_results = {}
    
    # 用于跨帧跟踪的计数器
    student_tracks = {}
    next_student_id = 1
    
    for frame_file in frame_files:
        frame_name = frame_file.name
        print(f"\n处理: {frame_name}")
        
        # 读取图片
        img = cv2.imread(str(frame_file))
        if img is None:
            print(f"  无法读取: {frame_name}")
            continue
        
        # YOLOv8 检测 + 跟踪
        results = model.track(img, persist=True, conf=conf_threshold, classes=[0])
        
        frame_detections = []
        
        if results[0].boxes.id is not None:
            boxes = results[0].boxes.xyxy.cpu().numpy()
            track_ids = results[0].boxes.id.cpu().numpy().astype(int)
            confidences = results[0].boxes.conf.cpu().numpy()
            
            for box, track_id, conf in zip(boxes, track_ids, confidences):
                # 分配稳定的 student_id
                if track_id not in student_tracks:
                    student_tracks[track_id] = f"student_{next_student_id:02d}"
                    next_student_id += 1
                
                student_id = student_tracks[track_id]
                x1, y1, x2, y2 = map(int, box)
                
                # 保存检测结果
                frame_detections.append({
                    "student_id": student_id,
                    "bbox": [x1, y1, x2, y2],
                    "confidence": round(float(conf), 3)
                })
                
                # 裁剪学生小图
                student_img = img[y1:y2, x1:x2]
                if student_img.size > 0:
                    student_dir = students_dir / student_id
                    student_dir.mkdir(exist_ok=True)
                    output_path = student_dir / frame_name
                    cv2.imwrite(str(output_path), student_img)
                    print(f"  {student_id}: 裁剪完成 ({x2-x1}x{y2-y1})")
        
        detection_results[frame_name] = frame_detections
        print(f"  检测到 {len(frame_detections)} 个学生")
    
    # 保存检测结果 JSON
    json_path = output_dir / "detection_results.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(detection_results, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 检测完成！")
    print(f"   结果 JSON: {json_path}")
    print(f"   学生裁剪图: {students_dir}")
    print(f"   共识别 {len(student_tracks)} 个学生")
    for track_id, student_id in sorted(student_tracks.items(), key=lambda x: x[1]):
        student_dir = students_dir / student_id
        frame_count = len(list(student_dir.glob("*.jpg")))
        print(f"     - {student_id}: {frame_count} 帧")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("学生检测脚本")
        print("用法: python detect_students.py <帧目录> <输出目录> [置信度阈值]")
        print("示例: python detect_students.py ./frames ./output")
        print("      python detect_students.py ./frames ./output 0.6")
        sys.exit(1)
    
    frames_dir = sys.argv[1]
    output_dir = sys.argv[2]
    conf_threshold = float(sys.argv[3]) if len(sys.argv) > 3 else 0.5
    
    detect_students(frames_dir, output_dir, conf_threshold)
