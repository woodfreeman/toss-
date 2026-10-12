# 项目说明 / Project Description

## GitHub About 简介 / Suggested GitHub About text

**中文：** 自托管局域网互传工具，支持文本、图片与文件；数据保存在接收实例，不经过云端中转。

**English:** A self-hosted LAN transfer tool for text, images, and files; data stays on the receiving instance, with no cloud relay.

**双语合并版 / Combined:** Toss 快抛 | Self-hosted LAN transfer for text, images, and files; local storage, no cloud relay.

## 中文项目说明

Toss 快抛是一款轻量级、自托管的局域网互传应用，面向需要在自己的电脑和可信网络设备之间传送文本、截图、图片及小文件的个人或小团队。项目使用 FastAPI 提供网页界面和 API，使用 SQLite 保存记录，并将上传文件放在运行实例本机的数据目录中。

每个 Toss 实例独立工作。用户可以运行多个实例，并通过“对方 Toss”快捷入口打开另一台设备上的页面；该入口不会同步记录。用户访问哪个实例，上传内容就存到哪个实例。程序不依赖云端中转。

当前源码以 Windows 使用和打包辅助流程为重点：包含当前用户开机启动脚本，并支持打包版程序从实例内已上传的新版本文件执行更新。

## English project description

Toss is a lightweight, self-hosted LAN transfer app for individuals and small teams who need to move text, screenshots, images, and small files between their own computers on a trusted network. FastAPI serves the web UI and API, SQLite stores item metadata and history, and uploaded files remain in the local data directory of the instance that receives them.

Each Toss instance is independent. Users may run multiple instances and use the “peer Toss” shortcut to open another instance in a browser, but that shortcut does not synchronize records. An upload is stored by the instance currently serving the page. The application does not rely on a cloud relay.

The current source focuses on Windows usage and packaging helpers. It includes scripts for current-user startup and an in-app update flow for packaged executables.

## 范围与边界 / Scope and boundaries

- **适用网络 / Intended network:** Trusted local networks. The server listens on all interfaces by default; the UI uses HTTP without TLS. Do not expose it directly to the public internet.
- **访问控制 / Authentication:** Optional access password. Set one before allowing other devices to connect; HTTP does not encrypt traffic.
- **存储 / Storage:** Local SQLite database, uploaded files, signing key, and logs under data/. No cloud backup or automatic instance replication.
- **保留期 / Retention:** 30 days by default, configurable from 1 to 90 days. Cleanup applies to active and trashed entries.
- **传输限制 / Transfer limits:** The UI recommends files up to 500 MB. Chunked and resumable transfers are not implemented.
- **仓库内容 / Repository contents:** Application source, frontend, portable tests, user documentation, general Windows helpers, and sanitized development notes are included. The notes omit device, network, and deployment-specific details. Environment-specific live update tests, a one-off internal deployment script, runtime data, and compiled executables are excluded.
- **许可证 / License:** No LICENSE file is currently included; reuse and redistribution terms have not been specified.

## 源码版本 / Source version

The backend currently declares version 0.1.7. This describes the checked-in source, not a hosted service or a promise that a packaged executable is available.
