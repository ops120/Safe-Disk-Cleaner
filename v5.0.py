import os
import shutil
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import ctypes
from ctypes import wintypes
import time

# ==========================================
# Windows API 定义 (Shell & Kernel)
# ==========================================
# 1. 回收站相关
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

# 2. 内存相关
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

# 3. CPU 相关
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
# 系统监控类 (纯 WinAPI 实现，无需 psutil)
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
        self.root.title("Win10 C盘深度清理专家 V5.0 (实时监控 + 风险预警)")
        self.root.geometry("1000x800")
        
        if not is_admin():
            messagebox.showwarning("权限警告", "建议以管理员身份运行，否则无法准确判断系统文件风险！")

        # 核心变量
        self.backup_path_var = tk.StringVar()
        self.enable_backup_var = tk.IntVar(value=0)
        self.is_working = False
        self.stop_event = False
        self.sys_mon = SystemMonitor()

        self.setup_ui()
        
        # 启动定时器刷新系统状态
        self.update_system_stats()

    def setup_ui(self):
        # --- 0. 顶部仪表盘 (Dashboard) ---
        dash_frame = tk.LabelFrame(self.root, text="📊 系统实时状态", padx=10, pady=5)
        dash_frame.pack(fill="x", padx=10, pady=5)
        
        # CPU 区域
        cpu_frame = tk.Frame(dash_frame)
        cpu_frame.pack(side="left", fill="x", expand=True, padx=10)
        tk.Label(cpu_frame, text="CPU:", font=("Arial", 9, "bold")).pack(side="left")
        self.pb_cpu = ttk.Progressbar(cpu_frame, orient="horizontal", mode="determinate", length=200)
        self.pb_cpu.pack(side="left", padx=5)
        self.lbl_cpu = tk.Label(cpu_frame, text="0%", width=5)
        self.lbl_cpu.pack(side="left")

        # 内存 区域
        mem_frame = tk.Frame(dash_frame)
        mem_frame.pack(side="left", fill="x", expand=True, padx=10)
        tk.Label(mem_frame, text="RAM:", font=("Arial", 9, "bold")).pack(side="left")
        self.pb_mem = ttk.Progressbar(mem_frame, orient="horizontal", mode="determinate", length=200)
        self.pb_mem.pack(side="left", padx=5)
        self.lbl_mem = tk.Label(mem_frame, text="0%", width=5)
        self.lbl_mem.pack(side="left")

        # --- 1. 备份设置 ---
        bk_frame = tk.LabelFrame(self.root, text="🛡️ 安全备份设置", padx=10, pady=5)
        bk_frame.pack(fill="x", padx=10, pady=5)
        
        tk.Checkbutton(bk_frame, text="删除前备份文件到:", variable=self.enable_backup_var, command=self.toggle_backup_ui).pack(side="left")
        self.entry_backup = tk.Entry(bk_frame, textvariable=self.backup_path_var, state="disabled", width=50)
        self.entry_backup.pack(side="left", padx=5)
        self.btn_browse = tk.Button(bk_frame, text="📂 选择...", command=self.browse_backup_folder, state="disabled")
        self.btn_browse.pack(side="left")

        # --- 2. 标签页 ---
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=5)

        self.tab_clean = tk.Frame(self.notebook)
        self.notebook.add(self.tab_clean, text="   🧹 垃圾清理   ")
        self.setup_clean_tab()

        self.tab_large = tk.Frame(self.notebook)
        self.notebook.add(self.tab_large, text="   🐘 大文件搜索   ")
        self.setup_large_tab()

        # --- 3. 底部进度 ---
        self.progress = ttk.Progressbar(self.root, orient="horizontal", mode="determinate")
        self.progress.pack(fill="x", padx=10, pady=5)
        self.lbl_status = tk.Label(self.root, text="准备就绪", fg="gray", anchor="w")
        self.lbl_status.pack(fill="x", padx=15, pady=(0, 5))

        # 右键菜单
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="📂 打开所在文件夹", command=self.open_selected_folder)

    # ---------------- 功能逻辑 ----------------

    def update_system_stats(self):
        """每秒更新CPU和内存显示"""
        try:
            # 获取数据
            mem_usage = self.sys_mon.get_memory_usage()
            cpu_usage = self.sys_mon.get_cpu_usage()
            
            # 更新UI
            self.pb_mem['value'] = mem_usage
            self.lbl_mem.config(text=f"{mem_usage}%")
            
            self.pb_cpu['value'] = cpu_usage
            self.lbl_cpu.config(text=f"{cpu_usage}%")
            
            # 变色预警 (如果占用过高显示红色，需配合Style，此处简化处理)
            if mem_usage > 90: self.lbl_mem.config(fg="red")
            else: self.lbl_mem.config(fg="black")
        except:
            pass
            
        # 1000ms 后再次调用
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
                path = vals[3]
                if os.path.isfile(path): path = os.path.dirname(path)
                if os.path.exists(path): os.startfile(path)

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

    # ================= 垃圾清理逻辑 =================
    def setup_clean_tab(self):
        af = tk.Frame(self.tab_clean, pady=5)
        af.pack(fill="x")
        
        self.btn_scan_junk = tk.Button(af, text="🔍 扫描垃圾", command=self.start_junk_scan, bg="#0078D7", fg="white", padx=15)
        self.btn_scan_junk.pack(side="left", padx=5)
        self.btn_stop_junk = tk.Button(af, text="🛑 停止", command=self.stop_current_action, state="disabled", padx=10)
        self.btn_stop_junk.pack(side="left", padx=5)
        self.btn_clean_junk = tk.Button(af, text="🗑️ 清理选中", command=self.start_junk_clean, state="disabled", bg="#d32f2f", fg="white", padx=15)
        self.btn_clean_junk.pack(side="left", padx=20)

        cols = ("check", "risk", "category", "path", "size", "status")
        self.tree_junk = ttk.Treeview(self.tab_clean, columns=cols, show="headings")
        self.tree_junk.heading("check", text="选"); self.tree_junk.column("check", width=40, anchor="center")
        self.tree_junk.heading("risk", text="风险"); self.tree_junk.column("risk", width=80, anchor="center")
        self.tree_junk.heading("category", text="分类"); self.tree_junk.column("category", width=80, anchor="center")
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
        threading.Thread(target=self.run_junk_scan, daemon=True).start()

    def run_junk_scan(self):
        for item in self.tree_junk.get_children(): self.tree_junk.delete(item)
        self.progress['value'] = 0
        local_app = os.environ.get('LOCALAPPDATA', '')
        targets = [
            ("开发工具", "Pip 缓存", os.path.join(local_app, "pip", "Cache"), True, "🟢 低"),
            ("开发工具", "uv 缓存", os.path.join(local_app, "uv", "cache"), True, "🟢 低"),
            ("系统", "系统临时", os.path.join(os.environ['WINDIR'], 'Temp'), True, "🟢 低"),
            ("系统", "用户临时", os.environ.get('TEMP'), True, "🟢 低"),
            ("系统", "错误报告", os.path.join(os.environ['ProgramData'], 'Microsoft/Windows/WER'), True, "🟢 低"),
            ("浏览器", "Chrome缓存", os.path.join(local_app, r"Google\Chrome\User Data\Default\Cache\Cache_Data"), True, "🟢 低"),
            ("浏览器", "Edge缓存", os.path.join(local_app, r"Microsoft\Edge\User Data\Default\Cache\Cache_Data"), True, "🟢 低"),
            ("系统风险", "Win更新包", os.path.join(os.environ['WINDIR'], 'SoftwareDistribution', 'Download'), False, "🟡 中"),
            ("系统风险", "预读取", os.path.join(os.environ['WINDIR'], 'Prefetch'), False, "🟡 中"),
        ]
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
                    self.tree_junk.insert("", "end", values=("☑" if df else "☐", risk, cat, path, format_size(sz), "待清理"), tags=(tag,))
                    total += sz
            self.progress['value'] = (i+1)/len(targets)*100
        
        self.finish_scan(f"扫描完成，发现 {format_size(total)}", self.btn_scan_junk, self.btn_stop_junk, self.btn_clean_junk)

    # ================= 大文件搜索逻辑 =================
    def setup_large_tab(self):
        cf = tk.Frame(self.tab_large, pady=5)
        cf.pack(fill="x")
        tk.Label(cf, text="最小(MB):").pack(side="left")
        self.entry_size = tk.Entry(cf, width=6); self.entry_size.insert(0, "100"); self.entry_size.pack(side="left")
        tk.Label(cf, text="路径:").pack(side="left")
        self.entry_path = tk.Entry(cf, width=25); self.entry_path.insert(0, os.path.expanduser("~")); self.entry_path.pack(side="left")
        tk.Button(cf, text="...", command=lambda: self.select_search_path(), width=3).pack(side="left")
        self.btn_scan_large = tk.Button(cf, text="🔍 搜索", command=self.start_large_scan, bg="#FF9800", fg="white", padx=10)
        self.btn_scan_large.pack(side="left", padx=10)
        self.btn_stop_large = tk.Button(cf, text="🛑 停止", command=self.stop_current_action, state="disabled", padx=10)
        self.btn_stop_large.pack(side="left", padx=5)
        self.btn_clean_large = tk.Button(cf, text="🗑️ 删除", command=self.start_large_clean, state="disabled", bg="#d32f2f", fg="white", padx=10)
        self.btn_clean_large.pack(side="left")

        cols = ("check", "risk", "name", "path", "size", "type")
        self.tree_large = ttk.Treeview(self.tab_large, columns=cols, show="headings")
        self.tree_large.heading("check", text="选"); self.tree_large.column("check", width=40, anchor="center")
        self.tree_large.heading("risk", text="风险"); self.tree_large.column("risk", width=80, anchor="center")
        self.tree_large.heading("name", text="文件名"); self.tree_large.column("name", width=150)
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

    def finish_scan(self, msg, btn_scan, btn_stop, btn_clean):
        if self.stop_event: msg = "扫描已停止"
        self.lbl_status.config(text=msg)
        self.is_working = False
        btn_scan.config(state="normal")
        btn_stop.config(state="disabled")
        btn_clean.config(state="normal")

    # ================= 通用清理逻辑 =================
    def start_junk_clean(self): self._do_clean(self.tree_junk, "junk")
    def start_large_clean(self): self._do_clean(self.tree_large, "large")

    def _do_clean(self, tree, mode):
        items = []
        for i in tree.get_children():
            v = tree.item(i)['values']
            if v[0] == "☑": items.append((i, v[3])) # path is index 3
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
        for i, (iid, path) in enumerate(items):
            self.lbl_status.config(text=f"清理: {path}")
            try:
                if bk:
                    ts = time.strftime("%H%M%S")
                    dst = os.path.join(bk, os.path.basename(path) + "_" + ts)
                    if os.path.isfile(path): shutil.copy2(path, dst)
                    else: shutil.copytree(path, dst, dirs_exist_ok=True)
                
                if mode=="large": send_to_recycle_bin(path)
                else:
                    if os.path.isdir(path):
                        for e in os.scandir(path): send_to_recycle_bin(e.path)
                    else: send_to_recycle_bin(path)
                
                vals = list(tree.item(iid)['values'])
                vals[0]="☐"; vals[4]="0 KB"; vals[5]="已清理"
                if mode=="large": tree.delete(iid)
                else: tree.item(iid, values=vals)
            except: pass
            self.progress['value'] = (i+1)/tot*100
            
        self.lbl_status.config(text="清理完成")
        self.is_working = False
        messagebox.showinfo("完成", "清理结束")

    def get_folder_size(self, path):
        t = 0
        try:
            with os.scandir(path) as it:
                for e in it:
                    if self.stop_event: break
                    if e.is_file(): t+=e.stat().st_size
                    elif e.is_dir(): t+=self.get_folder_size(e.path)
        except: pass
        return t

if __name__ == "__main__":
    root = tk.Tk()
    try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except: pass
    app = MonitorCleanerApp(root)
    root.mainloop()