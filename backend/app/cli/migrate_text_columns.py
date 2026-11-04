'''文本列类型迁移（幂等，可重复执行）

背景：早期版本的模型把 `document_chunk.content` / `chat_message.content` 声明成
VARCHAR(255)，后来改成 `Text`。但 SQLModel 的 `create_all` 只建缺表、**不会修改已存在的列**，
所以老库升级后这两列仍是 varchar(255)，引发两个问题：

1. 向量化：分块正文普遍 500~800 字，插入时报
   `(1406, "Data too long for column 'content'")`，整篇文档入库失败（页面显示"向量化失败"）；
2. 问答：AI 回答一般远超 255 字，写入 chat_message 同样失败，表现为发消息报错。

本脚本把这两列统一扩为 TEXT（与模型声明一致），不删表、不改数据，可重复执行。

用法：
    容器：docker compose exec backend python -m app.cli.migrate_text_columns
    本地：uv run python -m app.cli.migrate_text_columns --host 127.0.0.1 --port 16666
    预演：追加 --dry-run 只打印将要执行的 SQL
'''
import argparse
import sys

from app.cli._db import connect

# 需要确保为 TEXT 的列（表名, 列名, 模型中的声明）
TEXT_COLUMNS: list[tuple[str, str]] = [
    ("document_chunk", "content"),
    ("chat_message", "content"),
]

# 已经够宽的类型，无需处理
WIDE_TYPES = {"text", "mediumtext", "longtext"}


def column_type(cur, table: str, column: str) -> str | None:
    cur.execute(
        "SELECT DATA_TYPE FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s",
        (table, column),
    )
    row = cur.fetchone()
    return row[0].lower() if row else None


def run(host: str | None, port: int | None, dry_run: bool) -> int:
    conn, params = connect(host, port)
    print(f"[迁移]目标库：{params['user']}@{params['host']}:{params['port']}/{params['database']}")

    changed = 0
    try:
        with conn.cursor() as cur:
            for table, column in TEXT_COLUMNS:
                data_type = column_type(cur, table, column)
                if data_type is None:
                    print(f"[迁移]表 {table}.{column} 不存在，跳过（该表会在服务启动时自动创建）")
                    continue
                if data_type in WIDE_TYPES:
                    print(f"[迁移]{table}.{column} 已是 {data_type}，跳过")
                    continue

                cur.execute(f"SELECT COUNT(*) FROM `{table}`")
                before = cur.fetchone()[0]

                sql = f"ALTER TABLE `{table}` MODIFY COLUMN `{column}` TEXT NOT NULL"
                print(f"[迁移]{table}.{column} 当前 {data_type}，行数 {before}")
                print(f"[迁移]{'[dry-run] ' if dry_run else ''}{sql}")
                if dry_run:
                    continue
                cur.execute(sql)
                changed += 1
                print(f"[迁移]{table}.{column} → 已改为 TEXT")

            if dry_run:
                conn.rollback()
                print("[迁移]dry-run 结束，未写入任何变更")
                return 0

            conn.commit()

            # 复核
            for table, column in TEXT_COLUMNS:
                data_type = column_type(cur, table, column)
                if data_type is not None:
                    print(f"[迁移]复核 {table}.{column} = {data_type}")
        print(f"[迁移]完成，实际变更 {changed} 列")
        return 0
    except Exception as e:
        conn.rollback()
        print(f"[迁移]失败，已回滚：{e}", file=sys.stderr)
        return 1
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="文本列类型迁移（document_chunk / chat_message → TEXT）")
    parser.add_argument("--host", default=None, help="MySQL 主机（默认取环境变量/env 文件）")
    parser.add_argument("--port", type=int, default=None, help="MySQL 端口（默认取环境变量/env 文件）")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要执行的 SQL，不写入")
    args = parser.parse_args()
    return run(args.host, args.port, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
