import os
import shutil
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import ctypes
from ctypes import wintypes
import time
import hashlib
import winreg
import webbrowser
import json

# ==========================================
# Windows API 定义 (Shell & Kernel)
# ==========================================
FILEOP_FLAGS = wintypes.WORD
class SHFILEOPSTRUCT(ctypes.Structure):
    _pack_ = 8
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", FILEOP_FLAGS),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", wintypes.LPVOID),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]

FO_DELETE = 3
FOF_ALLOWUNDO = 0x40
FOF_NOCONFIRMATION = 0x10
FOF_NOERRORUI = 0x0400
FOF_SILENT = 0x0004

class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]
    def __init__(self):
        self.dwLength = ctypes.sizeof(self)

class FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

def send_to_recycle_bin(path):
    if not os.path.exists(path): return 0
    pFrom = os.path.abspath(path) + "\0\0"
    fileop = SHFILEOPSTRUCT()
    fileop.wFunc = FO_DELETE
    fileop.pFrom = pFrom
    fileop.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_NOERRORUI | FOF_SILENT
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(fileop))
    return result == 0

def is_admin():
    try: return ctypes.windll.shell32.IsUserAnAdmin()
    except: return False

def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024: return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"

# ==========================================
# 浅色主题配置
# ==========================================
LIGHT_THEME = {
    'bg': '#FAFBFC',
    'fg': '#24292E',
    'fg_secondary': '#586069',
    'entry_bg': '#FFFFFF',
    'entry_fg': '#24292E',
    'button_bg': '#2EA44F',
    'button_fg': '#FFFFFF',
    'button_hover': '#22863A',
    'danger_bg': '#CB2431',
    'success_bg': '#2EA44F',
    'warning_bg': '#DBAB09',
    'accent': '#0366D6',
    'border': '#E1E4E8',
    'tree_bg': '#FFFFFF',
    'tree_fg': '#24292E',
    'tree_selected': '#0366D6',
    'tree_header_bg': '#F6F8FA',
    'scrollbar_bg': '#F6F8FA',
    'scrollbar_thumb': '#C0C0C0',
    'link_color': '#0366D6',
}

THEME = LIGHT_THEME

# ==========================================
# 工具函数
# ==========================================
def get_available_drives():
    """获取系统可用盘符"""
    drives = []
    for letter in 'DEFGHIJKLMNOPQRSTUVWXYZ':
        drive = f'{letter}:'
        if os.path.exists(drive):
            drives.append(drive)
    if 'C:' not in drives:
        drives.insert(0, 'C:')
    drives.sort()
    return drives

def get_system_drive():
    """获取系统盘符"""
    return os.environ.get('SystemDrive', 'C:')

def get_disk_usage(drive):
    """获取磁盘使用情况"""
    try:
        free_bytes = ctypes.c_ulonglong(0)
        total_bytes = ctypes.c_ulonglong(0)
        ctypes.windll.kernel32.GetDiskFreeSpaceExW(ctypes.c_wchar_p(drive), None, ctypes.pointer(total_bytes), ctypes.pointer(free_bytes))
        total_gb = total_bytes.value / (1024**3)
        free_gb = free_bytes.value / (1024**3)
        used_gb = total_gb - free_gb
        return total_gb, free_gb, used_gb
    except:
        return 0, 0, 0

def load_history():
    """加载历史记录"""
    try:
        history_file = os.path.join(os.environ.get('LOCALAPPDATA', '.'), 'disk_cleaner_history.json')
        if os.path.exists(history_file):
            with open(history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {}

def save_history(history):
    """保存历史记录"""
    try:
        history_file = os.path.join(os.environ.get('LOCALAPPDATA', '.'), 'disk_cleaner_history.json')
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except:
        pass

# ==========================================
# 系统监控类
# ==========================================
class SystemMonitor:
    def __init__(self):
        self.last_idle = 0
        self.last_kernel = 0
        self.last_user = 0

    def get_memory_usage(self):
        stat = MEMORYSTATUSEX()
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return stat.dwMemoryLoad

    def get_memory_info(self):
        stat = MEMORYSTATUSEX()
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        return {
            'total': stat.ullTotalPhys,
            'available': stat.ullAvailPhys,
            'used': stat.ullTotalPhys - stat.ullAvailPhys,
            'percent': stat.dwMemoryLoad
        }

    def get_disk_info(self, drive='C:'):
        try:
            free_bytes = ctypes.c_ulonglong(0)
            total_bytes = ctypes.c_ulonglong(0)
            ctypes.windll.kernel32.GetDiskFreeSpaceExW(ctypes.c_wchar_p(drive), None, ctypes.byref(total_bytes), ctypes.byref(free_bytes))
            return {
                'total': total_bytes.value,
                'free': free_bytes.value,
                'used': total_bytes.value - free_bytes.value
            }
        except:
            return {'total': 0, 'free': 0, 'used': 0}

    def get_cpu_usage(self):
        idle = FILETIME()
        kernel = FILETIME()
        user = FILETIME()
        ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user))

        def ft_to_int(ft):
            return (ft.dwHighDateTime << 32) + ft.dwLowDateTime

        idle_time = ft_to_int(idle)
        kernel_time = ft_to_int(kernel)
        user_time = ft_to_int(user)

        if self.last_idle == 0:
            self.last_idle = idle_time
            self.last_kernel = kernel_time
            self.last_user = user_time
            return 0

        usr_diff = user_time - self.last_user
        ker_diff = kernel_time - self.last_kernel
        idle_diff = idle_time - self.last_idle

        sys_time = usr_diff + ker_diff

        self.last_idle = idle_time
        self.last_kernel = kernel_time
        self.last_user = user_time

        if sys_time == 0: return 0
        return int((sys_time - idle_diff) * 100 / sys_time)

# ==========================================
# 主程序逻辑
# ==========================================
class MonitorCleanerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("磁盘清理专家 V6.0 - by 你们喜爱的老王")
        self.root.geometry("1100x850")
        self.root.configure(bg=THEME['bg'])

        # 设置浅色主题
        self.setup_theme()

        # 初始化日志
        self.log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_file = os.path.join(self.log_dir, f"disk_cleaner_{time.strftime('%Y%m%d')}.log")
        self.log("=" * 50)
        self.log("程序启动")
        self.log(f"日志文件: {self.log_file}")

        if not is_admin():
            messagebox.showwarning("权限警告", "建议以管理员身份运行，否则无法准确判断系统文件风险！")

        self.backup_path_var = tk.StringVar()
        self.enable_backup_var = tk.IntVar(value=0)
        self.is_working = False
        self.stop_event = False
        self.sys_mon = SystemMonitor()
        self.scan_results = {}  # 存储扫描结果
        self.selected_drive = tk.StringVar(value=get_system_drive())
        self.last_scan_size = 0  # 上次扫描到的大小

        # 加载历史记录
        self.history = load_history()

        self.setup_ui()
        self.update_system_stats()
        self.update_history_display()

    def log(self, message):
        """写入日志并输出到终端"""
        try:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            log_line = f"[{timestamp}] {message}"
            # 写入日志文件
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(log_line + "\n")
                f.flush()  # 立即刷新到文件
            # 输出到终端
            print(log_line)
        except Exception as e:
            print(f"日志写入失败: {e}")

    def setup_theme(self):
        """配置浅色主题样式"""
        style = ttk.Style()
        style.theme_use('clam')

        style.configure("Treeview",
                       background=THEME['tree_bg'],
                       foreground=THEME['tree_fg'],
                       fieldbackground=THEME['tree_bg'],
                       borderwidth=0)
        style.map("Treeview",
                 background=[('selected', THEME['tree_selected'])],
                 foreground=[('selected', THEME['fg'])])

        style.configure("Treeview.Heading",
                       background=THEME['tree_header_bg'],
                       foreground=THEME['fg'],
                       relief="flat")
        style.map("Treeview.Heading",
                 background=[('active', THEME['border'])])

    def setup_ui(self):
        # 顶部仪表盘
        dash_frame = tk.LabelFrame(self.root, text="📊 系统实时状态", padx=10, pady=5, bg=THEME['bg'], fg=THEME['fg'])
        dash_frame.pack(fill="x", padx=10, pady=5)

        # CPU区域
        cpu_frame = tk.Frame(dash_frame, bg=THEME['bg'])
        cpu_frame.pack(side="left", fill="x", expand=True, padx=10)
        tk.Label(cpu_frame, text="CPU:", font=("Arial", 9, "bold"), bg=THEME['bg'], fg=THEME['fg']).pack(side="left")
        self.pb_cpu = ttk.Progressbar(cpu_frame, orient="horizontal", mode="determinate", length=150)
        self.pb_cpu.pack(side="left", padx=5)
        self.lbl_cpu = tk.Label(cpu_frame, text="0%", width=5, bg=THEME['bg'], fg=THEME['fg'])
        self.lbl_cpu.pack(side="left")

        # 内存区域
        mem_frame = tk.Frame(dash_frame, bg=THEME['bg'])
        mem_frame.pack(side="left", fill="x", expand=True, padx=10)
        tk.Label(mem_frame, text="RAM:", font=("Arial", 9, "bold"), bg=THEME['bg'], fg=THEME['fg']).pack(side="left")
        self.pb_mem = ttk.Progressbar(mem_frame, orient="horizontal", mode="determinate", length=150)
        self.pb_mem.pack(side="left", padx=5)
        self.lbl_mem = tk.Label(mem_frame, text="0%", width=5, bg=THEME['bg'], fg=THEME['fg'])
        self.lbl_mem.pack(side="left")

        # 磁盘区域
        disk_frame = tk.Frame(dash_frame, bg=THEME['bg'])
        disk_frame.pack(side="left", fill="x", expand=True, padx=10)
        tk.Label(disk_frame, text="C盘:", font=("Arial", 9, "bold"), bg=THEME['bg'], fg=THEME['fg']).pack(side="left")
        self.pb_disk = ttk.Progressbar(disk_frame, orient="horizontal", mode="determinate", length=150)
        self.pb_disk.pack(side="left", padx=5)
        self.lbl_disk = tk.Label(disk_frame, text="0%", width=8, bg=THEME['bg'], fg=THEME['fg'])
        self.lbl_disk.pack(side="left")

        # 备份设置 + 盘符选择
        bk_frame = tk.LabelFrame(self.root, text="🛡️ 磁盘清理设置", padx=10, pady=5, bg=THEME['bg'], fg=THEME['fg'])
        bk_frame.pack(fill="x", padx=10, pady=5)

        # 盘符选择
        tk.Label(bk_frame, text="选择磁盘:", bg=THEME['bg'], fg=THEME['fg']).pack(side="left", padx=5)
        drives = get_available_drives()
        self.combo_drive = ttk.Combobox(bk_frame, textvariable=self.selected_drive, values=drives, width=5, state="readonly")
        self.combo_drive.pack(side="left", padx=5)
        self.combo_drive.bind("<<ComboboxSelected>>", self.on_drive_changed)

        # 备份设置
        tk.Checkbutton(bk_frame, text="删除前备份到:",
                      variable=self.enable_backup_var,
                      command=self.toggle_backup_ui,
                      bg=THEME['bg'], fg=THEME['fg'],
                      selectcolor=THEME['bg']).pack(side="left", padx=20)
        self.entry_backup = tk.Entry(bk_frame, textvariable=self.backup_path_var, state="disabled",
                                    width=35, bg=THEME['entry_bg'], fg=THEME['entry_fg'])
        self.entry_backup.pack(side="left", padx=5)
        self.btn_browse = tk.Button(bk_frame, text="📂 选择...",
                                   command=self.browse_backup_folder, state="disabled",
                                   bg=THEME['button_bg'], fg=THEME['button_fg'])
        self.btn_browse.pack(side="left")

        # 备用按钮区域（右侧）
        self.btn_about = tk.Button(bk_frame, text="ℹ️ 关于",
                                  command=self.show_about,
                                  bg='#555555', fg=THEME['fg'])
        self.btn_about.pack(side="right", padx=10)

        # 标签页
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=5)

        self.tab_clean = tk.Frame(self.notebook)
        self.tab_clean = tk.Frame(self.notebook, bg=THEME['bg'])
        self.notebook.add(self.tab_clean, text="   🧹 垃圾清理   ")
        self.setup_clean_tab()

        self.tab_large = tk.Frame(self.notebook, bg=THEME['bg'])
        self.notebook.add(self.tab_large, text="   🐘 大文件搜索   ")
        self.setup_large_tab()

        self.tab_duplicate = tk.Frame(self.notebook, bg=THEME['bg'])
        self.notebook.add(self.tab_duplicate, text="   🔄 重复文件   ")
        self.setup_duplicate_tab()

        self.tab_empty = tk.Frame(self.notebook, bg=THEME['bg'])
        self.notebook.add(self.tab_empty, text="   📁 空文件夹   ")
        self.setup_empty_folder_tab()

        self.tab_startup = tk.Frame(self.notebook, bg=THEME['bg'])
        self.notebook.add(self.tab_startup, text="   🚀 启动项管理   ")
        self.setup_startup_tab()

        self.tab_uninstall = tk.Frame(self.notebook, bg=THEME['bg'])
        self.notebook.add(self.tab_uninstall, text="   📦 程序卸载   ")
        self.setup_uninstall_tab()

        self.tab_disk = tk.Frame(self.notebook, bg=THEME['bg'])
        self.notebook.add(self.tab_disk, text="   🔧 磁盘分析   ")
        self.setup_disk_tab()

        # 底部进度
        self.progress = ttk.Progressbar(self.root, orient="horizontal", mode="determinate")
        self.progress.pack(fill="x", padx=10, pady=5)
        self.lbl_status = tk.Label(self.root, text="准备就绪", fg=THEME['fg_secondary'], anchor="w", bg=THEME['bg'])
        self.lbl_status.pack(fill="x", padx=15, pady=(0, 5))

        # 历史记录显示
        self.lbl_history = tk.Label(self.root, text="", fg=THEME['fg_secondary'],
                                   bg=THEME['bg'], anchor="w", font=("Microsoft YaHei", 9))
        self.lbl_history.pack(fill="x", padx=15, pady=(0, 5))

        # 右键菜单
        self.context_menu = tk.Menu(self.root, tearoff=0, bg=THEME['tree_bg'], fg=THEME['tree_fg'])
        self.context_menu.add_command(label="📂 打开所在文件夹", command=self.open_selected_folder)
        self.context_menu.add_command(label="❌ 删除文件", command=self.delete_selected)

    # ================= 历史记录 =================
    def on_drive_changed(self, event):
        """盘符改变时的处理"""
        selected = self.selected_drive.get()
        drive = selected + '\\'
        if not os.path.exists(drive):
            messagebox.showwarning("警告", f"磁盘 {selected} 不存在或无法访问！")
            return
        # 更新大文件搜索的默认路径
        if hasattr(self, 'entry_path'):
            self.entry_path.delete(0, tk.END)
            self.entry_path.insert(0, drive)
        self.current_drive = selected

    def update_history_display(self):
        """更新历史记录显示"""
        if not self.history:
            self.lbl_history.config(text="")
            return

        drive = self.selected_drive.get()
        last_record = self.history.get(drive)
        total, _, used = get_disk_usage(drive + '\\')

        if last_record:
            last_cleaned = last_record.get('last_cleaned', 0)
            last_scanned = last_record.get('last_scanned', 0)
            last_date = last_record.get('date', '未知')

            if last_scanned > 0:
                ratio = (last_cleaned / last_scanned * 100) if last_scanned > 0 else 0
                self.lbl_history.config(
                    text=f"📊 上次扫描: {last_scanned} MB → 清理: {last_cleaned} MB ({ratio:.0f}%)| 当前: 已用 {used:.1f}/{total:.1f} GB | {last_date}"
                )
            else:
                self.lbl_history.config(
                    text=f"📊 上次清理: {last_cleaned} MB | 当前: 已用 {used:.1f}/{total:.1f} GB | {last_date}"
                )
        else:
            self.lbl_history.config(text=f"📊 当前: 已用 {used:.1f}/{total:.1f} GB")

    def add_clean_history(self, drive, cleaned_size, scanned_size=0):
        """添加清理历史记录"""
        if drive not in self.history:
            self.history[drive] = {}
        self.history[drive]['last_cleaned'] = cleaned_size
        self.history[drive]['last_scanned'] = scanned_size
        self.history[drive]['date'] = time.strftime("%Y-%m-%d %H:%M")
        save_history(self.history)
        self.update_history_display()

    # ================= 关于对话框 =================
    def show_about(self):
        """显示关于对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("关于")
        dialog.geometry("400x350")
        dialog.configure(bg=THEME['bg'])
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        title = tk.Label(dialog, text="磁盘清理专家 V6.0",
                       font=("Microsoft YaHei", 16, "bold"),
                       bg=THEME['bg'], fg=THEME['fg'])
        title.pack(pady=(20, 10))

        author = tk.Label(dialog, text="作者: 你们喜爱的老王",
                        font=("Microsoft YaHei", 12),
                        bg=THEME['bg'], fg=THEME['fg'])
        author.pack(pady=5)

        bilibili_label = tk.Label(dialog, text="B站: https://space.bilibili.com/97727630",
                                font=("Microsoft YaHei", 11),
                                bg=THEME['bg'], fg=THEME['link_color'],
                                cursor="hand2")
        bilibili_label.pack(pady=5)
        bilibili_label.bind("<Button-1>", lambda e: webbrowser.open("https://space.bilibili.com/97727630"))

        tk.Frame(dialog, height=1, bg=THEME['border']).pack(fill="x", padx=20, pady=15)

        features = tk.Label(dialog, text="功能:\n• 智能扫描系统垃圾文件\n• 大文件快速定位\n• 重复文件检测\n• 空文件夹清理\n• 磁盘分析\n• 启动项管理\n• 程序卸载\n• 安全的回收站机制",
                          font=("Microsoft YaHei", 10),
                          bg=THEME['bg'], fg=THEME['fg_secondary'],
                          justify="left")
        features.pack(pady=10)

        tips = tk.Label(dialog, text="提示: 建议以管理员身份运行",
                       font=("Microsoft YaHei", 9),
                       bg=THEME['bg'], fg=THEME['fg_secondary'])
        tips.pack(pady=(10, 20))

        btn_close = tk.Button(dialog, text="关闭", command=dialog.destroy,
                            bg=THEME['button_bg'], fg=THEME['button_fg'],
                            font=("Microsoft YaHei", 10),
                            padx=20, pady=5)
        btn_close.pack(pady=(0, 20))

    # ================= 系统状态 =================
    def update_system_stats(self):
        try:
            mem_usage = self.sys_mon.get_memory_usage()
            cpu_usage = self.sys_mon.get_cpu_usage()
            disk_info = self.sys_mon.get_disk_info('C:')

            self.pb_mem['value'] = mem_usage
            self.lbl_mem.config(text=f"{mem_usage}%")

            self.pb_cpu['value'] = cpu_usage
            self.lbl_cpu.config(text=f"{cpu_usage}%")

            if disk_info['total'] > 0:
                disk_used_pct = int((disk_info['used'] / disk_info['total']) * 100)
                self.pb_disk['value'] = disk_used_pct
                free_gb = disk_info['free'] / (1024**3)
                self.lbl_disk.config(text=f"{disk_used_pct}% ({free_gb:.1f}GB可用)")

            if mem_usage > 90: self.lbl_mem.config(fg="red")
            else: self.lbl_mem.config(fg="black")
        except:
            pass
        self.root.after(1000, self.update_system_stats)

    def toggle_backup_ui(self):
        state = "normal" if self.enable_backup_var.get() else "disabled"
        self.entry_backup.config(state=state)
        self.btn_browse.config(state=state)

    def browse_backup_folder(self):
        path = filedialog.askdirectory()
        if path: self.backup_path_var.set(path)

    def stop_current_action(self):
        if self.is_working:
            self.stop_event = True
            self.lbl_status.config(text="正在停止，请稍候...")

    def show_context_menu(self, event, tree):
        item = tree.identify_row(event.y)
        if item:
            tree.selection_set(item)
            self.context_menu_target = tree
            self.context_menu.post(event.x_root, event.y_root)

    def open_selected_folder(self):
        tree = getattr(self, 'context_menu_target', None)
        if tree:
            selected = tree.selection()
            if selected:
                vals = tree.item(selected[0])['values']
                path = vals[3] if len(vals) > 3 else vals[-1]
                if os.path.isfile(path): path = os.path.dirname(path)
                if os.path.exists(path): os.startfile(path)

    def delete_selected(self):
        tree = getattr(self, 'context_menu_target', None)
        if tree:
            selected = tree.selection()
            if selected:
                if messagebox.askyesno("确认", "确定要删除选中的项目吗？"):
                    for item in selected:
                        vals = tree.item(item)['values']
                        path = vals[3] if len(vals) > 3 else vals[-1]
                        send_to_recycle_bin(path)
                    tree.delete(*selected)

    def on_check_click(self, event, tree):
        region = tree.identify("region", event.x, event.y)
        if region == "cell":
            col = tree.identify_column(event.x)
            if col == "#1":
                item = tree.identify_row(event.y)
                val = tree.item(item)['values']
                new_mark = "☑" if val[0] == "☐" else "☐"
                new_vals = list(val)
                new_vals[0] = new_mark
                tree.item(item, values=new_vals)

    # ================= 垃圾清理 =================
    def setup_clean_tab(self):
        af = tk.Frame(self.tab_clean, pady=5, bg=THEME['bg'])
        af.pack(fill="x")

        self.btn_scan_junk = tk.Button(af, text="🔍 扫描垃圾", command=self.start_junk_scan,
                                      bg=THEME['button_bg'], fg=THEME['button_fg'], padx=15)
        self.btn_scan_junk.pack(side="left", padx=5)
        self.btn_stop_junk = tk.Button(af, text="🛑 停止", command=self.stop_current_action,
                                      state="disabled", padx=10, bg=THEME['button_bg'], fg=THEME['button_fg'])
        self.btn_stop_junk.pack(side="left", padx=5)
        self.btn_clean_junk = tk.Button(af, text="🗑️ 清理选中", command=self.start_junk_clean,
                                       state="disabled", bg="#d32f2f", fg="white", padx=15)
        self.btn_clean_junk.pack(side="left", padx=20)

        # 全选/取消全选按钮
        self.btn_select_all = tk.Button(af, text="☑ 全选", command=self.select_all_junk, padx=10,
                                       bg=THEME['button_bg'], fg=THEME['button_fg'])
        self.btn_select_all.pack(side="left", padx=5)
        self.btn_deselect_all = tk.Button(af, text="☐ 取消", command=self.deselect_all_junk, padx=10,
                                        bg=THEME['fg_secondary'], fg=THEME['button_fg'])
        self.btn_deselect_all.pack(side="left", padx=5)

        cols = ("check", "risk", "category", "path", "size", "status")
        self.tree_junk = ttk.Treeview(self.tab_clean, columns=cols, show="headings")
        self.tree_junk.heading("check", text="选"); self.tree_junk.column("check", width=40, anchor="center")
        self.tree_junk.heading("risk", text="风险"); self.tree_junk.column("risk", width=60, anchor="center")
        self.tree_junk.heading("category", text="分类"); self.tree_junk.column("category", width=100, anchor="center")
        self.tree_junk.heading("path", text="路径"); self.tree_junk.column("path", width=450)
        self.tree_junk.heading("size", text="占用"); self.tree_junk.column("size", width=80, anchor="e")
        self.tree_junk.heading("status", text="状态"); self.tree_junk.column("status", width=80, anchor="center")

        self.tree_junk.tag_configure('safe', foreground='#2E7D32')
        self.tree_junk.tag_configure('warn', foreground='#E65100')
        self.tree_junk.tag_configure('danger', foreground='#D32F2F')

        scroll = ttk.Scrollbar(self.tab_clean, orient="vertical", command=self.tree_junk.yview)
        self.tree_junk.configure(yscroll=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree_junk.pack(fill="both", expand=True)

        self.tree_junk.bind("<Button-1>", lambda e: self.on_check_click(e, self.tree_junk))
        self.tree_junk.bind("<Button-3>", lambda e: self.show_context_menu(e, self.tree_junk))

    def start_junk_scan(self):
        if self.is_working: return
        self.is_working = True; self.stop_event = False
        self.btn_scan_junk.config(state="disabled"); self.btn_stop_junk.config(state="normal"); self.btn_clean_junk.config(state="disabled")
        current_drive = self.selected_drive.get()
        threading.Thread(target=self.run_junk_scan, args=(current_drive,), daemon=True).start()

    def run_junk_scan(self, drive=None):
        for item in self.tree_junk.get_children(): self.tree_junk.delete(item)
        self.progress['value'] = 0

        if drive is None:
            drive = self.selected_drive.get()

        windir = drive + '\\Windows'
        local_app = os.environ.get('LOCALAPPDATA', '') if drive == 'C:' else ''
        program_data = drive + '\\ProgramData'
        user_temp = os.environ.get('TEMP', '')
        app_data = os.environ.get('APPDATA', '')
        user_profile = os.environ.get('USERPROFILE', '')

        targets = []

        # 临时文件（所有盘）
        targets.append(("系统", "临时文件", drive + '\\Temp', False, "🟢 低"))
        if user_temp:
            targets.append(("系统", "用户临时", user_temp, False, "🟢 低"))

        # C盘特有
        if drive == 'C:':
            # 开发工具
            targets.append(("开发工具", "Pip 缓存", os.path.join(local_app, "pip", "Cache"), False, "🟢 低"))
            targets.append(("开发工具", "uv 缓存", os.path.join(local_app, "uv", "cache"), False, "🟢 低"))
            targets.append(("开发工具", "npm 缓存", os.path.join(app_data, "npm-cache"), False, "🟢 低"))
            targets.append(("开发工具", "yarn 缓存", os.path.join(local_app, "Yarn", "Cache"), False, "🟢 低"))

            # 聊天软件
            wechat_base = os.path.join(user_profile, "Documents", "WeChat Files") if user_profile else ""
            if wechat_base and os.path.exists(wechat_base):
                try:
                    for user in os.listdir(wechat_base):
                        wechat_cache = os.path.join(wechat_base, user, "Cache")
                        if os.path.exists(wechat_cache):
                            targets.append(("聊天软件", f"微信-{user}", wechat_cache, False, "🟢 低"))
                except: pass
            qq_cache = os.path.join(app_data, "Tencent", "QQ", "NTData", "Cache") if app_data else ""
            if qq_cache and os.path.exists(qq_cache):
                targets.append(("聊天软件", "QQ缓存", qq_cache, False, "🟢 低"))
            dingtalk_cache = os.path.join(app_data, "DingTalk", "Cache") if app_data else ""
            if dingtalk_cache and os.path.exists(dingtalk_cache):
                targets.append(("聊天软件", "钉钉缓存", dingtalk_cache, False, "🟢 低"))

            # IDE
            vscode_cache = os.path.join(app_data, "Code", "Cache") if app_data else ""
            if vscode_cache and os.path.exists(vscode_cache):
                targets.append(("IDE", "VSCode缓存", vscode_cache, False, "🟢 低"))
            jetbrains_base = os.path.join(app_data, "JetBrains") if app_data else ""
            if jetbrains_base and os.path.exists(jetbrains_base):
                try:
                    for ide in os.listdir(jetbrains_base):
                        ide_cache = os.path.join(jetbrains_base, ide, "Cache")
                        if os.path.exists(ide_cache):
                            targets.append(("IDE", f"JetBrains-{ide}", ide_cache, False, "🟢 低"))
                except: pass

            # 系统
            targets.append(("系统", "系统临时", os.path.join(windir, 'Temp'), False, "🟢 低"))
            targets.append(("系统", "用户临时", os.environ.get('TEMP', ''), False, "🟢 低"))
            targets.append(("系统", "错误报告", os.path.join(program_data, 'Microsoft/Windows/WER'), False, "🟢 低"))
            targets.append(("系统", "缩略图缓存", os.path.join(local_app, "Microsoft", "Windows", "Explorer"), False, "🟢 低"))

            # 浏览器
            targets.append(("浏览器", "Chrome缓存", os.path.join(local_app, r"Google\Chrome\User Data\Default\Cache\Cache_Data"), False, "🟢 低"))
            targets.append(("浏览器", "Edge缓存", os.path.join(local_app, r"Microsoft\Edge\User Data\Default\Cache\Cache_Data"), False, "🟢 低"))
            targets.append(("浏览器", "Firefox缓存", os.path.join(local_app, "Mozilla", "Firefox", "profiles"), False, "🟢 低"))

            # 高风险
            targets.append(("高风险", "Win更新包", os.path.join(windir, 'SoftwareDistribution', 'Download'), False, "🔴 高"))
            targets.append(("高风险", "预读取", os.path.join(windir, 'Prefetch'), False, "🔴 高"))
            targets.append(("日志", "系统日志", os.path.join(windir, 'Logs'), False, "🟡 中"))
        else:
            # 非系统盘：扫描用户目录
            user_home = drive + '\\Users'
            if os.path.exists(user_home):
                try:
                    for user in os.listdir(user_home):
                        user_path = os.path.join(user_home, user, 'AppData', 'Local', 'Temp')
                        if os.path.exists(user_path):
                            targets.append(("用户", f"{user}的临时", user_path, False, "🟢 低"))
                except: pass

        total = 0
        for i, (cat, name, path, df, risk) in enumerate(targets):
            if self.stop_event: break
            self.lbl_status.config(text=f"扫描中: {name}")
            if path and os.path.exists(path):
                sz = self.get_folder_size(path)
                if sz > 0:
                    tag = 'safe'
                    if "高" in risk: tag='danger'
                    elif "中" in risk: tag='warn'
                    self.tree_junk.insert("", "end", values=("☐", risk, cat, path, format_size(sz), "待清理"), tags=(tag,))
                    total += sz
            self.progress['value'] = (i+1)/len(targets)*100

        # 记录扫描大小
        self.last_scan_size = total
        self.finish_scan(f"扫描完成，发现 {format_size(total)}", self.btn_scan_junk, self.btn_stop_junk, self.btn_clean_junk)

    # ================= 大文件搜索 =================
    def setup_large_tab(self):
        cf = tk.Frame(self.tab_large, pady=5, bg=THEME['bg'])
        cf.pack(fill="x")
        tk.Label(cf, text="最小(MB):", bg=THEME['bg'], fg=THEME['fg']).pack(side="left")
        self.entry_size = tk.Entry(cf, width=6, bg=THEME['entry_bg'], fg=THEME['entry_fg']); self.entry_size.insert(0, "100"); self.entry_size.pack(side="left")
        tk.Label(cf, text="路径:", bg=THEME['bg'], fg=THEME['fg']).pack(side="left")
        self.entry_path = tk.Entry(cf, width=25, bg=THEME['entry_bg'], fg=THEME['entry_fg']); self.entry_path.insert(0, os.path.expanduser("~")); self.entry_path.pack(side="left")
        tk.Button(cf, text="...", command=lambda: self.select_search_path(), width=3, bg=THEME['button_bg'], fg=THEME['button_fg']).pack(side="left")
        self.btn_scan_large = tk.Button(cf, text="🔍 搜索", command=self.start_large_scan, bg=THEME['button_bg'], fg=THEME['button_fg'], padx=10)
        self.btn_scan_large.pack(side="left", padx=10)
        self.btn_stop_large = tk.Button(cf, text="🛑 停止", command=self.stop_current_action, state="disabled", padx=10, bg=THEME['button_bg'], fg=THEME['button_fg'])
        self.btn_stop_large.pack(side="left", padx=5)
        self.btn_clean_large = tk.Button(cf, text="🗑️ 删除", command=self.start_large_clean, state="disabled", bg="#d32f2f", fg="white", padx=10)
        self.btn_clean_large.pack(side="left", padx=5)

        # 全选/取消全选按钮
        self.btn_select_all_large = tk.Button(cf, text="☑ 全选", command=self.select_all_large, padx=10,
                                             bg=THEME['button_bg'], fg=THEME['button_fg'])
        self.btn_select_all_large.pack(side="left", padx=5)
        self.btn_deselect_all_large = tk.Button(cf, text="☐ 取消", command=self.deselect_all_large, padx=10,
                                                bg=THEME['fg_secondary'], fg=THEME['button_fg'])
        self.btn_deselect_all_large.pack(side="left", padx=5)

        cols = ("check", "risk", "name", "path", "size", "type")
        self.tree_large = ttk.Treeview(self.tab_large, columns=cols, show="headings")
        self.tree_large.heading("check", text="选"); self.tree_large.column("check", width=40, anchor="center")
        self.tree_large.heading("risk", text="风险"); self.tree_large.column("risk", width=60, anchor="center")
        self.tree_large.heading("name", text="文件名"); self.tree_large.column("name", width=180)
        self.tree_large.heading("path", text="完整路径"); self.tree_large.column("path", width=400)
        self.tree_large.heading("size", text="大小"); self.tree_large.column("size", width=80, anchor="e")
        self.tree_large.heading("type", text="类型"); self.tree_large.column("type", width=60, anchor="center")

        self.tree_large.tag_configure('safe', foreground='#2E7D32')
        self.tree_large.tag_configure('warn', foreground='#E65100')
        self.tree_large.tag_configure('danger', foreground='#D32F2F')

        scroll = ttk.Scrollbar(self.tab_large, orient="vertical", command=self.tree_large.yview)
        self.tree_large.configure(yscroll=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree_large.pack(fill="both", expand=True)
        self.tree_large.bind("<Button-1>", lambda e: self.on_check_click(e, self.tree_large))
        self.tree_large.bind("<Button-3>", lambda e: self.show_context_menu(e, self.tree_large))

    def select_search_path(self):
        p = filedialog.askdirectory()
        if p: self.entry_path.delete(0, tk.END); self.entry_path.insert(0, p)

    def start_large_scan(self):
        if self.is_working: return
        try: limit = float(self.entry_size.get())
        except: return
        path = self.entry_path.get()
        self.is_working = True; self.stop_event = False
        self.btn_scan_large.config(state="disabled"); self.btn_stop_large.config(state="normal"); self.btn_clean_large.config(state="disabled")
        threading.Thread(target=self.run_large_scan, args=(path, limit), daemon=True).start()

    def run_large_scan(self, start_path, limit_mb):
        for item in self.tree_large.get_children(): self.tree_large.delete(item)
        self.progress['value'] = 0; self.progress.configure(mode='indeterminate'); self.progress.start(10)
        limit_b = limit_mb * 1024 * 1024
        count = 0

        try:
            for root, dirs, files in os.walk(start_path):
                if self.stop_event: break
                if "Windows" in root and "WinSxS" in root: continue
                for name in files:
                    if self.stop_event: break
                    try:
                        fp = os.path.join(root, name)
                        sz = os.path.getsize(fp)
                        if sz > limit_b:
                            ext = os.path.splitext(name)[1].lower()
                            risk = "🟢 低"
                            tag = 'safe'
                            if r"c:\windows" in fp.lower() or ext in ['.sys','.dll','.exe','.vhdx']: risk="🔴 高"; tag='danger'
                            elif ext in ['.msi','.iso','.wim']: risk="🟡 中"; tag='warn'

                            self.tree_large.insert("", "end", values=("☐", risk, name, fp, format_size(sz), ext), tags=(tag,))
                            count += 1
                    except: pass
        except: pass

        self.progress.stop(); self.progress.configure(mode='determinate'); self.progress['value'] = 100
        self.finish_scan(f"扫描完成，找到 {count} 个文件", self.btn_scan_large, self.btn_stop_large, self.btn_clean_large)

    # ================= 重复文件 =================
    def setup_duplicate_tab(self):
        cf = tk.Frame(self.tab_duplicate, pady=5)
        cf.pack(fill="x")

        tk.Label(cf, text="最小(MB):").pack(side="left")
        self.entry_dup_size = tk.Entry(cf, width=6); self.entry_dup_size.insert(0, "10"); self.entry_dup_size.pack(side="left")
        tk.Label(cf, text="路径:").pack(side="left")
        self.entry_dup_path = tk.Entry(cf, width=25); self.entry_dup_path.insert(0, os.path.expanduser("~")); self.entry_dup_path.pack(side="left")
        tk.Button(cf, text="...", command=lambda: self.select_dup_path(), width=3, bg=THEME['button_bg'], fg=THEME['button_fg']).pack(side="left")
        self.btn_scan_dup = tk.Button(cf, text="🔍 查找重复", command=self.start_duplicate_scan, bg=THEME['button_bg'], fg=THEME['button_fg'], padx=10)
        self.btn_scan_dup.pack(side="left", padx=10)
        self.btn_stop_dup = tk.Button(cf, text="🛑 停止", command=self.stop_current_action, state="disabled", padx=10, bg=THEME['button_bg'], fg=THEME['button_fg'])
        self.btn_stop_dup.pack(side="left", padx=5)
        self.btn_clean_dup = tk.Button(cf, text="🗑️ 删除选中", command=self.start_duplicate_clean, state="disabled", bg="#d32f2f", fg="white", padx=10)
        self.btn_clean_dup.pack(side="left")

        cols = ("check", "name", "size", "path", "hash")
        self.tree_dup = ttk.Treeview(self.tab_duplicate, columns=cols, show="headings")
        self.tree_dup.heading("check", text="选"); self.tree_dup.column("check", width=40, anchor="center")
        self.tree_dup.heading("name", text="文件名"); self.tree_dup.column("name", width=200)
        self.tree_dup.heading("size", text="大小"); self.tree_dup.column("size", width=80, anchor="e")
        self.tree_dup.heading("path", text="路径"); self.tree_dup.column("path", width=450)
        self.tree_dup.heading("hash", text="哈希值"); self.tree_dup.column("hash", width=120)

        self.tree_dup.tag_configure('duplicate', foreground='#E65100')
        self.tree_dup.tag_configure('original', foreground='#2E7D32')

        scroll = ttk.Scrollbar(self.tab_duplicate, orient="vertical", command=self.tree_dup.yview)
        self.tree_dup.configure(yscroll=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree_dup.pack(fill="both", expand=True)
        self.tree_dup.bind("<Button-1>", lambda e: self.on_check_click(e, self.tree_dup))
        self.tree_dup.bind("<Button-3>", lambda e: self.show_context_menu(e, self.tree_dup))

    def select_dup_path(self):
        p = filedialog.askdirectory()
        if p: self.entry_dup_path.delete(0, tk.END); self.entry_dup_path.insert(0, p)

    def start_duplicate_scan(self):
        if self.is_working: return
        try: limit = float(self.entry_dup_size.get())
        except: return
        path = self.entry_dup_path.get()
        self.is_working = True; self.stop_event = False
        self.btn_scan_dup.config(state="disabled"); self.btn_stop_dup.config(state="normal"); self.btn_clean_dup.config(state="disabled")
        threading.Thread(target=self.run_duplicate_scan, args=(path, limit), daemon=True).start()

    def run_duplicate_scan(self, start_path, limit_mb):
        for item in self.tree_dup.get_children(): self.tree_dup.delete(item)
        self.progress['value'] = 0; self.progress.configure(mode='indeterminate'); self.progress.start(10)

        limit_b = limit_mb * 1024 * 1024
        size_groups = {}

        # 第一步：按大小分组
        self.lbl_status.config(text="正在扫描文件...")
        try:
            for root, dirs, files in os.walk(start_path):
                if self.stop_event: break
                for name in files:
                    if self.stop_event: break
                    try:
                        fp = os.path.join(root, name)
                        sz = os.path.getsize(fp)
                        if sz >= limit_b:
                            if sz not in size_groups: size_groups[sz] = []
                            size_groups[sz].append(fp)
                    except: pass
        except: pass

        # 第二步：计算哈希
        hash_groups = {}
        total_files = sum(len(v) for v in size_groups.values() if len(v) > 1)
        processed = 0

        self.lbl_status.config(text="正在计算哈希值...")
        for size, paths in size_groups.items():
            if len(paths) < 2: continue
            for fp in paths:
                if self.stop_event: break
                try:
                    h = self.get_file_hash(fp)
                    if h:
                        key = (size, h)
                        if key not in hash_groups: hash_groups[key] = []
                        hash_groups[key].append(fp)
                except: pass
                processed += 1

        # 显示结果
        count = 0
        for (size, h), paths in hash_groups.items():
            if len(paths) > 1:
                for i, fp in enumerate(paths):
                    tag = 'original' if i == 0 else 'duplicate'
                    check = "☐" if i > 0 else "☐"
                    self.tree_dup.insert("", "end", values=(check, os.path.basename(fp), format_size(size), fp, h[:12]+"..."), tags=(tag,))
                    count += 1

        self.progress.stop(); self.progress.configure(mode='determinate'); self.progress['value'] = 100
        self.finish_scan(f"扫描完成，找到 {count} 个重复文件", self.btn_scan_dup, self.btn_stop_dup, self.btn_clean_dup)

    def get_file_hash(self, fp):
        try:
            h = hashlib.md5()
            with open(fp, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    h.update(chunk)
            return h.hexdigest()
        except: return None

    def start_duplicate_clean(self):
        self._do_clean(self.tree_dup, "duplicate")

    # ================= 空文件夹 =================
    def setup_empty_folder_tab(self):
        cf = tk.Frame(self.tab_empty, pady=5)
        cf.pack(fill="x")

        tk.Label(cf, text="路径:").pack(side="left")
        self.entry_empty_path = tk.Entry(cf, width=30); self.entry_empty_path.insert(0, os.path.expanduser("~")); self.entry_empty_path.pack(side="left")
        tk.Button(cf, text="...", command=lambda: self.select_empty_path(), width=3, bg=THEME['button_bg'], fg=THEME['button_fg']).pack(side="left")
        self.btn_scan_empty = tk.Button(cf, text="🔍 查找空文件夹", command=self.start_empty_scan, bg=THEME['button_bg'], fg=THEME['button_fg'], padx=10)
        self.btn_scan_empty.pack(side="left", padx=10)
        self.btn_stop_empty = tk.Button(cf, text="🛑 停止", command=self.stop_current_action, state="disabled", padx=10, bg=THEME['button_bg'], fg=THEME['button_fg'])
        self.btn_stop_empty.pack(side="left", padx=5)
        self.btn_clean_empty = tk.Button(cf, text="🗑️ 删除选中", command=self.start_empty_clean, state="disabled", bg="#d32f2f", fg="white", padx=10)
        self.btn_clean_empty.pack(side="left")

        cols = ("check", "name", "path")
        self.tree_empty = ttk.Treeview(self.tab_empty, columns=cols, show="headings")
        self.tree_empty.heading("check", text="选"); self.tree_empty.column("check", width=40, anchor="center")
        self.tree_empty.heading("name", text="文件夹名"); self.tree_empty.column("name", width=200)
        self.tree_empty.heading("path", text="路径"); self.tree_empty.column("path", width=600)

        scroll = ttk.Scrollbar(self.tab_empty, orient="vertical", command=self.tree_empty.yview)
        self.tree_empty.configure(yscroll=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree_empty.pack(fill="both", expand=True)
        self.tree_empty.bind("<Button-1>", lambda e: self.on_check_click(e, self.tree_empty))
        self.tree_empty.bind("<Button-3>", lambda e: self.show_context_menu(e, self.tree_empty))

    def select_empty_path(self):
        p = filedialog.askdirectory()
        if p: self.entry_empty_path.delete(0, tk.END); self.entry_empty_path.insert(0, p)

    def start_empty_scan(self):
        if self.is_working: return
        path = self.entry_empty_path.get()
        self.is_working = True; self.stop_event = False
        self.btn_scan_empty.config(state="disabled"); self.btn_stop_empty.config(state="normal"); self.btn_clean_empty.config(state="disabled")
        threading.Thread(target=self.run_empty_scan, args=(path,), daemon=True).start()

    def run_empty_scan(self, start_path):
        for item in self.tree_empty.get_children(): self.tree_empty.delete(item)
        self.progress['value'] = 0; self.progress.configure(mode='indeterminate'); self.progress.start(10)
        count = 0

        try:
            for root, dirs, files in os.walk(start_path, topdown=False):
                if self.stop_event: break
                for d in dirs:
                    dp = os.path.join(root, d)
                    try:
                        if not os.listdir(dp):
                            self.tree_empty.insert("", "end", values=("☑", d, dp))
                            count += 1
                    except: pass
        except: pass

        self.progress.stop(); self.progress.configure(mode='determinate'); self.progress['value'] = 100
        self.finish_scan(f"扫描完成，找到 {count} 个空文件夹", self.btn_scan_empty, self.btn_stop_empty, self.btn_clean_empty)

    def start_empty_clean(self):
        self._do_clean(self.tree_empty, "empty")

    # ================= 磁盘分析 =================
    def setup_disk_tab(self):
        # 显示"正在开发中"
        lbl = tk.Label(self.tab_disk, text="🔧 磁盘分析功能正在开发中...\n\n敬请期待！",
                      font=("Microsoft YaHei", 14), fg="#888888", bg=THEME['bg'])
        lbl.pack(expand=True)

    # ================= 启动项管理 =================
    def setup_startup_tab(self):
        cf = tk.Frame(self.tab_startup, pady=5)
        cf.pack(fill="x")

        self.btn_refresh_startup = tk.Button(cf, text="🔄 刷新", command=self.load_startup_items, padx=10, bg=THEME['button_bg'], fg=THEME['button_fg'])
        self.btn_refresh_startup.pack(side="left", padx=5)
        self.btn_disable_startup = tk.Button(cf, text="⏸ 禁用", command=self.disable_startup_item, state="disabled", padx=10, bg=THEME['button_bg'], fg=THEME['button_fg'])
        self.btn_disable_startup.pack(side="left", padx=5)
        self.btn_enable_startup = tk.Button(cf, text="▶ 启用", command=self.enable_startup_item, state="disabled", padx=10, bg=THEME['button_bg'], fg=THEME['button_fg'])
        self.btn_enable_startup.pack(side="left", padx=5)

        cols = ("name", "path", "status", "location")
        self.tree_startup = ttk.Treeview(self.tab_startup, columns=cols, show="headings")
        self.tree_startup.heading("name", text="程序名称"); self.tree_startup.column("name", width=180)
        self.tree_startup.heading("path", text="启动路径"); self.tree_startup.column("path", width=400)
        self.tree_startup.heading("status", text="状态"); self.tree_startup.column("status", width=80, anchor="center")
        self.tree_startup.heading("location", text="位置"); self.tree_startup.column("location", width=150)

        self.tree_startup.tag_configure('enabled', foreground='#2E7D32')
        self.tree_startup.tag_configure('disabled', foreground='#9E9E9E')

        scroll = ttk.Scrollbar(self.tab_startup, orient="vertical", command=self.tree_startup.yview)
        self.tree_startup.configure(yscroll=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree_startup.pack(fill="both", expand=True)

        self.tree_startup.bind("<<TreeviewSelect>>", self.on_startup_select)

        # 加载启动项
        self.load_startup_items()

    def load_startup_items(self):
        for item in self.tree_startup.get_children(): self.tree_startup.delete(item)

        # 从注册表读取启动项
        locations = [
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
        ]

        for hkey, subkey in locations:
            try:
                key = winreg.OpenKey(hkey, subkey)
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, i)
                        loc = "HKCU" if hkey == winreg.HKEY_CURRENT_USER else "HKLM"
                        self.tree_startup.insert("", "end", values=(name, value, "已启用", loc), tags=('enabled',))
                        i += 1
                    except: break
                winreg.CloseKey(key)
            except: pass

        self.btn_disable_startup.config(state="normal")
        self.btn_enable_startup.config(state="normal")

    def on_startup_select(self, event):
        pass

    def disable_startup_item(self):
        selected = self.tree_startup.selection()
        if not selected: return
        messagebox.showinfo("提示", "此功能需要管理员权限修改注册表，建议手动禁用启动项")

    def enable_startup_item(self):
        selected = self.tree_startup.selection()
        if not selected: return
        messagebox.showinfo("提示", "此功能需要管理员权限修改注册表，建议手动启用启动项")

    # ================= 程序卸载 =================
    def setup_uninstall_tab(self):
        cf = tk.Frame(self.tab_uninstall, pady=5)
        cf.pack(fill="x")

        self.btn_refresh_uninstall = tk.Button(cf, text="🔄 刷新", command=self.load_uninstall_items, padx=10, bg=THEME['button_bg'], fg=THEME['button_fg'])
        self.btn_refresh_uninstall.pack(side="left", padx=5)

        self.btn_uninstall = tk.Button(cf, text="🗑️ 卸载选中", command=self.uninstall_selected, padx=10, bg=THEME['button_bg'], fg=THEME['button_fg'])
        self.btn_uninstall.pack(side="left", padx=5)

        tk.Button(cf, text="🔗 控制面板", command=lambda: os.system("control appwiz.cpl"), padx=10, bg=THEME['button_bg'], fg=THEME['button_fg']).pack(side="left", padx=5)

        cols = ("name", "publisher", "size", "date")
        self.tree_uninstall = ttk.Treeview(self.tab_uninstall, columns=cols, show="headings")
        self.tree_uninstall.heading("name", text="程序名称"); self.tree_uninstall.column("name", width=250)
        self.tree_uninstall.heading("publisher", text="发布者"); self.tree_uninstall.column("publisher", width=180)
        self.tree_uninstall.heading("size", text="大小"); self.tree_uninstall.column("size", width=100, anchor="e")
        self.tree_uninstall.heading("date", text="安装日期"); self.tree_uninstall.column("date", width=120)

        scroll = ttk.Scrollbar(self.tab_uninstall, orient="vertical", command=self.tree_uninstall.yview)
        self.tree_uninstall.configure(yscroll=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree_uninstall.pack(fill="both", expand=True)

        self.load_uninstall_items()

    def load_uninstall_items(self):
        for item in self.tree_uninstall.get_children(): self.tree_uninstall.delete(item)

        self.uninstall_paths = {}  # 存储程序名称对应的卸载路径

        keys = [
            r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
            r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        ]

        for subkey in keys:
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey)
                i = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        subkey_path = f"{subkey}\\{subkey_name}"
                        try:
                            sk = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey_path)
                            name = publisher = size = date = ""
                            try:
                                name = winreg.QueryValueEx(sk, "DisplayName")[0]
                            except: pass
                            try:
                                publisher = winreg.QueryValueEx(sk, "Publisher")[0]
                            except: pass
                            try:
                                size = winreg.QueryValueEx(sk, "EstimatedSize")[0]
                                size = f"{size} KB"
                            except: pass
                            try:
                                date = winreg.QueryValueEx(sk, "InstallDate")[0]
                                if len(date) == 8:
                                    date = f"{date[:4]}-{date[4:6]}-{date[6:]}"
                            except: pass

                            if name:
                                item_id = self.tree_uninstall.insert("", "end", values=(name, publisher, size, date))
                                self.uninstall_paths[item_id] = subkey_path
                            winreg.CloseKey(sk)
                        except: pass
                        i += 1
                    except: break
                winreg.CloseKey(key)
            except: pass

    def uninstall_selected(self):
        """卸载选中的程序"""
        self.log("=" * 30)
        self.log("开始卸载流程")

        selection = self.tree_uninstall.selection()
        if not selection:
            self.log("错误: 未选中任何程序")
            messagebox.showwarning("提示", "请先选择一个程序")
            return

        item = selection[0]
        values = self.tree_uninstall.item(item, "values")
        program_name = values[0]
        subkey_path = self.uninstall_paths.get(item)

        self.log(f"选中程序: {program_name}")
        self.log(f"注册表路径: {subkey_path}")

        if not subkey_path:
            self.log("错误: 无法获取注册表路径")
            messagebox.showerror("错误", "无法获取卸载信息")
            return

        # 尝试获取卸载命令行
        uninstall_cmd = ""
        try:
            self.log(f"尝试打开注册表: HKEY_LOCAL_MACHINE\\{subkey_path}")
            sk = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey_path)
            try:
                uninstall_cmd = winreg.QueryValueEx(sk, "UninstallString")[0]
                self.log(f"UninstallString: {uninstall_cmd}")
            except Exception as e:
                self.log(f"UninstallString 获取失败: {e}")
                try:
                    uninstall_cmd = winreg.QueryValueEx(sk, "QuietUninstallString")[0]
                    self.log(f"QuietUninstallString: {uninstall_cmd}")
                except Exception as e2:
                    self.log(f"QuietUninstallString 获取失败: {e2}")
                    pass
            winreg.CloseKey(sk)
        except Exception as e:
            self.log(f"打开注册表失败: {e}")

        if not uninstall_cmd:
            self.log("错误: 无法找到卸载命令")
            messagebox.showerror("错误", "无法找到卸载程序")
            return

        # 确认卸载
        if not messagebox.askyesno("确认卸载", f"确定要卸载 [{program_name}] 吗？\n\n此操作不可恢复！"):
            self.log("用户取消卸载")
            return

        self.log(f"执行卸载命令: {uninstall_cmd}")
        self.lbl_status.config(text=f"正在卸载 {program_name}...")

        try:
            self.log("使用 os.system 执行卸载命令")

            # 使用 cmd /c 执行，带引号的完整命令
            if uninstall_cmd.lower().startswith("msiexec"):
                self.log("使用 msiexec 卸载")
                result = os.system(f'cmd /c "{uninstall_cmd}"')
                self.log(f"msiexec 返回码: {result}")
            else:
                self.log("使用普通命令卸载")
                # 直接执行整个命令字符串
                result = os.system(f'cmd /c "{uninstall_cmd}"')
                self.log(f"命令返回码: {result}")

            self.log(f"卸载完成，返回码: {result}")

            # 根据返回码判断是否成功
            if result == 0:
                self.root.after(100, lambda: self._refresh_uninstall_list_safe(program_name, True))
            else:
                self.root.after(100, lambda: self._refresh_uninstall_list_safe(program_name, False, result))

        except Exception as e:
            self.log(f"执行卸载命令异常: {type(e).__name__}: {e}")
            import traceback
            self.log(f"详细堆栈: {traceback.format_exc()}")
            self.root.after(100, lambda: self._refresh_uninstall_list_safe(program_name, False, -1))

    def _refresh_uninstall_list_safe(self, program_name, success=True, return_code=0):
        """安全刷新卸载列表"""
        try:
            self.log(f"刷新卸载列表: success={success}, return_code={return_code}")
            self.load_uninstall_items()
            if success:
                try:
                    messagebox.showinfo("完成", f"{program_name} 已卸载")
                except Exception as e:
                    self.log(f"showinfo异常: {type(e).__name__}: {e}")
                self.lbl_status.config(text="卸载完成")
            else:
                try:
                    messagebox.showwarning("警告", f"卸载命令执行失败 (返回码: {return_code})\n请手动检查是否卸载成功")
                except:
                    pass
                self.lbl_status.config(text="卸载失败")
        except Exception as e:
            self.log(f"刷新列表异常: {type(e).__name__}: {e}")
            import traceback
            self.log(f"详细堆栈: {traceback.format_exc()}")
            try:
                messagebox.showwarning("警告", "卸载完成，但刷新列表失败")
            except:
                pass

    # ================= 通用清理逻辑 =================
    def start_junk_clean(self): self._do_clean(self.tree_junk, "junk")
    def start_large_clean(self): self._do_clean(self.tree_large, "large")

    def _do_clean(self, tree, mode):
        items = []
        for i in tree.get_children():
            v = tree.item(i)['values']
            if v[0] == "☑":
                path_idx = 3 if len(v) > 3 else 2
                items.append((i, v[path_idx]))
        if not items: messagebox.showinfo("提示", "未勾选项目"); return

        bk = None
        if self.enable_backup_var.get():
            bk = self.backup_path_var.get()
            if not bk or not os.path.exists(bk): messagebox.showerror("错误", "备份路径无效"); return
            if not messagebox.askyesno("备份", "备份可能耗时，继续？"): return

        if not messagebox.askyesno("确认", f"删除 {len(items)} 个项目到回收站？"): return

        self.is_working = True
        threading.Thread(target=self.run_clean, args=(tree, items, bk, mode), daemon=True).start()

    def run_clean(self, tree, items, bk, mode):
        tot = len(items)
        cleaned_size = 0
        drive = self.selected_drive.get()

        for i, (iid, path) in enumerate(items):
            self.lbl_status.config(text=f"清理: {path}")
            try:
                # 获取清理前的大小
                if os.path.exists(path):
                    if os.path.isdir(path):
                        size_before = self.get_folder_size(path)
                    else:
                        size_before = os.path.getsize(path)
                else:
                    size_before = 0

                if bk:
                    ts = time.strftime("%H%M%S")
                    dst = os.path.join(bk, os.path.basename(path) + "_" + ts)
                    if os.path.isfile(path):
                        try: shutil.copy2(path, dst)
                        except: pass
                    else:
                        try: shutil.copytree(path, dst, dirs_exist_ok=True)
                        except: pass

                if mode == "large" or mode == "duplicate":
                    send_to_recycle_bin(path)
                elif mode == "empty":
                    try: os.rmdir(path)
                    except: pass
                else:
                    if os.path.isdir(path):
                        try:
                            for e in os.scandir(path):
                                send_to_recycle_bin(e.path)
                        except: pass
                    else:
                        send_to_recycle_bin(path)

                cleaned_size += size_before
                tree.delete(iid)
            except: pass
            self.progress['value'] = (i+1)/tot*100

        # 保存清理历史
        cleaned_mb = int(cleaned_size / (1024 * 1024))
        scanned_mb = int(self.last_scan_size / (1024 * 1024))
        self.root.after(0, lambda: self.add_clean_history(drive, cleaned_mb, scanned_mb))

        self.lbl_status.config(text=f"清理完成，共清理 {cleaned_mb} MB")
        self.is_working = False
        messagebox.showinfo("完成", f"清理结束，文件已移入回收站。\n本次清理: {cleaned_mb} MB")

    def finish_scan(self, msg, btn_scan, btn_stop, btn_clean):
        if self.stop_event: msg = "扫描已停止"
        self.lbl_status.config(text=msg)
        self.is_working = False
        btn_scan.config(state="normal")
        btn_stop.config(state="disabled")
        if btn_clean: btn_clean.config(state="normal")

    # ================= 全选/取消全选 =================
    def select_all_junk(self):
        """全选所有垃圾清理项目"""
        for item in self.tree_junk.get_children():
            val = list(self.tree_junk.item(item)['values'])
            val[0] = "☑"
            self.tree_junk.item(item, values=val)

    def deselect_all_junk(self):
        """取消全选所有垃圾清理项目"""
        for item in self.tree_junk.get_children():
            val = list(self.tree_junk.item(item)['values'])
            val[0] = "☐"
            self.tree_junk.item(item, values=val)

    def select_all_large(self):
        """全选所有大文件项目"""
        for item in self.tree_large.get_children():
            val = list(self.tree_large.item(item)['values'])
            val[0] = "☑"
            self.tree_large.item(item, values=val)

    def deselect_all_large(self):
        """取消全选所有大文件项目"""
        for item in self.tree_large.get_children():
            val = list(self.tree_large.item(item)['values'])
            val[0] = "☐"
            self.tree_large.item(item, values=val)

    def get_folder_size(self, path):
        t = 0
        try:
            with os.scandir(path) as it:
                for e in it:
                    if self.stop_event: break
                    try:
                        if e.is_file(): t += e.stat().st_size
                        elif e.is_dir(): t += self.get_folder_size(e.path)
                    except: pass
        except: pass
        return t

if __name__ == "__main__":
    import sys
    import traceback

    # 全局异常捕获
    def except_hook(exc_type, exc_value, exc_traceback):
        error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        print(f"[全局异常] {exc_type.__name__}: {exc_value}")
        print(error_msg)
        # 写入日志
        try:
            log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
            log_file = os.path.join(log_dir, f"error_{time.strftime('%Y%m%d_%H%M%S')}.log")
            with open(log_file, "w", encoding="utf-8") as f:
                f.write(error_msg)
        except:
            pass

    sys.excepthook = except_hook

    root = tk.Tk()
    try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except: pass

    app = MonitorCleanerApp(root)
    root.mainloop()
