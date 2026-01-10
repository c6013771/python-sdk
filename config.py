# config.py
from dotenv import load_dotenv
import os

load_dotenv()  # 加载 .env 文件

APIKEY = os.getenv("APIKEY")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")

