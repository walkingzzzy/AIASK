#!/usr/bin/env python
"""
启动Streamlit应用
"""
import subprocess
import sys
import os

# 获取app目录
app_dir = os.path.dirname(os.path.abspath(__file__))
app_file = os.path.join(app_dir, "app", "streamlit_app.py")


def main():
    """启动Streamlit应用"""
    print("🚀 启动A股智能分析系统...")
    print(f"📁 应用路径: {app_file}")
    print("-" * 50)

    # 启动streamlit
    cmd = [sys.executable, "-m", "streamlit", "run", app_file, "--server.port=8501"]

    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\n👋 应用已停止")
    except FileNotFoundError:
        print("❌ 请先安装streamlit: pip install streamlit")
        sys.exit(1)


if __name__ == "__main__":
    main()
