import os
import re
import json
import base64
import shutil
import subprocess
import argparse
import webbrowser
from pathlib import Path
from typing import Dict, List, Any, Optional

import pandas as pd
from tqdm import tqdm
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
import matplotlib.pyplot as plt


# =========================
# 1. 基础配置
# =========================

load_dotenv()

ARK_API_KEY = os.getenv("ARK_API_KEY")
ARK_MODEL = os.getenv("ARK_MODEL")
ARK_BASE_URL = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")

if not ARK_API_KEY:
    raise ValueError("请先在 .env 文件中配置 ARK_API_KEY")

if not ARK_MODEL:
    raise ValueError("请先在 .env 文件中配置 ARK_MODEL")

client = OpenAI(
    api_key=ARK_API_KEY,
    base_url=ARK_BASE_URL,
)

# 默认输入视频路径；也可以通过命令行 --video 指定。
DEFAULT_VIDEO_PATH = Path(os.getenv("VIDEO_PATH", "videos/test.mp4"))

# 输出目录
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "outputs"))
FRAME_DIR = OUTPUT_DIR / "frames"
ANNOTATED_DIR = OUTPUT_DIR / "annotated"
CHART_DIR = OUTPUT_DIR / "charts"
YOLO_DEBUG_DIR = OUTPUT_DIR / "yolo_debug"

OUTPUT_DIR.mkdir(exist_ok=True)
FRAME_DIR.mkdir(exist_ok=True)
ANNOTATED_DIR.mkdir(exist_ok=True)
CHART_DIR.mkdir(exist_ok=True)
YOLO_DEBUG_DIR.mkdir(exist_ok=True)

# 每 60 秒取一帧
SEGMENT_SECONDS = int(os.getenv("SEGMENT_SECONDS", "60"))

# 每分钟取中间帧。例如第 0 分钟取第 30 秒，第 1 分钟取第 90 秒。
# 如果你想每分钟开头取帧，可以改成 0。
FRAME_OFFSET_SECONDS = float(os.getenv("FRAME_OFFSET_SECONDS", "30"))

# 抽帧图片宽度。越大越清楚，但模型处理成本也更高。
FRAME_WIDTH = int(os.getenv("FRAME_WIDTH", "1280"))

# YOLO 配置
# yolo11n.pt 速度快，适合先调试；yolo11s.pt / yolo11m.pt 检测效果可能更好但更慢。
YOLO_MODEL_PATH = os.getenv("YOLO_MODEL", "yolo11n.pt")
YOLO_CONF = float(os.getenv("YOLO_CONF", "0.35"))
YOLO_IOU = float(os.getenv("YOLO_IOU", "0.50"))
YOLO_IMG_SIZE = int(os.getenv("YOLO_IMG_SIZE", "1280"))

# 已知课堂总人数。
# 新策略：YOLO 只负责识别“明显可见”的学生；没有被明显识别出来的学生，
# 程序会自动补齐为 unclear，使每分钟统计人数固定等于 EXPECTED_PEOPLE_COUNT。
EXPECTED_PEOPLE_COUNT = int(os.getenv("EXPECTED_PEOPLE_COUNT", "24"))

_yolo_model = None


# =========================
# 2. 命令行参数
# =========================

def parse_args():
    parser = argparse.ArgumentParser(description="课堂视频行为分析工具：YOLO 定位 + 豆包多模态模型判断行为")

    parser.add_argument(
        "--video",
        type=str,
        default=str(DEFAULT_VIDEO_PATH),
        help="要分析的课堂视频本地路径，例如 D:\\videos\\classroom.mp4。默认 videos/test.mp4"
    )

    parser.add_argument(
        "--open-report",
        action="store_true",
        help="分析完成后自动打开 HTML 可视化报告"
    )

    parser.add_argument(
        "--expected-people",
        type=int,
        default=EXPECTED_PEOPLE_COUNT,
        help="课堂实际总人数。默认读取 .env 中的 EXPECTED_PEOPLE_COUNT，若未设置则为 24。"
    )

    return parser.parse_args()


# =========================
# 3. 工具函数
# =========================

def check_ffmpeg() -> None:
    """检查 ffmpeg 和 ffprobe 是否可用。"""
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("未检测到 ffmpeg，请先安装 ffmpeg 并加入环境变量。")
    if shutil.which("ffprobe") is None:
        raise RuntimeError("未检测到 ffprobe，请先安装 ffprobe 并加入环境变量。")


def get_video_duration(video_path: Path) -> float:
    """获取视频总时长，单位：秒。"""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1",
        str(video_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


def extract_one_frame(video_path: Path, timestamp: float, output_path: Path) -> None:
    """从视频中抽取某一时刻的一帧。"""
    cmd = [
        "ffmpeg",
        "-y",
        "-ss", str(timestamp),
        "-i", str(video_path),
        "-frames:v", "1",
        "-vf", f"scale={FRAME_WIDTH}:-1",
        "-q:v", "2",
        str(output_path)
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)


def extract_minute_frames(video_path: Path) -> List[Dict[str, Any]]:
    """
    每一分钟抽取一帧。
    默认取每分钟中间时刻的一帧。
    """
    duration = get_video_duration(video_path)
    frames = []

    minute_index = 0
    start = 0.0

    while start < duration:
        end = min(start + SEGMENT_SECONDS, duration)

        frame_time = start + FRAME_OFFSET_SECONDS
        if frame_time >= duration or frame_time >= end:
            frame_time = start + max(0, (end - start) / 2)

        frame_path = FRAME_DIR / f"minute_{minute_index:03d}.jpg"
        extract_one_frame(video_path, frame_time, frame_path)

        frames.append({
            "minute_index": minute_index,
            "start_second": round(start, 2),
            "end_second": round(end, 2),
            "frame_time_second": round(frame_time, 2),
            "frame_path": frame_path
        })

        minute_index += 1
        start += SEGMENT_SECONDS

    return frames


def image_to_base64_data_url(image_path: Path) -> str:
    """将图片转成 base64 data URL。"""
    with open(image_path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
    return f"data:image/jpeg;base64,{encoded}"


def extract_json(text: str) -> Dict[str, Any]:
    """从模型返回内容中提取 JSON。"""
    text = text.strip()

    code_block = re.search(r"```json\s*(.*?)\s*```", text, re.S)
    if code_block:
        text = code_block.group(1).strip()

    # 兜底：截取第一个 { 到最后一个 }
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1 and last > first:
        text = text[first:last + 1]

    return json.loads(text)


def clamp(value: Any, min_value: float = 0.0, max_value: float = 1.0) -> float:
    """限制数值范围到 [0, 1]。"""
    try:
        value = float(value)
    except Exception:
        return min_value
    return max(min_value, min(max_value, value))


def safe_get_font(size: int = 18):
    """优先使用 Windows 中文字体。"""
    candidates = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]

    for font_path in candidates:
        if Path(font_path).exists():
            try:
                return ImageFont.truetype(font_path, size=size)
            except Exception:
                pass

    return ImageFont.load_default()


def output_relative_path(path: Optional[str]) -> str:
    """将输出文件路径转换成相对 HTML 的路径。"""
    if not path:
        return ""

    p = Path(path)
    try:
        return p.relative_to(OUTPUT_DIR).as_posix()
    except Exception:
        return p.as_posix()


def html_escape(text: Any) -> str:
    """简单 HTML 转义。"""
    if text is None:
        return ""

    text = str(text)

    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def get_pair(value):
    """安全取二维坐标。"""
    if isinstance(value, list) and len(value) == 2:
        return value
    return [None, None]


def get_box(value):
    """安全取四维框。"""
    if isinstance(value, list) and len(value) == 4:
        return value
    return [None, None, None, None]


def format_pair_norm(value):
    pair = get_pair(value)
    if pair[0] is None or pair[1] is None:
        return "无坐标"
    return f"({pair[0]:.3f}, {pair[1]:.3f})"


def format_pair_px(value):
    pair = get_pair(value)
    if pair[0] is None or pair[1] is None:
        return "无坐标"
    return f"({pair[0]}, {pair[1]})"


def make_unidentified_students(count: int, start_index: int = 1) -> List[Dict[str, Any]]:
    """
    根据课堂总人数补齐未被 YOLO 明显识别出的学生。
    这些学生没有坐标，只参与人数与 unclear 统计。
    """
    result = []
    for i in range(count):
        idx = start_index + i
        result.append({
            "student_id": f"S{idx:02d}",
            "det_id": f"UNDETECTED_{i + 1:02d}",
            "bbox_norm": None,
            "center_norm": None,
            "bbox_px": None,
            "center_px": None,
            "behavior": "unclear",
            "confidence": 0.0,
            "yolo_confidence": None,
            "is_detected": False,
            "evidence": "该学生未被 YOLO 明显识别出来；根据课堂总人数补齐，行为记为“不明确，需要注意观察”。"
        })
    return result


def recompute_behavior_counts(students: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {
        "raise_hand": 0,
        "look_up": 0,
        "look_down": 0,
        "talk": 0,
        "standing_or_leaving": 0,
        "unclear": 0
    }
    for stu in students:
        behavior = stu.get("behavior", "unclear")
        if behavior not in counts:
            behavior = "unclear"
        counts[behavior] += 1
    return counts


def normalize_to_expected_count(students: List[Dict[str, Any]], expected_count: int) -> List[Dict[str, Any]]:
    """
    保证最终 students 数量等于 expected_count。
    - 如果检测学生少于 expected_count：补齐 UNDETECTED 学生，行为为 unclear。
    - 如果检测学生多于 expected_count：保留综合置信度最高的 expected_count 个。
    """
    if expected_count <= 0:
        return students

    detected_students = [s for s in students if s.get("is_detected", True)]

    if len(detected_students) > expected_count:
        def score(stu):
            bc = stu.get("confidence") or 0.0
            yc = stu.get("yolo_confidence") or 0.0
            return 0.6 * float(bc) + 0.4 * float(yc)
        detected_students = sorted(detected_students, key=score, reverse=True)[:expected_count]

    # 重新编号，先给可检测学生编号 S01...
    normalized = []
    for idx, stu in enumerate(detected_students, start=1):
        stu = dict(stu)
        stu["student_id"] = f"S{idx:02d}"
        normalized.append(stu)

    missing = expected_count - len(normalized)
    if missing > 0:
        normalized.extend(make_unidentified_students(missing, start_index=len(normalized) + 1))

    return normalized


# =========================
# 4. YOLO 人体检测
# =========================

def get_yolo_model():
    """懒加载 YOLO 模型。"""
    global _yolo_model

    if _yolo_model is not None:
        return _yolo_model

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise ImportError(
            "未安装 ultralytics。请先执行：pip install -U ultralytics"
        ) from exc

    _yolo_model = YOLO(YOLO_MODEL_PATH)
    return _yolo_model


def detect_persons_yolo(image_path: Path) -> List[Dict[str, Any]]:
    """
    使用 YOLO 检测图片中的 person。
    坐标系：原点为图像左上角，x 轴向右，y 轴向下。
    返回：bbox_norm、center_norm、bbox_px、center_px。
    """
    image = Image.open(image_path).convert("RGB")
    width, height = image.size

    model = get_yolo_model()
    results = model(
        str(image_path),
        conf=YOLO_CONF,
        iou=YOLO_IOU,
        imgsz=YOLO_IMG_SIZE,
        verbose=False
    )

    result = results[0]
    detections = []

    if result.boxes is None:
        return detections

    names = result.names or {}

    raw_detections = []

    for box in result.boxes:
        cls_id = int(box.cls[0].item())
        cls_name = str(names.get(cls_id, cls_id)).lower()

        # 只保留 person 类。YOLO COCO 预训练模型中 person 通常是类别 0。
        if cls_name != "person" and cls_id != 0:
            continue

        conf = float(box.conf[0].item())
        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().tolist()

        # 限制到图像范围
        x1 = max(0.0, min(float(x1), float(width)))
        y1 = max(0.0, min(float(y1), float(height)))
        x2 = max(0.0, min(float(x2), float(width)))
        y2 = max(0.0, min(float(y2), float(height)))

        if x2 <= x1 or y2 <= y1:
            continue

        bbox_px = [int(x1), int(y1), int(x2), int(y2)]
        center_px = [int((x1 + x2) / 2), int((y1 + y2) / 2)]

        bbox_norm = [
            x1 / width,
            y1 / height,
            x2 / width,
            y2 / height
        ]
        center_norm = [
            ((x1 + x2) / 2) / width,
            ((y1 + y2) / 2) / height
        ]

        raw_detections.append({
            "bbox_norm": [round(v, 4) for v in bbox_norm],
            "center_norm": [round(v, 4) for v in center_norm],
            "bbox_px": bbox_px,
            "center_px": center_px,
            "yolo_confidence": round(conf, 4),
            "class_name": cls_name,
            "class_id": cls_id
        })

    # 稳定编号：先按 y 从上到下，再按 x 从左到右排序。
    raw_detections.sort(key=lambda d: (d["center_norm"][1], d["center_norm"][0]))

    for idx, det in enumerate(raw_detections, start=1):
        det["det_id"] = f"P{idx:02d}"
        detections.append(det)

    return detections


def draw_yolo_debug_frame(frame_info: Dict[str, Any], detections: List[Dict[str, Any]]) -> str:
    """可选调试图：只画 YOLO 检测到的所有 person 框。"""
    image_path = Path(frame_info["frame_path"])
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = safe_get_font(16)

    for det in detections:
        x1, y1, x2, y2 = det["bbox_px"]
        draw.rectangle([(x1, y1), (x2, y2)], outline=(30, 144, 255), width=3)
        label = f"{det['det_id']} person {det['yolo_confidence']:.2f}"
        text_bbox = draw.textbbox((x1, max(0, y1 - 22)), label, font=font)
        draw.rectangle(text_bbox, fill=(255, 255, 255))
        draw.text((x1, max(0, y1 - 22)), label, fill=(30, 144, 255), font=font)

    output_path = YOLO_DEBUG_DIR / f"minute_{frame_info['minute_index']:03d}_yolo.jpg"
    image.save(output_path, quality=95)
    return str(output_path)


# =========================
# 5. 豆包多模态模型判断行为
# =========================

def analyze_frame(frame_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    单帧分析流程：
    1. YOLO 检测画面中的 person，负责定位与坐标；
    2. 豆包多模态模型根据截图和 YOLO 候选框判断哪些是学生，以及每个学生的主要行为。
    """
    image_path = frame_info["frame_path"]

    with Image.open(image_path) as img:
        width, height = img.size

    yolo_detections = detect_persons_yolo(image_path)
    yolo_debug_path = draw_yolo_debug_frame(frame_info, yolo_detections)

    # 没有人体候选框时，不再返回 0 人，而是按课堂总人数补齐为 unclear。
    if not yolo_detections:
        students = normalize_to_expected_count([], EXPECTED_PEOPLE_COUNT)
        return {
            "minute_index": frame_info["minute_index"],
            "start_second": frame_info["start_second"],
            "end_second": frame_info["end_second"],
            "frame_time_second": frame_info["frame_time_second"],
            "frame_path": str(frame_info["frame_path"]),
            "image_width": width,
            "image_height": height,
            "coordinate_system": "origin_top_left_x_right_y_down_normalized",
            "expected_people_count": EXPECTED_PEOPLE_COUNT,
            "yolo_person_count": 0,
            "detected_student_count": 0,
            "undetected_student_count": EXPECTED_PEOPLE_COUNT,
            "yolo_detections": [],
            "yolo_debug_path": yolo_debug_path,
            "student_count": EXPECTED_PEOPLE_COUNT,
            "students": students,
            "excluded_persons": [],
            "behavior_counts": recompute_behavior_counts(students),
            "class_state": "未检测到明显学生",
            "summary": f"本分钟 YOLO 未检测到明显学生。根据课堂总人数 {EXPECTED_PEOPLE_COUNT} 人，全部记为不明确，需要注意观察。",
            "overall_confidence": 0.0
        }

    image_data_url = image_to_base64_data_url(image_path)

    # 只把必要坐标给模型，减少 prompt 长度。
    candidate_persons = [
        {
            "det_id": det["det_id"],
            "bbox_norm": det["bbox_norm"],
            "center_norm": det["center_norm"],
            "yolo_confidence": det["yolo_confidence"]
        }
        for det in yolo_detections
    ]

    detections_text = json.dumps(candidate_persons, ensure_ascii=False, indent=2)

    prompt = f"""
你是一个课堂行为分析助手。请分析这一张课堂视频截图。

该截图代表视频中的一个 1 分钟时间段：
- 分钟编号：{frame_info["minute_index"]}
- 时间段：{frame_info["start_second"]} 秒 到 {frame_info["end_second"]} 秒
- 截图时刻：第 {frame_info["frame_time_second"]} 秒

本课堂实际总人数已知为：{EXPECTED_PEOPLE_COUNT} 人。

现在 YOLO 已经检测出画面中的 person 候选框。请注意：
- 坐标由 YOLO 提供，你不要重新生成坐标，也不要修改坐标。
- 你只需要分析 YOLO 已经明显检测出来的候选框。
- 对于 YOLO 没有明显检测出来的学生，不要虚构坐标，也不要编造 det_id；程序会自动补齐为 unclear。
- 你需要根据截图和 YOLO 候选框判断：
  1. 哪些候选框是明显可见的学生；
  2. 哪些候选框是老师、路人或其他非学生，不计入“已识别学生”；
  3. 每个明显可见学生的主要课堂行为；
  4. 本分钟课堂整体状态。

隐私与安全要求：
- 不要识别学生身份。
- 不要做人脸识别。
- 不要推测姓名、性别、年龄、成绩、性格等隐私。
- 学生编号只按本帧中的学生顺序临时编号，例如 S01、S02、S03。

坐标系说明：
- 原点 O 为图像左上角。
- x 轴向右，y 轴向下。
- bbox_norm 和 center_norm 都是 YOLO 给出的归一化坐标，范围为 0 到 1。

YOLO 候选 person 框如下：
{detections_text}

每个学生的 behavior 只能从下面选择一个：
1. raise_hand：举手
2. look_up：抬头听讲、看老师、看黑板、看屏幕
3. look_down：低头、写字、看书、看桌面、疑似看手机
4. talk：与旁边同学交谈或明显侧头交流
5. standing_or_leaving：站立、走动、离座、进出教室
6. unclear：无法判断

请严格输出 JSON，不要输出任何解释性文字。
输出格式如下：

{{
  "minute_index": {frame_info["minute_index"]},
  "start_second": {frame_info["start_second"]},
  "end_second": {frame_info["end_second"]},
  "frame_time_second": {frame_info["frame_time_second"]},
  "student_count": 0,
  "students": [
    {{
      "det_id": "P01",
      "student_id": "S01",
      "is_student": true,
      "behavior": "look_up",
      "confidence": 0.80,
      "evidence": "该候选框中的人物面向讲台方向，头部抬起"
    }}
  ],
  "excluded_persons": [
    {{
      "det_id": "P05",
      "reason": "疑似教师或非学生"
    }}
  ],
  "behavior_counts": {{
    "raise_hand": 0,
    "look_up": 0,
    "look_down": 0,
    "talk": 0,
    "standing_or_leaving": 0,
    "unclear": 0
  }},
  "class_state": "听讲为主",
  "summary": "本分钟课堂整体状态的简短描述",
  "overall_confidence": 0.0
}}

注意：
- students 中只能使用 YOLO 候选框中已有的 det_id。
- 不要虚构新的 det_id。
- 不要输出 bbox_norm、center_norm，因为坐标由 YOLO 提供，程序会自动补充。
- 这里只输出 YOLO 明显检测出来、且你判断为学生的候选框。
- student_count 必须等于你输出的 students 数组长度，不要求等于课堂总人数。
- 不要把老师计入 student_count。
- 如果某个候选框虽然像学生但行为无法判断，可以保留为学生，behavior 设为 unclear，confidence 设低一些。
- 不要为了凑满 {EXPECTED_PEOPLE_COUNT} 人而虚构新的 det_id；未明显检测出来的人由程序自动补齐为 unclear。
"""

    response = client.chat.completions.create(
        model=ARK_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_data_url
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }
        ],
        temperature=0.1,
    )

    content = response.choices[0].message.content
    result = extract_json(content)

    det_map = {det["det_id"]: det for det in yolo_detections}
    allowed_behaviors = {
        "raise_hand",
        "look_up",
        "look_down",
        "talk",
        "standing_or_leaving",
        "unclear"
    }

    students_from_model = result.get("students", [])
    if not isinstance(students_from_model, list):
        students_from_model = []

    cleaned_students = []
    used_det_ids = set()

    for stu in students_from_model:
        if not isinstance(stu, dict):
            continue

        det_id = stu.get("det_id")
        if det_id not in det_map:
            continue

        if det_id in used_det_ids:
            continue
        used_det_ids.add(det_id)

        det = det_map[det_id]

        behavior = stu.get("behavior", "unclear")
        if behavior not in allowed_behaviors:
            behavior = "unclear"

        confidence = clamp(stu.get("confidence", 0.0))

        cleaned_students.append({
            "student_id": stu.get("student_id", f"S{len(cleaned_students) + 1:02d}"),
            "det_id": det_id,
            "bbox_norm": det["bbox_norm"],
            "center_norm": det["center_norm"],
            "bbox_px": det["bbox_px"],
            "center_px": det["center_px"],
            "behavior": behavior,
            "confidence": confidence,
            "yolo_confidence": det["yolo_confidence"],
            "is_detected": True,
            "evidence": stu.get("evidence", "")
        })

    excluded_persons = result.get("excluded_persons", [])
    if not isinstance(excluded_persons, list):
        excluded_persons = []

    cleaned_excluded = []
    for item in excluded_persons:
        if not isinstance(item, dict):
            continue
        det_id = item.get("det_id")
        if det_id not in det_map:
            continue
        cleaned_excluded.append({
            "det_id": det_id,
            "reason": item.get("reason", "未说明")
        })

    # 新策略：最终人数必须等于 EXPECTED_PEOPLE_COUNT。
    # YOLO + 模型能明显识别出来的学生保留真实坐标与行为；
    # 剩余未明显识别出来的人自动补齐为 unclear。
    detected_student_count_before_padding = len(cleaned_students)
    normalized_students = normalize_to_expected_count(cleaned_students, EXPECTED_PEOPLE_COUNT)
    detected_student_count = sum(1 for stu in normalized_students if stu.get("is_detected", True))
    undetected_student_count = max(0, EXPECTED_PEOPLE_COUNT - detected_student_count)
    behavior_counts = recompute_behavior_counts(normalized_students)

    base_summary = result.get("summary", "")
    summary = (
        f"{base_summary} 本分钟课堂总人数按 {EXPECTED_PEOPLE_COUNT} 人统计；"
        f"其中 YOLO 明显识别并完成行为判断的学生 {detected_student_count} 人，"
        f"未明显识别出的学生 {undetected_student_count} 人，已记为“不明确，需要注意观察”。"
    )

    final_result = {
        "minute_index": frame_info["minute_index"],
        "start_second": frame_info["start_second"],
        "end_second": frame_info["end_second"],
        "frame_time_second": frame_info["frame_time_second"],
        "frame_path": str(frame_info["frame_path"]),
        "image_width": width,
        "image_height": height,
        "coordinate_system": "origin_top_left_x_right_y_down_normalized",
        "expected_people_count": EXPECTED_PEOPLE_COUNT,
        "yolo_person_count": len(yolo_detections),
        "detected_student_count_before_padding": detected_student_count_before_padding,
        "detected_student_count": detected_student_count,
        "undetected_student_count": undetected_student_count,
        "yolo_detections": yolo_detections,
        "yolo_debug_path": yolo_debug_path,
        "student_count": EXPECTED_PEOPLE_COUNT,
        "students": normalized_students,
        "excluded_persons": cleaned_excluded,
        "behavior_counts": behavior_counts,
        "class_state": result.get("class_state", "无法判断"),
        "summary": summary,
        "overall_confidence": clamp(result.get("overall_confidence", 0.0))
    }

    return final_result


# =========================
# 6. 图片标注
# =========================

def behavior_color(behavior: str):
    """不同行为使用不同颜色。"""
    mapping = {
        "raise_hand": (255, 80, 80),
        "look_up": (80, 180, 80),
        "look_down": (80, 120, 255),
        "talk": (255, 180, 60),
        "standing_or_leaving": (180, 80, 255),
        "unclear": (160, 160, 160),
    }
    return mapping.get(behavior, (160, 160, 160))


def annotate_frame(result: Dict[str, Any]) -> str:
    """在图片上画出学生位置、编号、行为和坐标。"""
    image_path = Path(result["frame_path"])
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)

    font = safe_get_font(18)
    small_font = safe_get_font(14)

    width, height = image.size

    # 坐标轴
    axis_color = (30, 30, 30)
    draw.line([(0, 0), (120, 0)], fill=axis_color, width=3)
    draw.line([(0, 0), (0, 120)], fill=axis_color, width=3)
    draw.text((125, 2), "x", fill=axis_color, font=font)
    draw.text((5, 125), "y", fill=axis_color, font=font)
    draw.text((5, 5), "O(0,0)", fill=axis_color, font=small_font)

    # 底部标题
    title = (
        f"Minute {result['minute_index']} | "
        f"{result['start_second']}s-{result['end_second']}s | "
        f"YOLO persons: {result.get('yolo_person_count', 0)} | "
        f"Detected students: {result.get('detected_student_count', result['student_count'])} | "
        f"Total: {result['student_count']}"
    )
    draw.rectangle([(0, height - 38), (width, height)], fill=(255, 255, 255))
    draw.text((10, height - 31), title, fill=(0, 0, 0), font=font)

    # 先画被排除的人体框，灰色虚线效果用细框表示。
    excluded_det_ids = {item.get("det_id") for item in result.get("excluded_persons", [])}
    student_det_ids = {stu.get("det_id") for stu in result.get("students", [])}

    for det in result.get("yolo_detections", []):
        det_id = det.get("det_id")
        if det_id in student_det_ids:
            continue

        x1, y1, x2, y2 = det["bbox_px"]
        color = (180, 180, 180)
        draw.rectangle([(x1, y1), (x2, y2)], outline=color, width=2)

        label = f"{det_id} excluded" if det_id in excluded_det_ids else f"{det_id} yolo-only"
        label_x = max(0, x1)
        label_y = max(0, y1 - 22)
        text_bbox = draw.textbbox((label_x, label_y), label, font=small_font)
        draw.rectangle(text_bbox, fill=(255, 255, 255))
        draw.text((label_x, label_y), label, fill=color, font=small_font)

    # 再画被 YOLO 明显识别出来的学生框。
    # 未识别学生没有坐标，只参与 unclear 统计，不在图上画框。
    for stu in result["students"]:
        if not stu.get("is_detected", True):
            continue

        bbox = stu.get("bbox_px")
        center = stu.get("center_px")
        if not isinstance(bbox, list) or len(bbox) != 4 or not isinstance(center, list) or len(center) != 2:
            continue

        behavior = stu["behavior"]
        color = behavior_color(behavior)

        x1, y1, x2, y2 = bbox

        if x2 <= x1 or y2 <= y1:
            cx, cy = center
            x1, y1, x2, y2 = cx - 20, cy - 20, cx + 20, cy + 20

        draw.rectangle([(x1, y1), (x2, y2)], outline=color, width=3)

        cx, cy = center
        r = 5
        draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=color)

        label = (
            f"{stu['student_id']} {stu.get('det_id', '')} {behavior} "
            f"({stu['center_norm'][0]:.2f},{stu['center_norm'][1]:.2f})"
        )

        label_x = max(0, x1)
        label_y = max(0, y1 - 24)

        text_bbox = draw.textbbox((label_x, label_y), label, font=small_font)
        draw.rectangle(text_bbox, fill=(255, 255, 255))
        draw.text((label_x, label_y), label, fill=color, font=small_font)

    # 在左下角补充未识别人数提示。
    unknown_note = f"Unidentified students: {result.get('undetected_student_count', 0)} -> unclear"
    note_y = max(0, height - 70)
    note_bbox = draw.textbbox((10, note_y), unknown_note, font=small_font)
    draw.rectangle(note_bbox, fill=(255, 255, 255))
    draw.text((10, note_y), unknown_note, fill=(120, 120, 120), font=small_font)

    output_path = ANNOTATED_DIR / f"minute_{result['minute_index']:03d}_annotated.jpg"
    image.save(output_path, quality=95)

    return str(output_path)


# =========================
# 7. 结果整理和图表
# =========================

def flatten_results(results: List[Dict[str, Any]]) -> pd.DataFrame:
    """将结果展开为学生明细表，每个学生一行。"""
    rows = []

    for res in results:
        students = res.get("students", [])

        if not students:
            rows.append({
                "minute_index": res.get("minute_index"),
                "start_second": res.get("start_second"),
                "end_second": res.get("end_second"),
                "frame_time_second": res.get("frame_time_second"),
                "student_id": None,
                "det_id": None,
                "is_detected": None,
                "student_count_this_minute": res.get("student_count", 0),
                "yolo_person_count_this_minute": res.get("yolo_person_count", 0),
                "center_x_norm": None,
                "center_y_norm": None,
                "center_x_px": None,
                "center_y_px": None,
                "bbox_x1_norm": None,
                "bbox_y1_norm": None,
                "bbox_x2_norm": None,
                "bbox_y2_norm": None,
                "behavior": None,
                "behavior_confidence": None,
                "yolo_confidence": None,
                "evidence": None,
                "class_state": res.get("class_state"),
                "summary": res.get("summary"),
                "overall_confidence": res.get("overall_confidence"),
                "frame_path": res.get("frame_path"),
                "annotated_path": res.get("annotated_path"),
                "yolo_debug_path": res.get("yolo_debug_path"),
            })
            continue

        for stu in students:
            center_norm = get_pair(stu.get("center_norm"))
            center_px = get_pair(stu.get("center_px"))
            bbox_norm = get_box(stu.get("bbox_norm"))

            rows.append({
                "minute_index": res.get("minute_index"),
                "start_second": res.get("start_second"),
                "end_second": res.get("end_second"),
                "frame_time_second": res.get("frame_time_second"),
                "student_id": stu.get("student_id"),
                "det_id": stu.get("det_id"),
                "is_detected": stu.get("is_detected", True),
                "student_count_this_minute": res.get("student_count", 0),
                "yolo_person_count_this_minute": res.get("yolo_person_count", 0),
                "center_x_norm": center_norm[0],
                "center_y_norm": center_norm[1],
                "center_x_px": center_px[0],
                "center_y_px": center_px[1],
                "bbox_x1_norm": bbox_norm[0],
                "bbox_y1_norm": bbox_norm[1],
                "bbox_x2_norm": bbox_norm[2],
                "bbox_y2_norm": bbox_norm[3],
                "behavior": stu.get("behavior"),
                "behavior_confidence": stu.get("confidence"),
                "yolo_confidence": stu.get("yolo_confidence"),
                "evidence": stu.get("evidence"),
                "class_state": res.get("class_state"),
                "summary": res.get("summary"),
                "overall_confidence": res.get("overall_confidence"),
                "frame_path": res.get("frame_path"),
                "annotated_path": res.get("annotated_path"),
                "yolo_debug_path": res.get("yolo_debug_path"),
            })

    return pd.DataFrame(rows)


def build_minute_summary(results: List[Dict[str, Any]]) -> pd.DataFrame:
    """每分钟汇总一行。"""
    rows = []

    for res in results:
        bc = res.get("behavior_counts", {})

        rows.append({
            "minute_index": res.get("minute_index"),
            "start_second": res.get("start_second"),
            "end_second": res.get("end_second"),
            "frame_time_second": res.get("frame_time_second"),
            "expected_people_count": res.get("expected_people_count", EXPECTED_PEOPLE_COUNT),
            "yolo_person_count": res.get("yolo_person_count", 0),
            "detected_student_count": res.get("detected_student_count", res.get("student_count", 0)),
            "undetected_student_count": res.get("undetected_student_count", 0),
            "student_count": res.get("student_count", 0),
            "raise_hand": bc.get("raise_hand", 0),
            "look_up": bc.get("look_up", 0),
            "look_down": bc.get("look_down", 0),
            "talk": bc.get("talk", 0),
            "standing_or_leaving": bc.get("standing_or_leaving", 0),
            "unclear": bc.get("unclear", 0),
            "class_state": res.get("class_state"),
            "summary": res.get("summary"),
            "overall_confidence": res.get("overall_confidence", 0),
            "frame_path": res.get("frame_path"),
            "annotated_path": res.get("annotated_path"),
            "yolo_debug_path": res.get("yolo_debug_path"),
        })

    return pd.DataFrame(rows)


def build_yolo_detection_table(results: List[Dict[str, Any]]) -> pd.DataFrame:
    """YOLO 原始 person 候选框明细表。"""
    rows = []

    for res in results:
        student_det_ids = {stu.get("det_id") for stu in res.get("students", [])}
        excluded_reason_map = {
            item.get("det_id"): item.get("reason", "")
            for item in res.get("excluded_persons", [])
        }

        for det in res.get("yolo_detections", []):
            center_norm = det.get("center_norm", [None, None])
            center_px = det.get("center_px", [None, None])
            bbox_norm = det.get("bbox_norm", [None, None, None, None])
            bbox_px = det.get("bbox_px", [None, None, None, None])
            det_id = det.get("det_id")

            if det_id in student_det_ids:
                final_status = "student"
            elif det_id in excluded_reason_map:
                final_status = "excluded"
            else:
                final_status = "unused_by_model"

            rows.append({
                "minute_index": res.get("minute_index"),
                "start_second": res.get("start_second"),
                "end_second": res.get("end_second"),
                "det_id": det_id,
                "final_status": final_status,
                "excluded_reason": excluded_reason_map.get(det_id, ""),
                "yolo_confidence": det.get("yolo_confidence"),
                "center_x_norm": center_norm[0],
                "center_y_norm": center_norm[1],
                "center_x_px": center_px[0],
                "center_y_px": center_px[1],
                "bbox_x1_norm": bbox_norm[0],
                "bbox_y1_norm": bbox_norm[1],
                "bbox_x2_norm": bbox_norm[2],
                "bbox_y2_norm": bbox_norm[3],
                "bbox_x1_px": bbox_px[0],
                "bbox_y1_px": bbox_px[1],
                "bbox_x2_px": bbox_px[2],
                "bbox_y2_px": bbox_px[3],
                "frame_path": res.get("frame_path"),
                "yolo_debug_path": res.get("yolo_debug_path"),
            })

    return pd.DataFrame(rows)


def plot_behavior_timeline(summary_df: pd.DataFrame) -> str:
    """生成课堂行为变化趋势图。"""
    output_path = CHART_DIR / "behavior_timeline.png"

    x = summary_df["minute_index"]

    plt.figure(figsize=(12, 6))
    plt.plot(x, summary_df["yolo_person_count"], marker="o", label="yolo_person_count")
    plt.plot(x, summary_df["student_count"], marker="o", label="expected_student_count")
    if "detected_student_count" in summary_df.columns:
        plt.plot(x, summary_df["detected_student_count"], marker="o", label="detected_student_count")
    if "undetected_student_count" in summary_df.columns:
        plt.plot(x, summary_df["undetected_student_count"], marker="o", label="undetected_unclear_count")
    plt.plot(x, summary_df["raise_hand"], marker="o", label="raise_hand")
    plt.plot(x, summary_df["look_up"], marker="o", label="look_up")
    plt.plot(x, summary_df["look_down"], marker="o", label="look_down")
    plt.plot(x, summary_df["talk"], marker="o", label="talk")
    plt.plot(x, summary_df["standing_or_leaving"], marker="o", label="standing_or_leaving")
    plt.plot(x, summary_df["unclear"], marker="o", label="unclear")

    plt.xlabel("Minute")
    plt.ylabel("Count")
    plt.title("Classroom Behavior Timeline")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()

    return str(output_path)


def plot_student_position_map(student_df: pd.DataFrame) -> Optional[str]:
    """生成学生位置分布图。"""
    valid_df = student_df.dropna(subset=["center_x_norm", "center_y_norm"])

    if valid_df.empty:
        return None

    output_path = CHART_DIR / "student_position_map.png"

    plt.figure(figsize=(8, 6))

    behaviors = [
        "raise_hand",
        "look_up",
        "look_down",
        "talk",
        "standing_or_leaving",
        "unclear"
    ]

    for behavior in behaviors:
        part = valid_df[valid_df["behavior"] == behavior]
        if part.empty:
            continue

        plt.scatter(
            part["center_x_norm"],
            part["center_y_norm"],
            label=behavior,
            alpha=0.75
        )

    plt.xlim(0, 1)
    plt.ylim(1, 0)
    plt.xlabel("x normalized, origin at top-left")
    plt.ylabel("y normalized, origin at top-left")
    plt.title("Student Position Map From YOLO Boxes")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, dpi=200)
    plt.close()

    return str(output_path)


# =========================
# 8. 生成 HTML 可视化报告
# =========================

def generate_dashboard(
    results: List[Dict[str, Any]],
    summary_df: pd.DataFrame,
    behavior_chart_path: str,
    position_chart_path: Optional[str]
) -> str:
    """
    生成更紧凑的 HTML 可视化报告：
    1. 顶部统计卡片
    2. 图表区域
    3. 可滚动汇总表
    4. 缩略图网格
    5. 点击查看大图
    6. 明细默认折叠
    """

    output_path = OUTPUT_DIR / "classroom_dashboard.html"

    def col_mean(col_name: str) -> float:
        if col_name in summary_df.columns and not summary_df.empty:
            return float(summary_df[col_name].mean())
        return 0.0

    def col_max(col_name: str) -> float:
        if col_name in summary_df.columns and not summary_df.empty:
            return float(summary_df[col_name].max())
        return 0.0

    def row_value(row, col_name: str, default=""):
        try:
            value = row.get(col_name, default)
            if pd.isna(value):
                return default
            return value
        except Exception:
            return default

    # 兼容 expected_people_count 版本
    expected_people_count = ""
    if "expected_people_count" in summary_df.columns and not summary_df.empty:
        expected_people_count = int(summary_df["expected_people_count"].iloc[0])

    avg_student_count = col_mean("student_count")
    avg_detected = col_mean("detected_student_count")
    avg_undetected = col_mean("undetected_student_count")
    avg_unclear = col_mean("unclear")
    max_raise_hand = int(col_max("raise_hand"))

    behavior_chart_rel = output_relative_path(behavior_chart_path)
    position_chart_rel = output_relative_path(position_chart_path) if position_chart_path else ""

    total_minutes = len(summary_df)

    if expected_people_count:
        main_count_title = "固定课堂总人数"
        main_count_value = expected_people_count
    else:
        main_count_title = "平均可见学生人数"
        main_count_value = f"{avg_student_count:.2f}"

    # 顶部统计卡片
    cards_html = f"""
    <div class="cards">
      <div class="card primary-card">
        <div class="card-title">{main_count_title}</div>
        <div class="card-value">{main_count_value}</div>
      </div>
      <div class="card">
        <div class="card-title">分析分钟数</div>
        <div class="card-value">{total_minutes}</div>
      </div>
      <div class="card">
        <div class="card-title">平均明显识别人数</div>
        <div class="card-value">{avg_detected:.2f}</div>
      </div>
      <div class="card">
        <div class="card-title">平均不明确人数</div>
        <div class="card-value">{avg_unclear:.2f}</div>
      </div>
      <div class="card">
        <div class="card-title">最高举手人数</div>
        <div class="card-value">{max_raise_hand}</div>
      </div>
      <div class="card">
        <div class="card-title">平均未明显识别人数</div>
        <div class="card-value">{avg_undetected:.2f}</div>
      </div>
    </div>
    """

    # 汇总表
    summary_rows = ""

    for _, row in summary_df.iterrows():
        minute_index = row_value(row, "minute_index", "")
        start_second = row_value(row, "start_second", "")
        end_second = row_value(row, "end_second", "")
        student_count = row_value(row, "student_count", 0)
        detected_count = row_value(row, "detected_student_count", "")
        undetected_count = row_value(row, "undetected_student_count", "")
        raise_hand = row_value(row, "raise_hand", 0)
        look_up = row_value(row, "look_up", 0)
        look_down = row_value(row, "look_down", 0)
        talk = row_value(row, "talk", 0)
        standing = row_value(row, "standing_or_leaving", 0)
        unclear = row_value(row, "unclear", 0)
        class_state = html_escape(row_value(row, "class_state", ""))
        summary = html_escape(row_value(row, "summary", ""))

        summary_rows += f"""
        <tr>
          <td>{minute_index}</td>
          <td>{start_second} - {end_second}</td>
          <td>{student_count}</td>
          <td>{detected_count}</td>
          <td>{undetected_count}</td>
          <td>{raise_hand}</td>
          <td>{look_up}</td>
          <td>{look_down}</td>
          <td>{talk}</td>
          <td>{standing}</td>
          <td>{unclear}</td>
          <td>{class_state}</td>
          <td class="summary-cell">{summary}</td>
        </tr>
        """

    # 每分钟缩略图卡片
    minute_cards_html = ""

    for res in results:
        minute_index = res.get("minute_index", "")
        start_second = res.get("start_second", "")
        end_second = res.get("end_second", "")
        frame_time = res.get("frame_time_second", "")
        class_state = html_escape(res.get("class_state", ""))
        summary = html_escape(res.get("summary", ""))
        annotated_path = output_relative_path(res.get("annotated_path", ""))

        bc = res.get("behavior_counts", {})
        student_count = res.get("student_count", 0)
        detected_count = res.get("detected_student_count", "")
        undetected_count = res.get("undetected_student_count", "")

        raise_hand = bc.get("raise_hand", 0)
        look_up = bc.get("look_up", 0)
        look_down = bc.get("look_down", 0)
        talk = bc.get("talk", 0)
        standing = bc.get("standing_or_leaving", 0)
        unclear = bc.get("unclear", 0)

        students_html = ""

        for stu in res.get("students", []):
            student_id = html_escape(stu.get("student_id", ""))
            det_id = html_escape(stu.get("det_id", ""))
            behavior = html_escape(stu.get("behavior", ""))
            evidence = html_escape(stu.get("evidence", ""))
            confidence = stu.get("confidence", 0.0)
            is_detected = stu.get("is_detected", True)

            center_norm = stu.get("center_norm", None)
            if isinstance(center_norm, list) and len(center_norm) == 2:
                center_text = f"({center_norm[0]:.3f}, {center_norm[1]:.3f})"
            else:
                center_text = "无"

            try:
                confidence_text = f"{float(confidence):.2f}"
            except Exception:
                confidence_text = ""

            detect_text = "是" if is_detected else "否"

            students_html += f"""
            <tr>
              <td>{student_id}</td>
              <td>{det_id}</td>
              <td>{detect_text}</td>
              <td>{behavior}</td>
              <td>{center_text}</td>
              <td>{confidence_text}</td>
              <td class="evidence-cell">{evidence}</td>
            </tr>
            """

        if not students_html:
            students_html = """
            <tr>
              <td colspan="7">本分钟无学生明细。</td>
            </tr>
            """

        image_html = ""
        if annotated_path:
            image_html = f"""
            <div class="thumb-wrap">
              <img class="thumb-img" src="{annotated_path}" alt="minute {minute_index}">
            </div>
            """

        minute_cards_html += f"""
        <section class="minute-card" data-minute="{minute_index}">
          <div class="minute-header">
            <div>
              <h3>第 {minute_index} 分钟</h3>
              <p>{start_second}s - {end_second}s；截图：{frame_time}s</p>
            </div>
            <button class="view-btn" data-img="{annotated_path}" data-title="第 {minute_index} 分钟">
              查看大图
            </button>
          </div>

          {image_html}

          <div class="mini-stats">
            <span>总人数：{student_count}</span>
            <span>明显识别：{detected_count}</span>
            <span>未明显识别：{undetected_count}</span>
            <span>举手：{raise_hand}</span>
            <span>抬头：{look_up}</span>
            <span>低头：{look_down}</span>
            <span>交谈：{talk}</span>
            <span>站立/离座：{standing}</span>
            <span>不明确：{unclear}</span>
          </div>

          <p class="class-state"><b>课堂状态：</b>{class_state}</p>
          <p class="minute-summary">{summary}</p>

          <details>
            <summary>查看学生行为明细</summary>
            <div class="detail-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>编号</th>
                    <th>检测框</th>
                    <th>明显识别</th>
                    <th>行为</th>
                    <th>中心坐标</th>
                    <th>置信度</th>
                    <th>依据</th>
                  </tr>
                </thead>
                <tbody>
                  {students_html}
                </tbody>
              </table>
            </div>
          </details>
        </section>
        """

    position_chart_html = ""
    if position_chart_rel:
        position_chart_html = f"""
        <section class="panel">
          <h2>学生位置分布</h2>
          <p class="hint">坐标系：原点为图像左上角，x 轴向右，y 轴向下。</p>
          <img class="chart" src="{position_chart_rel}" alt="student position map">
        </section>
        """

    html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>课堂行为分析可视化报告</title>
  <style>
    * {{
      box-sizing: border-box;
    }}

    body {{
      font-family: "Microsoft YaHei", Arial, sans-serif;
      margin: 0;
      background: #f4f6fb;
      color: #1f2937;
    }}

    .page {{
      max-width: 1440px;
      margin: 0 auto;
      padding: 24px;
    }}

    .topbar {{
      position: sticky;
      top: 0;
      z-index: 20;
      background: rgba(244, 246, 251, 0.96);
      backdrop-filter: blur(8px);
      padding: 16px 0;
      border-bottom: 1px solid #e5e7eb;
      margin-bottom: 18px;
    }}

    .topbar h1 {{
      margin: 0 0 8px 0;
      font-size: 28px;
    }}

    .topbar p {{
      margin: 0;
      color: #6b7280;
      line-height: 1.6;
    }}

    .note {{
      background: #fff7df;
      border-left: 5px solid #f59e0b;
      padding: 12px 16px;
      border-radius: 10px;
      margin: 16px 0;
      color: #5f4100;
      line-height: 1.7;
    }}

    .cards {{
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 14px;
      margin: 18px 0;
    }}

    .card {{
      background: #fff;
      border-radius: 16px;
      padding: 16px;
      box-shadow: 0 6px 18px rgba(15, 23, 42, 0.08);
      min-height: 100px;
    }}

    .primary-card {{
      background: linear-gradient(135deg, #eef2ff, #ffffff);
    }}

    .card-title {{
      color: #6b7280;
      font-size: 14px;
      margin-bottom: 8px;
    }}

    .card-value {{
      font-size: 30px;
      font-weight: 700;
      color: #111827;
    }}

    .grid-2 {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 18px;
      align-items: start;
      margin-top: 18px;
    }}

    .panel {{
      background: #fff;
      border-radius: 18px;
      padding: 18px;
      box-shadow: 0 6px 18px rgba(15, 23, 42, 0.08);
      margin-bottom: 18px;
    }}

    .panel h2 {{
      margin: 0 0 12px 0;
      font-size: 22px;
    }}

    .hint {{
      color: #6b7280;
      font-size: 14px;
      margin-top: 0;
      line-height: 1.6;
    }}

    .chart {{
      width: 100%;
      max-height: 420px;
      object-fit: contain;
      display: block;
      border-radius: 12px;
      background: #fff;
    }}

    .table-wrap {{
      max-height: 420px;
      overflow: auto;
      border: 1px solid #e5e7eb;
      border-radius: 12px;
    }}

    table {{
      border-collapse: collapse;
      width: 100%;
      background: #fff;
      font-size: 14px;
    }}

    th, td {{
      border-bottom: 1px solid #e5e7eb;
      padding: 9px 10px;
      text-align: left;
      vertical-align: top;
      white-space: nowrap;
    }}

    th {{
      position: sticky;
      top: 0;
      background: #f9fafb;
      z-index: 5;
      font-weight: 700;
    }}

    .summary-cell,
    .evidence-cell {{
      white-space: normal;
      min-width: 260px;
      line-height: 1.6;
    }}

    .toolbar {{
      display: flex;
      gap: 12px;
      align-items: center;
      margin: 10px 0 16px 0;
      flex-wrap: wrap;
    }}

    .toolbar input {{
      width: 260px;
      padding: 10px 12px;
      border: 1px solid #d1d5db;
      border-radius: 10px;
      font-size: 14px;
    }}

    .minute-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 18px;
    }}

    .minute-card {{
      background: #fff;
      border-radius: 18px;
      padding: 16px;
      box-shadow: 0 6px 18px rgba(15, 23, 42, 0.08);
      display: flex;
      flex-direction: column;
      gap: 12px;
    }}

    .minute-header {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: flex-start;
    }}

    .minute-header h3 {{
      margin: 0;
      font-size: 20px;
    }}

    .minute-header p {{
      margin: 5px 0 0 0;
      color: #6b7280;
      font-size: 13px;
    }}

    .view-btn {{
      border: none;
      background: #2563eb;
      color: #fff;
      padding: 8px 12px;
      border-radius: 10px;
      cursor: pointer;
      white-space: nowrap;
    }}

    .view-btn:hover {{
      background: #1d4ed8;
    }}

    .thumb-wrap {{
      width: 100%;
      height: 220px;
      background: #f3f4f6;
      border-radius: 14px;
      overflow: hidden;
      border: 1px solid #e5e7eb;
    }}

    .thumb-img {{
      width: 100%;
      height: 100%;
      object-fit: contain;
      display: block;
    }}

    .mini-stats {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}

    .mini-stats span {{
      background: #f3f4f6;
      color: #374151;
      padding: 5px 8px;
      border-radius: 999px;
      font-size: 12px;
    }}

    .class-state,
    .minute-summary {{
      margin: 0;
      color: #374151;
      line-height: 1.7;
      font-size: 14px;
    }}

    details {{
      margin-top: 4px;
    }}

    summary {{
      cursor: pointer;
      font-weight: 700;
      color: #2563eb;
      margin-bottom: 8px;
    }}

    .detail-table-wrap {{
      max-height: 260px;
      overflow: auto;
      border: 1px solid #e5e7eb;
      border-radius: 12px;
      margin-top: 8px;
    }}

    .modal {{
      display: none;
      position: fixed;
      z-index: 100;
      left: 0;
      top: 0;
      width: 100%;
      height: 100%;
      background: rgba(0, 0, 0, 0.78);
      padding: 24px;
    }}

    .modal-content {{
      max-width: 96vw;
      max-height: 88vh;
      margin: 48px auto 0 auto;
      display: block;
      background: #fff;
      border-radius: 12px;
    }}

    .modal-title {{
      color: #fff;
      text-align: center;
      font-size: 18px;
      margin-top: 0;
    }}

    .modal-close {{
      position: fixed;
      right: 28px;
      top: 20px;
      color: #fff;
      font-size: 36px;
      cursor: pointer;
      font-weight: 700;
    }}

    @media (max-width: 1200px) {{
      .cards {{
        grid-template-columns: repeat(3, minmax(0, 1fr));
      }}

      .minute-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}

      .grid-2 {{
        grid-template-columns: 1fr;
      }}
    }}

    @media (max-width: 760px) {{
      .page {{
        padding: 14px;
      }}

      .cards {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}

      .minute-grid {{
        grid-template-columns: 1fr;
      }}

      .toolbar input {{
        width: 100%;
      }}

      .thumb-wrap {{
        height: 190px;
      }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <div class="topbar">
      <h1>课堂行为分析可视化报告</h1>
      <p>采用“已知总人数 + YOLO 明显学生检测 + 未明显识别者记为不明确”的统计策略。</p>
    </div>

    <div class="note">
      本报告不进行学生身份识别。YOLO 只负责识别画面中明显可见的学生；无法明显识别的学生统一归入“不明确，需要注意观察”。
      页面采用缩略图布局，点击“查看大图”可查看完整标注图。
    </div>

    {cards_html}

    <div class="grid-2">
      <section class="panel">
        <h2>行为变化趋势</h2>
        <img class="chart" src="{behavior_chart_rel}" alt="behavior timeline">
      </section>

      {position_chart_html}
    </div>

    <section class="panel">
      <h2>每分钟汇总表</h2>
      <p class="hint">表格区域可单独滚动，不再占用整页长度。</p>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>分钟</th>
              <th>时间段/s</th>
              <th>总人数</th>
              <th>明显识别</th>
              <th>未明显识别</th>
              <th>举手</th>
              <th>抬头</th>
              <th>低头</th>
              <th>交谈</th>
              <th>站立/离座</th>
              <th>不明确</th>
              <th>课堂状态</th>
              <th>摘要</th>
            </tr>
          </thead>
          <tbody>
            {summary_rows}
          </tbody>
        </table>
      </div>
    </section>

    <section class="panel">
      <h2>逐分钟标注截图</h2>
      <p class="hint">默认以缩略图卡片展示，明细信息折叠收起，避免页面过长。</p>

      <div class="toolbar">
        <input id="minuteSearch" type="text" placeholder="输入分钟编号筛选，例如 0 或 12">
      </div>

      <div class="minute-grid" id="minuteGrid">
        {minute_cards_html}
      </div>
    </section>
  </div>

  <div id="imageModal" class="modal">
    <span class="modal-close" id="modalClose">&times;</span>
    <p class="modal-title" id="modalTitle"></p>
    <img class="modal-content" id="modalImage">
  </div>

  <script>
    const modal = document.getElementById("imageModal");
    const modalImage = document.getElementById("modalImage");
    const modalTitle = document.getElementById("modalTitle");
    const modalClose = document.getElementById("modalClose");

    document.querySelectorAll(".view-btn").forEach(function(btn) {{
      btn.addEventListener("click", function() {{
        const img = this.getAttribute("data-img");
        const title = this.getAttribute("data-title");

        if (!img) {{
          alert("该分钟没有可查看的标注图片。");
          return;
        }}

        modal.style.display = "block";
        modalImage.src = img;
        modalTitle.textContent = title || "";
      }});
    }});

    modalClose.onclick = function() {{
      modal.style.display = "none";
      modalImage.src = "";
    }};

    modal.onclick = function(event) {{
      if (event.target === modal) {{
        modal.style.display = "none";
        modalImage.src = "";
      }}
    }};

    document.getElementById("minuteSearch").addEventListener("input", function() {{
      const keyword = this.value.trim();
      const cards = document.querySelectorAll(".minute-card");

      cards.forEach(function(card) {{
        const minute = card.getAttribute("data-minute") || "";
        if (!keyword || minute.includes(keyword)) {{
          card.style.display = "flex";
        }} else {{
          card.style.display = "none";
        }}
      }});
    }});
  </script>
</body>
</html>
"""

    output_path.write_text(html, encoding="utf-8")
    return str(output_path)

    output_path.write_text(html, encoding="utf-8")
    return str(output_path)


# =========================
# 9. 主流程
# =========================

def main():
    args = parse_args()
    global EXPECTED_PEOPLE_COUNT
    EXPECTED_PEOPLE_COUNT = int(args.expected_people)
    check_ffmpeg()

    video_path = Path(args.video).expanduser().resolve()
    if not video_path.exists():
        raise FileNotFoundError(f"未找到视频文件：{video_path}")

    print(f"当前方舟模型：{ARK_MODEL}")
    print(f"当前 YOLO 模型：{YOLO_MODEL_PATH}")
    print(f"YOLO_CONF={YOLO_CONF}, YOLO_IOU={YOLO_IOU}, YOLO_IMG_SIZE={YOLO_IMG_SIZE}")
    print(f"课堂固定总人数：{EXPECTED_PEOPLE_COUNT}")
    print(f"当前视频：{video_path}")

    print("开始每分钟抽取一帧...")
    frame_infos = extract_minute_frames(video_path)
    print(f"共抽取 {len(frame_infos)} 帧。")

    results = []

    print("开始执行 YOLO 检测并调用方舟模型分析每分钟截图...")

    for frame_info in tqdm(frame_infos):
        try:
            result = analyze_frame(frame_info)
            annotated_path = annotate_frame(result)
            result["annotated_path"] = annotated_path
            results.append(result)

        except Exception as e:
            print(f"第 {frame_info['minute_index']} 分钟分析失败：{e}")

            failed_result = {
                "minute_index": frame_info["minute_index"],
                "start_second": frame_info["start_second"],
                "end_second": frame_info["end_second"],
                "frame_time_second": frame_info["frame_time_second"],
                "frame_path": str(frame_info["frame_path"]),
                "annotated_path": "",
                "image_width": None,
                "image_height": None,
                "coordinate_system": "origin_top_left_x_right_y_down_normalized",
                "expected_people_count": EXPECTED_PEOPLE_COUNT,
                "yolo_person_count": 0,
                "detected_student_count": 0,
                "undetected_student_count": EXPECTED_PEOPLE_COUNT,
                "yolo_detections": [],
                "yolo_debug_path": "",
                "student_count": EXPECTED_PEOPLE_COUNT,
                "students": normalize_to_expected_count([], EXPECTED_PEOPLE_COUNT),
                "excluded_persons": [],
                "behavior_counts": recompute_behavior_counts(normalize_to_expected_count([], EXPECTED_PEOPLE_COUNT)),
                "class_state": "分析失败",
                "summary": str(e),
                "overall_confidence": 0.0
            }

            results.append(failed_result)

    print("开始整理结果...")

    json_path = OUTPUT_DIR / "classroom_behavior_result.json"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    student_df = flatten_results(results)
    summary_df = build_minute_summary(results)
    yolo_df = build_yolo_detection_table(results)

    student_csv_path = OUTPUT_DIR / "classroom_behavior_student_detail.csv"
    summary_csv_path = OUTPUT_DIR / "classroom_behavior_minute_summary.csv"
    yolo_csv_path = OUTPUT_DIR / "classroom_yolo_detection_detail.csv"
    xlsx_path = OUTPUT_DIR / "classroom_behavior_result.xlsx"

    student_df.to_csv(student_csv_path, index=False, encoding="utf-8-sig")
    summary_df.to_csv(summary_csv_path, index=False, encoding="utf-8-sig")
    yolo_df.to_csv(yolo_csv_path, index=False, encoding="utf-8-sig")

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="minute_summary", index=False)
        student_df.to_excel(writer, sheet_name="student_detail", index=False)
        yolo_df.to_excel(writer, sheet_name="yolo_detection_detail", index=False)

    behavior_chart_path = plot_behavior_timeline(summary_df)
    position_chart_path = plot_student_position_map(student_df)

    dashboard_path = generate_dashboard(
        results=results,
        summary_df=summary_df,
        behavior_chart_path=behavior_chart_path,
        position_chart_path=position_chart_path
    )

    print("分析完成！")
    print(f"JSON 结果：{json_path}")
    print(f"学生明细 CSV：{student_csv_path}")
    print(f"分钟汇总 CSV：{summary_csv_path}")
    print(f"YOLO 检测明细 CSV：{yolo_csv_path}")
    print(f"Excel 结果：{xlsx_path}")
    print(f"可视化报告：{dashboard_path}")
    print(f"可以直接双击打开 {OUTPUT_DIR / 'classroom_dashboard.html'} 查看结果。")

    if args.open_report:
        webbrowser.open(Path(dashboard_path).resolve().as_uri())


if __name__ == "__main__":
    main()
