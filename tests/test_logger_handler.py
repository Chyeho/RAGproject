# -*- coding: utf-8 -*-
"""日志管理工具模块单元测试"""
import logging

from app.utils.logger_handler import get_logger, logger, DEFAULT_LOG_FORMAT, LOG_ROOT


class TestGetLogger:
    """测试 get_logger() 函数"""

    def test_returns_logger_instance(self):
        """验证返回 logging.Logger 实例"""
        log = get_logger(name="test_unit")
        assert isinstance(log, logging.Logger)

    def test_default_name(self):
        """默认 name 为 agent"""
        log = get_logger()
        assert log.name == "agent"

    def test_custom_name(self):
        """自定义 name"""
        log = get_logger(name="my_test")
        assert log.name == "my_test"

    def test_logger_has_handlers(self):
        """验证日志器有处理器"""
        log = get_logger(name="test_handlers")
        assert len(log.handlers) >= 2  # console + file

    def test_logger_not_duplicate_handlers(self):
        """验证重复调用不会重复创建处理器"""
        log = get_logger(name="test_dup")
        handler_count = len(log.handlers)
        log2 = get_logger(name="test_dup")
        assert len(log2.handlers) == handler_count

    def test_logger_level_is_debug(self):
        """验证日志器级别为 DEBUG"""
        log = get_logger(name="test_level")
        assert log.level == logging.DEBUG


class TestModuleLogger:
    """测试模块级 logger"""

    def test_module_logger_exists(self):
        """验证模块级 logger 存在"""
        assert logger is not None
        assert isinstance(logger, logging.Logger)

    def test_module_logger_name_is_agent(self):
        """验证模块级 logger 名称为 agent"""
        assert logger.name == "agent"


class TestLogFormatter:
    """测试日志格式配置"""

    def test_formatter_is_logging_formatter(self):
        assert isinstance(DEFAULT_LOG_FORMAT, logging.Formatter)


class TestLogRoot:
    """测试日志根目录"""

    def test_log_root_is_string(self):
        assert isinstance(LOG_ROOT, str)

    def test_log_root_exists(self):
        import os
        assert os.path.exists(LOG_ROOT)
