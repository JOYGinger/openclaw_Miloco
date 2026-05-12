#!/usr/bin/env python3
"""
单张图片测试 - 验证阿里云百炼 API 是否正常工作
"""
import os
import sys
import base64
import requests

# 设置 API Key（从环境变量读取）
API_KEY = os.environ.get("DASHSCOPE_API_KEY")
if not API_KEY:
    print("错误：请设置环境变量 DASHSCOPE_API_KEY")
    print("示例: $env:DASHSCOPE_API_KEY='sk-xxxxx'")
    sys.exit(1)

def test_with_real_image(image_path):
    """用真实图片测试 API"""
    print(f"测试图片: {image_path}")
    print("-" * 50)
    
    # 读取图片
    with open(image_path, "rb") as f:
        image_base64 = base64.b64encode(f.read()).decode('utf-8')
    
    # 调用 API
    try:
        response = requests.post(
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "qwen-vl-max",
                "input": {
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"image": f"data:image/jpeg;base64,{image_base64}"},
                                {"text": "分析这个学生的学习行为：1.是否抬头看前方？2.是否举手？3.是否在记笔记？请用JSON格式返回结果。"}
                            ]
                        }
                    ]
                }
            },
            timeout=60
        )
        
        print(f"状态码: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            content = result.get("output", {}).get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"\n模型响应:")
            print(content)
            print("\n✅ API 调用成功！")
            return True
        else:
            print(f"错误: {response.text}")
            return False
            
    except Exception as e:
        print(f"调用失败: {e}")
        return False

if __name__ == "__main__":
    # 测试第一张学生图片
    test_image = r"F:\jhqstudy03\开源技术与应用\测试视频\30s_0421学生检测_v3\students\student_01\frame_0001.jpg"
    
    if not os.path.exists(test_image):
        print(f"错误：找不到图片 {test_image}")
        print("请提供正确的图片路径作为参数")
        sys.exit(1)
    
    test_with_real_image(test_image)
