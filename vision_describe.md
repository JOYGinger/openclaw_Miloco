# 基于fastAPI和Ollama大模型的智能视频识别web系统
## 系统工作流程
- 采集rtsp视频流
- 将视频流抽帧发送给大模型识别
- 分析结果通过webSocket推送给网页
- 浏览器通过http流实时显示画面
## 项目技术栈
### 后端：
FastAPI 
OpenCV 
Ollama
### 前端：
单页 HTML：左侧视频流，右侧识别结果（支持 Markdown 渲染）
### 通信：
视频走 HTTP MJPEG 流
识别结果走 WebSocket
## 文件结构
```vision_describe/
├── 📄 main.py                 # FastAPI主应用程序
├── 📄 version_llm.py          # 基于tkinter的桌面版本（原型）
├── 📄 requirements.txt        # Python依赖包列表
├── 📄 README.md              # 项目说明文档
├── 📁 templates/             # Jinja2模板文件夹
│   └── 📄 index.html         # 主页面模板
└── 📁 static/                # 静态资源文件夹
    ├── 📄 style.css          # 主样式文件
    ├── 📁 css/               # CSS样式文件夹
    │   └── 📄 markdown.css   # Markdown渲染样式
    └── 📁 js/                # JavaScript文件夹
        └── 📄 markdown-utils.js # Markdown工具函数
```
## 这个开源被壁了，没有使用openclaw