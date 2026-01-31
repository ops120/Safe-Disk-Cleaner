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
# Windows Shell API 定义 (用于放入回收站)
# ==========================================

# 修复点：手动定义 FILEOP_FLAGS 为 WORD 类型
FILEOP_FLAGS = wintypes.WORD

class SHFILEOPSTRUCT(ctypes.Structure):
    # 必须设置内存对齐，否则在 64 位系统上可能会崩溃或无效
    _pack_ = 8 
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", FILEOP_FLAGS), # 这里使用了修复后的类型
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", wintypes.LPVOID),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]

# API 常量
FO_DELETE = 3
FOF_ALLOWUNDO = 0x40         # 允许撤销 (放入回收站)
FOF_NOCONFIRMATION = 0x10    # 不弹窗确认
FOF_NOERRORUI = 0x0400       # 不弹窗报错
FOF_SILENT = 0x0004          # 不显示进度条 (我们要用自己的进度条)

def send_to_recycle_bin(path):
    """
    调用 Windows 底层 API 将文件或文件夹放入回收站
    返回: 0 表示成功
    """
    if not os.path.exists(path):
        return 0
    
    # 路径必须以双 null 结尾，这是 Windows API 的特殊要求
    pFrom = os.path.abspath(path) + "\0\0"
    
    fileop = SHFILEOPSTRUCT()
    fileop.wFunc = FO_DELETE
    fileop.pFrom = pFrom
    fileop.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_NOERRORUI | FOF_SILENT
    
    # 执行操作
    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(fileop))
    return result == 0

# ==========================================
# 主程序逻辑
# ==========================================
class SafeCleanerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Win10 C盘安全清理工具 (Dev版)")
        self.root.geometry("900x650")
        
        # 变量初始化
        self.backup_path_var = tk.StringVar()
        self.enable_backup_var = tk.IntVar(value=0) # 默认关闭备份
        self.scan_running = False
        self.clean_running = False
        
        # 样式设置
        style = ttk.Style()
        style.configure("Treeview", rowheight=25)
        
        # 检查管理员权限
        if not self.is_admin():
            messagebox.showwarning("权限警告", "检测到未以管理员运行！\n\n为了清理 Temp 和 Windows 目录，\n请关闭程序，右键选择【以管理员身份运行】。")

        self.setup_ui()

    def is_admin(self):
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False

    def setup_ui(self):
        # --- 1. 顶部控制区 ---
        top_frame = tk.Frame(self.root, pady=10)
        top_frame.pack(fill="x", padx=15)
        
        self.btn_scan = tk.Button(top_frame, text="🔍 开始扫描", command=self.start_scan_thread, 
                                  bg="#0078D7", fg="white", font=("Segoe UI", 11, "bold"), padx=15, pady=5)
        self.btn_scan.pack(side="left")
        
        self.lbl_status = tk.Label(top_frame, text="准备就绪", fg="#555", font=("Segoe UI", 10))
        self.lbl_status.pack(side="left", padx=20)

        # --- 2. 列表展示区 ---
        tree_frame = tk.Frame(self.root)
        tree_frame.pack(fill="both", expand=True, padx=15, pady=5)
        
        columns = ("check", "category", "path", "size", "status")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")
        
        self.tree.heading("check", text="选择")
        self.tree.heading("category", text="分类")
        self.tree.heading("path", text="路径 (右键可打开)")
        self.tree.heading("size", text="大小")
        self.tree.heading("status", text="状态")
        
        self.tree.column("check", width=50, anchor="center")
        self.tree.column("category", width=100, anchor="center")
        self.tree.column("path", width=450, anchor="w")
        self.tree.column("size", width=100, anchor="e")
        self.tree.column("status", width=120, anchor="center")
        
        # 滚动条
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

        # 绑定事件
        self.tree.bind("<Button-1>", self.on_tree_click) # 勾选
        self.tree.bind("<Button-3>", self.show_context_menu) # 右键菜单

        # --- 3. 底部操作区 ---
        bottom_frame = tk.LabelFrame(self.root, text="清理设置与执行", padx=15, pady=15)
        bottom_frame.pack(fill="x", padx=15, pady=15)
        
        # 备份行
        bk_frame = tk.Frame(bottom_frame)
        bk_frame.pack(fill="x", pady=5)
        
        cb_backup = tk.Checkbutton(bk_frame, text="清理前备份文件到:", variable=self.enable_backup_var, command=self.toggle_backup_ui)
        cb_backup.pack(side="left")
        
        self.entry_backup = tk.Entry(bk_frame, textvariable=self.backup_path_var, state="disabled", width=50)
        self.entry_backup.pack(side="left", padx=5)
        
        self.btn_browse = tk.Button(bk_frame, text="📁 选择目录", command=self.browse_backup_folder, state="disabled")
        self.btn_browse.pack(side="left")

        # 进度条
        self.progress = ttk.Progressbar(bottom_frame, orient="horizontal", mode="determinate")
        self.progress.pack(fill="x", pady=10)
        
        # 按钮行
        btn_frame = tk.Frame(bottom_frame)
        btn_frame.pack(fill="x")
        
        tk.Label(btn_frame, text="⚠️ 提示：删除操作会将文件移入回收站", fg="#e65100").pack(side="left", pady=5)
        
        self.btn_clean = tk.Button(btn_frame, text="🗑️ 清理勾选项目", command=self.start_clean_thread, 
                                   state="disabled", bg="#d32f2f", fg="white", font=("Segoe UI", 10, "bold"), padx=15)
        self.btn_clean.pack(side="right")

        # --- 右键菜单 ---
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="📂 打开所在目录", command=self.open_selected_folder)

    # ==========================
    # 交互逻辑
    # ==========================
    def toggle_backup_ui(self):
        state = "normal" if self.enable_backup_var.get() else "disabled"
        self.entry_backup.config(state=state)
        self.btn_browse.config(state=state)

    def browse_backup_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.backup_path_var.set(path)

    def show_context_menu(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)
            
    def open_selected_folder(self):
        selected = self.tree.selection()
        if selected:
            path = self.tree.item(selected[0])['values'][2]
            if os.path.exists(path):
                os.startfile(path)
            else:
                messagebox.showerror("错误", "目录不存在，可能已被删除。")

    def on_tree_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region == "cell":
            column = self.tree.identify_column(event.x)
            if column == "#1": # 点击第一列 (Check)
                item_id = self.tree.identify_row(event.y)
                current_val = self.tree.item(item_id)['values'][0]
                new_val = "☑" if current_val == "☐" else "☐"
                
                # 更新值
                vals = list(self.tree.item(item_id)['values'])
                vals[0] = new_val
                self.tree.item(item_id, values=vals)

    # ==========================
    # 扫描功能
    # ==========================
    def start_scan_thread(self):
        if self.scan_running or self.clean_running: return
        self.btn_clean.config(state="disabled")
        self.scan_running = True
        threading.Thread(target=self.run_scan, daemon=True).start()

    def run_scan(self):
        # 清空列表
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        self.lbl_status.config(text="正在初始化扫描...")
        self.progress['value'] = 0
        
        # 动态获取路径
        local_app_data = os.environ.get('LOCALAPPDATA', '')
        
        targets = [
            # (分类, 名称, 路径, 默认勾选)
            ("开发工具", "Pip 缓存", os.path.join(local_app_data, "pip", "Cache"), True),
            ("开发工具", "uv 缓存", os.path.join(local_app_data, "uv", "cache"), True),
            ("系统", "系统临时 (Win/Temp)", os.path.join(os.environ['WINDIR'], 'Temp'), True),
            ("系统", "用户临时 (%TEMP%)", os.environ.get('TEMP'), True),
            ("系统", "错误报告 (WER)", os.path.join(os.environ['ProgramData'], 'Microsoft/Windows/WER'), True),
            ("浏览器", "Chrome 缓存", os.path.join(local_app_data, r"Google\Chrome\User Data\Default\Cache\Cache_Data"), True),
            ("浏览器", "Edge 缓存", os.path.join(local_app_data, r"Microsoft\Edge\User Data\Default\Cache\Cache_Data"), True),
            ("系统风险", "Win更新下载 (SoftwareDistribution)", os.path.join(os.environ['WINDIR'], 'SoftwareDistribution', 'Download'), False),
            ("系统风险", "预读取 (Prefetch)", os.path.join(os.environ['WINDIR'], 'Prefetch'), False),
        ]

        total_files = 0
        total_size = 0
        
        count = len(targets)
        for i, (cat, name, path, default_check) in enumerate(targets):
            self.lbl_status.config(text=f"正在分析: {name}...")
            
            if path and os.path.exists(path):
                size = self.get_folder_size(path)
                if size > 0:
                    check_mark = "☑" if default_check else "☐"
                    self.tree.insert("", "end", values=(check_mark, cat, path, self.format_size(size), "待清理"))
                    total_size += size
            
            # 更新进度
            self.progress['value'] = ((i + 1) / count) * 100
            self.root.update_idletasks()

        self.scan_running = False
        self.btn_clean.config(state="normal")
        self.lbl_status.config(text=f"扫描完成，发现可清理空间: {self.format_size(total_size)}")

    def get_folder_size(self, path):
        total = 0
        try:
            with os.scandir(path) as it:
                for entry in it:
                    try:
                        if entry.is_file(follow_symlinks=False):
                            total += entry.stat().st_size
                        elif entry.is_dir(follow_symlinks=False):
                            total += self.get_folder_size(entry.path)
                    except OSError:
                        pass
        except OSError:
            pass
        return total

    def format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} TB"

    # ==========================
    # 清理功能 (核心)
    # ==========================
    def start_clean_thread(self):
        # 1. 获取勾选项
        items = []
        for item_id in self.tree.get_children():
            val = self.tree.item(item_id)['values']
            if val[0] == "☑":
                items.append((item_id, val[2], val[1])) # ID, Path, Name
        
        if not items:
            messagebox.showinfo("提示", "请先勾选需要清理的项目。")
            return

        # 2. 检查备份设置
        backup_dir = None
        if self.enable_backup_var.get():
            backup_dir = self.backup_path_var.get()
            if not backup_dir or not os.path.exists(backup_dir):
                messagebox.showerror("错误", "备份目录无效，请重新选择。")
                return
            
            # 确认提示
            msg = f"您选择了开启备份。\n\n文件将被复制到: {backup_dir}\n这可能会显著增加清理时间。\n\n是否继续？"
            if not messagebox.askyesno("备份确认", msg):
                return
        else:
            if not messagebox.askyesno("清理确认", "确定要清理勾选的项目吗？\n文件将被移入回收站。"):
                return

        self.clean_running = True
        self.btn_clean.config(state="disabled")
        self.btn_scan.config(state="disabled")
        
        threading.Thread(target=self.run_clean, args=(items, backup_dir), daemon=True).start()

    def run_clean(self, items, backup_dir):
        total_items = len(items)
        
        for idx, (item_id, path, name) in enumerate(items):
            self.lbl_status.config(text=f"正在处理: {name} ...")
            
            # 更新UI状态
            vals = list(self.tree.item(item_id)['values'])
            vals[4] = "处理中..."
            self.tree.item(item_id, values=vals)
            
            try:
                # --- 步骤 1: 备份 ---
                if backup_dir:
                    self.lbl_status.config(text=f"正在备份: {name} ...")
                    # 创建带时间戳的文件夹名
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    dest_name = f"{name.replace(' ', '_')}_{timestamp}"
                    dest_path = os.path.join(backup_dir, dest_name)
                    
                    try:
                        shutil.copytree(path, dest_path, dirs_exist_ok=True, ignore_dangling_symlinks=True)
                    except Exception as e:
                        print(f"Backup failed for {path}: {e}")

                # --- 步骤 2: 清理 (移入回收站) ---
                self.lbl_status.config(text=f"正在清理: {name} ...")
                
                # 注意：我们不删除根文件夹，只删除里面的内容
                with os.scandir(path) as it:
                    for entry in it:
                        try:
                            send_to_recycle_bin(entry.path)
                        except Exception:
                            pass # 跳过锁定文件
                
                # --- 步骤 3: 更新完成状态 ---
                vals[0] = "☐" # 取消勾选
                vals[3] = "0 KB"
                vals[4] = "已清理"
                self.tree.item(item_id, values=vals)

            except Exception as e:
                vals[4] = "部分失败"
                self.tree.item(item_id, values=vals)
                print(f"Error cleaning {path}: {e}")

            # 更新总进度
            self.progress['value'] = ((idx + 1) / total_items) * 100
            self.root.update_idletasks()

        self.clean_running = False
        self.btn_scan.config(state="normal")
        self.lbl_status.config(text="所有操作已完成")
        messagebox.showinfo("完成", "清理完成！\n被删除的文件已在回收站中。")

if __name__ == "__main__":
    root = tk.Tk()
    # 尝试设置高DPI支持
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except:
        pass
        
    app = SafeCleanerApp(root)
    root.mainloop()