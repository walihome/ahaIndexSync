# scrapers/registry.py
# 自动扫描 scrapers/ 目录，发现并实例化所有 BaseScraper 子类
# 新增 scraper 只需新建文件，不需要改这里

import importlib
import pkgutil
import inspect
from pathlib import Path
from infra.models import BaseScraper


def discover_scrapers() -> list[BaseScraper]:
    scrapers = []
    seen_classes = set()

    package_dir = Path(__file__).parent
    package_name = "scrapers"

    for finder, module_name, is_pkg in pkgutil.walk_packages(
        path=[str(package_dir)],
        prefix=f"{package_name}.",
        onerror=lambda x: None,
    ):
        if any(skip in module_name for skip in ["registry", "__"]):
            continue

        try:
            module = importlib.import_module(module_name)
        except Exception as e:
            print(f"⚠️ 导入模块失败 {module_name}: {e}")
            continue

        for _, cls in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(cls, BaseScraper)
                and cls is not BaseScraper
                and cls not in seen_classes
                and cls.__module__ == module_name
            ):
                seen_classes.add(cls)
                try:
                    scrapers.append(cls())
                except Exception as e:
                    print(f"⚠️ 实例化失败 {cls.__name__}: {e}")

    return scrapers