# Token Logger

将每次 LLM 调用的 token 用量静默记录到 AstrBot 日志中，不污染聊天消息。支持缓存 token 检测和费用计算。

## 日志输出示例

**基础（计费关闭）：**
```
[TokenLogger] model=gpt-4o | input=2006 | output=300 | total=2306 | finish=stop
```

**命中缓存 + 计费开启：**
```
[TokenLogger] model=gpt-4o | input=2006 (cached=1920) | output=300 | total=2306 | finish=stop
[TokenLogger] cost=$0.005615 (86 * $2.5/M + 1920 * $1.25/M + 300 * $10.0/M = $0.005615)
```

**无缓存 + 计费开启：**
```
[TokenLogger] model=gpt-4o | input=2006 | output=300 | total=2306 | finish=stop
[TokenLogger] cost=$0.008015 (2006 * $2.5/M + 300 * $10.0/M = $0.008015)
```

## 配置

在 AstrBot 管理面板的插件配置页中调整：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| enabled | bool | true | 启用/关闭 token 日志记录 |
| cost_enabled | bool | false | 启用/关闭费用计算 |
| input_cost_per_million | float | 2.50 | 每百万 input token 单价（美元） |
| cached_input_cost_per_million | float | 1.25 | 每百万 cached input token 单价（美元） |
| output_cost_per_million | float | 10.00 | 每百万 output token 单价（美元） |

## 安装

将 `count_token` 文件夹放入 AstrBot 插件目录，重启即可。

---

*Felis Abyssalis & Abyss AI*
