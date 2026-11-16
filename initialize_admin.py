"""Create a NEW installation's administrator credentials; never overwrite one."""
from pathlib import Path
import getpass
import json
import os
from server import secret_record

AUTH_PATH = Path(__file__).resolve().parent / 'data' / 'auth.json'


def initialize(path, password, answer):
    if not isinstance(password, str) or not 6 <= len(password) <= 128:
        raise ValueError('管理密码须为 6–128 个字符')
    if not isinstance(answer, str) or not 1 <= len(answer) <= 128:
        raise ValueError('恢复验证答案须为 1–128 个字符')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    config = dict(secret_record(password), verification=secret_record(answer))
    # O_EXCL protects an existing password even if another process creates it.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(config, stream)
        stream.flush()
        os.fsync(stream.fileno())


def main():
    if AUTH_PATH.exists():
        raise SystemExit('已有后台密码配置，本工具不会覆盖。请使用后台的修改密码功能。')
    password = getpass.getpass('设置新后台密码（6–128 个字符）：')
    if password != getpass.getpass('再次输入新后台密码：'):
        raise SystemExit('两次密码不一致，未创建配置。')
    answer = getpass.getpass('设置密码恢复验证答案（后台提示为“我是谁”）：')
    if answer != getpass.getpass('再次输入恢复验证答案：'):
        raise SystemExit('两次验证答案不一致，未创建配置。')
    try:
        initialize(AUTH_PATH, password, answer)
    except (ValueError, FileExistsError) as error:
        raise SystemExit(str(error))
    print('新安装的后台密码已初始化。请妥善保管密码与恢复验证答案。')


if __name__ == '__main__':
    main()
