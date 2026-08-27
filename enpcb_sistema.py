#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ENPCB — Sistema Integrado de Gestão de Formação (Secretaria Pedagógica)
Escola Nacional de Protecção Civil e Bombeiros — Angola

Aplicação de secretária (desktop), 100% offline, escrita apenas com a
biblioteca padrão do Python (Tkinter + SQLite3). Não requer ligação à
Internet nem dependências externas para correr.

Como correr:
    python enpcb_sistema.py

Como instalar como executável autónomo (Windows/Mac/Linux):
    pip install pyinstaller
    pyinstaller --onefile --windowed --name ENPCB enpcb_sistema.py

Os dados ficam guardados numa base de dados SQLite local, em:
    Windows:  %USERPROFILE%\\ENPCB\\dados\\enpcb.db
    Mac/Linux: ~/ENPCB/dados/enpcb.db

Utilizador predefinido no primeiro arranque:  admin / admin
"""

import os
import sys
import csv
import json
import uuid
import sqlite3
import datetime
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

APP_VERSION = "1.0.0"

# =====================================================================
#  Caminhos e base de dados
# =====================================================================

def app_data_dir():
    home = os.path.expanduser("~")
    d = os.path.join(home, "ENPCB", "dados")
    os.makedirs(d, exist_ok=True)
    return d

DB_PATH = os.path.join(app_data_dir(), "enpcb.db")
CERT_DIR = os.path.join(app_data_dir(), "certificados")
os.makedirs(CERT_DIR, exist_ok=True)


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY, nome TEXT, utilizador TEXT UNIQUE, senha TEXT,
    perfil TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS formandos (
    id TEXT PRIMARY KEY, nome TEXT, numero_bi TEXT, data_nascimento TEXT,
    genero TEXT, contacto TEXT, email TEXT, provincia TEXT, endereco TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS instrutores (
    id TEXT PRIMARY KEY, nome TEXT, especialidade TEXT, categoria TEXT,
    contacto TEXT, email TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS cursos (
    id TEXT PRIMARY KEY, nome TEXT, area TEXT, nivel TEXT,
    duracao_horas TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS disciplinas (
    id TEXT PRIMARY KEY, nome TEXT, curso_id TEXT, instrutor_id TEXT,
    carga_horaria TEXT, created_at TEXT,
    FOREIGN KEY(curso_id) REFERENCES cursos(id),
    FOREIGN KEY(instrutor_id) REFERENCES instrutores(id)
);
CREATE TABLE IF NOT EXISTS turmas (
    id TEXT PRIMARY KEY, codigo TEXT, curso_id TEXT, ano_letivo TEXT,
    turno TEXT, coordenador_id TEXT, local TEXT, data_inicio TEXT,
    data_fim TEXT, estado TEXT, created_at TEXT,
    FOREIGN KEY(curso_id) REFERENCES cursos(id),
    FOREIGN KEY(coordenador_id) REFERENCES instrutores(id)
);
CREATE TABLE IF NOT EXISTS matriculas (
    id TEXT PRIMARY KEY, numero_processo TEXT, formando_id TEXT,
    turma_id TEXT, data_matricula TEXT, estado TEXT, created_at TEXT,
    FOREIGN KEY(formando_id) REFERENCES formandos(id),
    FOREIGN KEY(turma_id) REFERENCES turmas(id)
);
CREATE TABLE IF NOT EXISTS notas (
    id TEXT PRIMARY KEY, matricula_id TEXT, disciplina_id TEXT,
    nota_continua TEXT, exame_final TEXT, created_at TEXT,
    UNIQUE(matricula_id, disciplina_id),
    FOREIGN KEY(matricula_id) REFERENCES matriculas(id),
    FOREIGN KEY(disciplina_id) REFERENCES disciplinas(id)
);
CREATE TABLE IF NOT EXISTS presencas (
    id TEXT PRIMARY KEY, turma_id TEXT, disciplina_id TEXT, data TEXT,
    created_at TEXT, UNIQUE(turma_id, disciplina_id, data),
    FOREIGN KEY(turma_id) REFERENCES turmas(id),
    FOREIGN KEY(disciplina_id) REFERENCES disciplinas(id)
);
CREATE TABLE IF NOT EXISTS presenca_registos (
    id TEXT PRIMARY KEY, presenca_id TEXT, formando_id TEXT, presente INTEGER,
    UNIQUE(presenca_id, formando_id),
    FOREIGN KEY(presenca_id) REFERENCES presencas(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS certificados (
    id TEXT PRIMARY KEY, matricula_id TEXT, numero TEXT, data_emissao TEXT,
    media_final TEXT, situacao_final TEXT, created_at TEXT,
    FOREIGN KEY(matricula_id) REFERENCES matriculas(id)
);
CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT);
"""


def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    cur = conn.execute("SELECT COUNT(*) AS n FROM users")
    if cur.fetchone()["n"] == 0:
        conn.execute(
            "INSERT INTO users (id,nome,utilizador,senha,perfil,created_at) VALUES (?,?,?,?,?,?)",
            (new_id(), "Administrador", "admin", "admin", "Administrador", now_iso()),
        )
        conn.commit()
    conn.close()


def new_id():
    return str(uuid.uuid4())


def now_iso():
    return datetime.datetime.now().isoformat(timespec="seconds")


def today_str():
    return datetime.date.today().isoformat()


def get_config(key, default=0):
    conn = get_conn()
    row = conn.execute("SELECT value FROM config WHERE key=?", (key,)).fetchone()
    conn.close()
    return int(row["value"]) if row else default


def bump_config(key):
    val = get_config(key, 0) + 1
    conn = get_conn()
    conn.execute("INSERT INTO config (key,value) VALUES (?,?) "
                 "ON CONFLICT(key) DO UPDATE SET value=?", (key, str(val), str(val)))
    conn.commit()
    conn.close()
    return val


# =====================================================================
#  Cálculos pedagógicos (notas / assiduidade / situação)
# =====================================================================

def calc_nota(conn, matricula_id, disciplina_id):
    m = conn.execute("SELECT * FROM matriculas WHERE id=?", (matricula_id,)).fetchone()
    sessions = conn.execute(
        "SELECT id FROM presencas WHERE turma_id=? AND disciplina_id=?",
        (m["turma_id"], disciplina_id),
    ).fetchall()
    total_sessions = len(sessions)
    faltas = 0
    if total_sessions:
        ids = [s["id"] for s in sessions]
        q = "SELECT COUNT(*) AS n FROM presenca_registos WHERE presente=0 AND formando_id=? AND presenca_id IN (%s)" % (
            ",".join("?" * len(ids))
        )
        faltas = conn.execute(q, [m["formando_id"]] + ids).fetchone()["n"]
    assiduidade = round(max(0.0, (1 - faltas / total_sessions) * 100), 2) if total_sessions else 100.0

    nota = conn.execute(
        "SELECT * FROM notas WHERE matricula_id=? AND disciplina_id=?",
        (matricula_id, disciplina_id),
    ).fetchone()
    media = None
    if nota and nota["nota_continua"] not in (None, "") and nota["exame_final"] not in (None, ""):
        try:
            nc = float(nota["nota_continua"]); ex = float(nota["exame_final"])
            media = round((nc + ex) / 2, 2)
        except ValueError:
            media = None
    situacao = "Incompleto"
    if media is not None:
        if total_sessions > 0 and assiduidade < 75:
            situacao = "Excluído por Faltas"
        elif media >= 10:
            situacao = "Aprovado"
        else:
            situacao = "Reprovado"
    return {"media": media, "assiduidade": assiduidade, "situacao": situacao,
            "total_sessions": total_sessions, "faltas": faltas}


def matricula_situacao(conn, matricula_id):
    m = conn.execute("SELECT * FROM matriculas WHERE id=?", (matricula_id,)).fetchone()
    if not m:
        return {"media": None, "situacao": "—", "assiduidade": None}
    turma = conn.execute("SELECT * FROM turmas WHERE id=?", (m["turma_id"],)).fetchone()
    discs = conn.execute("SELECT * FROM disciplinas WHERE curso_id=?", (turma["curso_id"],)).fetchall() if turma else []
    if not discs:
        return {"media": None, "situacao": "Sem Disciplinas", "assiduidade": None}
    calcs = [calc_nota(conn, matricula_id, d["id"]) for d in discs]
    completos = [c for c in calcs if c["media"] is not None]
    if len(completos) < len(discs):
        any_excl = any(c["situacao"] == "Excluído por Faltas" for c in calcs)
        return {"media": None, "situacao": "Excluído por Faltas" if any_excl else "Incompleto", "assiduidade": None}
    media = round(sum(c["media"] for c in completos) / len(completos), 2)
    assiduidade = round(sum(c["assiduidade"] for c in completos) / len(completos), 2)
    if all(c["situacao"] == "Aprovado" for c in completos):
        situacao = "Aprovado"
    elif any(c["situacao"] == "Excluído por Faltas" for c in completos):
        situacao = "Excluído por Faltas"
    else:
        situacao = "Reprovado"
    return {"media": media, "situacao": situacao, "assiduidade": assiduidade}


# =====================================================================
#  Aparência (cores / fontes) — tema institucional vermelho
# =====================================================================

RED_800 = "#7A1017"
RED_700 = "#8E1620"
RED_600 = "#B21F2B"
RED_500 = "#C1272D"
RED_100 = "#F7DEDF"
NAVY_900 = "#122845"
GOLD = "#F0BE2F"
GREEN_OK = "#2E7D4F"
GREEN_100 = "#DEEEE2"
PAPER = "#F5F1EC"
CARD = "#FFFFFF"
INK_900 = "#241A1B"
INK_600 = "#5B4E4F"
INK_400 = "#8C7F80"
LINE = "#E7DFD6"

F_BASE = ("Segoe UI", 10)
F_BASE_B = ("Segoe UI", 10, "bold")
F_H1 = ("Segoe UI", 18, "bold")
F_H2 = ("Segoe UI", 13, "bold")
F_H3 = ("Segoe UI", 11, "bold")
F_MONO = ("Consolas", 10)
F_BIG = ("Georgia", 40, "bold")
F_SMALL = ("Segoe UI", 9)


# =====================================================================
#  Definição das entidades (CRUD genérico)
# =====================================================================
# type: text | number | date | select | ref | password
# ref fields point to another entity's table and display its 'nome'/'codigo'

ENTITIES = {
    "formandos": {
        "table": "formandos", "label": "Formando", "label_plural": "Formandos", "icon": "🎓",
        "fields": [
            ("nome", "Nome completo", "text", True, None),
            ("numero_bi", "Nº do BI / Documento", "text", True, None),
            ("data_nascimento", "Data de nascimento (AAAA-MM-DD)", "date", False, None),
            ("genero", "Género", "select", False, ["Masculino", "Feminino"]),
            ("contacto", "Contacto (telefone)", "text", False, None),
            ("email", "E-mail", "text", False, None),
            ("provincia", "Província", "text", False, None),
            ("endereco", "Endereço", "text", False, None),
        ],
        "columns": [("nome", "Nome"), ("numero_bi", "Nº BI"), ("contacto", "Contacto"), ("provincia", "Província")],
    },
    "instrutores": {
        "table": "instrutores", "label": "Instrutor", "label_plural": "Instrutores", "icon": "👨‍🏫",
        "fields": [
            ("nome", "Nome completo", "text", True, None),
            ("especialidade", "Especialidade", "text", True, None),
            ("categoria", "Categoria", "select", False, ["Efectivo", "Convidado", "Cooperante"]),
            ("contacto", "Contacto (telefone)", "text", False, None),
            ("email", "E-mail", "text", False, None),
        ],
        "columns": [("nome", "Nome"), ("especialidade", "Especialidade"), ("categoria", "Categoria"), ("contacto", "Contacto")],
    },
    "cursos": {
        "table": "cursos", "label": "Curso", "label_plural": "Cursos", "icon": "📘",
        "fields": [
            ("nome", "Nome do curso", "text", True, None),
            ("area", "Área", "select", False, ["Combate a Incêndios", "Protecção Civil",
             "Socorrismo e Emergência Médica", "Busca e Salvamento", "Gestão de Risco de Desastres",
             "Administração e Logística"]),
            ("nivel", "Nível", "select", False, ["Básico", "Intermédio", "Avançado", "Especialização"]),
            ("duracao_horas", "Duração (horas)", "number", True, None),
        ],
        "columns": [("nome", "Nome"), ("area", "Área"), ("nivel", "Nível"), ("duracao_horas", "Duração (h)")],
    },
    "disciplinas": {
        "table": "disciplinas", "label": "Disciplina", "label_plural": "Disciplinas", "icon": "📗",
        "fields": [
            ("nome", "Nome da disciplina", "text", True, None),
            ("curso_id", "Curso", "ref", True, "cursos"),
            ("instrutor_id", "Instrutor responsável", "ref", False, "instrutores"),
            ("carga_horaria", "Carga horária (horas)", "number", False, None),
        ],
        "columns": [("nome", "Nome"), ("curso_id", "Curso"), ("instrutor_id", "Instrutor"), ("carga_horaria", "Carga (h)")],
    },
    "turmas": {
        "table": "turmas", "label": "Turma", "label_plural": "Turmas", "icon": "👥",
        "fields": [
            ("curso_id", "Curso", "ref", True, "cursos"),
            ("ano_letivo", "Ano lectivo", "text", True, None),
            ("turno", "Turno", "select", False, ["Manhã", "Tarde", "Noite"]),
            ("coordenador_id", "Coordenador (instrutor)", "ref", False, "instrutores"),
            ("local", "Local de formação", "text", False, None),
            ("data_inicio", "Data de início (AAAA-MM-DD)", "date", False, None),
            ("data_fim", "Data de conclusão (AAAA-MM-DD)", "date", False, None),
            ("estado", "Estado", "select", False, ["Planeada", "Em curso", "Concluída"]),
        ],
        "columns": [("codigo", "Código"), ("curso_id", "Curso"), ("ano_letivo", "Ano"), ("turno", "Turno"), ("estado", "Estado")],
        "auto_code": True,
    },
    "matriculas": {
        "table": "matriculas", "label": "Matrícula", "label_plural": "Matrículas", "icon": "📝",
        "fields": [
            ("formando_id", "Formando", "ref", True, "formandos"),
            ("turma_id", "Turma", "ref", True, "turmas"),
            ("data_matricula", "Data de matrícula (AAAA-MM-DD)", "date", False, None),
            ("estado", "Estado", "select", False, ["Activo", "Concluído", "Desistente", "Transferido"]),
        ],
        "columns": [("numero_processo", "Nº Processo"), ("formando_id", "Formando"), ("turma_id", "Turma"), ("estado", "Estado")],
        "auto_processo": True,
    },
    "users": {
        "table": "users", "label": "Utilizador", "label_plural": "Utilizadores e Permissões", "icon": "🛡",
        "fields": [
            ("nome", "Nome completo", "text", True, None),
            ("utilizador", "Utilizador (login)", "text", True, None),
            ("senha", "Senha", "password", True, None),
            ("perfil", "Perfil de acesso", "select", False,
             ["Administrador", "Secretário Pedagógico", "Instrutor", "Consulta"]),
        ],
        "columns": [("nome", "Nome"), ("utilizador", "Utilizador"), ("perfil", "Perfil")],
    },
}


def ref_label(conn, ref_table, ref_id):
    if not ref_id:
        return "—"
    row = conn.execute("SELECT * FROM %s WHERE id=?" % ref_table, (ref_id,)).fetchone()
    if not row:
        return "—"
    keys = row.keys()
    if "nome" in keys and row["nome"]:
        return row["nome"]
    if "codigo" in keys and row["codigo"]:
        return row["codigo"]
    if "numero_processo" in keys and row["numero_processo"]:
        return row["numero_processo"]
    return "—"


def field_def(entity, key):
    for f in ENTITIES[entity]["fields"]:
        if f[0] == key:
            return f
    return None


# =====================================================================
#  Widgets auxiliares
# =====================================================================

class ScrollableFrame(ttk.Frame):
    """Frame com barra de deslocamento vertical, para conteúdo longo."""
    def __init__(self, parent, bg=PAPER, **kw):
        super().__init__(parent, **kw)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.canvas.bind("<Configure>", self._on_resize)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")
        self.canvas.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-2, "units"))
        self.canvas.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(2, "units"))

    def _on_resize(self, event):
        self.canvas.itemconfig(self.win, width=event.width)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


def pill(parent, text, color, bg):
    lbl = tk.Label(parent, text=text, fg=color, bg=bg, font=F_SMALL, padx=8, pady=2)
    return lbl


def situacao_colors(situacao):
    if situacao in ("Aprovado", "Concluído", "Concluída"):
        return GREEN_OK, GREEN_100
    if situacao in ("Reprovado", "Excluído por Faltas", "Desistente"):
        return RED_700, RED_100
    if situacao in ("Activo", "Em curso"):
        return "#C9971E", "#FCEFD2"
    return INK_600, "#EDE8E1"


def card(parent, **kw):
    f = tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1, **kw)
    return f


def h_section(parent, text, sub=None):
    box = tk.Frame(parent, bg=PAPER)
    tk.Label(box, text=text, font=F_H1, bg=PAPER, fg=NAVY_900).pack(anchor="w")
    if sub:
        tk.Label(box, text=sub, font=F_BASE, bg=PAPER, fg=INK_600, wraplength=760, justify="left").pack(anchor="w", pady=(3, 0))
    return box


def btn(parent, text, command, kind="ghost", small=False):
    styles = {
        "primary": {"bg": RED_600, "fg": "white", "activebackground": RED_500, "activeforeground": "white"},
        "ghost": {"bg": "white", "fg": NAVY_900, "activebackground": "#FBF6F0", "activeforeground": RED_600,
                  "highlightbackground": LINE, "highlightthickness": 1, "bd": 0},
        "danger": {"bg": PAPER, "fg": RED_600, "activebackground": RED_100, "activeforeground": RED_700},
    }
    s = styles.get(kind, styles["ghost"])
    b = tk.Button(parent, text=text, command=command, font=F_SMALL if small else F_BASE_B,
                  relief="flat", cursor="hand2", padx=12 if small else 16, pady=4 if small else 8, **s)
    return b


# =====================================================================
#  Aplicação principal
# =====================================================================

class ENPCBApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ENPCB — Sistema Integrado de Gestão de Formação")
        self.root.geometry("1240x780")
        self.root.minsize(1000, 640)
        self.root.configure(bg=PAPER)
        self.auth_user = None
        self.current_route = "dashboard"

        # estado de navegação partilhado entre écrans
        self.state = {
            "search": {}, "pauta_turma": "", "pauta_disc": "",
            "pres_turma": "", "pres_disc": "", "pres_data": today_str(),
            "medias_turma": "", "pesquisa_termo": "",
        }

        self.build_login_screen()

    # ------------------------------------------------------------------
    # LOGIN
    # ------------------------------------------------------------------
    def build_login_screen(self):
        for w in self.root.winfo_children():
            w.destroy()
        self.auth_user = None

        outer = tk.Frame(self.root, bg=RED_700)
        outer.pack(fill="both", expand=True)

        header = tk.Frame(outer, bg=RED_700)
        header.pack(pady=(36, 10))
        tk.Label(header, text="REPÚBLICA DE ANGOLA", font=F_H3, bg=RED_700, fg="white").pack()
        tk.Label(header, text="MINISTÉRIO DO INTERIOR", font=F_SMALL, bg=RED_700, fg="#F6DCDD").pack()
        tk.Label(header, text="ESCOLA NACIONAL DE PROTECÇÃO CIVIL E BOMBEIROS",
                 font=("Segoe UI", 14, "bold"), bg=RED_700, fg="white").pack(pady=(8, 0))
        tk.Label(header, text="ENPCB", font=F_BIG, bg=RED_700, fg="white").pack()
        ribbon = tk.Label(header, text="  SECRETARIA PEDAGÓGICA  ", font=F_H3, bg=RED_500, fg="white")
        ribbon.pack(pady=(0, 8))
        tk.Label(header, text='"Formar para Prevenir, Proteger e Salvar Vidas"',
                 font=("Segoe UI", 10, "italic"), bg=RED_700, fg="#F6E4CF").pack()

        card_f = tk.Frame(outer, bg="white", padx=34, pady=26)
        card_f.pack(pady=18)
        tk.Label(card_f, text="🎓  Acesso ao Sistema", font=F_H2, bg="white", fg=NAVY_900).pack(anchor="w")
        tk.Label(card_f, text="Introduza as suas credenciais", font=F_SMALL, bg="white", fg=INK_600).pack(anchor="w", pady=(0, 14))

        self.login_error = tk.Label(card_f, text="", font=F_SMALL, bg=RED_100, fg=RED_700, padx=10, pady=6)

        tk.Label(card_f, text="Utilizador", font=F_SMALL, bg="white", fg=INK_600, anchor="w").pack(fill="x")
        self.ent_user = tk.Entry(card_f, font=F_BASE, width=32, relief="solid", bd=1)
        self.ent_user.pack(fill="x", pady=(2, 10), ipady=5)

        tk.Label(card_f, text="Senha", font=F_SMALL, bg="white", fg=INK_600, anchor="w").pack(fill="x")
        self.ent_pass = tk.Entry(card_f, font=F_BASE, width=32, relief="solid", bd=1, show="•")
        self.ent_pass.pack(fill="x", pady=(2, 14), ipady=5)

        btn(card_f, "➜  Entrar", self.try_login, kind="primary").pack(fill="x", ipady=4)
        tk.Label(card_f, text="Primeiro acesso? Utilizador: admin   ·   Senha: admin",
                 font=F_SMALL, bg="white", fg=INK_400).pack(pady=(10, 0))

        self.ent_pass.bind("<Return>", lambda e: self.try_login())
        self.ent_user.bind("<Return>", lambda e: self.ent_pass.focus())
        self.ent_user.focus()

        tk.Label(outer, text='"Prevenir é Salvar"', font=("Segoe UI", 11, "italic bold"),
                 bg=NAVY_900, fg="white", pady=10).pack(fill="x", side="bottom")
        tk.Label(outer, text=f"ENPCB · Sistema Local · v{APP_VERSION} · Dados em {DB_PATH}",
                 font=F_SMALL, bg=RED_700, fg="#F6DCDD").pack(side="bottom", pady=4)

    def try_login(self):
        u = self.ent_user.get().strip()
        p = self.ent_pass.get()
        conn = get_conn()
        row = conn.execute("SELECT * FROM users WHERE utilizador=? AND senha=?", (u, p)).fetchone()
        conn.close()
        if not row:
            self.login_error.config(text="Utilizador ou senha inválidos.")
            self.login_error.pack(fill="x", pady=(0, 10), before=self.ent_user.master.winfo_children()[2])
            return
        self.auth_user = dict(row)
        self.build_app_shell()

    def logout(self):
        self.build_login_screen()

    # ------------------------------------------------------------------
    # APP SHELL
    # ------------------------------------------------------------------
    NAV = [
        ("dashboard", "🏠", "Dashboard"),
        ("formandos", "🎓", "Formandos"),
        ("instrutores", "👨‍🏫", "Instrutores"),
        ("cursos", "📘", "Cursos"),
        ("turmas", "👥", "Turmas"),
        ("disciplinas", "📗", "Disciplinas"),
        ("matriculas", "📝", "Matrículas"),
        ("pautas", "🗂", "Mini Pauta"),
        ("presencas", "✅", "Presenças"),
        ("medias", "📊", "Médias e Resultados"),
        ("certificados", "🏅", "Certificados"),
        ("relatorios", "📑", "Relatórios"),
        ("pesquisa", "🔍", "Pesquisa"),
        ("backup", "☁", "Backup"),
        ("users", "🛡", "Utilizadores e Permissões"),
    ]

    def build_app_shell(self):
        for w in self.root.winfo_children():
            w.destroy()

        header = tk.Frame(self.root, bg=RED_600, height=64)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)
        left = tk.Frame(header, bg=RED_600)
        left.pack(side="left", padx=20)
        tk.Label(left, text="ENPCB", font=("Georgia", 20, "bold"), bg=RED_600, fg="white").pack(anchor="w", pady=(8, 0))
        tk.Label(left, text="ESCOLA NACIONAL DE PROTECÇÃO CIVIL E BOMBEIROS", font=F_SMALL,
                 bg=RED_600, fg="#F6DCDD").pack(anchor="w")
        right = tk.Frame(header, bg=RED_600)
        right.pack(side="right", padx=20)
        initials = (self.auth_user["nome"] or "?").strip()[0].upper()
        tk.Label(right, text=initials, font=F_H3, bg="white", fg=RED_600, width=3, height=1).pack(side="left", padx=(0, 10))
        who = tk.Frame(right, bg=RED_600)
        who.pack(side="left")
        tk.Label(who, text=self.auth_user["nome"], font=F_BASE_B, bg=RED_600, fg="white").pack(anchor="w")
        tk.Label(who, text="Perfil: " + self.auth_user["perfil"], font=F_SMALL, bg=RED_600, fg="#F6DCDD").pack(anchor="w")

        body = tk.Frame(self.root, bg=PAPER)
        body.pack(fill="both", expand=True)

        sidebar = tk.Frame(body, bg="white", width=248)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        self.nav_buttons = {}
        nav_wrap = tk.Frame(sidebar, bg="white")
        nav_wrap.pack(fill="x", pady=10, padx=10)
        for key, ic, label in self.NAV:
            b = tk.Button(nav_wrap, text=f"  {ic}  {label}", anchor="w", font=("Segoe UI", 9, "bold"),
                          relief="flat", bg="white", fg=INK_900, activebackground=RED_100,
                          cursor="hand2", command=lambda k=key: self.navigate(k), padx=6, pady=9,
                          wraplength=210, justify="left")
            b.pack(fill="x", pady=1)
            self.nav_buttons[key] = b

        btn(sidebar, "↩  Sair", self.logout, kind="primary").pack(side="bottom", fill="x", padx=10, pady=14)

        self.content = ScrollableFrame(body, bg=PAPER)
        self.content.pack(side="left", fill="both", expand=True)

        footer = tk.Frame(self.root, bg="white", height=28)
        footer.pack(fill="x", side="bottom")
        tk.Label(footer, text="ENPCB - Sistema Integrado de Gestão de Formação (offline)", font=F_SMALL,
                 bg="white", fg=INK_400).pack(side="left", padx=16)
        tk.Label(footer, text=f"Versão {APP_VERSION}", font=F_SMALL, bg="white", fg=INK_400).pack(side="right", padx=16)

        self.navigate("dashboard")

    def navigate(self, route):
        self.current_route = route
        for key, b in self.nav_buttons.items():
            if key == route:
                b.configure(bg=RED_600, fg="white", activebackground=RED_600)
            else:
                b.configure(bg="white", fg=INK_900, activebackground=RED_100)
        for w in self.content.inner.winfo_children():
            w.destroy()
        builder = getattr(self, "view_" + route, None)
        if builder:
            builder(self.content.inner)
        self.content.canvas.yview_moveto(0)

    def toast(self, msg, ok=True):
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.configure(bg=NAVY_900 if ok else RED_700)
        x = self.root.winfo_x() + self.root.winfo_width() - 340
        y = self.root.winfo_y() + self.root.winfo_height() - 90
        win.geometry(f"300x50+{x}+{y}")
        tk.Label(win, text=msg, bg=NAVY_900 if ok else RED_700, fg="white", font=F_BASE,
                 wraplength=280, justify="left", padx=12, pady=10).pack(fill="both", expand=True)
        win.after(2600, win.destroy)

    # ------------------------------------------------------------------
    # DASHBOARD
    # ------------------------------------------------------------------
    def view_dashboard(self, parent):
        conn = get_conn()
        n_formandos = conn.execute("SELECT COUNT(*) n FROM formandos").fetchone()["n"]
        n_instrutores = conn.execute("SELECT COUNT(*) n FROM instrutores").fetchone()["n"]
        n_cursos = conn.execute("SELECT COUNT(*) n FROM cursos").fetchone()["n"]
        n_turmas = conn.execute("SELECT COUNT(*) n FROM turmas").fetchone()["n"]

        regs = conn.execute("SELECT presente FROM presenca_registos").fetchall()
        taxa = round(sum(1 for r in regs if r["presente"]) / len(regs) * 100, 1) if regs else None

        h_section(parent, f"Bem-vindo(a), {self.auth_user['nome']}",
                  "Sistema Integrado de Gestão de Formação — visão consolidada da actividade pedagógica.").pack(
            anchor="w", padx=24, pady=(20, 14), fill="x")

        kpi_wrap = tk.Frame(parent, bg=PAPER)
        kpi_wrap.pack(fill="x", padx=24)
        kpis = [("🎓", str(n_formandos), "Formandos", "formandos"),
                ("👨‍🏫", str(n_instrutores), "Instrutores", "instrutores"),
                ("📘", str(n_cursos), "Cursos", "cursos"),
                ("👥", str(n_turmas), "Turmas", "turmas"),
                ("✅", (f"{taxa}%" if taxa is not None else "—"), "Taxa de Presença", "presencas")]
        for ic, num, label, route in kpis:
            c = card(kpi_wrap, padx=16, pady=14)
            c.pack(side="left", padx=(0, 12), fill="both", expand=True)
            tk.Label(c, text=ic, font=("Segoe UI", 16), bg=CARD, fg=RED_600).pack(anchor="w")
            tk.Label(c, text=num, font=("Segoe UI", 22, "bold"), bg=CARD, fg=NAVY_900).pack(anchor="w")
            tk.Label(c, text=label, font=F_SMALL, bg=CARD, fg=INK_600).pack(anchor="w")
            tk.Button(c, text="Ver todos →", font=F_SMALL, bg=CARD, fg=RED_600, relief="flat",
                      cursor="hand2", command=lambda r=route: self.navigate(r)).pack(anchor="w", pady=(4, 0))

        row2 = tk.Frame(parent, bg=PAPER)
        row2.pack(fill="x", padx=24, pady=18)

        # Formandos por curso (barras horizontais simples)
        c1 = card(row2, padx=16, pady=14)
        c1.pack(side="left", fill="both", expand=True, padx=(0, 10))
        tk.Label(c1, text="Formandos por Curso", font=F_H3, bg=CARD, fg=NAVY_900).pack(anchor="w")
        counts = conn.execute("""
            SELECT c.nome AS nome, COUNT(*) AS n FROM matriculas m
            JOIN turmas t ON t.id = m.turma_id
            JOIN cursos c ON c.id = t.curso_id
            GROUP BY c.id ORDER BY n DESC
        """).fetchall()
        if not counts:
            tk.Label(c1, text="Sem matrículas para apresentar.", font=F_SMALL, bg=CARD, fg=INK_600).pack(anchor="w", pady=10)
        else:
            maxn = max(r["n"] for r in counts)
            for r in counts[:8]:
                row = tk.Frame(c1, bg=CARD)
                row.pack(fill="x", pady=3)
                tk.Label(row, text=r["nome"], font=F_SMALL, bg=CARD, fg=INK_900, width=22, anchor="w").pack(side="left")
                bar_bg = tk.Frame(row, bg="#EDE4D8", height=14, width=180)
                bar_bg.pack(side="left", padx=6)
                bar_bg.pack_propagate(False)
                w = max(4, int(180 * r["n"] / maxn))
                tk.Frame(bar_bg, bg=RED_600, height=14, width=w).place(x=0, y=0)
                tk.Label(row, text=str(r["n"]), font=F_SMALL, bg=CARD, fg=INK_900).pack(side="left")

        # Turmas por estado
        c2 = card(row2, padx=16, pady=14)
        c2.pack(side="left", fill="both", expand=True, padx=(10, 0))
        tk.Label(c2, text="Turmas por Estado", font=F_H3, bg=CARD, fg=NAVY_900).pack(anchor="w")
        estados = conn.execute("SELECT estado, COUNT(*) n FROM turmas GROUP BY estado").fetchall()
        if not estados:
            tk.Label(c2, text="Sem turmas para apresentar.", font=F_SMALL, bg=CARD, fg=INK_600).pack(anchor="w", pady=10)
        else:
            colors = {"Planeada": INK_400, "Em curso": "#C9971E", "Concluída": GREEN_OK}
            for r in estados:
                fg, bgc = situacao_colors(r["estado"])
                row = tk.Frame(c2, bg=CARD)
                row.pack(fill="x", pady=4)
                pill(row, r["estado"] or "—", fg, bgc).pack(side="left")
                tk.Label(row, text=str(r["n"]), font=F_BASE_B, bg=CARD, fg=NAVY_900).pack(side="right")

        row3 = tk.Frame(parent, bg=PAPER)
        row3.pack(fill="x", padx=24, pady=(0, 24))

        c3 = card(row3, padx=16, pady=14)
        c3.pack(side="left", fill="both", expand=True, padx=(0, 10))
        tk.Label(c3, text="🔔 Avisos e Notificações", font=F_H3, bg=CARD, fg=NAVY_900).pack(anchor="w", pady=(0, 6))
        notices = self._dashboard_notices(conn)
        if not notices:
            tk.Label(c3, text="Sem novas notificações.", font=F_SMALL, bg=CARD, fg=INK_600).pack(anchor="w")
        for tag, title, sub in notices:
            row = tk.Frame(c3, bg=CARD)
            row.pack(fill="x", pady=5)
            fg, bgc = situacao_colors("Reprovado" if tag == "Importante" else "Activo" if tag == "Atenção" else "X")
            pill(row, tag, fg, bgc).pack(side="left", padx=(0, 8))
            txt = tk.Frame(row, bg=CARD)
            txt.pack(side="left")
            tk.Label(txt, text=title, font=F_BASE_B, bg=CARD, fg=NAVY_900, anchor="w").pack(anchor="w")
            tk.Label(txt, text=sub, font=F_SMALL, bg=CARD, fg=INK_600, anchor="w").pack(anchor="w")

        c4 = card(row3, padx=16, pady=14)
        c4.pack(side="left", fill="both", expand=True, padx=(10, 0))
        tk.Label(c4, text="🕓 Actividades Recentes", font=F_H3, bg=CARD, fg=NAVY_900).pack(anchor="w", pady=(0, 6))
        acts = self._recent_activities(conn)
        if not acts:
            tk.Label(c4, text="Sem actividade recente.", font=F_SMALL, bg=CARD, fg=INK_600).pack(anchor="w")
        for ic, text, sub, at in acts:
            row = tk.Frame(c4, bg=CARD)
            row.pack(fill="x", pady=4)
            tk.Label(row, text=ic, font=F_BASE, bg=CARD).pack(side="left", padx=(0, 8))
            txt = tk.Frame(row, bg=CARD)
            txt.pack(side="left", fill="x", expand=True)
            tk.Label(txt, text=text, font=F_BASE_B, bg=CARD, fg=NAVY_900, anchor="w").pack(anchor="w")
            tk.Label(txt, text=sub, font=F_SMALL, bg=CARD, fg=INK_600, anchor="w").pack(anchor="w")
            tk.Label(row, text=(at or "")[:16].replace("T", " "), font=F_SMALL, bg=CARD, fg=INK_400).pack(side="right")

        conn.close()

    def _dashboard_notices(self, conn):
        notices = []
        matriculas = conn.execute("SELECT id FROM matriculas").fetchall()
        aprov_sem_cert = 0
        for m in matriculas:
            sit = matricula_situacao(conn, m["id"])
            if sit["situacao"] == "Aprovado":
                has_cert = conn.execute("SELECT 1 FROM certificados WHERE matricula_id=?", (m["id"],)).fetchone()
                if not has_cert:
                    aprov_sem_cert += 1
        if aprov_sem_cert:
            notices.append(("Importante", f"{aprov_sem_cert} formando(s) aprovados sem certificado", "Aceda a Certificados para emitir."))
        turmas = conn.execute("SELECT id, curso_id FROM turmas").fetchall()
        sem_disc = sum(1 for t in turmas if not conn.execute("SELECT 1 FROM disciplinas WHERE curso_id=?", (t["curso_id"],)).fetchone())
        if sem_disc:
            notices.append(("Atenção", f"{sem_disc} turma(s) sem disciplinas associadas", "Verifique os cursos correspondentes."))
        sem_mat = sum(1 for t in turmas if not conn.execute("SELECT 1 FROM matriculas WHERE turma_id=?", (t["id"],)).fetchone())
        if sem_mat:
            notices.append(("Informação", f"{sem_mat} turma(s) ainda sem formandos matriculados", "Registe matrículas para iniciar a formação."))
        return notices[:3]

    def _recent_activities(self, conn):
        items = []
        for r in conn.execute("SELECT nome, created_at FROM formandos"):
            items.append(("🎓", "Novo formando cadastrado", r["nome"], r["created_at"]))
        for r in conn.execute("""SELECT m.created_at, f.nome fnome, t.codigo tcodigo FROM matriculas m
                                  LEFT JOIN formandos f ON f.id=m.formando_id LEFT JOIN turmas t ON t.id=m.turma_id"""):
            items.append(("📝", "Matrícula realizada", f"{r['fnome'] or '—'} — {r['tcodigo'] or '—'}", r["created_at"]))
        for r in conn.execute("""SELECT p.created_at, p.data, t.codigo tcodigo, d.nome dnome FROM presencas p
                                  LEFT JOIN turmas t ON t.id=p.turma_id LEFT JOIN disciplinas d ON d.id=p.disciplina_id"""):
            items.append(("✅", "Presença lançada", f"Turma {r['tcodigo'] or '—'} ({r['dnome'] or '—'})", r["created_at"] or r["data"]))
        for r in conn.execute("""SELECT c.created_at, c.numero, f.nome fnome FROM certificados c
                                  LEFT JOIN matriculas m ON m.id=c.matricula_id LEFT JOIN formandos f ON f.id=m.formando_id"""):
            items.append(("🏅", "Certificado emitido", f"{r['fnome'] or '—'} — {r['numero']}", r["created_at"]))
        items = [it for it in items if it[3]]
        items.sort(key=lambda x: x[3], reverse=True)
        return items[:6]

    # ------------------------------------------------------------------
    # CRUD genérico (Formandos / Instrutores / Cursos / Disciplinas /
    # Turmas / Matrículas / Utilizadores)
    # ------------------------------------------------------------------
    def view_formandos(self, parent): self._generic_list_view(parent, "formandos")
    def view_instrutores(self, parent): self._generic_list_view(parent, "instrutores")
    def view_cursos(self, parent): self._generic_list_view(parent, "cursos")
    def view_disciplinas(self, parent): self._generic_list_view(parent, "disciplinas")
    def view_turmas(self, parent): self._generic_list_view(parent, "turmas")
    def view_matriculas(self, parent): self._generic_list_view(parent, "matriculas")
    def view_users(self, parent): self._generic_list_view(parent, "users")

    def _generic_list_view(self, parent, entity):
        meta = ENTITIES[entity]
        top = tk.Frame(parent, bg=PAPER)
        top.pack(fill="x", padx=24, pady=(20, 10))
        h_section(top, f"{meta['icon']} {meta['label_plural']}").pack(side="left", anchor="w")
        btn(top, f"+ Novo {meta['label']}", lambda: self._open_form(entity, None), kind="primary").pack(side="right")

        toolbar = tk.Frame(parent, bg=PAPER)
        toolbar.pack(fill="x", padx=24)
        search_var = tk.StringVar(value=self.state["search"].get(entity, ""))
        ent = tk.Entry(toolbar, textvariable=search_var, font=F_BASE, width=32, relief="solid", bd=1)
        ent.pack(side="left", ipady=4)
        tree_holder = tk.Frame(parent, bg=PAPER)

        def refresh(*_):
            self.state["search"][entity] = search_var.get()
            for w in tree_holder.winfo_children():
                w.destroy()
            self._render_table(tree_holder, entity, search_var.get())

        btn(toolbar, "⬇ Exportar CSV", lambda: self._export_entity_csv(entity), kind="ghost", small=True).pack(side="left", padx=8)
        ent.bind("<KeyRelease>", refresh)

        tree_holder.pack(fill="both", expand=True, padx=24, pady=14)
        refresh()

    def _render_table(self, parent, entity, term):
        meta = ENTITIES[entity]
        conn = get_conn()
        rows = conn.execute(f"SELECT * FROM {meta['table']} ORDER BY created_at DESC").fetchall()
        conn.close()

        cols = [c[0] for c in meta["columns"]]
        heads = [c[1] for c in meta["columns"]]

        style = ttk.Style()
        style.configure("ENPCB.Treeview", rowheight=28, font=F_BASE, background="white", fieldbackground="white")
        style.configure("ENPCB.Treeview.Heading", font=F_SMALL)

        wrap = card(parent)
        wrap.pack(fill="both", expand=True)
        tree = ttk.Treeview(wrap, columns=cols, show="headings", style="ENPCB.Treeview", height=16)
        for c, h in zip(cols, heads):
            tree.heading(c, text=h)
            tree.column(c, width=160, anchor="w")
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True, padx=(1, 0), pady=1)
        vsb.pack(side="right", fill="y")

        conn = get_conn()
        id_by_iid = {}
        shown = 0
        for row in rows:
            values = []
            haystack = []
            for c in cols:
                fd = field_def(entity, c)
                if c == "codigo":
                    v = row["codigo"] if "codigo" in row.keys() else "—"
                elif c == "numero_processo":
                    v = row["numero_processo"] if "numero_processo" in row.keys() else "—"
                elif fd and fd[2] == "ref":
                    v = ref_label(conn, fd[4], row[c])
                elif fd and fd[2] == "password":
                    v = "••••••"
                else:
                    v = row[c] if c in row.keys() and row[c] is not None else "—"
                values.append(v)
                haystack.append(str(v))
            if term and term.lower() not in " ".join(haystack).lower():
                continue
            iid = tree.insert("", "end", values=values)
            id_by_iid[iid] = row["id"]
            shown += 1
        conn.close()

        actions = tk.Frame(parent, bg=PAPER)
        actions.pack(fill="x", pady=8)
        tk.Label(actions, text=f"{shown} registo(s)", font=F_SMALL, bg=PAPER, fg=INK_600).pack(side="left")

        def get_selected_id():
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("Seleccione um registo", "Seleccione uma linha na tabela primeiro.")
                return None
            return id_by_iid[sel[0]]

        def edit_sel():
            rid = get_selected_id()
            if rid: self._open_form(entity, rid)

        def del_sel():
            rid = get_selected_id()
            if not rid: return
            if entity == "users":
                conn2 = get_conn()
                n = conn2.execute("SELECT COUNT(*) n FROM users").fetchone()["n"]
                conn2.close()
                if n <= 1:
                    messagebox.showwarning("Não permitido", "Não é possível eliminar o único utilizador do sistema.")
                    return
            if not messagebox.askyesno("Confirmar eliminação", f"Eliminar este registo de {meta['label'].lower()}? Esta acção não pode ser desfeita."):
                return
            conn2 = get_conn()
            conn2.execute(f"DELETE FROM {meta['table']} WHERE id=?", (rid,))
            conn2.commit()
            conn2.close()
            self.toast(f"{meta['label']} eliminado.")
            self.navigate(self.current_route)

        tree.bind("<Double-1>", lambda e: edit_sel())
        btn(actions, "Editar seleccionado", edit_sel, kind="ghost", small=True).pack(side="right", padx=4)
        btn(actions, "Eliminar seleccionado", del_sel, kind="danger", small=True).pack(side="right", padx=4)

    def _export_entity_csv(self, entity):
        meta = ENTITIES[entity]
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile=f"{entity}_enpcb.csv",
                                             filetypes=[("CSV", "*.csv")])
        if not path:
            return
        conn = get_conn()
        rows = conn.execute(f"SELECT * FROM {meta['table']} ORDER BY created_at DESC").fetchall()
        heads = [c[1] for c in meta["columns"]]
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(heads)
            for row in rows:
                line = []
                for c, _ in meta["columns"]:
                    fd = field_def(entity, c)
                    if c == "codigo":
                        v = row["codigo"] if "codigo" in row.keys() else ""
                    elif c == "numero_processo":
                        v = row["numero_processo"] if "numero_processo" in row.keys() else ""
                    elif fd and fd[2] == "ref":
                        v = ref_label(conn, fd[4], row[c])
                    elif fd and fd[2] == "password":
                        v = ""
                    else:
                        v = row[c] or ""
                    line.append(v)
                w.writerow(line)
        conn.close()
        self.toast("Ficheiro exportado: " + os.path.basename(path))

    # ---------------- Formulário genérico (Toplevel) ----------------
    def _open_form(self, entity, record_id):
        meta = ENTITIES[entity]
        conn = get_conn()
        record = conn.execute(f"SELECT * FROM {meta['table']} WHERE id=?", (record_id,)).fetchone() if record_id else None

        win = tk.Toplevel(self.root)
        win.title(("Editar " if record_id else "Novo ") + meta["label"])
        win.configure(bg="white")
        win.geometry("460x" + str(120 + 70 * len(meta["fields"])))
        win.transient(self.root)
        win.grab_set()

        tk.Label(win, text=("Editar " if record_id else "Novo ") + meta["label"], font=F_H2,
                 bg="white", fg=NAVY_900).pack(anchor="w", padx=20, pady=(18, 10))

        form = tk.Frame(win, bg="white")
        form.pack(fill="both", expand=True, padx=20)
        widgets = {}

        for key, label, ftype, required, opts in meta["fields"]:
            tk.Label(form, text=label + (" *" if required else ""), font=F_SMALL, bg="white", fg=INK_600, anchor="w").pack(fill="x", pady=(6, 2))
            current = record[key] if record and key in record.keys() and record[key] is not None else ""
            if ftype == "select":
                var = tk.StringVar(value=current)
                cb = ttk.Combobox(form, textvariable=var, values=opts, state="readonly", font=F_BASE)
                cb.pack(fill="x", ipady=3)
                widgets[key] = var
            elif ftype == "ref":
                ref_rows = conn.execute(f"SELECT * FROM {opts} ORDER BY nome" if _has_col(conn, opts, "nome") else f"SELECT * FROM {opts}").fetchall()
                labels = [ref_label(conn, opts, r["id"]) for r in ref_rows]
                ids = [r["id"] for r in ref_rows]
                var = tk.StringVar(value=(labels[ids.index(current)] if current in ids else ""))
                cb = ttk.Combobox(form, textvariable=var, values=labels, state="readonly", font=F_BASE)
                cb.pack(fill="x", ipady=3)
                widgets[key] = (var, ids, labels)
            elif ftype == "password":
                var = tk.StringVar(value=current)
                e = tk.Entry(form, textvariable=var, font=F_BASE, show="•", relief="solid", bd=1)
                e.pack(fill="x", ipady=4)
                widgets[key] = var
            else:
                var = tk.StringVar(value=current)
                e = tk.Entry(form, textvariable=var, font=F_BASE, relief="solid", bd=1)
                e.pack(fill="x", ipady=4)
                widgets[key] = var

        def save():
            data = {}
            for key, label, ftype, required, opts in meta["fields"]:
                if ftype == "ref":
                    var, ids, labels = widgets[key]
                    val = var.get()
                    data[key] = ids[labels.index(val)] if val in labels else ""
                else:
                    data[key] = widgets[key].get().strip()
                if required and not data[key]:
                    messagebox.showwarning("Campo obrigatório", f"Preencha o campo: {label}")
                    return
            conn2 = get_conn()
            if entity == "users":
                dupe = conn2.execute("SELECT 1 FROM users WHERE utilizador=? AND id<>?",
                                      (data["utilizador"], record_id or "")).fetchone()
                if dupe:
                    messagebox.showwarning("Utilizador existente", "Já existe um utilizador com este nome de acesso.")
                    conn2.close()
                    return
            if record_id:
                sets = ",".join(f"{k}=?" for k in data)
                conn2.execute(f"UPDATE {meta['table']} SET {sets} WHERE id=?", list(data.values()) + [record_id])
            else:
                new_rid = new_id()
                cols = list(data.keys()) + ["id", "created_at"]
                vals = list(data.values()) + [new_rid, now_iso()]
                if meta.get("auto_code"):
                    seq = bump_config("turma_seq")
                    codigo = f"T-{data.get('ano_letivo') or datetime.date.today().year}-{seq:02d}"
                    cols.append("codigo"); vals.append(codigo)
                if meta.get("auto_processo"):
                    seq = bump_config("matricula_seq")
                    ano = (data.get("data_matricula") or today_str())[:4]
                    numero = f"M-{ano}-{seq:04d}"
                    cols.append("numero_processo"); vals.append(numero)
                placeholders = ",".join("?" * len(cols))
                conn2.execute(f"INSERT INTO {meta['table']} ({','.join(cols)}) VALUES ({placeholders})", vals)
            conn2.commit()
            conn2.close()
            win.destroy()
            self.toast(f"{meta['label']} guardado com sucesso.")
            self.navigate(self.current_route)

        conn.close()
        foot = tk.Frame(win, bg="white")
        foot.pack(fill="x", padx=20, pady=16)
        btn(foot, "Cancelar", win.destroy, kind="ghost").pack(side="right", padx=(6, 0))
        btn(foot, "Guardar", save, kind="primary").pack(side="right")

    # ------------------------------------------------------------------
    # MINI PAUTA
    # ------------------------------------------------------------------
    def view_pautas(self, parent):
        conn = get_conn()
        h_section(parent, "🗂 Mini Pauta de Notas",
                  "Média = (Avaliação Contínua + Exame Final) / 2. A assiduidade vem das sessões lançadas em Presenças. "
                  "Aprovação requer média ≥ 10 e assiduidade ≥ 75%.").pack(anchor="w", padx=24, pady=(20, 14), fill="x")

        sel = card(parent, padx=16, pady=14)
        sel.pack(fill="x", padx=24)
        turmas = conn.execute("SELECT * FROM turmas ORDER BY codigo").fetchall()
        t_labels = [f"{t['codigo']} — {ref_label(conn, 'cursos', t['curso_id'])}" for t in turmas]
        t_ids = [t["id"] for t in turmas]

        tk.Label(sel, text="Turma", font=F_SMALL, bg=CARD, fg=INK_600).grid(row=0, column=0, sticky="w")
        turma_var = tk.StringVar()
        if self.state["pauta_turma"] in t_ids:
            turma_var.set(t_labels[t_ids.index(self.state["pauta_turma"])])
        cb_turma = ttk.Combobox(sel, textvariable=turma_var, values=t_labels, state="readonly", width=40)
        cb_turma.grid(row=1, column=0, sticky="w", pady=(2, 0))

        tk.Label(sel, text="Disciplina", font=F_SMALL, bg=CARD, fg=INK_600).grid(row=0, column=1, sticky="w", padx=(20, 0))
        disc_var = tk.StringVar()
        cb_disc = ttk.Combobox(sel, textvariable=disc_var, values=[], state="readonly", width=40)
        cb_disc.grid(row=1, column=1, sticky="w", padx=(20, 0), pady=(2, 0))

        table_holder = tk.Frame(parent, bg=PAPER)
        table_holder.pack(fill="both", expand=True, padx=24, pady=16)

        def load_discs(preselect=None):
            tid = t_ids[t_labels.index(turma_var.get())] if turma_var.get() in t_labels else None
            self.state["pauta_turma"] = tid or ""
            discs = conn.execute("SELECT d.* FROM disciplinas d JOIN turmas t ON t.curso_id=d.curso_id WHERE t.id=?", (tid,)).fetchall() if tid else []
            labels = [d["nome"] for d in discs]
            ids = [d["id"] for d in discs]
            cb_disc["values"] = labels
            if preselect and preselect in ids:
                disc_var.set(labels[ids.index(preselect)])
            else:
                disc_var.set("")
            cb_disc.disc_ids = ids
            render_table()

        def render_table(*_):
            for w in table_holder.winfo_children():
                w.destroy()
            if not turma_var.get() or not disc_var.get():
                tk.Label(table_holder, text="Seleccione uma turma e uma disciplina para lançar ou consultar a mini-pauta.",
                         font=F_BASE, bg="#FCEFD2", fg="#6B4C10", padx=12, pady=10).pack(fill="x")
                return
            did = cb_disc.disc_ids[cb_disc["values"].index(disc_var.get())]
            self.state["pauta_disc"] = did
            tid = self.state["pauta_turma"]
            matriculas = conn.execute("""SELECT m.*, f.nome fnome FROM matriculas m
                                          LEFT JOIN formandos f ON f.id=m.formando_id WHERE m.turma_id=?""", (tid,)).fetchall()
            if not matriculas:
                tk.Label(table_holder, text="Sem formandos matriculados nesta turma.", font=F_BASE, bg=CARD, fg=INK_600).pack()
                return
            wrap = card(table_holder, padx=14, pady=14)
            wrap.pack(fill="both", expand=True)
            head = tk.Frame(wrap, bg=CARD)
            head.pack(fill="x")
            for txt, w in [("Formando", 24), ("Av. Contínua", 12), ("Exame Final", 12), ("Média", 8), ("Assiduidade", 12), ("Situação", 16)]:
                tk.Label(head, text=txt, font=F_SMALL, bg=CARD, fg=INK_400, width=w, anchor="w").pack(side="left")
            entries = []
            for m in matriculas:
                row = tk.Frame(wrap, bg=CARD)
                row.pack(fill="x", pady=3)
                tk.Label(row, text=m["fnome"] or "—", font=F_BASE, bg=CARD, width=24, anchor="w").pack(side="left")
                nota = conn.execute("SELECT * FROM notas WHERE matricula_id=? AND disciplina_id=?", (m["id"], did)).fetchone()
                nc_var = tk.StringVar(value=(nota["nota_continua"] if nota and nota["nota_continua"] else ""))
                ex_var = tk.StringVar(value=(nota["exame_final"] if nota and nota["exame_final"] else ""))
                tk.Entry(row, textvariable=nc_var, width=10, relief="solid", bd=1).pack(side="left", padx=(0, 30))
                tk.Entry(row, textvariable=ex_var, width=10, relief="solid", bd=1).pack(side="left", padx=(0, 22))
                calc = calc_nota(conn, m["id"], did)
                tk.Label(row, text=(calc["media"] if calc["media"] is not None else "—"), font=F_MONO, bg=CARD, width=8, anchor="w").pack(side="left")
                assid_txt = f'{calc["assiduidade"]}%' if calc["total_sessions"] > 0 else "Sem sessões"
                tk.Label(row, text=assid_txt, font=F_MONO, bg=CARD, width=12, anchor="w").pack(side="left")
                fg, bgc = situacao_colors(calc["situacao"])
                pill(row, calc["situacao"], fg, bgc).pack(side="left")
                entries.append((m["id"], nc_var, ex_var))

            def save_pauta():
                conn3 = get_conn()
                for mid, nc_var, ex_var in entries:
                    exists = conn3.execute("SELECT id FROM notas WHERE matricula_id=? AND disciplina_id=?", (mid, did)).fetchone()
                    if exists:
                        conn3.execute("UPDATE notas SET nota_continua=?, exame_final=? WHERE id=?",
                                      (nc_var.get(), ex_var.get(), exists["id"]))
                    else:
                        conn3.execute("INSERT INTO notas (id,matricula_id,disciplina_id,nota_continua,exame_final,created_at) VALUES (?,?,?,?,?,?)",
                                      (new_id(), mid, did, nc_var.get(), ex_var.get(), now_iso()))
                conn3.commit()
                conn3.close()
                self.toast("Mini-pauta guardada com sucesso.")
                render_table()

            def export_pauta():
                path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="pauta_enpcb.csv", filetypes=[("CSV", "*.csv")])
                if not path: return
                with open(path, "w", newline="", encoding="utf-8-sig") as f:
                    w = csv.writer(f, delimiter=";")
                    w.writerow(["Formando", "Av. Contínua", "Exame Final", "Média", "Assiduidade (%)", "Situação"])
                    for mid, nc_var, ex_var in entries:
                        c = calc_nota(conn, mid, did)
                        fnome = conn.execute("SELECT f.nome FROM matriculas m JOIN formandos f ON f.id=m.formando_id WHERE m.id=?", (mid,)).fetchone()[0]
                        w.writerow([fnome, nc_var.get(), ex_var.get(), c["media"] or "", c["assiduidade"] if c["total_sessions"] else "", c["situacao"]])
                self.toast("Ficheiro exportado: " + os.path.basename(path))

            fbar = tk.Frame(table_holder, bg=PAPER)
            fbar.pack(fill="x", pady=10)
            btn(fbar, "Guardar Mini Pauta", save_pauta, kind="primary").pack(side="left", padx=(0, 8))
            btn(fbar, "⬇ Exportar Pauta (CSV)", export_pauta, kind="ghost").pack(side="left")

        cb_turma.bind("<<ComboboxSelected>>", lambda e: load_discs())
        cb_disc.bind("<<ComboboxSelected>>", render_table)
        load_discs(preselect=self.state.get("pauta_disc"))

    # ------------------------------------------------------------------
    # PRESENÇAS
    # ------------------------------------------------------------------
    def view_presencas(self, parent):
        conn = get_conn()
        h_section(parent, "✅ Registo de Presenças",
                  "Cada sessão lançada aqui alimenta automaticamente o cálculo de assiduidade nas Mini-Pautas e nos Resultados.").pack(
            anchor="w", padx=24, pady=(20, 14), fill="x")

        sel = card(parent, padx=16, pady=14)
        sel.pack(fill="x", padx=24)
        turmas = conn.execute("SELECT * FROM turmas ORDER BY codigo").fetchall()
        t_labels = [f"{t['codigo']} — {ref_label(conn, 'cursos', t['curso_id'])}" for t in turmas]
        t_ids = [t["id"] for t in turmas]

        tk.Label(sel, text="Turma", font=F_SMALL, bg=CARD, fg=INK_600).grid(row=0, column=0, sticky="w")
        turma_var = tk.StringVar()
        cb_turma = ttk.Combobox(sel, textvariable=turma_var, values=t_labels, state="readonly", width=32)
        cb_turma.grid(row=1, column=0, sticky="w")

        tk.Label(sel, text="Disciplina", font=F_SMALL, bg=CARD, fg=INK_600).grid(row=0, column=1, sticky="w", padx=(20, 0))
        disc_var = tk.StringVar()
        cb_disc = ttk.Combobox(sel, textvariable=disc_var, values=[], state="readonly", width=32)
        cb_disc.grid(row=1, column=1, sticky="w", padx=(20, 0))

        tk.Label(sel, text="Data da sessão (AAAA-MM-DD)", font=F_SMALL, bg=CARD, fg=INK_600).grid(row=0, column=2, sticky="w", padx=(20, 0))
        data_var = tk.StringVar(value=self.state["pres_data"] or today_str())
        e_data = tk.Entry(sel, textvariable=data_var, width=16, relief="solid", bd=1)
        e_data.grid(row=1, column=2, sticky="w", padx=(20, 0), ipady=2)

        table_holder = tk.Frame(parent, bg=PAPER)
        table_holder.pack(fill="both", expand=True, padx=24, pady=16)

        def load_discs():
            tid = t_ids[t_labels.index(turma_var.get())] if turma_var.get() in t_labels else None
            self.state["pres_turma"] = tid or ""
            discs = conn.execute("SELECT d.* FROM disciplinas d JOIN turmas t ON t.curso_id=d.curso_id WHERE t.id=?", (tid,)).fetchall() if tid else []
            labels = [d["nome"] for d in discs]
            cb_disc["values"] = labels
            cb_disc.disc_ids = [d["id"] for d in discs]
            disc_var.set("")
            render()

        def render(*_):
            for w in table_holder.winfo_children():
                w.destroy()
            if not turma_var.get() or not disc_var.get():
                tk.Label(table_holder, text="Seleccione uma turma e uma disciplina para registar a presença de uma sessão.",
                         font=F_BASE, bg="#FCEFD2", fg="#6B4C10", padx=12, pady=10).pack(fill="x")
                return
            did = cb_disc.disc_ids[cb_disc["values"].index(disc_var.get())]
            self.state["pres_disc"] = did
            self.state["pres_data"] = data_var.get()
            tid = self.state["pres_turma"]
            matriculas = conn.execute("""SELECT m.*, f.nome fnome FROM matriculas m
                                          LEFT JOIN formandos f ON f.id=m.formando_id WHERE m.turma_id=?""", (tid,)).fetchall()
            if not matriculas:
                tk.Label(table_holder, text="Sem formandos matriculados nesta turma.", font=F_BASE, bg=CARD, fg=INK_600).pack()
                return
            existing = conn.execute("SELECT * FROM presencas WHERE turma_id=? AND disciplina_id=? AND data=?", (tid, did, data_var.get())).fetchone()
            registos = {}
            if existing:
                for r in conn.execute("SELECT * FROM presenca_registos WHERE presenca_id=?", (existing["id"],)):
                    registos[r["formando_id"]] = bool(r["presente"])

            wrap = card(table_holder, padx=14, pady=14)
            wrap.pack(fill="both", expand=True)
            tk.Label(wrap, text=f"Sessão de {data_var.get()} · {len(matriculas)} formando(s)", font=F_H3, bg=CARD, fg=NAVY_900).pack(anchor="w")
            check_vars = []
            for m in matriculas:
                row = tk.Frame(wrap, bg=CARD)
                row.pack(fill="x", pady=2)
                tk.Label(row, text=m["fnome"] or "—", font=F_BASE, bg=CARD, width=30, anchor="w").pack(side="left")
                present_default = registos.get(m["formando_id"], True)
                var = tk.BooleanVar(value=present_default)
                cb = tk.Checkbutton(row, text="Presente", variable=var, font=F_SMALL, bg=CARD, fg=GREEN_OK,
                                     selectcolor="white", onvalue=True, offvalue=False)
                cb.pack(side="left")
                check_vars.append((m["formando_id"], var))

            def mark_all(v):
                for _, var in check_vars:
                    var.set(v)

            def save_session():
                conn3 = get_conn()
                exist = conn3.execute("SELECT * FROM presencas WHERE turma_id=? AND disciplina_id=? AND data=?", (tid, did, data_var.get())).fetchone()
                if exist:
                    pid = exist["id"]
                    conn3.execute("DELETE FROM presenca_registos WHERE presenca_id=?", (pid,))
                else:
                    pid = new_id()
                    conn3.execute("INSERT INTO presencas (id,turma_id,disciplina_id,data,created_at) VALUES (?,?,?,?,?)",
                                  (pid, tid, did, data_var.get(), now_iso()))
                for fid, var in check_vars:
                    conn3.execute("INSERT INTO presenca_registos (id,presenca_id,formando_id,presente) VALUES (?,?,?,?)",
                                  (new_id(), pid, fid, 1 if var.get() else 0))
                conn3.commit()
                conn3.close()
                self.toast("Presenças guardadas com sucesso.")
                render()

            fbar = tk.Frame(table_holder, bg=PAPER)
            fbar.pack(fill="x", pady=10)
            btn(fbar, "Marcar todos Presentes", lambda: mark_all(True), kind="ghost", small=True).pack(side="left", padx=(0, 8))
            btn(fbar, "Guardar Presenças", save_session, kind="primary").pack(side="left")

            # histórico
            hist = conn.execute("SELECT * FROM presencas WHERE turma_id=? AND disciplina_id=? ORDER BY data DESC", (tid, did)).fetchall()
            hwrap = card(table_holder, padx=14, pady=14)
            hwrap.pack(fill="both", expand=True, pady=(14, 0))
            tk.Label(hwrap, text="Histórico de Sessões", font=F_H3, bg=CARD, fg=NAVY_900).pack(anchor="w", pady=(0, 6))
            if not hist:
                tk.Label(hwrap, text="Ainda sem sessões registadas.", font=F_SMALL, bg=CARD, fg=INK_600).pack(anchor="w")
            for h in hist:
                regs = conn.execute("SELECT presente FROM presenca_registos WHERE presenca_id=?", (h["id"],)).fetchall()
                pres = sum(1 for r in regs if r["presente"])
                falt = sum(1 for r in regs if not r["presente"])
                row = tk.Frame(hwrap, bg=CARD)
                row.pack(fill="x", pady=2)
                tk.Label(row, text=h["data"], font=F_MONO, bg=CARD, width=14, anchor="w").pack(side="left")
                tk.Label(row, text=f"Presentes: {pres}", font=F_SMALL, bg=CARD, fg=GREEN_OK, width=14, anchor="w").pack(side="left")
                tk.Label(row, text=f"Faltas: {falt}", font=F_SMALL, bg=CARD, fg=RED_600, width=12, anchor="w").pack(side="left")

                def del_sess(hid=h["id"]):
                    if not messagebox.askyesno("Eliminar sessão", "Eliminar esta sessão de presença? Isto recalcula a assiduidade."):
                        return
                    c3 = get_conn(); c3.execute("DELETE FROM presencas WHERE id=?", (hid,)); c3.commit(); c3.close()
                    self.toast("Sessão eliminada."); render()

                btn(row, "Eliminar", del_sess, kind="danger", small=True).pack(side="right")

        cb_turma.bind("<<ComboboxSelected>>", lambda e: load_discs())
        cb_disc.bind("<<ComboboxSelected>>", render)
        e_data.bind("<FocusOut>", render)
        e_data.bind("<Return>", render)
        if not turma_var.get():
            tk.Label(table_holder, text="Seleccione uma turma e uma disciplina para registar a presença de uma sessão.",
                     font=F_BASE, bg="#FCEFD2", fg="#6B4C10", padx=12, pady=10).pack(fill="x")

    # ------------------------------------------------------------------
    # MÉDIAS E RESULTADOS
    # ------------------------------------------------------------------
    def view_medias(self, parent):
        conn = get_conn()
        h_section(parent, "📊 Médias e Resultados",
                  "Boletim consolidado por turma, com a média de cada disciplina e a situação final de cada formando.").pack(
            anchor="w", padx=24, pady=(20, 14), fill="x")

        sel = card(parent, padx=16, pady=14)
        sel.pack(fill="x", padx=24)
        turmas = conn.execute("SELECT * FROM turmas ORDER BY codigo").fetchall()
        t_labels = [f"{t['codigo']} — {ref_label(conn, 'cursos', t['curso_id'])}" for t in turmas]
        t_ids = [t["id"] for t in turmas]
        tk.Label(sel, text="Turma", font=F_SMALL, bg=CARD, fg=INK_600).pack(anchor="w")
        turma_var = tk.StringVar()
        cb = ttk.Combobox(sel, textvariable=turma_var, values=t_labels, state="readonly", width=44)
        cb.pack(anchor="w", pady=(2, 0))

        holder = tk.Frame(parent, bg=PAPER)
        holder.pack(fill="both", expand=True, padx=24, pady=16)

        def render(*_):
            for w in holder.winfo_children():
                w.destroy()
            if not turma_var.get():
                tk.Label(holder, text="Seleccione uma turma para consultar o boletim de médias e resultados.",
                         font=F_BASE, bg="#FCEFD2", fg="#6B4C10", padx=12, pady=10).pack(fill="x")
                return
            tid = t_ids[t_labels.index(turma_var.get())]
            turma = conn.execute("SELECT * FROM turmas WHERE id=?", (tid,)).fetchone()
            discs = conn.execute("SELECT * FROM disciplinas WHERE curso_id=?", (turma["curso_id"],)).fetchall()
            matriculas = conn.execute("""SELECT m.*, f.nome fnome FROM matriculas m
                                          LEFT JOIN formandos f ON f.id=m.formando_id WHERE m.turma_id=?""", (tid,)).fetchall()
            if not matriculas or not discs:
                tk.Label(holder, text="Dados insuficientes: a turma precisa de disciplinas e formandos matriculados.",
                         font=F_BASE, bg=CARD, fg=INK_600).pack()
                return
            style = ttk.Style()
            style.configure("Medias.Treeview", rowheight=28, font=F_BASE)
            cols = ["formando"] + [d["id"] for d in discs] + ["media", "situacao"]
            wrap = card(holder)
            wrap.pack(fill="both", expand=True)
            tree = ttk.Treeview(wrap, columns=cols, show="headings", style="Medias.Treeview", height=14)
            tree.heading("formando", text="Formando"); tree.column("formando", width=200)
            for d in discs:
                tree.heading(d["id"], text=d["nome"]); tree.column(d["id"], width=110, anchor="center")
            tree.heading("media", text="Média Geral"); tree.column("media", width=90, anchor="center")
            tree.heading("situacao", text="Situação"); tree.column("situacao", width=140, anchor="center")
            tree.pack(fill="both", expand=True)
            rows_export = []
            for m in matriculas:
                sit = matricula_situacao(conn, m["id"])
                vals = [m["fnome"] or "—"]
                exp_row = [m["fnome"] or "—"]
                for d in discs:
                    c = calc_nota(conn, m["id"], d["id"])
                    vals.append(c["media"] if c["media"] is not None else "—")
                    exp_row.append(c["media"] if c["media"] is not None else "")
                vals += [sit["media"] if sit["media"] is not None else "—", sit["situacao"]]
                exp_row += [sit["media"] if sit["media"] is not None else "", sit["situacao"]]
                tree.insert("", "end", values=vals)
                rows_export.append(exp_row)

            def export_medias():
                path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile=f"medias_{turma['codigo']}.csv", filetypes=[("CSV", "*.csv")])
                if not path: return
                with open(path, "w", newline="", encoding="utf-8-sig") as f:
                    w = csv.writer(f, delimiter=";")
                    w.writerow(["Formando"] + [d["nome"] for d in discs] + ["Média Geral", "Situação"])
                    w.writerows(rows_export)
                self.toast("Ficheiro exportado: " + os.path.basename(path))

            btn(holder, "⬇ Exportar CSV", export_medias, kind="ghost").pack(anchor="e", pady=8)

        cb.bind("<<ComboboxSelected>>", render)
        render()

    # ------------------------------------------------------------------
    # CERTIFICADOS
    # ------------------------------------------------------------------
    def view_certificados(self, parent):
        conn = get_conn()
        h_section(parent, "🏅 Certificados",
                  "Emissão automática com numeração sequencial única, disponível apenas para formandos "
                  'com situação final "Aprovado".').pack(anchor="w", padx=24, pady=(20, 14), fill="x")

        elegiveis = []
        for m in conn.execute("SELECT * FROM matriculas").fetchall():
            sit = matricula_situacao(conn, m["id"])
            if sit["situacao"] == "Aprovado":
                elegiveis.append((m, sit))

        c1 = card(parent, padx=16, pady=14)
        c1.pack(fill="x", padx=24, pady=(0, 16))
        tk.Label(c1, text=f"Formandos elegíveis ({len(elegiveis)})", font=F_H3, bg=CARD, fg=NAVY_900).pack(anchor="w")
        if not elegiveis:
            tk.Label(c1, text="Nenhum formando elegível. Lance notas e presenças para apurar a situação final.",
                     font=F_SMALL, bg=CARD, fg=INK_600).pack(anchor="w", pady=8)
        for m, sit in elegiveis:
            turma = conn.execute("SELECT * FROM turmas WHERE id=?", (m["turma_id"],)).fetchone()
            formando = conn.execute("SELECT * FROM formandos WHERE id=?", (m["formando_id"],)).fetchone()
            ja_emitido = conn.execute("SELECT * FROM certificados WHERE matricula_id=?", (m["id"],)).fetchone()
            row = tk.Frame(c1, bg=CARD)
            row.pack(fill="x", pady=4)
            tk.Label(row, text=formando["nome"] if formando else "—", font=F_BASE, bg=CARD, width=26, anchor="w").pack(side="left")
            tk.Label(row, text=turma["codigo"] if turma else "—", font=F_MONO, bg=CARD, width=12, anchor="w").pack(side="left")
            tk.Label(row, text=f'Média: {sit["media"]}', font=F_SMALL, bg=CARD, width=14, anchor="w").pack(side="left")
            if ja_emitido:
                pill(row, f"Emitido: {ja_emitido['numero']}", INK_600, "#EDE8E1").pack(side="left")
            else:
                btn(row, "Emitir Certificado", lambda mid=m["id"]: self._emitir_certificado(mid), kind="primary", small=True).pack(side="left")

        c2 = card(parent, padx=16, pady=14)
        c2.pack(fill="both", expand=True, padx=24, pady=(0, 20))
        top = tk.Frame(c2, bg=CARD); top.pack(fill="x")
        tk.Label(top, text="Certificados emitidos", font=F_H3, bg=CARD, fg=NAVY_900).pack(side="left")
        btn(top, "⬇ Exportar CSV", self._export_certificados_csv, kind="ghost", small=True).pack(side="right")

        certs = conn.execute("SELECT * FROM certificados ORDER BY created_at DESC").fetchall()
        if not certs:
            tk.Label(c2, text="Ainda sem certificados emitidos.", font=F_SMALL, bg=CARD, fg=INK_600).pack(anchor="w", pady=8)
        for c in certs:
            m = conn.execute("SELECT * FROM matriculas WHERE id=?", (c["matricula_id"],)).fetchone()
            formando = conn.execute("SELECT * FROM formandos WHERE id=?", (m["formando_id"],)).fetchone() if m else None
            turma = conn.execute("SELECT * FROM turmas WHERE id=?", (m["turma_id"],)).fetchone() if m else None
            row = tk.Frame(c2, bg=CARD)
            row.pack(fill="x", pady=4)
            tk.Label(row, text=c["numero"], font=F_MONO, bg=CARD, width=18, anchor="w").pack(side="left")
            tk.Label(row, text=formando["nome"] if formando else "—", font=F_BASE, bg=CARD, width=24, anchor="w").pack(side="left")
            tk.Label(row, text=turma["codigo"] if turma else "—", font=F_MONO, bg=CARD, width=12, anchor="w").pack(side="left")
            tk.Label(row, text=c["data_emissao"], font=F_SMALL, bg=CARD, width=12, anchor="w").pack(side="left")
            btn(row, "Ver / Imprimir", lambda cid=c["id"]: self._preview_certificado(cid), kind="ghost", small=True).pack(side="right")
        conn.close()

    def _emitir_certificado(self, matricula_id):
        conn = get_conn()
        sit = matricula_situacao(conn, matricula_id)
        if sit["situacao"] != "Aprovado":
            self.toast("Apenas formandos Aprovados podem receber certificado.", ok=False)
            conn.close(); return
        if conn.execute("SELECT 1 FROM certificados WHERE matricula_id=?", (matricula_id,)).fetchone():
            self.toast("Certificado já foi emitido para este formando.", ok=False)
            conn.close(); return
        seq = bump_config("cert_seq")
        ano = datetime.date.today().year
        numero = f"ENPCB/{ano}/{seq:04d}"
        cid = new_id()
        conn.execute("INSERT INTO certificados (id,matricula_id,numero,data_emissao,media_final,situacao_final,created_at) "
                     "VALUES (?,?,?,?,?,?,?)", (cid, matricula_id, numero, today_str(), sit["media"], sit["situacao"], now_iso()))
        conn.commit()
        conn.close()
        self.toast("Certificado emitido: " + numero)
        self.navigate("certificados")
        self._preview_certificado(cid)

    def _preview_certificado(self, cert_id):
        conn = get_conn()
        c = conn.execute("SELECT * FROM certificados WHERE id=?", (cert_id,)).fetchone()
        m = conn.execute("SELECT * FROM matriculas WHERE id=?", (c["matricula_id"],)).fetchone()
        formando = conn.execute("SELECT * FROM formandos WHERE id=?", (m["formando_id"],)).fetchone()
        turma = conn.execute("SELECT * FROM turmas WHERE id=?", (m["turma_id"],)).fetchone()
        curso = conn.execute("SELECT * FROM cursos WHERE id=?", (turma["curso_id"],)).fetchone()
        conn.close()

        html = f"""<!DOCTYPE html><html lang="pt-AO"><head><meta charset="utf-8">
        <title>Certificado {c['numero']}</title>
        <style>
        body{{font-family:Georgia,serif;background:#F5F1EC;padding:40px;}}
        .sheet{{max-width:720px;margin:0 auto;background:#fff;border:3px solid #122845;padding:50px 56px;position:relative;}}
        .sheet::before{{content:"";position:absolute;inset:10px;border:1px solid #F0BE2F;}}
        .top{{text-align:center;margin-bottom:22px;}}
        .top small{{letter-spacing:2px;text-transform:uppercase;color:#5B4E4F;font-size:12px;}}
        .top h1{{color:#122845;margin:8px 0 0;font-size:26px;}}
        .body{{text-align:center;font-size:16px;line-height:2;margin:26px 0;color:#241A1B;}}
        .foot{{display:flex;justify-content:space-between;margin-top:36px;font-size:12px;color:#5B4E4F;}}
        @media print{{ body{{background:#fff;padding:0;}} .sheet{{border:2px solid #122845;}} }}
        </style></head><body>
        <div class="sheet">
          <div class="top"><small>República de Angola · Escola Nacional de Protecção Civil e Bombeiros</small><h1>Certificado de Formação</h1></div>
          <div class="body">Certifica-se que <b>{formando['nome']}</b>, portador(a) do documento nº <b>{formando['numero_bi'] or '—'}</b>,
          concluiu com aproveitamento o curso de <b>{curso['nome'] if curso else '—'}</b>, na turma <b>{turma['codigo']}</b>,
          com média final de <b>{c['media_final']}</b> valores, tendo obtido a situação de <b>{c['situacao_final']}</b>.</div>
          <div class="foot"><span>Nº de Certificado: <b>{c['numero']}</b></span><span>Emitido em: {c['data_emissao']}</span></div>
        </div>
        </body></html>"""
        path = os.path.join(CERT_DIR, f"certificado_{c['numero'].replace('/', '-')}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        webbrowser.open("file://" + path)
        self.toast("Certificado aberto no navegador para visualização/impressão.")

    def _export_certificados_csv(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="certificados_enpcb.csv", filetypes=[("CSV", "*.csv")])
        if not path: return
        conn = get_conn()
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["Número", "Formando", "Turma", "Curso", "Data de Emissão", "Média Final", "Situação"])
            for c in conn.execute("SELECT * FROM certificados ORDER BY created_at"):
                m = conn.execute("SELECT * FROM matriculas WHERE id=?", (c["matricula_id"],)).fetchone()
                formando = conn.execute("SELECT * FROM formandos WHERE id=?", (m["formando_id"],)).fetchone() if m else None
                turma = conn.execute("SELECT * FROM turmas WHERE id=?", (m["turma_id"],)).fetchone() if m else None
                curso = conn.execute("SELECT * FROM cursos WHERE id=?", (turma["curso_id"],)).fetchone() if turma else None
                w.writerow([c["numero"], formando["nome"] if formando else "", turma["codigo"] if turma else "",
                            curso["nome"] if curso else "", c["data_emissao"], c["media_final"], c["situacao_final"]])
        conn.close()
        self.toast("Ficheiro exportado: " + os.path.basename(path))

    # ------------------------------------------------------------------
    # RELATÓRIOS
    # ------------------------------------------------------------------
    def view_relatorios(self, parent):
        conn = get_conn()
        h_section(parent, "📑 Relatórios e Exportações",
                  "Relatórios consolidados prontos para exportação em CSV (compatível com Excel).").pack(
            anchor="w", padx=24, pady=(20, 14), fill="x")

        matriculas = conn.execute("SELECT * FROM matriculas").fetchall()
        situacoes = [(m, matricula_situacao(conn, m["id"])) for m in matriculas]
        aprov = sum(1 for _, s in situacoes if s["situacao"] == "Aprovado")
        reprov = sum(1 for _, s in situacoes if s["situacao"] == "Reprovado")
        excl = sum(1 for _, s in situacoes if s["situacao"] == "Excluído por Faltas")
        pend = len(situacoes) - aprov - reprov - excl

        kpi_wrap = tk.Frame(parent, bg=PAPER)
        kpi_wrap.pack(fill="x", padx=24)
        for label, num in [("Aprovados", aprov), ("Reprovados", reprov), ("Excluídos por faltas", excl), ("Por avaliar", pend)]:
            c = card(kpi_wrap, padx=16, pady=14)
            c.pack(side="left", fill="both", expand=True, padx=(0, 10))
            tk.Label(c, text=str(num), font=("Segoe UI", 22, "bold"), bg=CARD, fg=NAVY_900).pack(anchor="w")
            tk.Label(c, text=label, font=F_SMALL, bg=CARD, fg=INK_600).pack(anchor="w")

        c1 = card(parent, padx=16, pady=14)
        c1.pack(fill="both", expand=True, padx=24, pady=16)
        top = tk.Frame(c1, bg=CARD); top.pack(fill="x")
        tk.Label(top, text="Relatório de Situação Final por Formando", font=F_H3, bg=CARD, fg=NAVY_900).pack(side="left")
        btn(top, "⬇ Exportar CSV", lambda: self._export_situacao_csv(situacoes, conn), kind="ghost", small=True).pack(side="right")

        style = ttk.Style(); style.configure("Rel.Treeview", rowheight=26, font=F_BASE)
        tree = ttk.Treeview(c1, columns=["formando", "turma", "media", "assid", "situacao"], show="headings", style="Rel.Treeview", height=12)
        for c, t, w in [("formando", "Formando", 220), ("turma", "Turma", 100), ("media", "Média", 80), ("assid", "Assiduidade", 100), ("situacao", "Situação", 160)]:
            tree.heading(c, text=t); tree.column(c, width=w, anchor="w" if c == "formando" else "center")
        tree.pack(fill="both", expand=True, pady=(8, 0))
        for m, sit in situacoes:
            formando = conn.execute("SELECT * FROM formandos WHERE id=?", (m["formando_id"],)).fetchone()
            turma = conn.execute("SELECT * FROM turmas WHERE id=?", (m["turma_id"],)).fetchone()
            tree.insert("", "end", values=[formando["nome"] if formando else "—", turma["codigo"] if turma else "—",
                                            sit["media"] if sit["media"] is not None else "—",
                                            f'{sit["assiduidade"]}%' if sit["assiduidade"] is not None else "—", sit["situacao"]])

        grid2 = tk.Frame(parent, bg=PAPER)
        grid2.pack(fill="x", padx=24, pady=(0, 24))
        exports = [("Formandos (base completa)", "formandos"), ("Turmas (base completa)", "turmas"),
                   ("Matrículas (base completa)", "matriculas")]
        for label, entity in exports:
            c = card(grid2, padx=16, pady=14)
            c.pack(side="left", fill="both", expand=True, padx=(0, 10))
            tk.Label(c, text=label, font=F_H3, bg=CARD, fg=NAVY_900).pack(anchor="w", pady=(0, 8))
            btn(c, "⬇ Exportar CSV", lambda e=entity: self._export_entity_csv(e), kind="ghost", small=True).pack(anchor="w")
        c = card(grid2, padx=16, pady=14)
        c.pack(side="left", fill="both", expand=True)
        tk.Label(c, text="Certificados emitidos", font=F_H3, bg=CARD, fg=NAVY_900).pack(anchor="w", pady=(0, 8))
        btn(c, "⬇ Exportar CSV", self._export_certificados_csv, kind="ghost", small=True).pack(anchor="w")
        conn.close()

    def _export_situacao_csv(self, situacoes, conn):
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile="situacao_final_enpcb.csv", filetypes=[("CSV", "*.csv")])
        if not path: return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["Formando", "Turma", "Curso", "Média", "Assiduidade (%)", "Situação"])
            for m, sit in situacoes:
                formando = conn.execute("SELECT * FROM formandos WHERE id=?", (m["formando_id"],)).fetchone()
                turma = conn.execute("SELECT * FROM turmas WHERE id=?", (m["turma_id"],)).fetchone()
                curso = conn.execute("SELECT * FROM cursos WHERE id=?", (turma["curso_id"],)).fetchone() if turma else None
                w.writerow([formando["nome"] if formando else "", turma["codigo"] if turma else "",
                            curso["nome"] if curso else "", sit["media"] or "", sit["assiduidade"] or "", sit["situacao"]])
        self.toast("Ficheiro exportado: " + os.path.basename(path))

    # ------------------------------------------------------------------
    # PESQUISA GLOBAL
    # ------------------------------------------------------------------
    def view_pesquisa(self, parent):
        h_section(parent, "🔍 Pesquisa Global",
                  "Procure formandos, instrutores, cursos ou turmas em toda a base de dados.").pack(
            anchor="w", padx=24, pady=(20, 14), fill="x")
        top = card(parent, padx=16, pady=14)
        top.pack(fill="x", padx=24)
        var = tk.StringVar(value=self.state.get("pesquisa_termo", ""))
        e = tk.Entry(top, textvariable=var, font=F_BASE, relief="solid", bd=1)
        e.pack(fill="x", ipady=5)
        e.focus()

        holder = tk.Frame(parent, bg=PAPER)
        holder.pack(fill="both", expand=True, padx=24, pady=16)

        def render(*_):
            term = var.get().strip()
            self.state["pesquisa_termo"] = term
            for w in holder.winfo_children():
                w.destroy()
            if len(term) < 2:
                tk.Label(holder, text="Escreva um termo de pesquisa para começar.", font=F_BASE,
                         bg="#FCEFD2", fg="#6B4C10", padx=12, pady=10).pack(fill="x")
                return
            conn = get_conn()
            q = term.lower()
            groups = [
                ("🎓 Formandos", "formandos", conn.execute("SELECT * FROM formandos").fetchall(),
                 lambda r: q in (r["nome"] or "").lower() or q in (r["numero_bi"] or "").lower(),
                 lambda r: (r["nome"], r["numero_bi"])),
                ("👨‍🏫 Instrutores", "instrutores", conn.execute("SELECT * FROM instrutores").fetchall(),
                 lambda r: q in (r["nome"] or "").lower(), lambda r: (r["nome"], r["especialidade"])),
                ("📘 Cursos", "cursos", conn.execute("SELECT * FROM cursos").fetchall(),
                 lambda r: q in (r["nome"] or "").lower(), lambda r: (r["nome"], r["area"])),
                ("👥 Turmas", "turmas", conn.execute("SELECT * FROM turmas").fetchall(),
                 lambda r: q in (r["codigo"] or "").lower(), lambda r: (r["codigo"], ref_label(conn, "cursos", r["curso_id"]))),
            ]
            any_found = False
            for title, entity, rows, matchfn, labelfn in groups:
                matches = [r for r in rows if matchfn(r)]
                if not matches:
                    continue
                any_found = True
                c = card(holder, padx=16, pady=14)
                c.pack(fill="x", pady=(0, 10))
                tk.Label(c, text=f"{title} ({len(matches)})", font=F_H3, bg=CARD, fg=NAVY_900).pack(anchor="w", pady=(0, 6))
                for r in matches[:20]:
                    label, sub = labelfn(r)
                    row = tk.Frame(c, bg=CARD)
                    row.pack(fill="x", pady=2)
                    tk.Label(row, text=label, font=F_BASE_B, bg=CARD, fg=INK_900).pack(side="left")
                    tk.Label(row, text=f"  ·  {sub}" if sub else "", font=F_SMALL, bg=CARD, fg=INK_400).pack(side="left")
                    btn(row, "Abrir", lambda en=entity, rid=r["id"]: self._open_form(en, rid), kind="ghost", small=True).pack(side="right")
            conn.close()
            if not any_found:
                tk.Label(holder, text=f'Sem resultados para "{term}".', font=F_BASE, bg=CARD, fg=INK_600, padx=12, pady=10).pack(fill="x")

        e.bind("<KeyRelease>", render)
        render()

    # ------------------------------------------------------------------
    # BACKUP
    # ------------------------------------------------------------------
    def view_backup(self, parent):
        h_section(parent, "☁ Cópia de Segurança",
                  "Exporte toda a base de dados do sistema para um ficheiro local, ou restaure a partir de uma cópia anterior.").pack(
            anchor="w", padx=24, pady=(20, 14), fill="x")

        row = tk.Frame(parent, bg=PAPER)
        row.pack(fill="x", padx=24)

        c1 = card(row, padx=18, pady=16)
        c1.pack(side="left", fill="both", expand=True, padx=(0, 10))
        tk.Label(c1, text="Exportar cópia de segurança", font=F_H3, bg=CARD, fg=NAVY_900).pack(anchor="w")
        tk.Label(c1, text="Gera um ficheiro .json com todos os registos do sistema.", font=F_SMALL, bg=CARD,
                 fg=INK_600, wraplength=280, justify="left").pack(anchor="w", pady=(4, 12))
        btn(c1, "⬇ Exportar Base de Dados", self._export_backup, kind="primary").pack(anchor="w")

        c2 = card(row, padx=18, pady=16)
        c2.pack(side="left", fill="both", expand=True, padx=(10, 0))
        tk.Label(c2, text="Restaurar cópia de segurança", font=F_H3, bg=CARD, fg=NAVY_900).pack(anchor="w")
        tk.Label(c2, text="⚠ A restauração substitui todos os dados actuais pelos dados do ficheiro.", font=F_SMALL,
                 bg=CARD, fg=INK_600, wraplength=280, justify="left").pack(anchor="w", pady=(4, 12))
        btn(c2, "Restaurar a partir de um ficheiro", self._restore_backup, kind="ghost").pack(anchor="w")

        info = card(parent, padx=18, pady=16)
        info.pack(fill="x", padx=24, pady=18)
        tk.Label(info, text="Localização dos dados", font=F_H3, bg=CARD, fg=NAVY_900).pack(anchor="w")
        tk.Label(info, text=DB_PATH, font=F_MONO, bg=CARD, fg=INK_600).pack(anchor="w", pady=(4, 0))

    def _export_backup(self):
        path = filedialog.asksaveasfilename(defaultextension=".json",
                                             initialfile=f"backup_enpcb_{today_str()}.json",
                                             filetypes=[("JSON", "*.json")])
        if not path:
            return
        conn = get_conn()
        payload = {"exported_at": now_iso(), "tables": {}}
        for table in ["users", "formandos", "instrutores", "cursos", "disciplinas", "turmas",
                      "matriculas", "notas", "presencas", "presenca_registos", "certificados", "config"]:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            payload["tables"][table] = [dict(r) for r in rows]
        conn.close()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        self.toast("Cópia de segurança exportada: " + os.path.basename(path))

    def _restore_backup(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        if not messagebox.askyesno("Confirmar restauro", "Isto irá substituir TODOS os dados actuais pelos dados do ficheiro. Continuar?"):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            conn = get_conn()
            conn.execute("PRAGMA foreign_keys = OFF;")
            conn.executescript(SCHEMA)
            # eliminar filhos antes dos pais para respeitar as chaves estrangeiras
            delete_order = ["certificados", "presenca_registos", "presencas", "notas", "matriculas",
                             "disciplinas", "turmas", "cursos", "instrutores", "formandos", "users", "config"]
            for table in delete_order:
                if table in payload["tables"]:
                    conn.execute(f"DELETE FROM {table}")
            # inserir pais antes dos filhos
            for table in reversed(delete_order):
                rows = payload["tables"].get(table, [])
                if rows:
                    cols = list(rows[0].keys())
                    placeholders = ",".join("?" * len(cols))
                    conn.executemany(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})",
                                      [[r.get(c) for c in cols] for r in rows])
            conn.commit()
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.close()
            self.toast("Base de dados restaurada com sucesso.")
            self.navigate("dashboard")
        except Exception as e:
            messagebox.showerror("Erro ao restaurar", f"Ficheiro inválido ou corrompido.\n\n{e}")


def _has_col(conn, table, col):
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(r["name"] == col for r in cur.fetchall())


# =====================================================================
#  Ponto de entrada
# =====================================================================

def main():
    init_db()
    root = tk.Tk()
    try:
        root.state("zoomed")  # Windows/Linux
    except tk.TclError:
        try:
            root.attributes("-zoomed", True)  # alguns Linux/Mac
        except tk.TclError:
            pass
    app = ENPCBApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
