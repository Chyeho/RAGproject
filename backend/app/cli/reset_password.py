'''命令行重置账号密码（不走 UI，适用于重置管理员密码）

用法：
    uv run python -m app.cli.reset_password --username admin
    uv run python -m app.cli.reset_password --username admin --password 'NewPassw0rd!'
    docker compose exec backend python -m app.cli.reset_password --username admin

不带 --password 时随机生成并仅在终端打印一次；重置后置 must_change_password=1。
'''
import argparse
import sys

from app.cli._db import connect
from app.core.security import generate_password, hash_password


def main() -> int:
    parser = argparse.ArgumentParser(description="重置账号密码（仅修改哈希，不打印存储值）")
    parser.add_argument("--username", required=True, help="要重置的登录账号")
    parser.add_argument("--password", default=None, help="指定新密码（不传则随机生成）")
    parser.add_argument("--host", default=None, help="MySQL 主机（默认取环境变量/env 文件）")
    parser.add_argument("--port", type=int, default=None, help="MySQL 端口（默认取环境变量/env 文件）")
    args = parser.parse_args()

    password = args.password or generate_password()
    if len(password) < 8:
        print("[重置]密码长度不足 8 位，已拒绝执行", file=sys.stderr)
        return 1

    conn, params = connect(args.host, args.port)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, role, status FROM `user` WHERE `username` = %s AND `deleted_at` IS NULL",
                (args.username,),
            )
            row = cur.fetchone()
            if not row:
                print(f"[重置]账号 {args.username} 不存在，未做任何修改", file=sys.stderr)
                return 1

            user_id, role, status = row
            cur.execute(
                "UPDATE `user` SET `password_hash` = %s, `must_change_password` = 1, "
                "`failed_attempts` = 0, `locked_until` = NULL WHERE `id` = %s",
                (hash_password(password), user_id),
            )
            conn.commit()

        print(f"[重置]已重置账号 {args.username}（id={user_id}, role={role}, status={status}）")
        if args.password:
            print("[重置]已使用指定密码，请妥善保管")
        else:
            print(f"[重置]临时密码（仅显示这一次）：{password}")
        print("[重置]下次登录后请立即修改密码")
        return 0
    except Exception as e:
        conn.rollback()
        print(f"[重置]失败：{e}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
