from __future__ import annotations

import ctypes
import os
import threading
import tkinter as tk
from tkinter import font as tkfont
from typing import Callable

import rdp_core as core

C = {
    "bg": "#101216",
    "panel": "#16181e",
    "panel_alt": "#1b1e26",
    "line": "#2a2e38",
    "text": "#eceff4",
    "muted": "#8b919c",
    "dim": "#5c6370",
    "accent": "#6ea0ff",
    "accent_dim": "#2a3a58",
    "ok": "#6fcf97",
    "warn": "#e0b25a",
    "danger": "#d97a7a",
    "row": "#181b22",
    "row_hover": "#22262f",
    "row_on": "#1c2433",
}


def _try_app_id() -> None:
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("OpenRPA.RDPManager")
    except Exception:
        pass


class PillButton(tk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        text: str,
        command: Callable[[], None],
        *,
        kind: str = "ghost",
        width: int = 0,
    ) -> None:
        super().__init__(master, bg=master.cget("bg") if hasattr(master, "cget") else C["bg"])
        self.command = command
        self.kind = kind
        self.disabled = False
        colors = {
            "primary": (C["accent"], "#0d1118", C["text"]),
            "ghost": (C["panel_alt"], C["text"], C["line"]),
            "ok": ("#1f3a2e", C["ok"], "#2d5a43"),
            "warn": ("#3a3220", C["warn"], "#5a4a28"),
            "danger": ("#3a2224", C["danger"], "#5a3236"),
        }
        self.bg, self.fg, self.bd = colors.get(kind, colors["ghost"])
        self.label = tk.Label(
            self,
            text=text,
            bg=self.bg,
            fg=self.fg,
            padx=12 if width == 0 else 8,
            pady=6,
            font=("Segoe UI", 9),
            cursor="hand2",
        )
        if width:
            self.label.configure(width=width)
        self.label.pack(fill="both")
        self.configure(bg=self.bd, padx=1, pady=1)
        for widget in (self, self.label):
            widget.bind("<Button-1>", self._click)
            widget.bind("<Enter>", self._enter)
            widget.bind("<Leave>", self._leave)

    def set_text(self, text: str) -> None:
        self.label.configure(text=text)

    def set_enabled(self, enabled: bool) -> None:
        self.disabled = not enabled
        self.label.configure(cursor="hand2" if enabled else "arrow", fg=self.fg if enabled else C["dim"])

    def _click(self, _event: tk.Event | None = None) -> None:
        if not self.disabled:
            self.command()

    def _enter(self, _event: tk.Event | None = None) -> None:
        if not self.disabled:
            self.label.configure(bg=self._blend())

    def _leave(self, _event: tk.Event | None = None) -> None:
        self.label.configure(bg=self.bg)

    def _blend(self) -> str:
        if self.kind == "primary":
            return "#7cacff"
        return "#262a34"


class AccountRow(tk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        account: core.Account,
        selected: bool,
        on_toggle: Callable[[core.Account], None],
        on_action: Callable[[str, core.Account], None],
    ) -> None:
        super().__init__(master, bg=C["row"], highlightthickness=0)
        self.account = account
        self.selected = selected
        self.on_toggle = on_toggle
        self.on_action = on_action
        self.configure(bg=self._bg())
        inner = tk.Frame(self, bg=self._bg())
        inner.pack(fill="x", padx=10, pady=8)

        self.mark = tk.Canvas(inner, width=16, height=16, bg=self._bg(), highlightthickness=0, cursor="hand2")
        self.mark.pack(side="left")
        self._draw_mark()

        info = tk.Frame(inner, bg=self._bg())
        info.pack(side="left", fill="x", expand=True, padx=(10, 8))
        tk.Label(
            info,
            text=account.name,
            bg=self._bg(),
            fg=C["text"],
            font=("Segoe UI Semibold", 10),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            info,
            text=f"{account.username}   ·   {account.rdp_address}",
            bg=self._bg(),
            fg=C["muted"],
            font=("Segoe UI", 8),
            anchor="w",
        ).pack(fill="x")

        actions = tk.Frame(inner, bg=self._bg())
        actions.pack(side="right")
        PillButton(actions, "RDP", lambda: on_action("rdp", account), kind="ghost").pack(side="left", padx=(0, 4))
        PillButton(actions, "Shadow", lambda: on_action("shadow", account), kind="ghost").pack(side="left", padx=(0, 4))
        PillButton(actions, "Control", lambda: on_action("control", account), kind="ok").pack(side="left")

        for widget in (self, inner, info, self.mark):
            widget.bind("<Button-1>", self._toggle)
            widget.bind("<Double-Button-1>", lambda _e: on_action("rdp", account))
            widget.bind("<Enter>", self._enter)
            widget.bind("<Leave>", self._leave)

    def _bg(self) -> str:
        return C["row_on"] if self.selected else C["row"]

    def _draw_mark(self) -> None:
        self.mark.delete("all")
        self.mark.configure(bg=self._bg())
        color = C["accent"] if self.selected else C["line"]
        self.mark.create_rectangle(1, 1, 15, 15, outline=color, width=1)
        if self.selected:
            self.mark.create_rectangle(4, 4, 12, 12, fill=C["accent"], outline="")

    def _toggle(self, _event: tk.Event | None = None) -> None:
        self.on_toggle(self.account)

    def _enter(self, _event: tk.Event | None = None) -> None:
        if not self.selected:
            self._recolor(C["row_hover"])

    def _leave(self, _event: tk.Event | None = None) -> None:
        self._recolor(self._bg())

    def _recolor(self, color: str) -> None:
        self.configure(bg=color)
        for child in self.winfo_children():
            self._recolor_tree(child, color)
        self.mark.configure(bg=color)
        self._draw_mark()

    def _recolor_tree(self, widget: tk.Misc, color: str) -> None:
        try:
            if isinstance(widget, PillButton) or isinstance(widget, tk.Canvas):
                return
            widget.configure(bg=color)
        except tk.TclError:
            return
        for child in widget.winfo_children():
            self._recolor_tree(child, color)


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        _try_app_id()
        tkfont.nametofont("TkDefaultFont").configure(family="Segoe UI", size=9)
        self.title("OpenRPA · RDP Manager")
        self.geometry("980x640")
        self.minsize(860, 540)
        self.configure(bg=C["bg"])
        self.data: core.AppData | None = None
        self.selected: set[str] = set()
        self.machine_filter = ""
        self.search_var = tk.StringVar()
        self.busy = False
        self.status_var = tk.StringVar(value="Загрузка учёток…")
        self._build()
        self.search_var.trace_add("write", lambda *_: self.render_accounts())
        self.after(80, self.reload)
        self.bind("<F5>", lambda _e: self.reload())
        self.bind("<Control-a>", self._select_visible)
        self.bind("<Return>", lambda _e: self.run_selected("rdp"))

    def _build(self) -> None:
        header = tk.Frame(self, bg=C["bg"])
        header.pack(fill="x", padx=18, pady=(16, 10))
        titles = tk.Frame(header, bg=C["bg"])
        titles.pack(side="left")
        tk.Label(
            titles,
            text="RDP Manager",
            bg=C["bg"],
            fg=C["text"],
            font=("Segoe UI Semibold", 16),
        ).pack(anchor="w")
        self.path_label = tk.Label(
            titles,
            text="accounts.json",
            bg=C["bg"],
            fg=C["dim"],
            font=("Segoe UI", 8),
        )
        self.path_label.pack(anchor="w")

        tools = tk.Frame(header, bg=C["bg"])
        tools.pack(side="right")
        PillButton(tools, "JSON", self.open_json).pack(side="left", padx=4)
        PillButton(tools, "Обновить", self.reload).pack(side="left", padx=4)
        PillButton(tools, "Очистить кэш", self.clear_cache, kind="danger").pack(side="left", padx=4)

        body = tk.Frame(self, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=18, pady=(0, 10))

        self.side = tk.Frame(body, bg=C["panel"], width=210)
        self.side.pack(side="left", fill="y")
        self.side.pack_propagate(False)
        tk.Label(
            self.side,
            text="МАШИНЫ",
            bg=C["panel"],
            fg=C["dim"],
            font=("Segoe UI", 8),
            anchor="w",
        ).pack(fill="x", padx=14, pady=(14, 8))
        self.machine_box = tk.Frame(self.side, bg=C["panel"])
        self.machine_box.pack(fill="both", expand=True, padx=8, pady=(0, 12))

        main = tk.Frame(body, bg=C["panel"])
        main.pack(side="left", fill="both", expand=True, padx=(10, 0))

        toolbar = tk.Frame(main, bg=C["panel"])
        toolbar.pack(fill="x", padx=12, pady=12)
        search_wrap = tk.Frame(toolbar, bg=C["line"], padx=1, pady=1)
        search_wrap.pack(side="left", fill="x", expand=True)
        search = tk.Entry(
            search_wrap,
            textvariable=self.search_var,
            bg=C["panel_alt"],
            fg=C["text"],
            insertbackground=C["text"],
            relief="flat",
            font=("Segoe UI", 10),
        )
        search.pack(fill="x", ipady=6, padx=8)
        search.insert(0, "")
        self.search_placeholder = "Поиск по имени, логину или машине"
        self._placeholder_on = True
        search.bind("<FocusIn>", self._search_in)
        search.bind("<FocusOut>", self._search_out)
        self.search_entry = search

        PillButton(toolbar, "Все", lambda: self.set_visible_selected(True), width=6).pack(side="left", padx=(8, 4))
        PillButton(toolbar, "Сброс", lambda: self.set_visible_selected(False), width=6).pack(side="left")

        list_wrap = tk.Frame(main, bg=C["panel"])
        list_wrap.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.canvas = tk.Canvas(list_wrap, bg=C["panel"], highlightthickness=0)
        scroll = tk.Scrollbar(list_wrap, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.rows = tk.Frame(self.canvas, bg=C["panel"])
        self.rows_id = self.canvas.create_window((0, 0), window=self.rows, anchor="nw")
        self.rows.bind("<Configure>", lambda _e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._stretch_rows)
        self.canvas.bind_all("<MouseWheel>", self._wheel)

        footer = tk.Frame(self, bg=C["bg"])
        footer.pack(fill="x", padx=18, pady=(0, 14))
        self.count_label = tk.Label(footer, text="Выбрано: 0", bg=C["bg"], fg=C["muted"], font=("Segoe UI", 9))
        self.count_label.pack(side="left")
        actions = tk.Frame(footer, bg=C["bg"])
        actions.pack(side="right")
        PillButton(actions, "RDP выбранных", lambda: self.run_selected("rdp"), kind="primary").pack(side="left", padx=4)
        PillButton(actions, "Shadow", lambda: self.run_selected("shadow")).pack(side="left", padx=4)
        PillButton(actions, "Shadow Control", lambda: self.run_selected("control"), kind="ok").pack(side="left", padx=4)

        status = tk.Frame(self, bg=C["panel_alt"])
        status.pack(fill="x")
        tk.Label(
            status,
            textvariable=self.status_var,
            bg=C["panel_alt"],
            fg=C["muted"],
            font=("Segoe UI", 8),
            anchor="w",
            padx=18,
            pady=7,
        ).pack(fill="x")
        self._search_out()

    def _search_in(self, _event: tk.Event | None = None) -> None:
        if self._placeholder_on:
            self.search_entry.delete(0, "end")
            self.search_entry.configure(fg=C["text"])
            self._placeholder_on = False

    def _search_out(self, _event: tk.Event | None = None) -> None:
        if not self.search_var.get():
            self._placeholder_on = True
            self.search_entry.configure(fg=C["dim"])
            self.search_entry.delete(0, "end")
            self.search_entry.insert(0, self.search_placeholder)

    def _query(self) -> str:
        if self._placeholder_on:
            return ""
        return self.search_var.get().strip().lower()

    def _stretch_rows(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self.rows_id, width=event.width)

    def _wheel(self, event: tk.Event) -> None:
        if self.canvas.winfo_containing(event.x_root, event.y_root) is None:
            return
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def visible_accounts(self) -> list[core.Account]:
        if not self.data:
            return []
        query = self._query()
        items: list[core.Account] = []
        for account in self.data.accounts:
            if not account.enabled:
                continue
            if self.machine_filter and account.host.lower() != self.machine_filter.lower():
                continue
            blob = f"{account.name} {account.username} {account.machine}".lower()
            if query and query not in blob:
                continue
            items.append(account)
        return items

    def reload(self) -> None:
        try:
            self.data = core.load_accounts()
        except Exception as exc:
            self.set_status(f"Ошибка JSON: {exc}")
            self._dialog("Не удалось прочитать accounts.json", str(exc), danger=True)
            return
        self.path_label.configure(text=str(self.data.source))
        known = {item.key for item in self.data.accounts}
        self.selected &= known
        if self.machine_filter and self.machine_filter not in {item.host for item in self.data.accounts}:
            self.machine_filter = ""
        self.render_machines()
        self.render_accounts()
        self.set_status(f"Загружено {len(self.data.accounts)} учёток · {self.data.source.name}")

    def render_machines(self) -> None:
        for child in self.machine_box.winfo_children():
            child.destroy()
        if not self.data:
            return
        counts: dict[str, int] = {}
        for account in self.data.accounts:
            if account.enabled:
                counts[account.host] = counts.get(account.host, 0) + 1
        self._machine_item("Все", "", sum(counts.values()))
        for host in sorted(counts):
            self._machine_item(host, host, counts[host])

    def _machine_item(self, title: str, value: str, count: int) -> None:
        active = self.machine_filter == value
        bg = C["accent_dim"] if active else C["panel"]
        fg = C["accent"] if active else C["text"]
        row = tk.Frame(self.machine_box, bg=bg, cursor="hand2")
        row.pack(fill="x", pady=2)
        tk.Label(row, text=title, bg=bg, fg=fg, font=("Segoe UI", 9), anchor="w").pack(
            side="left", padx=(10, 4), pady=7
        )
        tk.Label(row, text=str(count), bg=bg, fg=C["dim"], font=("Segoe UI", 8)).pack(side="right", padx=10)
        row.bind("<Button-1>", lambda _e, v=value: self.set_machine(v))
        for child in row.winfo_children():
            child.bind("<Button-1>", lambda _e, v=value: self.set_machine(v))

    def set_machine(self, value: str) -> None:
        self.machine_filter = value
        self.render_machines()
        self.render_accounts()
        label = value or "все машины"
        self.set_status(f"Фильтр: {label}")

    def render_accounts(self) -> None:
        if not hasattr(self, "rows"):
            return
        for child in self.rows.winfo_children():
            child.destroy()
        items = self.visible_accounts()
        if not items:
            tk.Label(
                self.rows,
                text="Нет учёток по текущему фильтру",
                bg=C["panel"],
                fg=C["dim"],
                font=("Segoe UI", 10),
                pady=40,
            ).pack()
        for account in items:
            AccountRow(
                self.rows,
                account,
                account.key in self.selected,
                self.toggle,
                self.run_one,
            ).pack(fill="x", pady=3, padx=4)
        self.count_label.configure(text=f"Выбрано: {len(self.selected)}")

    def toggle(self, account: core.Account) -> None:
        if account.key in self.selected:
            self.selected.discard(account.key)
        else:
            self.selected.add(account.key)
        self.render_accounts()

    def set_visible_selected(self, value: bool) -> None:
        keys = {item.key for item in self.visible_accounts()}
        if value:
            self.selected |= keys
        else:
            self.selected -= keys
        self.render_accounts()

    def _select_visible(self, event: tk.Event | None = None):
        self.set_visible_selected(True)
        return "break"

    def selected_accounts(self) -> list[core.Account]:
        if not self.data:
            return []
        lookup = {item.key: item for item in self.data.accounts}
        return [lookup[key] for key in self.selected if key in lookup]

    def run_one(self, action: str, account: core.Account) -> None:
        self._start_jobs([(action, account)])

    def run_selected(self, action: str) -> None:
        accounts = self.selected_accounts()
        if not accounts:
            self.set_status("Ничего не выбрано")
            return
        self._start_jobs([(action, item) for item in accounts])

    def _start_jobs(self, jobs: list[tuple[str, core.Account]]) -> None:
        if self.busy:
            self.set_status("Дождитесь завершения текущих подключений")
            return
        if not self.data:
            return
        self.busy = True
        settings = self.data.settings
        thread = threading.Thread(target=self._worker, args=(jobs, settings), daemon=True)
        thread.start()

    def _worker(self, jobs: list[tuple[str, core.Account]], settings: core.Settings) -> None:
        errors: list[str] = []
        total = len(jobs)
        for index, (action, account) in enumerate(jobs, start=1):
            label = {"rdp": "RDP", "shadow": "Shadow", "control": "Shadow Control"}[action]
            self.after(0, lambda i=index, t=total, n=account.name, l=label: self.set_status(f"{l} {i}/{t}: {n}"))
            try:
                if action == "rdp":
                    core.connect_rdp(account, settings)
                else:
                    session = core.connect_shadow(account, settings, control=action == "control")
                    self.after(
                        0,
                        lambda n=account.name, s=session: self.set_status(
                            f"{n}: сессия {s.session_id} ({s.state_name})"
                        ),
                    )
            except Exception as exc:
                errors.append(f"{account.name}: {exc}")
            if index < total:
                core.staggered_pause(settings)
        self.after(0, lambda: self._done(total, errors))

    def _done(self, total: int, errors: list[str]) -> None:
        self.busy = False
        if errors:
            self.set_status(f"Готово с ошибками: {len(errors)} из {total}")
            self._dialog("Часть подключений не удалась", "\n".join(errors), danger=True)
        else:
            self.set_status(f"Запущено подключений: {total}")

    def open_json(self) -> None:
        path = core.accounts_path()
        if not path.exists():
            self.set_status("accounts.json не найден")
            return
        os.startfile(path)  # noqa: S606

    def clear_cache(self) -> None:
        if not self._confirm(
            "Очистить кэш RDP?",
            "Будут удалены локальный кэш mstsc, история подключений и сохранённые TERMSRV-учётные данные Windows.",
        ):
            return

        def work() -> None:
            try:
                result = core.clear_rdp_cache()
            except Exception as exc:
                self.after(0, lambda: self._dialog("Ошибка очистки", str(exc), danger=True))
                return
            summary = (
                f"Файлы: {result.files}\n"
                f"Записи реестра: {result.registry_keys}\n"
                f"Учётные данные: {result.credentials}"
            )
            if result.errors:
                summary += "\n\n" + "\n".join(result.errors[:8])
            self.after(0, lambda: self._after_cache(summary, bool(result.errors)))

        threading.Thread(target=work, daemon=True).start()

    def _after_cache(self, summary: str, had_errors: bool) -> None:
        self.set_status("Кэш RDP очищен" if not had_errors else "Кэш очищен с замечаниями")
        self._dialog("Кэш RDP", summary, danger=had_errors)

    def _dialog(self, title: str, body: str, danger: bool = False) -> None:
        win = tk.Toplevel(self)
        win.title(title)
        win.configure(bg=C["panel"])
        win.transient(self)
        win.resizable(False, False)
        tk.Label(win, text=title, bg=C["panel"], fg=C["danger"] if danger else C["text"], font=("Segoe UI Semibold", 11)).pack(
            anchor="w", padx=18, pady=(16, 8)
        )
        tk.Label(
            win,
            text=body,
            bg=C["panel"],
            fg=C["muted"],
            font=("Segoe UI", 9),
            justify="left",
            wraplength=520,
        ).pack(anchor="w", padx=18, pady=(0, 16))
        PillButton(win, "Закрыть", win.destroy, kind="ghost").pack(anchor="e", padx=18, pady=(0, 16))
        win.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - win.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - win.winfo_height()) // 3
        win.geometry(f"+{x}+{y}")
        win.grab_set()

    def _confirm(self, title: str, body: str) -> bool:
        result = {"ok": False}
        win = tk.Toplevel(self)
        win.title(title)
        win.configure(bg=C["panel"])
        win.transient(self)
        win.resizable(False, False)
        tk.Label(win, text=title, bg=C["panel"], fg=C["text"], font=("Segoe UI Semibold", 11)).pack(
            anchor="w", padx=18, pady=(16, 8)
        )
        tk.Label(win, text=body, bg=C["panel"], fg=C["muted"], font=("Segoe UI", 9), wraplength=480, justify="left").pack(
            anchor="w", padx=18, pady=(0, 16)
        )
        bar = tk.Frame(win, bg=C["panel"])
        bar.pack(fill="x", padx=18, pady=(0, 16))

        def accept() -> None:
            result["ok"] = True
            win.destroy()

        PillButton(bar, "Отмена", win.destroy).pack(side="right", padx=(8, 0))
        PillButton(bar, "Очистить", accept, kind="danger").pack(side="right")
        win.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - win.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - win.winfo_height()) // 3
        win.geometry(f"+{x}+{y}")
        win.grab_set()
        self.wait_window(win)
        return result["ok"]


def main() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
