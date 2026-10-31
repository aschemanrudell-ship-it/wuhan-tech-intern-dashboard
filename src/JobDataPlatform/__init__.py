"""JobDataPlatform 包。

Django 走 MySQL 后端时默认找 MySQLdb；本项目装的是 PyMySQL，这里做一次适配。
"""
import pymysql

pymysql.install_as_MySQLdb()

__version__ = "0.1.0"
