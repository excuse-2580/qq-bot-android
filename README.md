# QQ 官方机器人（QQ 开放平台 API / botpy）

用**腾讯官方 API** 做的 QQ 聊天机器人：规则命中秒回，没命中交给大模型自由对话。
同一份代码可：桌面/服务器命令行运行，也可打包成**安卓 APK 后台常驻**。

> 与第三方协议框架（NoneBot + OneBot / NapCat 等）的区别：官方 API 合规稳定、不封号，但**只能在用户 @ 或私聊时被动回复**，不能主动在群里刷屏，且群聊场景要求企业主体。

---

## 零、安卓 APK

不用自己配环境，本仓库配置了 GitHub Actions 自动编译：

1. 进入仓库的 **Actions** 页 → 选 `Build Android APK` → 点 **Run workflow**
2. 等 20～40 分钟，构建完成后在 **Artifacts** 里下载 `qqbot-apk`
3. 手机安装 → 打开 App 填 AppID / AppSecret → 点「启动服务」

App 自带：凭证填写与保存、服务启停、实时日志、断线自动重连。
服务以**前台服务**方式运行（有常驻通知），比普通后台进程更不容易被系统回收。
建议装完后在系统设置里把本应用的电池优化设为「不限制」。

想自己编译：

```bash
pip install buildozer
buildozer -v android debug     # 产物在 bin/
```

依赖刻意做了精简：**没用 openai SDK**（它依赖 Rust 编译的 pydantic-core，安卓构建极易失败），
改用 aiohttp 直接 POST `/chat/completions`，接口完全兼容。

---

## 一、先看清官方 API 的硬限制

这是写代码前必须知道的，决定了整个架构：

| 场景 | 被动回复有效期 | 每条消息最多回复 | 主动消息配额 |
|---|---|---|---|
| 群聊 @机器人 | **5 分钟** | **5 次** | 每群每月 4 条 |
| 单聊 / 私聊 | **60 分钟** | **4 次** | 每用户每月 4 条 |
| 频道 | 5 分钟 | 不限次数 | 每子频道每天 20 条 |

含义：
- 机器人**不能主动找话题**，只能"你问我答"
- 一条消息回复超过上限后，必须等用户**再 @ 一次**才能继续
- 主动消息配额极紧（每月 4 条），别指望用它兜底

代码里的 `core/passive.py` 就是在自动管理这个窗口：超限自动放弃发送，**发送失败还会回滚计数**，避免白白消耗配额。

**接入门槛**（容易踩坑）：
- 群聊场景：**仅企业主体**，个人主体申请不了
- 单聊场景：定向邀请
- 频道场景：个人/企业均可
- 沙箱环境自 2026-01 起**不再支持群聊**测试，只能测频道和私聊

---

## 二、三步跑起来

```bash
pip install qq-botpy openai pyyaml
cp config.yaml.example config.yaml
# 填入 appid / secret
python bot.py
```

先在 [QQ 开放平台](https://q.qq.com) 创建机器人，在「开发管理 → 开发设置」拿到 **AppID** 和 **AppSecret**（Secret 只显示一次），并在「权限配置」里开启群聊/单聊权限。

看到 `机器人 XXX 已上线` 就通了。

---

## 三、配置（config.yaml）

**最低配置**（只跑规则回复）：

```yaml
appid: "1020xxxxx"
secret: "xxxxxxxxxxxx"
enable_group: true
enable_c2c: true
```

**开启 AI**：

```yaml
ai_api_key: "sk-xxxxxxxx"
ai_base_url: "https://api.deepseek.com"
ai_model: "deepseek-chat"
```

| 配置项 | 说明 |
|---|---|
| `enable_group` / `enable_c2c` / `enable_guild` | 监听哪些场景，对应不同 intents 位 |
| `ai_api_key` | 留空 → 自动只走规则回复 |
| `ai_base_url` | 换通义 / Kimi / 本地 Ollama 改这一行即可 |
| `ai_system_prompt` | 人设，决定说话风格 |
| `ai_history_size` / `ai_history_ttl` | 上下文条数 / 过期分钟数 |
| `group_passive_*` / `c2c_passive_*` | 被动窗口限制，与平台保持一致，**别动** |

所有配置都可用环境变量覆盖（大写形式，如 `AI_API_KEY=xxx`）。

---

## 四、加规则

编辑 `data/rules.json`，**保存即生效，不用重启**：

```json
{
  "keywords": ["你好", "hi"],
  "match": "contains",
  "reply": ["你好呀 {nickname}～"],
  "scope": "all"
}
```

| 字段 | 可选值 |
|---|---|
| `match` | `contains` 包含 / `exact` 完全相等 / `prefix` 开头 / `regex` 正则 |
| `scope` | `all` / `group` 群聊 / `c2c` 单聊 / `guild` 频道 |
| `reply` | 字符串，或数组（随机选一条） |
| `{nickname}` | 替换为发送者标识 |

> 注意：官方 API 的事件体**不返回用户昵称**，只有 openid，所以 `{nickname}` 实际填的是 openid 后 6 位（如 `…a3f9c1`）。

---

## 五、内置指令

| 指令 | 作用 |
|---|---|
| `/clear`、`/清空` | 清空当前会话上下文 |
| 群里 `@机器人 ...` | 触发对话 |
| 私聊直接说话 | 触发对话 |

---

## 六、自检

不用登录、不联网，直接验证匹配与配额逻辑：

```bash
python selftest.py    # 通过 41 项，失败 0 项
```

覆盖了规则匹配、scope 隔离、被动窗口配额与过期、msg_seq 递增、失败回滚、消息去重、长文本分段、intents 位构造。

---

## 七、常见问题

**机器人不回消息**
- 群里必须 **@ 机器人**，官方 API 收不到未 @ 的群消息（`GROUP_AT_MESSAGE_CREATE`）
- 检查开放平台里机器人状态是否为「已上线」，开发中的机器人调不了 API
- 确认「权限配置」里开了群聊/单聊权限

**报鉴权失败**
- AppSecret 只显示一次，忘了只能重置
- Token 鉴权方式已废弃，现在用 AppID + AppSecret 换 access_token，SDK 已内部处理

**回复到一半断了**
- 触发了被动回复上限（群 5 次 / 单聊 4 次），让用户重新 @ 一次即可
- 长回复会自动分段，每段都占一次配额

**同一条消息回了两次**
- 平台为保证可达会重复推送，代码已用 `(msg_id, msg_seq)` 去重

**怎么发图片 / Markdown**
- 官方支持 `msg_type=2`(Markdown)、`7`(富媒体)，但 Markdown 需要平台报备模板 id
- 本项目默认走 `msg_type=0` 纯文本，最稳

---

## 八、目录结构（含安卓）

```
qq-bot-official/
├── bot.py                 入口：事件回调 + 统一处理 + 发送配额管理
├── config.yaml.example    配置模板
├── selftest.py            逻辑自检
├── main.py                安卓 Kivy 界面（填凭证 / 启停 / 看日志）
├── service.py             安卓后台常驻服务（前台服务 + 断线重连）
├── buildozer.spec         APK 打包配置
└── .github/workflows/build-apk.yml   自动编译 APK
├── data/
│   ├── rules.json         规则库（热重载）
│   └── sessions.json      上下文持久化（自动生成）
└── core/
    ├── config.py          配置（yaml + 环境变量）
    ├── rules.py           规则引擎
    ├── ai.py              大模型客户端（OpenAI 兼容）
    ├── memory.py          会话记忆
    ├── passive.py         被动回复窗口管理（官方 API 核心约束）
    └── paths.py           桌面 / 安卓 路径适配
```
