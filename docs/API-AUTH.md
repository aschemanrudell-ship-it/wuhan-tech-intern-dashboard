# 认证与收藏

> 端点：`/api/auth/*`（4 个）+ `/api/favorites`（按 method 分派）+ `/api/favorites/<uid>`
> 测试：`tests/test_api_favorites.py`（30 项）

---

## 1. 为什么用 Bearer token 而不是 Cookie+Session

| 方案 | 代价 |
| --- | --- |
| Cookie + Session | 所有写操作必须配 CSRF token；curl / fetch 多一层；跨域更麻烦 |
| **Bearer token** | 天然免疫 CSRF（浏览器不会自动附带）；客户端只需一个 header |

代价：token 泄露即失权，所以设置了 7 天过期，并且**库里只存 SHA-256**。

---

## 2. 端点

| 方法 | 路径 | 说明 | 失败码 |
| --- | --- | --- | --- |
| POST | `/api/auth/register` | `{username, password}` | 400 参数 / 409 用户名已存在 |
| POST | `/api/auth/login` | `{username, password}` → `{token, expires_at, user}` | 401 |
| POST | `/api/auth/logout` | 作废当前 token | 幂等，总是 200 |
| GET | `/api/auth/me` | 当前用户 | 401 |
| GET | `/api/favorites` | 我的收藏（分页） | 401 |
| POST | `/api/favorites` | `{job_uid}` 收藏 | 400 / 404 / 401 |
| DELETE | `/api/favorites/<job_uid>` | 取消收藏 | 404 / 401 |

调用方式：

```bash
curl -X POST http://127.0.0.1:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"demo","password":"Passw0rd!x"}'

curl http://127.0.0.1:8000/api/favorites \
  -H 'Authorization: Bearer <token>'
```

---

## 3. 三条验收项（测试里逐条断言）

### 3.1 未登录 → 401

```python
class UnauthorizedTest:
    def test_favorites_list_401(self):   # + add / remove / me
        r = Client().get("/api/favorites")
        self.assertEqual(r.status_code, 401)
        self.assertIn("WWW-Authenticate", r)     # 带上正确响应头
```

同时断言 `health` / `stats/*` / `jobs` **仍然公开**——不能因为加了认证把看板锁死。

### 3.2 A 删不掉 B 的收藏

关键是 SQL 里带 `user_id` 条件，而不是「先查出来再判断」：

```sql
DELETE FROM favorites WHERE user_id = :me AND job_id = :job
```

测试：

```python
def test_cannot_remove_others_favorite(self):
    self.add(b, job)                     # B 收藏
    r = a.delete(f"/api/favorites/{job}")  # A 试图删
    self.assertEqual(r.json()["removed"], 0)      # A 删了 0 行
    self.assertEqual(b.get("/api/favorites").json()["total"], 1)   # B 的还在
```

`removed=0` 对外不区分「本来没收藏」和「收藏是别人的」—— 不泄露存在性。

另有一条 `test_cannot_see_others_favorites`：A 的列表里看不到 B 的收藏。

### 3.3 重复收藏幂等

```sql
UNIQUE KEY uk_favorites_user_job (user_id, job_id)
```
```python
_exec("INSERT IGNORE INTO favorites (user_id, job_id) VALUES (%s,%s)", ...)
```

用 `INSERT IGNORE` 而不是「先 SELECT 再 INSERT」——后者在并发下会撞唯一键报错。

测试连点 3 次，断言 `my_favorites` 恒为 1，且库里只有 1 行。

---

## 4. 安全细节

| 项 | 做法 | 测试 |
| --- | --- | --- |
| 密码存储 | `django.contrib.auth.hashers.make_password`（PBKDF2-SHA256 + 每用户 salt） | `test_password_not_stored_plaintext` 断言不含明文、以 `pbkdf2_` 开头 |
| 令牌存储 | 只存 `SHA2(token,256)`，原文只返回一次 | `test_token_stored_hashed` 断言库里查不到明文 token |
| 用户名枚举 | 用户不存在与密码错误返回**完全相同**的响应 | `test_no_username_enumeration` |
| 过期的清理 | 登录时顺手 `DELETE ... WHERE expires_at <= NOW()` | — |
| 级联删除 | `FK ... ON DELETE CASCADE` | `test_cascade_on_user_delete` |
| 方法校验 | register/login 只接受 POST，其余 405 | `test_register_get_405` |
| body 校验 | 非 JSON 对象 → 400，不是 500 | `test_bad_json_body_400` |

`MIN_PASSWORD_LEN = 8`，用户名 3..64。

---

## 5. 开发中撞到的坑

**`POST /api/favorites` 返回了收藏列表**

原因：`/api/favorites` 路由到 `favorite_list`，而它**没有校验 method**，直接返回了 200 + 列表。

这类错误数字上都对（200、合法 JSON），只有断言 `my_favorites` 字段的测试能抓住。

修法：`/api/favorites` 按 method 分派（GET 列表 / POST 添加），不再有 `/favorites/add` 这种冗余路径。

**`Client.defaults["HTTP_AUTHORIZATION"]` 不生效**

Django 测试客户端的 `defaults` 不会把值拼进 WSGI 环境。要用 `Client(headers={"authorization": ...})` 或每次传 `HTTP_AUTHORIZATION=`。四种传法都用脚本验证过（`work/diagnose_auth.py`，已清理）。

---

## 6. 未做

| 项 | 说明 |
| --- | --- |
| 令牌刷新 | 7 天过期后需重新登录，没有 refresh token |
| 限流 | 登录接口没有失败次数限制，可被暴力尝试 |
| 角色/权限 | 只有「登录用户」一种角色，没有管理员 |
| 收藏分组/备注 | 只有一个平铺列表 |
