# RetainPDF Relay Proxy

RetainPDF Relay Proxy 是一个给 RetainPDF 桌面版使用的本地 OpenAI 兼容中转代理。它不修改 RetainPDF 源码，也不修改已打包的 RetainPDF.exe，而是在本机启动一个轻量代理服务，把 RetainPDF 的模型请求转发到你配置的上游中转站。

原软件项目：[wxyhgk/retain-pdf](https://github.com/wxyhgk/retain-pdf)

本项目是独立辅助工具，不代表原项目官方组件。

## 功能简介

- 本地监听 `http://127.0.0.1:18181/v1`。
- 转发 RetainPDF 的 `/v1/chat/completions` 请求到上游 OpenAI 兼容接口。
- 提供 `/models` 和 `/user/balance` 本地响应，方便部分隐藏设置的桌面版本通过启动和提交前检查。
- 支持并发数和 RPM 限制，避免上游中转站超限。
- 支持固定上游 API Key 和模型名，也可以沿用 RetainPDF 传入的模型。
- 可自动写入 RetainPDF 桌面隐藏配置，并通过本工具启动 RetainPDF。
- Windows GUI 已做 DPI 感知和现代化界面优化。

## 快速开始

打开配置窗口：

```powershell
.\Start-RetainPdfRelayProxy.ps1 -Gui
```

填写：

- 中转站网址：例如 `https://your-relay.example.com/v1`
- API Key：你的上游中转站密钥
- 模型名：可选；为空时沿用 RetainPDF 请求中的模型
- RetainPDF.exe：可选；用于“保存并启动”

配置会保存为 `retainpdf-relay-proxy.json`。该文件包含个人 API Key，默认被 `.gitignore` 忽略，不应提交到仓库。

## 示例配置

复制示例配置：

```powershell
Copy-Item .\retainpdf-relay-proxy.example.json .\retainpdf-relay-proxy.json
```

示例内容：

```json
{
  "listen_host": "127.0.0.1",
  "listen_port": 18181,
  "upstream_base_url": "https://your-relay.example.com/v1",
  "upstream_api_key": "sk-your-relay-api-key",
  "upstream_model": "",
  "upstream_transport": "auto",
  "retainpdf_exe_path": "",
  "max_concurrent": 5,
  "max_requests_per_minute": 60,
  "patch_desktop_config": true,
  "mock_balance": true
}
```

说明：

- `upstream_transport` 建议保持 `auto`。Windows 下会优先使用系统 `curl.exe` 转发上游请求，减少部分服务对 Python HTTP 指纹的拦截。
- `max_concurrent` 控制同时转发的请求数。
- `max_requests_per_minute` 为 `0` 时不限制 RPM。
- `mock_balance` 用于本地模拟余额检查，只是为了让非官方 DeepSeek 接口的中转服务通过 RetainPDF 的提交前检查。

## 一键启动

双击：

```text
OneClick-Start-RetainPDF-Relay.vbs
```

或使用兼容批处理：

```text
OneClick-Start-RetainPDF-Relay.bat
```

启动器会优先使用 `dist\RetainPdfRelayProxy.exe`。如果不存在，则回退到 `pythonw.exe retainpdf_relay_proxy.py`。

## RetainPDF 设置

如果需要手动填写 RetainPDF 开发者设置：

- Base URL：`http://127.0.0.1:18181/api.deepseek.com/v1`
- API Key：任意非空值，或你的真实上游 Key
- Model：你的中转站模型名，除非已在本工具中固定 `upstream_model`

对于隐藏开发者设置的桌面版本，保持 `patch_desktop_config` 为 `true`，并通过本工具启动 RetainPDF。

## 健康检查

代理启动后可检查：

```powershell
Invoke-RestMethod http://127.0.0.1:18181/health
Invoke-RestMethod http://127.0.0.1:18181/user/balance
Invoke-RestMethod http://127.0.0.1:18181/api.deepseek.com/v1/models
```

## 构建 Windows exe

安装 PyInstaller：

```powershell
python -m pip install pyinstaller
```

构建：

```powershell
.\Build-WindowsExe.ps1
```

生成文件：

```text
dist\RetainPdfRelayProxy.exe
```

构建脚本会带上 `RetainPdfRelayProxy.exe.manifest`，使 exe 支持 Windows Per-Monitor DPI，减少高分屏下字体模糊或锯齿。

## 发布打包

生成干净发布包：

```powershell
.\Package-Release.ps1 -Version 0.1.0
```

如果希望同时构建 exe：

```powershell
.\Package-Release.ps1 -Version 0.1.0 -BuildExe
```

发布包会排除：

- `retainpdf-relay-proxy.json`
- `*.log`
- `dist\build`
- `*.spec`
- `__pycache__`
- 其他本地配置文件

请只发布 `release\retainpdf-relay-proxy-版本号.zip`，不要上传个人配置和日志。

## GitHub 开源建议

建议新建独立仓库，例如：

```text
retainpdf-relay-proxy
```

初始化并提交：

```powershell
git init
git add .
git commit -m "Initial open-source release"
git branch -M main
git remote add origin https://github.com/<your-name>/retainpdf-relay-proxy.git
git push -u origin main
```

发布 Release 时上传 `Package-Release.ps1` 生成的 zip 包。

## 安全提醒

- 不要提交 `retainpdf-relay-proxy.json`。
- 不要提交真实 API Key、真实中转站地址、本机软件路径或日志。
- 如果曾误提交 API Key，请立即到上游服务商后台重置密钥。

## 开源协议

本项目使用 [MIT License](LICENSE)。
