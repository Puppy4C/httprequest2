# 简单压测器

这是一个用 Python 编写的简单网页压测器。它提供一个网页界面，可以配置并发数、持续时间和目标 URL，启动后会并发发送带随机人名的 GET 请求（q 参数），并在页面上显示基本统计信息。

运行：

```bash
python3 -m pip install -r requirements.txt
python3 server.py
# 打开浏览器访问 http://localhost:8000
```

注意：此工具用于测试目的。请确保你有权对目标地址进行压测，避免对未授权的服务发起高并发请求。
# httprequest