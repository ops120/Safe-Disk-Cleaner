# 🚀 Win10/11 C盘深度清理专家 (C-Drive Deep Cleaner)

[![Python](https://img.shields.io/badge/Python-3.x-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows-win.svg)](https://microsoft.com/windows)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](./LICENSE)

**一个安全、可视化的 Windows 系统清理工具。** 无需安装庞大的第三方软件，基于 Python 原生 WinAPI 开发，提供系统垃圾扫描、大文件可视化搜索、实时性能监控以及安全的回收站机制。

## ✨ 核心功能 (Features)

* **📊 实时系统监控**：顶部仪表盘实时显示 CPU 和 内存 (RAM) 占用率。
* **🛡️ 安全第一**：
    * **回收站机制**：所有删除操作默认将文件移入回收站，提供“后悔药”。
    * **自动备份**：支持在清理前将文件备份到指定目录。
* **🧹 智能垃圾清理**：
    * 深度扫描系统临时文件 (`Temp`)、浏览器缓存 (`Chrome`/`Edge`)。
    * 专为开发者优化：支持清理 `pip` 和 `uv` 等 Python 开发工具缓存。
* **🐘 大文件搜索**：
    * 自定义大小阈值（如 >1GB）。
    * **风险评估**：通过 红/黄/绿 三色标签自动识别系统敏感文件（如 `.sys`, `.dll`），防止误删。
* **⚡ 零依赖**：完全基于 Python 标准库 (`tkinter`, `ctypes`) 开发，无需安装 `psutil` 等第三方库。

## 🛠️ 运行环境 (Requirements)

* Windows 10 或 Windows 11
* Python 3.8+ (如果是运行源码)
* **注意**：必须以 **管理员身份 (Administrator)** 运行，否则无法清理系统路径。

## 🚀 快速开始 (Usage)

### 方式一：直接运行源码
```bash
# 1. 克隆仓库
git clone [https://github.com/你的用户名/你的仓库名.git](https://github.com/你的用户名/你的仓库名.git)

# 2. 进入目录
cd 你的仓库名

# 3. 运行脚本 (请确保以管理员权限打开终端)
python cleaner.py
```
### 方式二：打包为 EXE (推荐)

如果你想生成一个可以在任何电脑上运行的 .exe 文件：

```bash
# 1. 安装 PyInstaller
pip install pyinstaller

# 2. 执行打包命令
pyinstaller --onefile --noconsole --uac-admin --name="C盘深度清理专家" cleaner.py

# 3. 在 dist 文件夹中找到生成的 exe 文件
```
