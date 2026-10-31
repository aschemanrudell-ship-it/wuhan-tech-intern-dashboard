-- ============================================================================
-- 招聘数据服务平台 · 阶段一 建表脚本
-- 目标：MySQL 8.0+（utf8mb4 / InnoDB）
-- 依据：docs/DESIGN.md §7（表由查询推导）、docs/FIELD-AUDIT.md（字段事实）
--
-- 约定
--   1. 只建与性能无关的必需约束（业务唯一键、外键）；性能索引见 index-candidates.sql
--   2. 低覆盖字段一律允许 NULL，不设默认假值，避免把「不知道」写成「0」
--   3. 薪资单位显式建模；day_mid_comparable 是生成列，供统计口径直接过滤
--   4. 所有 CREATED/updated 时间戳由数据库维护
-- ============================================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ---------------------------------------------------------------------------
-- 1. 字典表：来源
--    由 Q1 的来源筛选、Q3 的分来源统计推出。实测 4 个取值。
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS sources;
CREATE TABLE sources (
  id          TINYINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name        VARCHAR(32)      NOT NULL COMMENT 'BOSS直聘 / 智联招聘 / 猎聘 / 实习僧',
  code        VARCHAR(16)      NOT NULL COMMENT 'boss / zhilian / liepin / shixiseng',
  created_at  TIMESTAMP        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_sources_name (name),
  UNIQUE KEY uk_sources_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='数据来源字典';

-- ---------------------------------------------------------------------------
-- 2. 公司表
--    由 Q1 展示公司信息、Q6 公司维度推出。
--    实测：company 有 1954 种取值，86 行为空（全部 BOSS）→ 允许 jobs.company_id 为 NULL
--    normalized_name 用于去空格/全半角归一后的去重
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS companies;
CREATE TABLE companies (
  id               INT UNSIGNED     NOT NULL AUTO_INCREMENT,
  name             VARCHAR(128)     NOT NULL COMMENT '公司名原文',
  normalized_name  VARCHAR(128)     NOT NULL COMMENT '归一化后用于唯一键',
  industry         VARCHAR(64)      NULL COMMENT 'company_industry，缺失 90.3%',
  size             VARCHAR(32)      NULL COMMENT 'company_size，缺失 0.8%',
  financing        VARCHAR(32)      NULL COMMENT 'financing，缺失 30.2%',
  open_jobs        INT UNSIGNED     NULL COMMENT 'company_open_jobs，缺失 88.1%',
  boss_count       INT UNSIGNED     NULL COMMENT 'company_bosses，缺失 88.1%',
  created_at       TIMESTAMP        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at       TIMESTAMP        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_companies_normalized_name (normalized_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='公司档案（含 BOSS 公司页画像）';

-- ---------------------------------------------------------------------------
-- 3. 技术方向字典
--    由 Q1 多方向筛选、Q3 按方向计数、Q4 方向薪资推出。实测 15 个取值。
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS stacks;
CREATE TABLE stacks (
  id    TINYINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name  VARCHAR(32)      NOT NULL COMMENT 'Python / Java / 算法/AI …',
  PRIMARY KEY (id),
  UNIQUE KEY uk_stacks_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='技术方向字典（15 类）';

-- ---------------------------------------------------------------------------
-- 4. 技能标签字典
--    由 Q2 展示技能标签推出。实测 1762 种取值 → 必须独立表，不能塞进 jobs 一列
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS tags;
CREATE TABLE tags (
  id    SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT,
  -- 必须大小写敏感：源数据里同时存在 'Java'(143) 与 'java'(2)。
  -- 用 *_ci collation 会把两者合并到同一行，导致 'Java' 的关联全部丢失。
  name  VARCHAR(64)       NOT NULL COLLATE utf8mb4_0900_as_cs COMMENT 'MySQL / Spring / 深度学习 …',
  PRIMARY KEY (id),
  UNIQUE KEY uk_tags_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='技能标签字典（name 区分大小写）';

-- ---------------------------------------------------------------------------
-- 5. 岗位标签字典（BOSS labels：5天/周、3个月、本科…）
--    实测 132 种取值、缺失 21.9%
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS job_label_dict;
CREATE TABLE job_label_dict (
  id    SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT,
  name  VARCHAR(32)       NOT NULL COLLATE utf8mb4_0900_as_cs,
  PRIMARY KEY (id),
  UNIQUE KEY uk_job_label_dict_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='BOSS 岗位标签字典（到岗/学历/经验等，区分大小写）';

-- ---------------------------------------------------------------------------
-- 6. 导入批次
--    由 §3.1 幂等与追溯推出：记录每次导入，用于「重复导入不产生新行」的验收
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS import_batch;
CREATE TABLE import_batch (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  source_file   VARCHAR(255)    NOT NULL COMMENT '快照文件名',
  file_sha256   CHAR(64)        NOT NULL COMMENT '文件内容指纹，识别「同一份数据」',
  row_total     INT UNSIGNED    NOT NULL DEFAULT 0,
  row_inserted  INT UNSIGNED    NOT NULL DEFAULT 0,
  row_updated   INT UNSIGNED    NOT NULL DEFAULT 0,
  row_skipped   INT UNSIGNED    NOT NULL DEFAULT 0,
  started_at    DATETIME        NOT NULL,
  finished_at   DATETIME        NULL,
  PRIMARY KEY (id),
  KEY idx_import_batch_sha (file_sha256)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='每次导入的运行记录';

-- ---------------------------------------------------------------------------
-- 7. 岗位主表
--    服务 Q1–Q8 全部。字段取舍见 DESIGN.md §4
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS jobs;
CREATE TABLE jobs (
  id                  BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,

  -- 身份 ------------------------------------------------------------------
  job_uid             VARCHAR(200)     NOT NULL COMMENT '原始 job_id，全局唯一（实测 3013/3013）',
  source_id           TINYINT UNSIGNED NOT NULL,
  source_job_id       VARCHAR(120)     NOT NULL COMMENT '剥离来源前缀后的原始 ID',
  crawl_keyword       VARCHAR(64)      NULL COMMENT '召回该岗位的搜索词（源 keyword，BOSS 为中文）',
  crawl_slug          VARCHAR(64)      NULL COMMENT '采集批次标识（源 slug，BOSS 为英文如 boss_wuhan_python；ft_* 表示正式岗基线）',

  -- 基本信息 --------------------------------------------------------------
  title               VARCHAR(255)     NOT NULL,
  company_id          INT UNSIGNED     NULL     COMMENT '86 行 BOSS 数据公司名为空',
  city                VARCHAR(32)      NOT NULL,
  is_wuhan            TINYINT(1)       NOT NULL DEFAULT 0,
  district            VARCHAR(32)      NULL     COMMENT '缺失 16.1%',
  degree              VARCHAR(32)      NOT NULL COMMENT '清洗后：不限/中专高中/大专/本科/硕士/博士',
  degree_raw          VARCHAR(32)      NULL     COMMENT '原始值，保留脏值痕迹',
  experience          VARCHAR(32)      NULL     COMMENT '缺失 21.9%',
  is_intern           TINYINT(1)       NOT NULL DEFAULT 0,
  is_edu_excluded     TINYINT(1)       NOT NULL DEFAULT 0 COMMENT '教育培训类岗位，导入时已判定',

  -- 实习条件（从 durations/labels 正则解析，解析不出为 NULL）---------------
  weekly_days         TINYINT UNSIGNED NULL COMMENT '每周到岗天数，可解析 20.1%',
  intern_months       TINYINT UNSIGNED NULL COMMENT '实习月数，可解析 20.1%',
  title_has_intern    TINYINT(1)       NOT NULL DEFAULT 0 COMMENT '标题含「实习」；严格薪资口径依赖此列',

  -- 薪资（9 种单位形态显式建模）------------------------------------------
  salary_raw          VARCHAR(32)      NULL COMMENT '原文，缺失 27.9%',
  salary_unit         ENUM('DAY','K_MONTH','K_MONTH_X','MONTH_YUAN','WAN_MONTH','NEGOTIABLE','UNKNOWN','MISSING')
                      NOT NULL DEFAULT 'MISSING' COMMENT '见 DESIGN.md §5.1',
  day_low             DECIMAL(8,2)     NULL,
  day_high            DECIMAL(8,2)     NULL,
  day_mid             DECIMAL(8,2)     NULL COMMENT '日薪中值；注意含元/月口径折算值，不可直接统计',

  -- 两种统计口径都做成生成列，避免每个查询重复写 CASE WHEN
  day_mid_comparable  TINYINT(1)       GENERATED ALWAYS AS
                        (salary_unit IN ('DAY','K_MONTH','K_MONTH_X')) STORED
                      COMMENT '宽口径 = 单位层面可折算日薪（含全部 K/月，实测 623 行）',
  intern_daily_sample TINYINT(1)       GENERATED ALWAYS AS
                        (salary_unit IN ('DAY','K_MONTH','K_MONTH_X')
                         AND (salary_unit = 'DAY' OR title_has_intern = 1)) STORED
                      COMMENT '严口径 = 元/天 或 标题含实习的 K/月（实习薪资统计用这个）',

  month_low           DECIMAL(10,2)    NULL,
  month_high          DECIMAL(10,2)    NULL,
  month_mid           DECIMAL(10,2)    NULL,

  -- 辅助信息 --------------------------------------------------------------
  industry            VARCHAR(64)      NULL COMMENT '岗位所属行业（源 industry，缺失 14.0%）；注意与 companies.industry 不同',
  primary_stack       VARCHAR(32)      NULL COMMENT '主方向，实测 16 种',
  boss_name           VARCHAR(64)      NULL COMMENT '招聘者，缺失 47%',
  boss_title          VARCHAR(128)     NULL,
  publish_time        DATETIME         NULL COMMENT '缺失 94.3%（仅智联有），保留以便时间维度',
  url                 VARCHAR(512)     NULL COMMENT '缺失 2.5%',
  dup_group_key       CHAR(32)         NULL COMMENT 'title+company 归一哈希，标记跨源/同源同名，不合并',

  -- 血缘 ------------------------------------------------------------------
  first_batch_id      BIGINT UNSIGNED  NULL COMMENT '首次入库批次',
  last_batch_id       BIGINT UNSIGNED  NULL COMMENT '最近一次写入批次',
  created_at          TIMESTAMP        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at          TIMESTAMP        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

  PRIMARY KEY (id),
  UNIQUE KEY uk_jobs_job_uid (job_uid),
  KEY idx_jobs_dup_group (dup_group_key),
  CONSTRAINT fk_jobs_source  FOREIGN KEY (source_id)  REFERENCES sources (id),
  CONSTRAINT fk_jobs_company FOREIGN KEY (company_id) REFERENCES companies (id),
  CONSTRAINT fk_jobs_first_batch FOREIGN KEY (first_batch_id) REFERENCES import_batch (id),
  CONSTRAINT fk_jobs_last_batch  FOREIGN KEY (last_batch_id)  REFERENCES import_batch (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='岗位主表';

-- ---------------------------------------------------------------------------
-- 8. 岗位 × 方向（多对多）
--    由 Q1 一次查多个方向、Q3 按方向计数推出
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS job_stacks;
CREATE TABLE job_stacks (
  job_id    BIGINT UNSIGNED  NOT NULL,
  stack_id  TINYINT UNSIGNED NOT NULL,
  ordinal   TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '源数组中的顺序，保留原始优先级',
  PRIMARY KEY (job_id, stack_id),
  KEY idx_job_stacks_stack (stack_id, job_id),
  CONSTRAINT fk_job_stacks_job   FOREIGN KEY (job_id)   REFERENCES jobs (id) ON DELETE CASCADE,
  CONSTRAINT fk_job_stacks_stack FOREIGN KEY (stack_id) REFERENCES stacks (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='岗位-技术方向';

-- ---------------------------------------------------------------------------
-- 9. 岗位 × 技能标签
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS job_tags;
CREATE TABLE job_tags (
  job_id  BIGINT UNSIGNED   NOT NULL,
  tag_id  SMALLINT UNSIGNED NOT NULL,
  PRIMARY KEY (job_id, tag_id),
  KEY idx_job_tags_tag (tag_id, job_id),
  CONSTRAINT fk_job_tags_job FOREIGN KEY (job_id) REFERENCES jobs (id) ON DELETE CASCADE,
  CONSTRAINT fk_job_tags_tag FOREIGN KEY (tag_id) REFERENCES tags (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='岗位-技能标签';

-- ---------------------------------------------------------------------------
-- 10. 岗位 × 标签
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS job_label_links;
CREATE TABLE job_label_links (
  job_id       BIGINT UNSIGNED   NOT NULL,
  label_id     SMALLINT UNSIGNED NOT NULL,
  PRIMARY KEY (job_id, label_id),
  KEY idx_job_label_links_label (label_id, job_id),
  CONSTRAINT fk_jll_job   FOREIGN KEY (job_id)   REFERENCES jobs (id) ON DELETE CASCADE,
  CONSTRAINT fk_jll_label FOREIGN KEY (label_id) REFERENCES job_label_dict (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='岗位-BOSS 标签';

-- ---------------------------------------------------------------------------
-- 11. JD 正文（1:1，独立表）
--     理由：只有 5.2% 的行有正文（156/3013），放主表会显著撑大主表行宽、拖慢列表扫描
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS job_descriptions;
CREATE TABLE job_descriptions (
  job_id      BIGINT UNSIGNED NOT NULL,
  content     MEDIUMTEXT        NOT NULL COMMENT 'JD 原文（已去 HTML 标签）',
  char_count  SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  acquired_by VARCHAR(64)       NULL COMMENT '采集来源，如 zhilian_ssr_jobDetailData.position.desc',
  fetched_at  DATETIME          NULL,
  PRIMARY KEY (job_id),
  CONSTRAINT fk_jd_job FOREIGN KEY (job_id) REFERENCES jobs (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='岗位 JD 正文（覆盖 5.2%）';

-- ---------------------------------------------------------------------------
-- 12. 用户（Q7 收藏需要主体）
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS users;
CREATE TABLE users (
  id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  username       VARCHAR(64)     NOT NULL,
  password_hash  VARCHAR(255)    NOT NULL COMMENT 'Django 的 pbkdf2/argon2 格式串，不存明文',
  is_active      TINYINT(1)      NOT NULL DEFAULT 1,
  created_at     TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_users_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='平台用户';

-- ---------------------------------------------------------------------------
-- 13. 收藏（Q7）
--     UNIQUE(user_id, job_id) 同时承担「防重复收藏」与「权限校验落点」
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS favorites;
CREATE TABLE favorites (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id     BIGINT UNSIGNED NOT NULL,
  job_id      BIGINT UNSIGNED NOT NULL,
  created_at  TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_favorites_user_job (user_id, job_id),
  KEY idx_favorites_user_time (user_id, created_at),
  CONSTRAINT fk_fav_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
  CONSTRAINT fk_fav_job  FOREIGN KEY (job_id)  REFERENCES jobs (id)  ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='用户收藏';

-- ---------------------------------------------------------------------------
-- 14. 认证令牌
--     用 Bearer token 而不是 Cookie+Session：那样写操作必须配 CSRF，
--     API 客户端（curl / 前端 fetch）会多一层负担。
--     只存 SHA-256(token)：库被读走也拿不到可用令牌。
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS user_tokens;
CREATE TABLE user_tokens (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id     BIGINT UNSIGNED NOT NULL,
  token_hash  CHAR(64)        NOT NULL COMMENT 'SHA-256(随机令牌) 的十六进制，不存原文',
  created_at  TIMESTAMP       NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at  TIMESTAMP       NOT NULL COMMENT '过期时间，查询时用它过滤',
  PRIMARY KEY (id),
  UNIQUE KEY uk_user_tokens_hash (token_hash),
  KEY idx_user_tokens_user (user_id, expires_at),
  CONSTRAINT fk_token_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='API 认证令牌';

SET FOREIGN_KEY_CHECKS = 1;

-- ============================================================================
-- 建表完成后的自检（人工执行）
--   SHOW TABLES;                                        -- 应为 13 张
--   SELECT COUNT(*) FROM information_schema.tables
--    WHERE table_schema = DATABASE();                   -- 13
-- ============================================================================
