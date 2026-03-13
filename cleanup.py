# cleanup.py
# 清空测试表，只在 TABLE_SUFFIX 非空时允许执行

import os
import sys
from infra.db import supabase, RAW_TABLE, PROCESSED_TABLE, DISPLAY_TABLE

TABLE_SUFFIX = os.getenv("TABLE_SUFFIX", "")

# 各表用哪个字段做 delete 条件（Supabase delete 必须带 where）
TABLE_DELETE_KEY = {
    RAW_TABLE:       ("id", ""),
    PROCESSED_TABLE: ("item_id", ""),
    DISPLAY_TABLE:   ("id", "00000000-0000-0000-0000-000000000000"),  # uuid 类型
}


def main():
    if not TABLE_SUFFIX:
        print("❌ TABLE_SUFFIX 为空，拒绝执行，保护生产数据")
        sys.exit(1)

    print(f"\n🗑️  清空测试表（suffix={TABLE_SUFFIX}）")

    for table, (key, exclude_val) in TABLE_DELETE_KEY.items():
        try:
            supabase.table(table).delete().neq(key, exclude_val).execute()
            print(f"  ✅ {table} 已清空")
        except Exception as e:
            print(f"  ⚠️  {table} 清空失败: {e}")

    print("✨ 完成\n")


if __name__ == "__main__":
    main()
