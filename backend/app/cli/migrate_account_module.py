'''账号管理模块数据库迁移脚本（幂等，可重复执行）

只做三件事：
1. 放宽 `user.phone` 为可空（字段类型不变，仅去掉 NOT NULL）
2. 新增账号模块字段（已存在则跳过）
3. `username` 加唯一索引并回填历史数据

不删表、不改字段类型、不物理删除数据。

用法：
    本地：uv run python -m app.cli.migrate_account_module
    容器：docker compose exec backend python -m app.cli.migrate_account_module
    可指定连接：--host 127.0.0.1 --port 16666
'''
import argparse
import sys

from app.cli._db import connect

# 新增列定义（列名, DDL 片段）
NEW_COLUMNS: list[tuple[str, str]] = [
    ("role", "varchar(10) NOT NULL DEFAULT 'user' COMMENT '角色：admin/user'"),
    ("level", "tinyint NULL DEFAULT 1 COMMENT '等级：1/2/3；管理员为 NULL'"),
    ("status", "varchar(10) NOT NULL DEFAULT 'active' COMMENT '状态：active/disabled'"),
    ("must_change_password", "tinyint(1) NOT NULL DEFAULT 0 COMMENT '是否需修改密码'"),
    ("created_by", "int NULL COMMENT '创建人 user.id'"),
    ("deleted_at", "datetime NULL COMMENT '软删除时间'"),
    ("failed_attempts", "int NOT NULL DEFAULT 0 COMMENT '连续登录失败次数'"),
    ("locked_until", "datetime NULL COMMENT '登录锁定截止时间'"),
]


def column_exists(cur, table: str, column: str) -> bool:
    cur.execute(
        "SELECT 1 FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s",
        (table, column),
    )
    return cur.fetchone() is not None


def phone_is_nullable(cur) -> bool:
    cur.execute(
        "SELECT IS_NULLABLE FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'user' AND COLUMN_NAME = 'phone'",
    )
    row = cur.fetchone()
    return bool(row) and row[0] == "YES"


def has_unique_index_on(cur, table: str, column: str) -> bool:
    cur.execute(
        "SELECT INDEX_NAME, NON_UNIQUE, GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS cols "
        "FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s "
        "GROUP BY INDEX_NAME, NON_UNIQUE",
        (table,),
    )
    for _name, non_unique, cols in cur.fetchall():
        if non_unique == 0 and cols == column:
            return True
    return False


def run(host: str | None, port: int | None, dry_run: bool) -> int:
    conn, params = connect(host, port)
    print(f"[迁移]目标库：{params['user']}@{params['host']}:{params['port']}/{params['database']}")

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM user")
            total_before = cur.fetchone()[0]
            print(f"[迁移]当前 user 表行数：{total_before}")

            # ---------- 1. phone 放宽为可空 ----------
            if phone_is_nullable(cur):
                print("[迁移]phone 已可空，跳过")
            else:
                sql = "ALTER TABLE `user` MODIFY COLUMN `phone` varchar(20) NULL COMMENT '手机号（历史字段，新账号为空）'"
                print(f"[迁移]{'[dry-run] ' if dry_run else ''}{sql}")
                if not dry_run:
                    cur.execute(sql)

            # ---------- 2. 新增列 ----------
            for column, ddl in NEW_COLUMNS:
                if column_exists(cur, "user", column):
                    print(f"[迁移]列 {column} 已存在，跳过")
                    continue
                sql = f"ALTER TABLE `user` ADD COLUMN `{column}` {ddl}"
                print(f"[迁移]{'[dry-run] ' if dry_run else ''}{sql}")
                if not dry_run:
                    cur.execute(sql)

            # ---------- 3. username 唯一索引 ----------
            if has_unique_index_on(cur, "user", "username"):
                print("[迁移]username 唯一索引已存在，跳过")
            else:
                sql = "ALTER TABLE `user` ADD UNIQUE KEY `ux_user_username` (`username`)"
                print(f"[迁移]{'[dry-run] ' if dry_run else ''}{sql}")
                if not dry_run:
                    cur.execute(sql)

            # ---------- 4. 历史数据回填 ----------
            backfills = [
                ("回填 username=phone", "UPDATE `user` SET `username` = `phone` "
                                        "WHERE (`username` IS NULL OR `username` = '') AND `phone` IS NOT NULL AND `phone` <> ''"),
                ("回填 role=user", "UPDATE `user` SET `role` = 'user' WHERE `role` IS NULL OR `role` = ''"),
                ("回填 level=1", "UPDATE `user` SET `level` = 1 WHERE `level` IS NULL"),
                ("回填 status=active", "UPDATE `user` SET `status` = 'active' WHERE `status` IS NULL OR `status` = ''"),
            ]
            for label, sql in backfills:
                if dry_run:
                    print(f"[迁移][dry-run] {label}")
                    continue
                cur.execute(sql)
                print(f"[迁移]{label}，影响 {cur.rowcount} 行")

            if dry_run:
                conn.rollback()
                print("[迁移]dry-run 结束，未写入任何变更")
                return 0

            conn.commit()

            cur.execute("SELECT COUNT(*) FROM user")
            total_after = cur.fetchone()[0]
            print(f"[迁移]完成，user 表行数：{total_before} → {total_after}")
        return 0
    except Exception as e:
        conn.rollback()
        print(f"[迁移]失败，已回滚：{e}", file=sys.stderr)
        return 1
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="账号管理模块数据库迁移（幂等）")
    parser.add_argument("--host", default=None, help="MySQL 主机（默认取环境变量/env 文件）")
    parser.add_argument("--port", type=int, default=None, help="MySQL 端口（默认取环境变量/env 文件）")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要执行的 SQL，不写入")
    args = parser.parse_args()
    return run(args.host, args.port, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
