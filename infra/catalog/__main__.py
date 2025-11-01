"""
Catalog模块命令行入口点

支持通过 python -m catalog 调用CLI工具
"""

import sys
from .cli import main

if __name__ == '__main__':
    sys.exit(main())