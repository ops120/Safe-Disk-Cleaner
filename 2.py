import os
import shutil
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import ctypes
from ctypes import wintypes
import time
from pathlib import Path

# ==========================================
# Windows Shell API 定义 (回收站支持)
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

def send_to_recycle_bin(path):
    if not os.path.exists(path): return 0
    pFrom = os.path.abspath(path) + "\0\0"
    fileop = SHFILEOPSTRUCT()
    fileop.wFunc = FO_DELETE
    fileop.pFrom = pFrom
    fileop.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_NOERRORUI | FOF_SILENT
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(fileop))
    return result == 0

# ==========================================
# 工具类方法
# ==========================================
def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"

def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

# ==========================================
# 主程序逻辑
# ==========================================
class UltimateCleanerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Win10 C盘深度清理专家 V2.0 (含大文件搜索)")
        self.root.geometry("950x700")
        
        if not is_admin():
            messagebox.showwarning("权限警告", "建议以管理员身份运行，否则无法扫描系统目录！")

        # 全局变量
        self.backup_path_var = tk.StringVar()
        self.enable_backup_var = tk.IntVar(value=0)
        self.lock = threading.Lock() # 线程锁
        self.is_working = False

        self.setup_ui()

    def setup_ui(self):
        # 1. 顶部：备份设置 (全局通用)
        top_frame = tk.LabelFrame(self.root, text="🛡️ 安全备份设置 (通用)", padx=10, pady=5)
        top_frame.pack(fill="x", padx=10, pady=5)
        
        tk.Checkbutton(top_frame, text="删除前备份文件到:", variable=self.enable_backup_var, command=self.toggle_backup_ui).pack(side="left")
        self.entry_backup = tk.Entry(top_frame, textvariable=self.backup_path_var, state="disabled", width=50)
        self.entry_backup.pack(side="left", padx=5)
        self.btn_browse = tk.Button(top_frame, text="📂 选择...", command=self.browse_backup_folder, state="disabled")
        self.btn_browse.pack(side="left")

        # 2. 中间：多标签页
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=5)

        # tab1: 垃圾清理
        self.tab_clean = tk.Frame(self.notebook)
        self.notebook.add(self.tab_clean, text="   🧹 垃圾清理   ")
        self.setup_clean_tab()

        # tab2: 大文件搜索
        self.tab_large = tk.Frame(self.notebook)
        self.notebook.add(self.tab_large, text="   🐘 大文件搜索   ")
        self.setup_large_tab()

        # 3. 底部：进度条
        self.progress = ttk.Progressbar(self.root, orient="horizontal", mode="determinate")
        self.progress.pack(fill="x", padx=10, pady=5)
        
        self.lbl_status = tk.Label(self.root, text="准备就绪", fg="gray", anchor="w")
        self.lbl_status.pack(fill="x", padx=15, pady=(0, 5))

        # 右键菜单
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="📂 打开所在文件夹", command=self.open_selected_folder)

    # ---------------- UI 辅助 ----------------
    def toggle_backup_ui(self):
        state = "normal" if self.enable_backup_var.get() else "disabled"
        self.entry_backup.config(state=state)
        self.btn_browse.config(state=state)

    def browse_backup_folder(self):
        path = filedialog.askdirectory()
        if path: self.backup_path_var.set(path)

    def show_context_menu(self, event, tree):
        item = tree.identify_row(event.y)
        if item:
            tree.selection_set(item)
            self.context_menu_target = tree # 记录是哪个树触发的
            self.context_menu.post(event.x_root, event.y_root)

    def open_selected_folder(self):
        tree = getattr(self, 'context_menu_target', None)
        if tree:
            selected = tree.selection()
            if selected:
                path = tree.item(selected[0])['values'][2]
                # 如果是文件，打开所在目录；如果是目录，直接打开
                if os.path.isfile(path):
                    path = os.path.dirname(path)
                if os.path.exists(path):
                    os.startfile(path)

    # ========================================================
    # 模块一：垃圾清理 (Tab 1)
    # ========================================================
    def setup_clean_tab(self):
        # 顶部按钮
        action_frame = tk.Frame(self.tab_clean, pady=5)
        action_frame.pack(fill="x")
        
        tk.Button(action_frame, text="🔍 扫描垃圾", command=self.start_junk_scan, bg="#0078D7", fg="white", padx=15).pack(side="left", padx=5)
        self.btn_clean_junk = tk.Button(action_frame, text="🗑️ 清理选中", command=self.start_junk_clean, state="disabled", bg="#d32f2f", fg="white", padx=15)
        self.btn_clean_junk.pack(side="left", padx=5)

        # 列表
        columns = ("check", "category", "path", "size", "status")
        self.tree_junk = ttk.Treeview(self.tab_clean, columns=columns, show="headings")
        
        self.tree_junk.heading("check", text="选择")
        self.tree_junk.heading("category", text="分类")
        self.tree_junk.heading("path", text="路径")
        self.tree_junk.heading("size", text="占用")
        self.tree_junk.heading("status", text="状态")
        
        self.tree_junk.column("check", width=50, anchor="center")
        self.tree_junk.column("category", width=100, anchor="center")
        self.tree_junk.column("path", width=450)
        self.tree_junk.column("size", width=100, anchor="e")
        self.tree_junk.column("status", width=100, anchor="center")
        
        scroll = ttk.Scrollbar(self.tab_clean, orient="vertical", command=self.tree_junk.yview)
        self.tree_junk.configure(yscroll=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree_junk.pack(fill="both", expand=True)

        self.tree_junk.bind("<Button-1>", lambda e: self.on_check_click(e, self.tree_junk))
        self.tree_junk.bind("<Button-3>", lambda e: self.show_context_menu(e, self.tree_junk))

    def start_junk_scan(self):
        if self.is_working: return
        self.is_working = True
        self.btn_clean_junk.config(state="disabled")
        threading.Thread(target=self.run_junk_scan, daemon=True).start()

    def run_junk_scan(self):
        for item in self.tree_junk.get_children(): self.tree_junk.delete(item)
        self.progress['value'] = 0
        
        local_app = os.environ.get('LOCALAPPDATA', '')
        targets = [
            ("开发工具", "Pip 缓存", os.path.join(local_app, "pip", "Cache"), True),
            ("开发工具", "uv 缓存", os.path.join(local_app, "uv", "cache"), True),
            ("系统", "系统临时", os.path.join(os.environ['WINDIR'], 'Temp'), True),
            ("系统", "用户临时", os.environ.get('TEMP'), True),
            ("系统", "错误报告", os.path.join(os.environ['ProgramData'], 'Microsoft/Windows/WER'), True),
            ("浏览器", "Chrome 缓存", os.path.join(local_app, r"Google\Chrome\User Data\Default\Cache\Cache_Data"), True),
            ("浏览器", "Edge 缓存", os.path.join(local_app, r"Microsoft\Edge\User Data\Default\Cache\Cache_Data"), True),
            ("系统风险", "Win更新缓存", os.path.join(os.environ['WINDIR'], 'SoftwareDistribution', 'Download'), False),
        ]

        total_size = 0
        for i, (cat, name, path, default) in enumerate(targets):
            self.lbl_status.config(text=f"扫描中: {name}")
            if path and os.path.exists(path):
                size = self.get_folder_size(path)
                if size > 0:
                    mark = "☑" if default else "☐"
                    self.tree_junk.insert("", "end", values=(mark, cat, path, format_size(size), "待清理"))
                    total_size += size
            self.progress['value'] = (i + 1) / len(targets) * 100
        
        self.lbl_status.config(text=f"垃圾扫描完成，共发现 {format_size(total_size)}")
        self.is_working = False
        self.btn_clean_junk.config(state="normal")

    # ========================================================
    # 模块二：大文件搜索 (Tab 2 - 新增功能)
    # ========================================================
    def setup_large_tab(self):
        # 控制栏
        ctrl_frame = tk.Frame(self.tab_large, pady=5)
        ctrl_frame.pack(fill="x")

        tk.Label(ctrl_frame, text="最小大小(MB):").pack(side="left", padx=5)
        self.entry_size = tk.Entry(ctrl_frame, width=8)
        self.entry_size.insert(0, "100") # 默认100MB
        self.entry_size.pack(side="left")

        tk.Label(ctrl_frame, text="搜索路径:").pack(side="left", padx=5)
        self.entry_path = tk.Entry(ctrl_frame, width=30)
        self.entry_path.insert(0, os.path.expanduser("~")) # 默认 C:\Users\User
        self.entry_path.pack(side="left")
        
        tk.Button(ctrl_frame, text="...", command=lambda: self.select_search_path(), width=3).pack(side="left")
        
        tk.Button(ctrl_frame, text="🔍 搜索大文件", command=self.start_large_scan, bg="#FF9800", fg="white", padx=10).pack(side="left", padx=15)
        self.btn_clean_large = tk.Button(ctrl_frame, text="🗑️ 删除选中", command=self.start_large_clean, state="disabled", bg="#d32f2f", fg="white", padx=10)
        self.btn_clean_large.pack(side="left")

        # 列表
        columns = ("check", "name", "path", "size", "type")
        self.tree_large = ttk.Treeview(self.tab_large, columns=columns, show="headings")
        
        self.tree_large.heading("check", text="选择")
        self.tree_large.heading("name", text="文件名")
        self.tree_large.heading("path", text="完整路径")
        self.tree_large.heading("size", text="大小")
        self.tree_large.heading("type", text="类型")

        self.tree_large.column("check", width=50, anchor="center")
        self.tree_large.column("name", width=200)
        self.tree_large.column("path", width=400)
        self.tree_large.column("size", width=100, anchor="e")
        self.tree_large.column("type", width=80, anchor="center")

        scroll2 = ttk.Scrollbar(self.tab_large, orient="vertical", command=self.tree_large.yview)
        self.tree_large.configure(yscroll=scroll2.set)
        scroll2.pack(side="right", fill="y")
        self.tree_large.pack(fill="both", expand=True)

        self.tree_large.bind("<Button-1>", lambda e: self.on_check_click(e, self.tree_large))
        self.tree_large.bind("<Button-3>", lambda e: self.show_context_menu(e, self.tree_large))

    def select_search_path(self):
        p = filedialog.askdirectory()
        if p:
            self.entry_path.delete(0, tk.END)
            self.entry_path.insert(0, p)

    def start_large_scan(self):
        if self.is_working: return
        try:
            limit_mb = float(self.entry_size.get())
            path = self.entry_path.get()
        except ValueError:
            messagebox.showerror("错误", "请输入有效的数字大小！")
            return
        
        self.is_working = True
        self.btn_clean_large.config(state="disabled")
        threading.Thread(target=self.run_large_scan, args=(path, limit_mb), daemon=True).start()

    def run_large_scan(self, start_path, limit_mb):
        for item in self.tree_large.get_children(): self.tree_large.delete(item)
        self.progress['value'] = 0
        self.progress.configure(mode='indeterminate')
        self.progress.start(10)
        
        limit_bytes = limit_mb * 1024 * 1024
        count = 0
        
        self.lbl_status.config(text=f"正在搜索大文件 (> {limit_mb}MB)...")

        try:
            for root, dirs, files in os.walk(start_path):
                # 过滤掉一些敏感目录，防止扫描太慢或报错
                if "Windows" in root and "WinSxS" in root: continue
                
                for name in files:
                    try:
                        filepath = os.path.join(root, name)
                        # 获取文件大小
                        fsize = os.path.getsize(filepath)
                        if fsize > limit_bytes:
                            # 插入结果 (默认不勾选，防误删)
                            ext = os.path.splitext(name)[1]
                            self.tree_large.insert("", "end", values=("☐", name, filepath, format_size(fsize), ext))
                            count += 1
                    except Exception:
                        pass
        except Exception as e:
            print(e)

        self.progress.stop()
        self.progress.configure(mode='determinate')
        self.progress['value'] = 100
        self.lbl_status.config(text=f"搜索完成，找到 {count} 个大于 {limit_mb}MB 的文件")
        self.is_working = False
        self.btn_clean_large.config(state="normal")

    # ========================================================
    # 通用清理逻辑 (支持两个 Tab)
    # ========================================================
    def start_junk_clean(self):
        self._start_generic_clean(self.tree_junk, "junk")

    def start_large_clean(self):
        self._start_generic_clean(self.tree_large, "large")

    def _start_generic_clean(self, tree_widget, mode):
        # 1. 收集需清理项
        items = []
        for item_id in tree_widget.get_children():
            val = tree_widget.item(item_id)['values']
            if val[0] == "☑":
                items.append((item_id, val[2])) # ID, Path
        
        if not items:
            messagebox.showinfo("提示", "请先勾选要删除的项目！")
            return

        # 2. 确认备份
        backup_dir = None
        if self.enable_backup_var.get():
            backup_dir = self.backup_path_var.get()
            if not backup_dir or not os.path.exists(backup_dir):
                messagebox.showerror("错误", "备份路径无效！")
                return
            if not messagebox.askyesno("备份警告", "大文件备份可能非常耗时，确定继续吗？"):
                return

        if not messagebox.askyesno("最后确认", f"即将删除 {len(items)} 个项目到回收站。\n确定吗？"):
            return

        self.is_working = True
        threading.Thread(target=self.run_generic_clean, args=(tree_widget, items, backup_dir, mode), daemon=True).start()

    def run_generic_clean(self, tree, items, backup_dir, mode):
        total = len(items)
        for i, (item_id, path) in enumerate(items):
            self.lbl_status.config(text=f"处理中: {path}")
            vals = list(tree.item(item_id)['values'])
            
            try:
                # A. 备份
                if backup_dir:
                    timestamp = time.strftime("%H%M%S")
                    dest = os.path.join(backup_dir, os.path.basename(path) + "_" + timestamp)
                    if os.path.isfile(path):
                        shutil.copy2(path, dest)
                    else:
                        shutil.copytree(path, dest, dirs_exist_ok=True)

                # B. 删除 (区别对待文件和文件夹)
                if mode == "large":
                    # 大文件模式直接删文件
                    send_to_recycle_bin(path)
                else:
                    # 垃圾清理模式，删文件夹下的内容
                    if os.path.isdir(path):
                        for entry in os.scandir(path):
                            send_to_recycle_bin(entry.path)
                    else:
                        send_to_recycle_bin(path)

                vals[0] = "☐"
                vals[3] = "0 KB"
                vals[4] = "已清理" # 状态列位置不同，需注意
                if mode == "large":
                     # 大文件列表没有状态列，或者直接从列表中移除更直观？
                     # 这里选择直接移除行，因为大文件清理后就没了
                     tree.delete(item_id)
                     continue
                
                tree.item(item_id, values=vals)

            except Exception as e:
                print(f"Error: {e}")
            
            self.progress['value'] = (i+1)/total * 100
        
        self.lbl_status.config(text="清理完成")
        self.is_working = False
        messagebox.showinfo("完成", "清理结束，文件已移入回收站。")

    # ========================================================
    # 辅助逻辑
    # ========================================================
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

    def get_folder_size(self, path):
        total = 0
        try:
            with os.scandir(path) as it:
                for entry in it:
                    if entry.is_file(): total += entry.stat().st_size
                    elif entry.is_dir(): total += self.get_folder_size(entry.path)
        except: pass
        return total

if __name__ == "__main__":
    root = tk.Tk()
    try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except: pass
    app = UltimateCleanerApp(root)
    root.mainloop()