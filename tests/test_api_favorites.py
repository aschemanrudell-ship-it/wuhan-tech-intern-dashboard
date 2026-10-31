# -*- coding: utf-8 -*-
"""认证与收藏的权限测试。

这是阶段一验收清单里点名要的三条：
  1. 未登录访问 → 401
  2. A 用户删不掉 B 用户的收藏
  3. 重复收藏幂等（数量不变）

另外覆盖：密码哈希、用户名枚举防护、令牌伪造/失效、注册边界。
"""
import json
import os
import sys
import unittest

import django
from django.conf import settings

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "JobDataPlatform.settings")
if not settings.configured:
    django.setup()

from django.db import connection                                  # noqa: E402
from django.test import Client                                    # noqa: E402


def _exec(sql, params=None):
    with connection.cursor() as cur:
        cur.execute(sql, params)
        return cur.rowcount


def _rows(sql, params=None):
    with connection.cursor() as cur:
        cur.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _cleanup(usernames):
    """按用户名清理测试用户（favorites/tokens 靠 ON DELETE CASCADE）。"""
    for u in usernames:
        _exec("DELETE FROM users WHERE username LIKE %s", (f"{u}%",))


class Base(unittest.TestCase):
    """提供注册/登录辅助，并在结束时清理测试数据。"""

    @classmethod
    def setUpClass(cls):
        cls.prefix = f"t_{cls.__name__.lower()[:12]}"
        _cleanup(cls.prefix)

    @classmethod
    def tearDownClass(cls):
        _cleanup(cls.prefix)

    def reg(self, name, pw="Passw0rd!x"):
        r = Client().post("/api/auth/register",
                          data=json.dumps({"username": name, "password": pw}),
                          content_type="application/json")
        return r

    def login(self, name, pw="Passw0rd!x"):
        r = Client().post("/api/auth/login",
                          data=json.dumps({"username": name, "password": pw}),
                          content_type="application/json")
        return r

    def make_user(self, name):
        """注册并登录，返回 (token, uid)。"""
        r = self.reg(name)
        self.assertIn(r.status_code, (201, 409), r.content)
        r = self.login(name)
        self.assertEqual(r.status_code, 200, r.content)
        d = r.json()
        return d["token"], d["user"]["id"]

    def auth(self, token):
        """带 Bearer token 的客户端。

        用 Client(headers=...) 而不是 Client.defaults —— 后者不会把
        HTTP_AUTHORIZATION 拼进 WSGI 环境。
        """
        return Client(headers={"authorization": f"Bearer {token}"})


class RegisterLoginTest(Base):
    def test_register_ok(self):
        r = self.reg(self.prefix + "_r1")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["username"], self.prefix + "_r1")

    def test_password_not_stored_plaintext(self):
        """密码必须是哈希，不能明文入库。"""
        name = self.prefix + "_hash"
        self.reg(name, "PlainSecret123")
        row = _rows("SELECT password_hash FROM users WHERE username=%s", (name,))[0]
        self.assertNotIn("PlainSecret123", row["password_hash"])
        self.assertTrue(row["password_hash"].startswith("pbkdf2_"),
                        "应使用 Django 的 PBKDF2 格式")

    def test_duplicate_username_409(self):
        name = self.prefix + "_dup"
        self.assertEqual(self.reg(name).status_code, 201)
        r = self.reg(name)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["error"], "username_taken")

    def test_short_password_400(self):
        r = self.reg(self.prefix + "_short", "123")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["field"], "password")

    def test_short_username_400(self):
        r = self.reg("ab")
        self.assertEqual(r.status_code, 400)

    def test_wrong_password_401(self):
        name = self.prefix + "_wp"
        self.reg(name)
        r = self.login(name, "WrongPass999")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["error"], "invalid_credentials")

    def test_no_username_enumeration(self):
        """不存在用户与密码错误必须返回同一个响应，避免枚举用户名。"""
        self.reg(self.prefix + "_enum")
        a = self.login(self.prefix + "_enum", "WrongPass1")
        b = self.login(self.prefix + "_ghost", "WrongPass1")
        self.assertEqual(a.status_code, b.status_code)
        self.assertEqual(a.json(), b.json())

    def test_token_works(self):
        token, uid = self.make_user(self.prefix + "_tk")
        r = self.auth(token).get("/api/auth/me")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["id"], uid)

    def test_logout_invalidates_token(self):
        token, _ = self.make_user(self.prefix + "_lo")
        self.assertEqual(self.auth(token).post("/api/auth/logout").status_code, 200)
        self.assertEqual(self.auth(token).get("/api/auth/me").status_code, 401)

    def test_logout_idempotent(self):
        """没有 token 也返回 200，客户端不必纠结。"""
        self.assertEqual(Client().post("/api/auth/logout").status_code, 200)

    def test_forged_token_401(self):
        self.assertEqual(self.auth("forged-token-xxx").get("/api/auth/me").status_code, 401)

    def test_token_stored_hashed(self):
        """库里必须是 SHA-256，不能存明文 token。"""
        token, _ = self.make_user(self.prefix + "_th")
        row = _rows("SELECT token_hash FROM user_tokens WHERE token_hash=SHA2(%s,256)", (token,))
        self.assertEqual(len(row), 1, "token 未以 SHA-256 形式存储")
        plain = _rows("SELECT id FROM user_tokens WHERE token_hash=%s", (token,))
        self.assertEqual(plain, [], "库中出现了明文 token")


class UnauthorizedTest(Base):
    """未登录访问受保护资源必须是 401（不是 403、不是空 200）。"""

    def test_favorites_list_401(self):
        r = Client().get("/api/favorites")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["error"], "unauthorized")
        self.assertIn("WWW-Authenticate", r)

    def test_favorites_add_401(self):
        r = Client().post("/api/favorites", data=json.dumps({"job_uid": "x"}),
                          content_type="application/json")
        self.assertEqual(r.status_code, 401)

    def test_favorites_remove_401(self):
        self.assertEqual(Client().delete("/api/favorites/any-uid").status_code, 401)

    def test_me_401(self):
        self.assertEqual(Client().get("/api/auth/me").status_code, 401)

    def test_public_endpoints_still_open(self):
        """统计与岗位列表不需要登录。"""
        c = Client()
        for ep in ("/api/health", "/api/stats/summary", "/api/jobs"):
            with self.subTest(endpoint=ep):
                self.assertEqual(c.get(ep).status_code, 200)


class FavoriteTest(Base):
    def setUp(self):
        self.token_a, self.uid_a = self.make_user(self.prefix + "_a")
        self.token_b, self.uid_b = self.make_user(self.prefix + "_b")
        self.job = Client().get("/api/jobs?page_size=1").json()["items"][0]["job_uid"]

    def tearDown(self):
        for uid in (self.uid_a, self.uid_b):
            _exec("DELETE FROM favorites WHERE user_id=%s", (uid,))

    def add(self, client, job_uid):
        return client.post("/api/favorites", data=json.dumps({"job_uid": job_uid}),
                           content_type="application/json")

    # ---- 基本功能 ----
    def test_add_and_list(self):
        a = self.auth(self.token_a)
        self.assertEqual(self.add(a, self.job).status_code, 201)
        d = a.get("/api/favorites").json()
        self.assertEqual(d["total"], 1)
        self.assertEqual(d["items"][0]["job_uid"], self.job)

    def test_add_unknown_job_404(self):
        r = self.add(self.auth(self.token_a), "no-such-uid")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["error"], "job_not_found")

    def test_add_without_job_uid_400(self):
        r = self.auth(self.token_a).post("/api/favorites", data=json.dumps({}),
                                         content_type="application/json")
        self.assertEqual(r.status_code, 400)

    # ---- 验收项 3：幂等 ----
    def test_repeat_add_idempotent(self):
        a = self.auth(self.token_a)
        self.assertEqual(self.add(a, self.job).json()["my_favorites"], 1)
        for _ in range(3):
            r = self.add(a, self.job)
            self.assertEqual(r.status_code, 201)
            self.assertEqual(r.json()["my_favorites"], 1, "重复收藏不应增加数量")
        self.assertEqual(a.get("/api/favorites").json()["total"], 1)
        rows = _rows("SELECT COUNT(*) c FROM favorites WHERE user_id=%s AND job_id="
                     "(SELECT id FROM jobs WHERE job_uid=%s)", (self.uid_a, self.job))
        self.assertEqual(rows[0]["c"], 1, "库里出现了重复行")

    # ---- 验收项 2：不能删别人的 ----
    def test_cannot_remove_others_favorite(self):
        a, b = self.auth(self.token_a), self.auth(self.token_b)
        self.add(b, self.job)                       # B 收藏

        r = a.delete(f"/api/favorites/{self.job}")  # A 试图删
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["removed"], 0, "A 不应该能删掉 B 的收藏")
        self.assertEqual(r.json()["my_favorites"], 0)

        # B 的收藏必须还在
        self.assertEqual(b.get("/api/favorites").json()["total"], 1, "B 的收藏被删了")
        rows = _rows("SELECT COUNT(*) c FROM favorites WHERE user_id=%s", (self.uid_b,))
        self.assertEqual(rows[0]["c"], 1)

    def test_cannot_see_others_favorites(self):
        a, b = self.auth(self.token_a), self.auth(self.token_b)
        self.add(b, self.job)
        self.assertEqual(a.get("/api/favorites").json()["total"], 0, "A 看到了 B 的收藏")

    def test_remove_own_then_idempotent(self):
        a = self.auth(self.token_a)
        self.add(a, self.job)
        self.assertEqual(a.delete(f"/api/favorites/{self.job}").json()["removed"], 1)
        r = a.delete(f"/api/favorites/{self.job}")
        self.assertEqual(r.json()["removed"], 0, "第二次删除应为 0 行")

    def test_remove_unknown_job_404(self):
        self.assertEqual(
            self.auth(self.token_a).delete("/api/favorites/no-such-uid").status_code, 404)

    def test_favorites_pagination(self):
        a = self.auth(self.token_a)
        uids = [i["job_uid"] for i in
                Client().get("/api/jobs?page_size=3").json()["items"]]
        for u in uids:
            self.add(a, u)
        d = a.get("/api/favorites?page=1&page_size=2").json()
        self.assertEqual(d["total"], 3)
        self.assertEqual(len(d["items"]), 2)
        self.assertEqual(d["pages"], 2)

    def test_cascade_on_user_delete(self):
        """删用户时收藏与令牌应级联删除（FK ON DELETE CASCADE）。"""
        token, uid = self.make_user(self.prefix + "_cas")
        self.add(self.auth(token), self.job)
        _exec("DELETE FROM users WHERE id=%s", (uid,))
        self.assertEqual(_rows("SELECT COUNT(*) c FROM favorites WHERE user_id=%s", (uid,))[0]["c"], 0)
        self.assertEqual(_rows("SELECT COUNT(*) c FROM user_tokens WHERE user_id=%s", (uid,))[0]["c"], 0)


class MethodTest(Base):
    def test_register_get_405(self):
        self.assertEqual(Client().get("/api/auth/register").status_code, 405)

    def test_login_get_405(self):
        self.assertEqual(Client().get("/api/auth/login").status_code, 405)

    def test_bad_json_body_400(self):
        r = Client().post("/api/auth/login", data="not json", content_type="application/json")
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
