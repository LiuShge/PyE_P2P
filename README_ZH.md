# PyE_P2P - Python 加密点对点通信

<div align="center">

![Python](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python)
![License](https://img.shields.io/badge/License-MIT-green?logo=github)
![Status](https://img.shields.io/badge/Status-Planning-yellow)
![Platform](https://img.shields.io/badge/Platform-Windows%7CmacOS%7CLinux%7CMobile-blue?logo=linux)

<h3>一个面向任意 Python 环境的端到端加密 P2P 通信工具</h3>

分层依赖、零依赖模式、单文件部署、移动优先、开源透明。

[English](./README.md) | [中文](./README_ZH.md)

---

</div>

## 概述

**PyE_P2P**（Python Encrypted Peer-to-Peer）是一个规划中的轻量化、可移植的 P2P 通信项目。

它的核心目标很简单：

> 让任何可以运行 Python 的环境，都能以尽量少的依赖和更清晰的分层结构，实现安全的 P2P 通信。

当前仓库仍处于探索阶段，已经有一些后续将被接入全栈的独立工具：

- `tools/ip_acquirer`：从多个提供商获取公网 IP，带简单重试、校验和静默的最快 provider 缓存。
- `tools/explorer_core`：文件与目录管理工具，可读取、写入、列举和搜索，支持可选 base64。
- `tools/terminal_panel`：仅桌面可用的终端面板引导程序。
- `net_core/handshake/token.py`：握手令牌层的设计草稿。

## 当前目录结构

```text
PyE_P2P/
├─ net_core/
│  └─ handshake/token.py              # 握手令牌设计 stub
├─ tools/
│  ├─ ip_acquirer/                    # 公网 IP 获取器 + provider 列表
│  │  ├─ acquirer.py
│  │  └─ provider.json
│  ├─ explorer_core/                  # 文件/目录工具
│  │  └─ file_manager.py
│  └─ terminal_panel/                 # 桌面终端面板引导
│     └─ manager.py
└─ TODO/                              # 布局与目标说明
   ├─ files.md
   └─ purpose.md
```

## 可用的小工具用法

- 公网 IP：`python tools/ip_acquirer/acquirer.py` 会调用多个提供商并输出公网 IP 及来源；provider 文件会缓存 hash 和最快的 60% provider。
- 文件工具：`from tools.explorer_core.file_manager import FileManager` 可进行文件/目录读写与管理。
- 终端面板：桌面平台工具，启动方式见 `tools/terminal_panel/manager.py` 的文档字符串。

## 设计目标

- UI、加密、网络三层可替换实现。
- 基于标准库的零依赖模式。
- 提供更强加密与更丰富界面的高配模式。
- 支持单文件部署，便于分发。
- 面向终端优先和移动端友好使用场景。

## 规划架构

项目围绕三大核心层展开：

- `ui_core`：TUI、Tkinter、Qt 等前端。
- `encrypt_core`：低安全级与高安全级加密后端。
- `net_core`：握手、会话、传输逻辑。

### 依赖策略

| Layer | Low Mode | High Mode |
|---|---|---|
| UI | TUI, Tkinter | Qt |
| Encryption | XOR, PBKDF2, HMAC | AES-GCM, ECDH, Argon2 |
| Network | `threading` | `asyncio` |

### 预期流程

1. 手动交换密钥信息。
2. 握手与对端验证。
3. 密钥协商。
4. 会话建立。
5. 消息传输与心跳保活。
6. 会话关闭与失步处理。

## 目标特性

| Feature | Description | Status |
|---|---|---|
| Layered dependencies | 标准库与高级实现可切换 | 规划中 |
| Mobile-friendly UI | 面向 Termux 等移动终端优化 | 规划中 |
| Single-file deployment | 可整合为单文件便于复制运行 | 规划中 |
| Dual crypto backends | 低模式与高模式加密后端 | 规划中 |
| P2P direct connection | 无需中继服务器 | 规划中 |
| File transfer | 分块传输与断点续传 | 规划中 |
| Multi-UI support | TUI、Tkinter、Qt 三种界面 | 规划中 |
| Zero-dependency mode | 仅依赖标准库运行 | 规划中 |

## 配置

规划中的环境变量：

| Variable | Default | Description |
|---|---|---|
| `PYE_MODE` | `auto` | 加密模式：`low`、`high` 或 `auto` |
| `PYE_UI` | `tui` | 界面类型：`tui`、`tk` 或 `qt` |
| `PYE_SYNC` | `strict` | 同步策略 |

配置文件示例：

```json
{
  "encryption": {
    "mode": "high",
    "key_length": 32,
    "kdf_iterations": 100000
  },
  "network": {
    "bind_address": "0.0.0.0",
    "port_range": [5000, 6000],
    "timeout": 30
  },
  "security": {
    "strict_sync": true,
    "log_level": "info"
  }
}
```

## 安全声明

本项目面向学习、原型验证以及受控的私有通信场景。

- 代码应保持可审计。
- 低安全级后端仅用于兼容和教学。
- 严肃用途应优先选择高安全级后端。
- 用户必须遵守所在地法律法规。

## 开发路线

### 第一阶段

- 项目架构设计
- 加密接口抽象
- 基于 socket 的通信框架
- 有限状态机管理

### 第二阶段

- 文件传输与断点续传
- TUI 改进
- 跨平台兼容性测试

### 第三阶段

- 移动端轻量化版本
- 单文件打包流程
- 完整文档与 API 参考

## 贡献

等实现进入稳定阶段后，欢迎贡献。

可参与的方向：

- 网络与协议设计
- 加密后端实现
- UI 原型开发
- 文档与测试

## 许可证

MIT License。

## 备注

当前仓库主要反映规划阶段，而不是完整实现。
