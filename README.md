# Lite Tools

轻量跨平台的开发小工具箱。纯 Python + Tkinter 实现，运行时只依赖标准库，打包后是单个可执行文件（约 15 MB）。

## 功能

| 模块 | 能力 |
| --- | --- |
| **JSON 工具** | 格式化（2/4 空格、Tab、单行）、压缩、转义与反转义、中文 `\uXXXX` 互转、合法性校验、结构统计、右键菜单与 JSON 语法高亮；**宽松模式**可自动修复注释、单引号、未加引号的键、尾随逗号、Python 字面量等无歧义写法 |
| **时间戳转换** | 10/13/16 位时间戳与 16 种日期格式互转，ISO8601 / RFC2822 / Nginx 日志时间，时区换算（9 个常用时区），实时时钟 |
| **启动变量** | IDEA Run Configuration ↔ Linux `export` ↔ `.env` ↔ `docker -e` ↔ JSON 五种格式互转，自动处理引号与分号 |
| **JSON 生成** | Java 实体类 → JSON 样例（支持泛型、集合、Map、嵌套类、Java 8 时间类型）；JSON → Java POJO（自动推断类型、嵌套静态内部类、Lombok / Jackson 注解、下划线转驼峰） |
| **网络工具** | 本机网卡 IP / 公网 IP / IP 归属地、DNS 解析与缓存清理、ping、端口连通检测（telnet） |
| **设置** | 开机自启、全局快捷键、最小化到托盘、窗口置顶 |

## 快速开始

```bash
# 运行（无需安装任何依赖）
python main.py

# Windows 托盘需要 pywin32，其余功能不受影响
pip install pywin32
```

要求 Python 3.9 及以上。

## 界面特性

- **高分屏清晰**：启动时开启进程 DPI 感知并按系统缩放比例调整字体与尺寸，避免 Windows 位图拉伸导致的文字发虚。
- **自适应布局**：工具栏按钮在窗口变窄时自动换行；左右分栏在宽度不足时自动改为上下堆叠；页面内容超出可视区域时出现滚动条。窗口最窄可缩到 720 × 500。
- **耗时操作有反馈**：执行任务时相关按钮自动禁用（防止重复点击），底部显示细长进度条（端口检测按进度推进，其余为循环动画）。
- **拖动流畅**：Tk 缩放时会遍历所有控件重算几何并重绘，每多一个控件就多约 0.6~1 ms，控件一多就跟不上鼠标。因此连续变化时用 `WM_SETREDRAW` 暂停重绘，停下来再整体刷新一次（实测 45.8 → 23 ms/帧）。
- **滚轮随处可用**：滚轮事件不会沿父子层级冒泡，页面滚动采用全局分发并按鼠标位置判断归属；鼠标在代码框或表格上时优先滚动它们自身。
- **圆润外观**：卡片、按钮、页签、导航项自绘圆角；输入框、下拉框、复选框、表格、滚动条交给系统原生渲染，保证清晰度。

## 打包

```bash
pip install pyinstaller
python build.py            # 生成 dist/LiteTools/ 目录（推荐，启动最快）
python build.py --onefile  # 生成单个 exe，便于分发但每次启动都要先解压
```

两种产物功能完全一样，区别只在启动速度：

- **目录版**（默认）：直接运行 `dist/LiteTools/LiteTools.exe`，无额外启动开销。整个目录可拷贝到其它机器使用。
- **单文件版**：每次运行都要先把整个包解压到临时目录再启动，体积越大等待越久。分发方便，但启动明显更慢。

打包脚本已排除 numpy / pandas / PyQt 等无关的大块依赖，并关闭 UPX 压缩（压缩后的自解压也会拖慢启动）。

## 开机自启与快捷键

- **开机自启**：在「设置」页勾选即可。Windows 写入注册表 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`，macOS 写入 LaunchAgent，Linux 写入 `~/.config/autostart`。
- **全局快捷键**：默认 `Ctrl + Alt + L`，按下可在任意程序中呼出或隐藏主窗口。快捷键仅 Windows 支持（使用系统 `RegisterHotKey`，不依赖第三方库）。
- **托盘**：勾选「点击关闭按钮时最小化到托盘」后，关闭窗口不会退出程序，可右键托盘图标退出。

## 配置文件

所有设置保存在用户目录，删除即恢复默认：

| 平台 | 路径 |
| --- | --- |
| Windows | `%APPDATA%\LiteTools\config.json` |
| macOS | `~/Library/Application Support/LiteTools/config.json` |
| Linux | `~/.config/LiteTools/config.json` |

## 支持的输入格式

**时间戳**：`1712300000`、`1712300000000`、`now`、`2024-03-05 12:30:00`、`2024-03-05`、`2024/03/05`、`20240305`、`12:30`、`2024-03-05T12:30:00+08:00`、`Tue, 05 Mar 2024 12:30:00 GMT`、`05/Mar/2024:12:30:00`

**启动变量**：

```
IDEA          DB_HOST=127.0.0.1;JAVA_OPTS="-Xms512m -Xmx1024m"
Linux export  export DB_HOST=127.0.0.1
.env          DB_HOST=127.0.0.1
docker -e     -e DB_HOST=127.0.0.1
JSON          {"DB_HOST": "127.0.0.1"}
```

## 目录结构

```
main.py                  程序入口
selftest.py              核心逻辑自检（不依赖界面）
build.py                 打包脚本
app/
  config.py              配置读写
  theme.py               配色与 ttk 样式
  widgets.py             通用组件（代码框、卡片、右键菜单）
  window.py              主窗口与导航
  core/                  纯逻辑层，可独立调用
    json_utils.py        JSON 处理
    time_utils.py        时间转换
    env_utils.py         启动变量格式互转
    codegen.py           Java ↔ JSON
    net_utils.py         网络工具
  native/                平台相关能力
    autostart.py         开机自启
    hotkey.py            全局快捷键（ctypes 调 Win32）
    tray.py              系统托盘
    icon.py              图标生成
    redraw.py            拖动窗口时暂停/恢复重绘
  pages/                 界面页面
```

## 开发提示

- `app/core/` 与界面完全解耦，改动后执行 `python selftest.py` 可快速验证。
- 耗时操作请用 `Page.run_async` / `Page.run_stream`，**不要在工作线程中读取 Tk 变量**（`StringVar.get()` 等），先在主线程取出值再传入。它们同时负责禁用按钮与驱动进度条。
- 布局优先使用现成组件：`FlowFrame`（自动换行）、`SplitPanes`（过窄自动堆叠）、`ScrollArea`（内容超高滚动）、`Card`（圆角卡片，内容放 `card.content`）。
- 不要直接使用 `ttk.Button`，改用 `widgets.button()` 以获得统一的圆角外观；复选框同理用 `widgets.check_box()`。
- 所有像素尺寸请用 `theme.sp()` 换算，否则在高 DPI 屏幕上比例会失真。
