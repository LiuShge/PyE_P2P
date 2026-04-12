### 当前目录（2026-04-11）
```text
PyE_P2P/
├─ net_core/
│  └─ handshake/
│     └─ token.py               # 令牌层设计 stub
├─ tools/
│  ├─ ip_acquirer/              # 公网 IP 获取器
│  │  ├─ acquirer.py
│  │  └─ provider.json
│  ├─ explorer_core/            # 文件/目录工具
│  │  └─ file_searcher.py
│  └─ terminal_panel/           # 桌面终端面板
│     └─ manager.py
├─ TODO/
│  ├─ files.md
│  └─ purpose.md
├─ README.md / README_ZH.md
```

### 规划中的完整布局（待实现）
```text
net_core/
 ├─ handshake/
 │  ├─ token.py
 │  ├─ peer_info.py
 │  ├─ renew_token.py
 │  └─ __init__.py
 ├─ session/
 │  ├─ verify.py
 │  ├─ status.py
 │  ├─ message.py
 │  └─ __init__.py
 ├─ tools/
 │  ├─ dir_transport/
 │  │  ├─ dir_convert.py
 │  │  ├─ display_tree.py   # 显示传输目录树
 │  │  ├─ open_file.py      # 从传输目录打开文件
 │  │  └─ __init__.py
 │  └─ __init__.py
 └─ __init__.py

ui_core/
 ├─ tui/__init__.py
 ├─ tk/__init__.py
 └─ qt/__init__.py

encrypt_core/
 ├─ __init__.py
 ├─ interface.py
 ├─ backend_low/
 │  ├─ basic_xor.py
 │  ├─ pbkdf2_kdf.py
 │  ├─ hmac_crypto.py
 │  ├─ base64_codec.py
 │  └─ __init__.py
 └─ backend_high/
    ├─ aes_gcm.py
    ├─ ecdh_exchange.py
    ├─ argon2_kdf.py
    └─ __init__.py
```

### 补充说明
- “当前目录”反映了仓库已有的可运行/草稿代码。
- “规划中的完整布局”保留原始设计，便于后续对齐和分解任务。
