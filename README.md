# Toss 快抛

Toss is a self-hosted, Windows-first tool for moving text, images, and files between devices on a trusted local network. It runs on your own computer, stores data locally, and does not use a cloud relay.

**Source version:** 0.1.7 (from backend/main.py)

[简体中文](README.zh-CN.md) · [Project description](PROJECT_DESCRIPTION.md) · [Chinese deployment guide](部署说明.md)

## Features

- Send text snippets and multi-file uploads, including images and screenshots pasted from the clipboard.
- Browse, preview, download, annotate, and rename saved items.
- Move items to a recoverable trash view, restore them, or permanently remove them.
- Configure an optional access password and a retention period from 1 to 90 days (30 days by default).
- Show the current instance address and keep a shortcut to a peer Toss instance.
- In packaged Windows builds, check for and apply a newer Toss executable uploaded to the instance.
- Optionally register the packaged app to start when the current Windows user signs in.

## How it works

Run one Toss instance on each computer, or run a single instance and let other devices access it. Each instance has its own database and files. The “peer Toss” button opens the saved peer address in a browser; it does not synchronize or copy records between instances. An upload is stored on the instance currently serving the page.

By default the app listens on all network interfaces at port 8400 so other devices on the LAN can connect. Set TOSS_PORT to use a different port.

## Run from source

From the repository root, install the Python dependencies and start the app:

    python -m pip install -r requirements.txt
    python backend/main.py

Open http://localhost:8400 on the same computer. To connect from another device, use the host computer’s reachable LAN address and port, for example http://<LAN-IP>:8400. Allow the app through the Windows firewall on a trusted private network when prompted.

To change the port in PowerShell:

    $env:TOSS_PORT = "8401"
    python backend/main.py

The source repository does not include a compiled executable or a pinned release build configuration.

## Data and security

- Transfer history, uploaded files, the SQLite database, the signing key, and logs are stored under the runtime data directory: data/.
- Keep data/ private and out of source control. It contains user content and the key used to sign login sessions; the repository ignore rules exclude it.
- The access password is optional. Set one before sharing the service with other devices. Passwords are stored as PBKDF2-HMAC-SHA256 hashes.
- The app serves plain HTTP and does not enable TLS by default. Use it only on a network you trust. Do not expose it directly to the public internet or configure router port forwarding.
- The app does not provide cloud backup, automatic replication, resumable uploads, or chunked file transfer.

## Retention and limits

The default retention period is 30 days and can be changed to 1–90 days in Settings. Cleanup applies to saved and trashed entries. The upload interface recommends keeping individual files at or below 500 MB; uploads are not chunked or resumable.

## Windows helpers

install-autostart.bat registers Toss.exe to start at sign-in for the current Windows user. remove-autostart.bat removes that entry. Both scripts expect Toss.exe beside the script.

The packaged-build self-update flow is Windows-specific and works only when Toss is running as a bundled executable. A newer package must be uploaded with a name such as Toss-v0.1.8.exe.

## Repository contents

This source snapshot includes the application, frontend, portable tests, user documentation, general Windows helpers, and sanitized development notes. The notes omit device, network, and deployment-specific details; environment-specific live update tests and a one-off internal deployment script are excluded.

## License

There is no LICENSE file in this repository. Public visibility does not grant reuse or redistribution rights; a license has not been specified.
