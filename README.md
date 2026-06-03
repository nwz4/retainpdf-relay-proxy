# RetainPDF Relay Proxy

<img src="assets/retainpdf-relay-proxy.png" width="96" alt="RetainPDF Relay Proxy 图标">

RetainPDF Relay Proxy 是一个给 RetainPDF 桌面版使用的本地 OpenAI 兼容中转代理。它不会修改 RetainPDF 源码，也不会修改已经打包的 RetainPDF.exe；工具会在本机启动一个轻量 HTTP 服务，把 RetainPDF 的模型请求转发到你配置的上游中转站或 OpenAI 兼容接口。

原软件项目：[wxyhgk/retain-pdf](https://github.com/wxyhgk/retain-pdf)

本项目是独立辅助工具，不代表 RetainPDF 官方组件。

## 功能

- 本地监听 `http://127.0.0.1:18181/v1`。
- 转发 `/v1/chat/completions` 请求到上游 OpenAI 兼容接口。
- 本地响应 `/models` 和 `/user/balance`，方便部分隐藏开发者设置的桌面版本通过启动和提交前检查。
- 支持固定上游 API Key、固定模型名、并发限制和 RPM 限制。
- 可自动写入 RetainPDF 桌面隐藏配置，并通过本工具启动 RetainPDF。
- Windows GUI 支持高 DPI 显示，并使用项目图标。

## 快速开始

双击启动：

```text
OneClick-Start-RetainPDF-Relay.vbs
```

或打开配置窗口：

```powershell
.\Start-RetainPdfRelayProxy.ps1 -Gui
```

配置窗口中填写：

- 中转站网址：例如 `https://your-relay.example.com/v1`
- API Key：你的上游中转站密钥
- 模型名：可选；为空时沿用 RetainPDF 请求中的模型
- RetainPDF.exe：可选；用于“保存并启动”

保存后会在项目根目录生成 `retainpdf-relay-proxy.json`。该文件包含个人 API Key，已被 `.gitignore` 忽略，不会作为公开文件提交。

## 示例配置

可以从示例文件复制一份本地配置：

```powershell
Copy-Item .\config\retainpdf-relay-proxy.example.json .\retainpdf-relay-proxy.json
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
  "acquire_timeout_seconds": 3600,
  "upstream_timeout_seconds": 180,
  "forward_authorization": true,
  "log_requests": true,
  "patch_desktop_config": true,
  "desktop_config_path": "",
  "retainpdf_api_key": "",
  "mock_balance": true,
  "mock_balance_total": "999.00"
}
```

`upstream_transport` 建议保持 `auto`。在 Windows 下会优先使用系统 `curl.exe` 转发上游请求；如果不可用，会回退到 Python 内置 HTTP 客户端。

## RetainPDF 设置

如果需要在 RetainPDF 中手动填写开发者设置：

- Base URL：`http://127.0.0.1:18181/api.deepseek.com/v1`
- API Key：任意非空值，或你的真实上游 Key
- Model：你的中转站模型名；如果已在本工具中固定 `upstream_model`，这里可以保持一致

对于隐藏开发者设置的桌面版本，保持 `patch_desktop_config` 为 `true`，并通过本工具启动 RetainPDF。

## 健康检查

代理启动后可以检查：

```powershell
Invoke-RestMethod http://127.0.0.1:18181/health
Invoke-RestMethod http://127.0.0.1:18181/user/balance
Invoke-RestMethod http://127.0.0.1:18181/api.deepseek.com/v1/models
```

## 目录结构

```text
.
├─ assets/      # 图标和 Windows manifest
├─ config/      # 示例配置
├─ scripts/     # 构建和打包脚本
├─ src/         # Python 主程序
├─ dist/        # 本地构建产物，默认不提交
└─ release/     # 本地发布包，默认不提交
```

根目录保留 `Start-RetainPdfRelayProxy.ps1`、`OneClick-Start-RetainPDF-Relay.vbs` 和 `OneClick-Start-RetainPDF-Relay.bat`，方便直接启动。

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

构建脚本会使用 `assets\retainpdf-relay-proxy.ico` 和 `assets\RetainPdfRelayProxy.exe.manifest`，让 exe 带有图标并支持 Windows Per-Monitor DPI。

## 生成发布包

```powershell
.\Package-Release.ps1 -Version 0.1.0
```

如需同时构建 exe：

```powershell
.\Package-Release.ps1 -Version 0.1.0 -BuildExe
```

发布包采用白名单复制，只包含公开源码、启动脚本、示例配置、图标、README 和许可证；不会包含本地 `retainpdf-relay-proxy.json`、日志、构建缓存或个人路径。

## 安全提示

- 不要提交 `retainpdf-relay-proxy.json`。
- 不要提交真实 API Key、真实中转站地址、本机软件路径或日志。
- 如果曾误提交 API Key，请立即到上游服务商后台重置密钥。

## 开源协议

本项目使用 [MIT License](LICENSE)。
