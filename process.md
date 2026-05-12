## 前置准备
### 账号准备
阿里云账号 用魔塔社区在线调用

尝试Qwen3-VL
提示词如下


### 云端大模型
云服务器租用 AutoDL
配置要求：

### 本地大模型
#### 环境与准备
Win11：Windows 11 
CPU：12th Gen Intel(R) Core(TM) i7-12700H (2.30 GHz)
内存：16.0 GB
显卡：4GB
Ollama： 0.17.7
大模型：qwen2.5-7b-instruct-q4_k_m

### 0421汇报记录

下一步工作：
- 找论文和baseline，学习图像识别相关流程
- 有github源码/skill供参考，（腾讯skillhub；阿里skill某平台，不清楚具体名字；clawhub中文官方镜像）
- 最后集成一个工作流workflow -> 
  |
  视频
  |
  视频拆分（一分钟截图一次）
  |
  视频切割（利用传统图像识别模型，对坐标/位置进行拆分）
  |
  给大模型（识别学生专注/分散行为）
  |
  蒸馏出一个skill（输入位置坐标，输出该位置上学生的专注行为）
- **汇报0428**，要求初步demo，对GitHub上项目跑通

Q：直接调用大模型API以对话的形式上传一段视频，ai对人物状态变化识别准确，但是对人物数量识别不准
A：大模型除非是调用外部calculator工具，不然确实不具备准确计算能力。实际上大模型是基于transformer模型，把输入拆成token，与海量的数据匹配去计算token和token的上下文概率。有的大模型能够答对可能是曾经有人给他喂了答案。

### 0421-0422
openclaw配置，还没有接入qq
openclaw gateway token==
```
138ee2817a53136a067a42db0964d33f3df089a66685ffc6
```
### 0427
将openclaw接入qq，可以对浏览器进行操作
现在的问题，找到一篇参考论文
柳暗花明又一村，找到了一篇开源GitHub，天助我也。

#### 记录
理论文章https://cloud.tencent.com/developer/article/2593005


#### 配置进度
- 创建python虚拟环境，在项目目录下
```
python -m venv venv
venv\Scripts\activate
```
- 安装python依赖
```







pip install -r requirements.txt
```
- ollama部署qwen2.5-3b本地大模型
```
//启动
ollama serve
//拉取qwen2.5vl-3b
ollama pull qwen2.5vl:3b
```
（以下为尝试，已失败）
- 将电脑自带摄像头转换为rtsp视频流，参考文章https://blog.csdn.net/qq_15060477/article/details/150153673
```
//本地摄像头名称
"USB2.0 FHD UVC WebCam" (video)

ffplay -f dshow -i video="USB2.0 FHD UVC WebCam"

//
ffmpeg -f dshow -i video="USB2.0 FHD UVC WebCam" -preset ultrafast -tune zerolatency -f rtsp rtsp://localhost:8554/live.stream

//改进版，电脑摄像头太清晰了
ffmpeg -f dshow -video_size 640x480 -framerate 30 -i video="USB2.0 FHD UVC WebCam" -c:v libx264 -preset ultrafast -tune zerolatency -f rtsp rtsp://localhost:8554/live.stream

//rtsp视频流地址
rtsp://localhost:8554/live.stream
```
（以上为尝试，已失败）
- 将rtsp视频流暂时设置为电脑自带摄像头
- 运行，在虚拟环境下
```
python main.py
```
- 本地访问：http://localhost:8000

#### 总结
电脑配置不足，跑的非常慢，需要一个服务器，希望可以提供autoDL账号、腾讯云或者阿里云账号

【还需要做的】
- 思考云服务器配置与大模型部署
- miloco的rtsp视频流放入代码
- 如何云连接大模型
- 报告输出是否需要数据库
- 大模型是否需要训练？如何训练？
- 技术栈的选型？

## 0429
在使用龙虾进行工作流创建
买了一个百度千帆codingplan
需要进行配置


## 0508
项目进度记录
```
memory/2026-05-08-classroom-analysis-project.md
```

## 0512
需要做的
- 首先固定坐标位置识别人像
- yolov8微调，考虑是否有其他可以裁切
- 多模态大模型调用

【注意-上传至GitHub远程仓库时不要开梯子，不然端口号不同找不到仓库】