#!/usr/bin/env python3
"""
AhaIndexSync Pipeline 统一入口

用法:
    python main.py                          # 默认 daily 模式
    python main.py --mode test --suffix _test
    python main.py --scraper "GitHub Trending"
"""

import argparse
import os
from pipeline.runner import run_pipeline


def main():
    parser = argparse.ArgumentParser(description="AhaIndexSync Pipeline")
    parser.add_argument("--mode", default=os.getenv("RUN_MODE", "daily"), help="运行模式: daily / test / manual")
    parser.add_argument("--suffix", default=os.getenv("TABLE_SUFFIX", ""), help="表后缀，如 _test")
    parser.add_argument("--scraper", default=os.getenv("SCRAPER_NAME", ""), help="指定 scraper name 或 type")
    args = parser.parse_args()

    run_pipeline(
        mode=args.mode,
        table_suffix=args.suffix,
        scraper_name=args.scraper,
    )


if __name__ == "__main__":
    main()
