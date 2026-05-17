import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from datetime import datetime


VIDEO_EXTENSIONS = {
    ".mp4",
    ".avi",
    ".mov",
    ".mkv",
    ".flv",
    ".wmv",
    ".m4v"
}


def safe_name(name: str) -> str:
    """将视频文件名转成适合作为输出文件夹名的安全名称。"""
    name = Path(name).stem
    name = re.sub(r'[\\/:*?"<>|]+', "_", name)
    name = re.sub(r"\s+", "_", name)
    return name[:80] if len(name) > 80 else name


def find_videos(folder: Path, recursive: bool = False):
    """查找文件夹中的视频文件。"""
    if recursive:
        files = folder.rglob("*")
    else:
        files = folder.glob("*")

    videos = [
        p for p in files
        if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
    ]

    videos.sort(key=lambda p: p.name.lower())
    return videos


def run_one_video(
    video_path: Path,
    script_path: Path,
    expected_people: int,
    output_root: Path,
    python_exe: str,
    open_report: bool = False
):
    """调用主分析脚本分析单个视频。"""
    video_name = safe_name(video_path.name)
    output_dir = output_root / video_name

    output_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()

    # 这里覆盖 .env 中的 OUTPUT_DIR。
    # python-dotenv 默认不会覆盖系统环境变量，所以这个设置会优先生效。
    env["OUTPUT_DIR"] = str(output_dir)
    env["EXPECTED_PEOPLE_COUNT"] = str(expected_people)

    cmd = [
        python_exe,
        str(script_path),
        "--video",
        str(video_path),
        "--expected-people",
        str(expected_people)
    ]

    if open_report:
        cmd.append("--open-report")

    print("=" * 80)
    print(f"开始分析视频：{video_path}")
    print(f"输出目录：{output_dir}")
    print(f"课堂总人数：{expected_people}")
    print("=" * 80)

    result = subprocess.run(
        cmd,
        cwd=str(script_path.parent),
        env=env,
        text=True
    )

    dashboard_path = output_dir / "classroom_dashboard.html"
    excel_path = output_dir / "classroom_behavior_result.xlsx"
    summary_csv_path = output_dir / "classroom_behavior_minute_summary.csv"

    return {
        "video": str(video_path),
        "output_dir": str(output_dir),
        "dashboard": str(dashboard_path) if dashboard_path.exists() else "",
        "excel": str(excel_path) if excel_path.exists() else "",
        "summary_csv": str(summary_csv_path) if summary_csv_path.exists() else "",
        "return_code": result.returncode
    }


def generate_batch_index(records, output_root: Path):
    """生成一个批量分析总览 HTML。"""
    index_path = output_root / "batch_index.html"

    rows = ""

    for idx, rec in enumerate(records, start=1):
        status = "成功" if rec["return_code"] == 0 else "失败"

        dashboard_link = (
            f'<a href="{Path(rec["dashboard"]).name}">打开报告</a>'
            if rec["dashboard"] and Path(rec["dashboard"]).parent == output_root
            else ""
        )

        # 每个视频有独立子目录，所以这里用相对路径
        if rec["dashboard"]:
            dashboard_rel = Path(rec["dashboard"]).relative_to(output_root).as_posix()
            dashboard_link = f'<a href="{dashboard_rel}" target="_blank">打开 HTML 报告</a>'

        excel_link = ""
        if rec["excel"]:
            excel_rel = Path(rec["excel"]).relative_to(output_root).as_posix()
            excel_link = f'<a href="{excel_rel}" target="_blank">打开 Excel</a>'

        summary_link = ""
        if rec["summary_csv"]:
            csv_rel = Path(rec["summary_csv"]).relative_to(output_root).as_posix()
            summary_link = f'<a href="{csv_rel}" target="_blank">打开 CSV</a>'

        rows += f"""
        <tr>
          <td>{idx}</td>
          <td>{rec["video"]}</td>
          <td>{status}</td>
          <td>{rec["output_dir"]}</td>
          <td>{dashboard_link}</td>
          <td>{excel_link}</td>
          <td>{summary_link}</td>
        </tr>
        """

    html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>课堂视频批量分析结果</title>
  <style>
    body {{
      font-family: "Microsoft YaHei", Arial, sans-serif;
      background: #f5f6fa;
      margin: 0;
      padding: 24px;
      color: #222;
    }}
    .container {{
      max-width: 1280px;
      margin: 0 auto;
      background: #fff;
      border-radius: 16px;
      padding: 24px;
      box-shadow: 0 6px 20px rgba(0,0,0,0.08);
    }}
    h1 {{
      margin-top: 0;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 16px;
    }}
    th, td {{
      border: 1px solid #ddd;
      padding: 10px;
      font-size: 14px;
      vertical-align: top;
    }}
    th {{
      background: #f0f2f5;
    }}
    a {{
      color: #2563eb;
      text-decoration: none;
      font-weight: bold;
    }}
    .note {{
      background: #fff8e1;
      border-left: 5px solid #ffcc33;
      padding: 12px 16px;
      border-radius: 8px;
      margin: 16px 0;
    }}
  </style>
</head>
<body>
  <div class="container">
    <h1>课堂视频批量分析结果</h1>
    <div class="note">
      生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}<br>
      每个视频的分析结果保存在独立子目录中。
    </div>
    <table>
      <thead>
        <tr>
          <th>序号</th>
          <th>视频路径</th>
          <th>状态</th>
          <th>输出目录</th>
          <th>HTML 报告</th>
          <th>Excel 结果</th>
          <th>CSV 汇总</th>
        </tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>
  </div>
</body>
</html>
"""

    index_path.write_text(html, encoding="utf-8")
    return index_path


def main():
    parser = argparse.ArgumentParser(description="批量分析文件夹中的课堂视频")
    parser.add_argument(
        "--folder",
        required=True,
        help="包含课堂视频的文件夹路径"
    )
    parser.add_argument(
        "--expected-people",
        type=int,
        default=24,
        help="课堂总人数，默认 24"
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="是否递归分析子文件夹中的视频"
    )
    parser.add_argument(
        "--output-root",
        default="outputs_known_total",
        help="批量输出根目录"
    )
    parser.add_argument(
        "--script",
        default="analyze_classroom_yolo_known_total.py",
        help="主分析脚本路径"
    )
    parser.add_argument(
        "--open-first-report",
        action="store_true",
        help="是否自动打开第一个视频的报告"
    )
    args = parser.parse_args()

    project_dir = Path(__file__).resolve().parent
    folder = Path(args.folder).expanduser().resolve()
    script_path = (project_dir / args.script).resolve()
    output_root = (project_dir / args.output_root).resolve()

    if not folder.exists():
        raise FileNotFoundError(f"未找到视频文件夹：{folder}")

    if not script_path.exists():
        raise FileNotFoundError(f"未找到主分析脚本：{script_path}")

    output_root.mkdir(parents=True, exist_ok=True)

    videos = find_videos(folder, recursive=args.recursive)

    if not videos:
        print(f"在文件夹中没有找到视频文件：{folder}")
        print(f"支持的视频后缀：{sorted(VIDEO_EXTENSIONS)}")
        return

    print(f"共找到 {len(videos)} 个视频文件。")

    records = []

    for idx, video_path in enumerate(videos):
        open_report = args.open_first_report and idx == 0

        rec = run_one_video(
            video_path=video_path,
            script_path=script_path,
            expected_people=args.expected_people,
            output_root=output_root,
            python_exe=sys.executable,
            open_report=open_report
        )

        records.append(rec)

    index_path = generate_batch_index(records, output_root)

    print("=" * 80)
    print("批量分析完成。")
    print(f"总览页面：{index_path}")
    print("每个视频的报告在 outputs_known_total 对应子文件夹中。")
    print("=" * 80)


if __name__ == "__main__":
    main()