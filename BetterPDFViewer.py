# -*- coding: utf-8 -*-
"""
BetterPDFViewer.py - Burp Suite Extension (single file)
Version 1.0 — first release.
Load in Burp: Extensions > Add > Type: Python > select this file

Requirements:
  1. Jython 2.7 (Extender > Options > Python Environment)
  2. Python 3 installed (python.org, Homebrew, apt, etc.)

PyMuPDF must already be installed for the detected Python 3 — the
extension only detects, it NEVER installs anything. Install it manually:
  Windows:      py -m pip install pymupdf
  macOS/Linux:  python3 -m pip install pymupdf
On macOS it probes Homebrew, python.org framework installs, pyenv, Conda,
/usr/bin/python3 and PATH — Burp launched from Finder/Dock has no shell
PATH, so the explicit locations matter.
"""
_HELPER_SRC = r"""#!/usr/bin/env python3
import sys,json,base64,traceback
def _w(d,o):
    s=json.dumps(d)
    open(o,"w",encoding="utf-8").write(s) if o else print(s)
def _e(m,o): _w({"success":False,"error":m},o)
def cmd_render(pdf,pg,zm,o):
    try:
        import fitz
        doc=fitz.open(pdf);tot=doc.page_count
        meta=doc.metadata or {}
        toc=[{"level":t[0],"title":t[1],"page":t[2]} for t in (doc.get_toc() or [])]
        res={"success":True,"total_pages":tot,"metadata":{k:meta.get(k,"") for k in ("title","author","subject","creator","producer","creationDate","modDate","format","encryption")},"toc":toc,"pages":[]}
        n=int(pg)
        if 0<=n<tot:
            p=doc[n];mat=fitz.Matrix(float(zm),float(zm))
            pix=p.get_pixmap(matrix=mat,alpha=False,colorspace=fitz.csRGB);rc=p.rect
            res["pages"].append({"page_num":n,"image_b64":base64.b64encode(pix.tobytes("png")).decode(),"width_px":pix.width,"height_px":pix.height,"width_pt":rc.width,"height_pt":rc.height,"text":p.get_text("text"),"links":[{"uri":lk.get("uri",""),"page":lk.get("page",-1)} for lk in p.get_links()]})
        doc.close();_w(res,o)
    except ImportError: _e("PyMuPDF not installed. Run: pip install pymupdf",o)
    except Exception: _e(traceback.format_exc(),o)
def cmd_thumbs(pdf,zm,o):
    try:
        import fitz;doc=fitz.open(pdf)
        res={"success":True,"total_pages":doc.page_count,"thumbnails":[]}
        for i in range(min(doc.page_count,200)):
            p=doc[i];mat=fitz.Matrix(float(zm),float(zm));pix=p.get_pixmap(matrix=mat,alpha=False,colorspace=fitz.csRGB)
            res["thumbnails"].append({"page_num":i,"image_b64":base64.b64encode(pix.tobytes("png")).decode(),"width_px":pix.width,"height_px":pix.height})
        doc.close();_w(res,o)
    except ImportError: _e("PyMuPDF not installed. Run: pip install pymupdf",o)
    except Exception: _e(traceback.format_exc(),o)
def cmd_alltext(pdf,o):
    try:
        import fitz;doc=fitz.open(pdf)
        pages=[{"page_num":i,"text":doc[i].get_text("text")} for i in range(doc.page_count)]
        doc.close();_w({"success":True,"total_pages":len(pages),"pages":pages},o)
    except ImportError: _e("PyMuPDF not installed. Run: pip install pymupdf",o)
    except Exception: _e(traceback.format_exc(),o)
def cmd_check(o):
    try:
        import fitz;_w({"success":True,"pymupdf_version":fitz.version[0],"python":sys.version},o)
    except ImportError: _e("PyMuPDF not installed. Run: pip install pymupdf",o)
if __name__=="__main__":
    if len(sys.argv)<2: print(json.dumps({"success":False,"error":"no command"}));sys.exit(1)
    c=sys.argv[1]
    if c=="render": cmd_render(sys.argv[2],sys.argv[3],sys.argv[4],sys.argv[5] if len(sys.argv)>5 else None)
    elif c=="thumbs": cmd_thumbs(sys.argv[2],sys.argv[3],sys.argv[4] if len(sys.argv)>4 else None)
    elif c=="alltext": cmd_alltext(sys.argv[2],sys.argv[3] if len(sys.argv)>3 else None)
    elif c=="check": cmd_check(sys.argv[2] if len(sys.argv)>2 else None)
    else: print(json.dumps({"success":False,"error":"unknown command: "+c}))
"""
from burp import IBurpExtender, IMessageEditorTabFactory, IMessageEditorTab, IExtensionStateListener
import os, json, base64, threading, tempfile
from java.awt import BorderLayout, FlowLayout, Color, Font, Dimension, Cursor
from java.awt.event import MouseAdapter, MouseWheelListener, KeyAdapter, KeyEvent
from java.io import ByteArrayInputStream
from javax.imageio import ImageIO
from javax.swing import (JPanel, JButton, JLabel, JScrollPane, JTextArea,
    JTextField, SwingUtilities, ImageIcon, BorderFactory, SwingConstants,
    JTabbedPane, JFileChooser, JOptionPane, Box, BoxLayout, JComponent)
from javax.swing.border import EmptyBorder
from java.lang import System

EXT_NAME="Better PDF Viewer"; EXT_VER="1.0"
ZOOMS=[0.5,0.75,1.0,1.25,1.5,1.75,2.0,2.5,3.0,4.0]; DEF_ZOOM=1.5; THMB_ZOOM=0.13
C_BG=Color(0x2B,0x2B,0x2B); C_TB=Color(0x3C,0x3F,0x41); C_ACC=Color(0xE8,0x58,0x1A)
C_FG=Color(0xCC,0xCC,0xCC); C_DIM=Color(0x88,0x88,0x88); C_EDIT=Color(0x1E,0x1E,0x1E)
C_CVS=Color(0x55,0x55,0x55); C_SEL=Color(0x4A,0x4A,0x4A)
_HDIR=_HPATH=_PY3=_CB=None; _READY=False

def _extract():
    global _HDIR,_HPATH
    _HDIR=os.path.join(tempfile.gettempdir(),"burp_bpdfv")
    _HPATH=os.path.join(_HDIR,"h.py")
    if not os.path.isdir(_HDIR): os.makedirs(_HDIR)
    with open(_HPATH,"wb") as f: f.write(_HELPER_SRC.encode("utf-8"))

def _run_proc(args_list):
    """Run process via Java ProcessBuilder (Jython 2.7 compatible).

    Jython's `except Exception:` does NOT catch Java exceptions, so any Java
    Throwable raised here (e.g. IOException when the program is not on PATH —
    common when Burp is launched from Finder/Dock without the shell PATH) is
    converted into a Python exception. Otherwise it would escape every
    `except Exception:` in the callers and crash registerExtenderCallbacks
    before the message-editor tab factory is registered.
    """
    from java.lang import ProcessBuilder, Throwable
    from java.util import ArrayList
    try:
        jargs = ArrayList()
        for a in args_list: jargs.add(a)
        pb = ProcessBuilder(jargs)
        pb.redirectErrorStream(True)
        p = pb.start()
        from java.io import BufferedReader, InputStreamReader
        br = BufferedReader(InputStreamReader(p.getInputStream(), "UTF-8"))
        out = []
        line = br.readLine()
        while line is not None:
            out.append(line)
            line = br.readLine()
        p.waitFor()
        return "\n".join(out), p.exitValue()
    except Throwable as ex:
        raise RuntimeError(str(ex))

def _py3_candidates():
    """Every detected Python 3 executable, in preference order."""
    home=System.getProperty("user.home")
    cands=[]
    # pythoncore pattern - Python 3.14+ (os.listdir Jython compatible)
    py_base=os.path.join(home,"AppData","Local","Python")
    try:
        if os.path.isdir(py_base):
            for d in os.listdir(py_base):
                exe=os.path.join(py_base,d,"python.exe")
                if os.path.isfile(exe): cands.insert(0,exe)
    except Exception: pass
    # Classic Windows paths Programs\Python
    for v in ["314","313","312","311","310","39","38"]:
        cands.append(os.path.join(home,"AppData","Local","Programs","Python","Python"+v,"python.exe"))
        cands.append("C:\\Python"+v+"\\python.exe")
    # Linux / macOS — Homebrew first (usually newer than the OS-shipped Python)
    cands += [
        "/opt/homebrew/bin/python3",        # macOS Homebrew (Apple Silicon)
        "/opt/homebrew/opt/python3/bin/python3",
        "/usr/local/bin/python3",           # macOS Intel (Homebrew) / Linux
        os.path.join(home, ".pyenv", "shims", "python3"),    # pyenv
        os.path.join(home, "miniconda3", "bin", "python3"),  # Conda
        os.path.join(home, "anaconda3", "bin", "python3"),   # Conda
        "/usr/bin/python3",
        "/usr/bin/python",
        "/usr/local/bin/python",
    ]
    # python.org installer on macOS (framework build): not in PATH when Burp
    # is launched from Finder/Dock, so probe the standard location explicitly.
    fw_base = "/Library/Frameworks/Python.framework/Versions"
    try:
        if os.path.isdir(fw_base):
            for d in sorted(os.listdir(fw_base)):
                exe = os.path.join(fw_base, d, "bin", "python3")
                if os.path.isfile(exe): cands.insert(0, exe)
    except Exception: pass
    cands+=["python","python3"]
    found=[]
    for c in cands:
        if not c: continue
        if c not in ["python","python3"] and not os.path.isfile(c): continue
        try:
            out,_=_run_proc([c,"--version"])
            if out.strip().startswith("Python 3"): found.append(c)
        except Exception: pass
    return found

def _find_py3():
    """First detected Python 3 (startup check and log)."""
    found = _py3_candidates()
    return found[0] if found else None

def _call(cmd,args):
    """Call Python3 helper and read JSON result. Uses Java ProcessBuilder (Jython-safe)."""
    fd,tmp=tempfile.mkstemp(suffix=".json",dir=_HDIR); os.close(fd)
    try:
        _run_proc([_PY3,_HPATH,cmd]+[str(a) for a in args]+[tmp])
        if os.path.isfile(tmp):
            import io
            with io.open(tmp,"r",encoding="utf-8") as f: return json.load(f)
        return {"success":False,"error":"no output from helper"}
    except Exception as ex: return {"success":False,"error":str(ex)}
    finally:
        try: os.remove(tmp)
        except Exception: pass

def _is_windows():
    return "windows" in System.getProperty("os.name","").lower()

def _venv_dir():
    # Optional manually-prepared venv location. The extension only READS it;
    # it never creates it and never installs anything.
    return os.path.join(System.getProperty("user.home"), ".burp_bpdfv", "venv")

def _venv_python(vdir):
    if _is_windows(): return os.path.join(vdir, "Scripts", "python.exe")
    return os.path.join(vdir, "bin", "python")

def _pipx_venv_python():
    """Locate a pipx-installed pymupdf (pipx isolates each app in its own
    venv). Returns the venv's python or None. Detection only — never installs."""
    home = System.getProperty("user.home")
    bases = []
    try:
        px_home = os.environ.get("PIPX_HOME")
        if px_home: bases.append(px_home)
    except Exception: pass
    if _is_windows(): bases.append(os.path.join(home, "pipx"))
    else: bases.append(os.path.join(home, ".local", "pipx"))
    for b in bases:
        if not b: continue
        vp = os.path.join(b, "venvs", "pymupdf")
        py = os.path.join(vp, "Scripts", "python.exe") if _is_windows() else os.path.join(vp, "bin", "python")
        if os.path.isfile(py): return py
    return None

def _ensure_pymupdf(log):
    """Find a Python 3 that already has PyMuPDF. NEVER installs anything.
    Preference: manual venv > pipx venv > every detected python, in order.
    Updates the global _PY3 and returns the 'check' result dict."""
    global _PY3
    tries = []
    vpy = _venv_python(_venv_dir())
    if os.path.isfile(vpy): tries.append(("manual venv", vpy))
    px = _pipx_venv_python()
    if px: tries.append(("pipx", px))
    for c in _py3_candidates(): tries.append(("python", c))

    for label, py in tries:
        _PY3 = py
        res = _call("check", [])
        if res.get("success"):
            log("Using %s interpreter: %s" % (label, py))
            return res
        log("%s lacks PyMuPDF: %s" % (label, py))

    log("PyMuPDF not found in any detected Python. Install it manually:")
    log("  Windows:      py -m pip install pymupdf")
    log("  macOS/Linux:  python3 -m pip install pymupdf")
    log("  or via pipx:  pipx install pymupdf")
    log("Then reload the extension.")
    return {"success": False, "error": "PyMuPDF not found in any detected Python"}

def _jimg(b64): return ImageIO.read(ByteArrayInputStream(base64.b64decode(b64)))
def _mk_btn(txt,tip=None):
    b=JButton(txt); b.setBackground(C_TB); b.setForeground(C_FG)
    b.setFocusPainted(False); b.setBorderPainted(False); b.setOpaque(True)
    b.setCursor(Cursor.getPredefinedCursor(Cursor.HAND_CURSOR))
    if tip: b.setToolTipText(tip)
    return b
def _mk_lbl(txt,c=C_FG,bold=False,sz=12):
    l=JLabel(txt); l.setForeground(c)
    l.setFont(Font("SansSerif",Font.BOLD if bold else Font.PLAIN,sz))
    return l

class ThumbPanel(JPanel):
    """Left sidebar with page thumbnails."""
    def __init__(self, on_page):
        super(ThumbPanel,self).__init__()
        self._on_page=on_page; self._items=[]; self._cur=0
        self.setLayout(BoxLayout(self,BoxLayout.Y_AXIS))
        self.setBackground(C_BG); self.setBorder(EmptyBorder(4,4,4,4))

    def load(self,thumbs):
        self.removeAll(); self._items=[]
        for t in thumbs:
            try:
                il=JLabel(ImageIcon(_jimg(t["image_b64"])))
                il.setAlignmentX(JComponent.CENTER_ALIGNMENT)
                nl=_mk_lbl(str(t["page_num"]+1),C_DIM,sz=10)
                nl.setHorizontalAlignment(SwingConstants.CENTER)
                nl.setAlignmentX(JComponent.CENTER_ALIGNMENT)
                w=JPanel(); w.setLayout(BoxLayout(w,BoxLayout.Y_AXIS))
                w.setBackground(C_SEL); w.setBorder(BorderFactory.createLineBorder(C_BG,2))
                w.setAlignmentX(JComponent.CENTER_ALIGNMENT)
                w.add(Box.createVerticalStrut(3)); w.add(il); w.add(nl); w.add(Box.createVerticalStrut(3))
                pn=t["page_num"]; pr=w; ir=self._items; op=self._on_page; sr=self
                class _ML(MouseAdapter):
                    def mouseClicked(s,e): op(pn)
                    def mouseEntered(s,e): pr.setBackground(Color(0x5A,0x5A,0x5A))
                    def mouseExited(s,e):
                        idx=ir.index((pr,il)) if (pr,il) in ir else -1
                        pr.setBackground(C_ACC if idx==sr._cur else C_SEL)
                w.addMouseListener(_ML())
                self._items.append((w,il)); self.add(w); self.add(Box.createVerticalStrut(4))
            except Exception: pass
        self.revalidate(); self.repaint()

    def select(self,n):
        self._cur=n
        for i,(w,il) in enumerate(self._items):
            if i==n: w.setBackground(C_ACC); w.setBorder(BorderFactory.createLineBorder(C_ACC,2))
            else: w.setBackground(C_SEL); w.setBorder(BorderFactory.createLineBorder(C_BG,2))
        self.revalidate(); self.repaint()


class CanvasPanel(JPanel):
    """Main area displaying the rendered PDF page."""
    def __init__(self):
        super(CanvasPanel,self).__init__(BorderLayout())
        self.setBackground(C_CVS)
        self._lbl=JLabel("",SwingConstants.CENTER)
        self._lbl.setBackground(C_CVS); self.add(self._lbl,BorderLayout.CENTER)

    def show_image(self,jimg):
        if jimg: self._lbl.setIcon(ImageIcon(jimg)); self._lbl.setText("")
        else: self._lbl.setIcon(None); self._lbl.setText("<html><center><font color='#888888'>No page</font></center></html>")
        self.revalidate(); self.repaint()

    def show_loading(self):
        self._lbl.setIcon(None)
        self._lbl.setText("<html><center><font color='#aaaaaa' size='4'>Rendering page...</font></center></html>")
        self.revalidate(); self.repaint()

    def show_error(self,msg):
        self._lbl.setIcon(None)
        safe=msg.replace("&","&"+"amp;").replace("<","&"+"lt;").replace(">","&"+"gt;").replace("\n","<br>")
        self._lbl.setText("<html><center><font color='#ff6060'><b>Error</b><br><br>"+safe+"</font></center></html>")
        self.revalidate(); self.repaint()

    def show_setup(self,msg):
        self._lbl.setIcon(None)
        self._lbl.setText("<html><center><font color='#ffaa00' size='4'>"+msg+"</font></center></html>")
        self.revalidate(); self.repaint()


class MetaPanel(JPanel):
    """PDF metadata and table of contents panel."""
    def __init__(self):
        super(MetaPanel,self).__init__(BorderLayout())
        self.setBackground(C_BG)
        self._ta=JTextArea(); self._ta.setEditable(False)
        self._ta.setBackground(C_EDIT); self._ta.setForeground(C_FG)
        self._ta.setFont(Font("Monospaced",Font.PLAIN,12)); self._ta.setBorder(EmptyBorder(8,8,8,8))
        sp=JScrollPane(self._ta); sp.setBorder(None)
        self.add(sp,BorderLayout.CENTER)

    def set_meta(self,meta,toc,total):
        lines=["=== PDF Metadata ==="]
        for k,v in meta.items():
            if v: lines.append("  %-16s %s"%(k.replace("_"," ").title()+":",v))
        lines+=["","  %-16s %d"%("Total pages:",total),""]
        if toc:
            lines.append("=== Table of Contents ===")
            for item in toc:
                lines.append("  "*item.get("level",1)+"* "+item.get("title","")+"  (p.%d)"%item.get("page",0))
        self._ta.setText("\n".join(lines)); self._ta.setCaretPosition(0)

class PDFViewerTab(IMessageEditorTab):
    """Tab displayed in the Burp message editor when the response is a PDF."""

    def __init__(self, controller, editable):
        self._controller = controller
        self._current_page = 0
        self._total_pages  = 0
        self._zoom         = DEF_ZOOM
        self._pdf_bytes    = None
        self._pdf_tmp      = None
        self._meta         = {}
        self._toc          = []
        self._loading      = False

        # --- root panel ---
        self._root = JPanel(BorderLayout())
        self._root.setBackground(C_BG)

        # --- top toolbar ---
        tb = JPanel(FlowLayout(FlowLayout.CENTER, 4, 4))
        tb.setBackground(C_TB)
        tb.setBorder(EmptyBorder(2,4,2,4))

        self._btn_prev  = _mk_btn(" < ", "Previous page")
        self._lbl_pg    = _mk_lbl("  -/-  ", C_FG, sz=12)
        self._btn_next  = _mk_btn(" > ", "Next page")
        self._btn_zm_m  = _mk_btn(" - ", "Zoom out")
        self._lbl_zm    = _mk_lbl(" 150% ", C_FG, sz=11)
        self._btn_zm_p  = _mk_btn(" + ", "Zoom in")
        self._btn_dl    = _mk_btn(" Download ", "Save PDF to disk")
        self._btn_txt   = _mk_btn(" Metadata ", "View PDF metadata")

        for w in [self._btn_prev, self._lbl_pg, self._btn_next,
                  _mk_lbl("  |  ", C_DIM),
                  self._btn_zm_m, self._lbl_zm, self._btn_zm_p,
                  _mk_lbl("  |  ", C_DIM),
                  self._btn_dl,
                  _mk_lbl("  |  ", C_DIM),
                  self._btn_txt]:
            tb.add(w)

        # --- central area: thumbnails + canvas ---
        self._thumb_panel = ThumbPanel(self._goto_page)
        thumb_scroll = JScrollPane(self._thumb_panel)
        thumb_scroll.setPreferredSize(Dimension(115, 0))
        thumb_scroll.setBackground(C_BG)
        thumb_scroll.getViewport().setBackground(C_BG)
        thumb_scroll.setBorder(None)

        self._canvas = CanvasPanel()
        canvas_scroll = JScrollPane(self._canvas)
        canvas_scroll.setBackground(C_CVS)
        canvas_scroll.getViewport().setBackground(C_CVS)
        canvas_scroll.setBorder(None)

        # zoom with mouse wheel
        class _MWL(MouseWheelListener):
            def mouseWheelMoved(s, e):
                if e.isControlDown():
                    if e.getWheelRotation() < 0: self._zoom_in()
                    else: self._zoom_out()
                else:
                    canvas_scroll.getVerticalScrollBar().setValue(
                        canvas_scroll.getVerticalScrollBar().getValue() +
                        e.getWheelRotation() * 30)
        canvas_scroll.addMouseWheelListener(_MWL())

        center = JPanel(BorderLayout())
        center.add(thumb_scroll, BorderLayout.WEST)
        center.add(canvas_scroll, BorderLayout.CENTER)

        # --- metadata panel (hidden by default) ---
        self._meta_panel = MetaPanel()
        self._side_tabs  = JTabbedPane()
        self._side_tabs.setBackground(C_BG)
        self._side_tabs.setForeground(C_FG)
        self._side_tabs.addTab("Metadata", self._meta_panel)

        from javax.swing import JSplitPane
        self._split = JSplitPane(JSplitPane.HORIZONTAL_SPLIT, center, self._side_tabs)
        self._split.setResizeWeight(0.72)
        self._split.setDividerSize(5)
        self._split.setBackground(C_BG)
        self._side_tabs.setVisible(False)
        self._split.setDividerLocation(1.0)

        # Toolbar added directly (no scroll pane) so FlowLayout.CENTER can
        # center the buttons across the full width; if the panel gets too
        # narrow the buttons wrap to a new row instead of being clipped.
        self._root.add(tb, BorderLayout.NORTH)
        self._root.add(self._split, BorderLayout.CENTER)

        # status bar
        sb = JPanel(FlowLayout(FlowLayout.LEFT, 6, 2))
        sb.setBackground(C_TB)
        self._lbl_status = _mk_lbl("Waiting for PDF...", C_DIM, sz=11)
        sb.add(self._lbl_status)
        self._root.add(sb, BorderLayout.SOUTH)

        # --- event wiring ---
        self._btn_prev.addActionListener(lambda e: self._page_delta(-1))
        self._btn_next.addActionListener(lambda e: self._page_delta(+1))
        self._btn_zm_m.addActionListener(lambda e: self._zoom_out())
        self._btn_zm_p.addActionListener(lambda e: self._zoom_in())
        self._btn_dl.addActionListener(lambda e: self._download())
        self._btn_txt.addActionListener(lambda e: self._toggle_side())

        self._canvas.show_setup("No PDF loaded yet.")

    # ---- IMessageEditorTab interface ----
    def getTabCaption(self): return EXT_NAME
    def getUiComponent(self): return self._root
    def isEnabled(self, content, isRequest):
        if isRequest: return False
        if not content: return False
        try:
            # Look for the Content-Type only in the header section (up to
            # \r\n\r\n), so a body that merely mentions "application/pdf"
            # (e.g. HTML docs) is not a false positive.
            header_raw = "".join([chr(content[i] & 0xFF) for i in range(min(len(content), 2000))])
            hdr_end = header_raw.find("\r\n\r\n")
            ct_zone = header_raw[:hdr_end] if hdr_end >= 0 else header_raw
            if "application/pdf" in ct_zone.lower():
                return True
            # Check %PDF magic bytes anywhere in the first 4096 bytes
            lim = min(len(content), 4096)
            for i in range(lim - 3):
                if ((content[i]   & 0xFF) == 0x25 and   # %
                    (content[i+1] & 0xFF) == 0x50 and   # P
                    (content[i+2] & 0xFF) == 0x44 and   # D
                    (content[i+3] & 0xFF) == 0x46):     # F
                    return True
        except Exception:
            pass
        return False
    def isModified(self): return False
    def getSelectedData(self): return None

    def setMessage(self, content, isRequest):
        if isRequest or not content: return
        try:
            # Find body offset: try Burp API, then manual fallback (\r\n\r\n)
            offset = 0
            try:
                offset = _CB.getHelpers().analyzeResponse(content).getBodyOffset()
            except Exception:
                n = len(content)
                for i in range(n - 3):
                    if ((content[i]   & 0xFF) == 13 and
                        (content[i+1] & 0xFF) == 10 and
                        (content[i+2] & 0xFF) == 13 and
                        (content[i+3] & 0xFF) == 10):
                        offset = i + 4; break
            # Convert Java byte array to Python bytearray
            self._pdf_bytes = bytearray([content[offset + i] & 0xFF
                                          for i in range(len(content) - offset)])
            self._load_pdf()
        except Exception as ex:
            self._canvas.show_error(str(ex))

    # ---- internal methods ----
    def _write_tmp(self):
        if self._pdf_tmp and os.path.isfile(self._pdf_tmp):
            try: os.remove(self._pdf_tmp)
            except Exception: pass
        fd,self._pdf_tmp = tempfile.mkstemp(suffix=".pdf", dir=_HDIR)
        os.close(fd)
        with open(self._pdf_tmp, "wb") as f:
            f.write(self._pdf_bytes)

    def _load_pdf(self):
        if not _READY:
            self._canvas.show_setup("Configure Python 3 + PyMuPDF.<br>Check the extension Output panel.")
            return
        if self._loading: return
        self._loading = True
        self._canvas.show_loading()
        self._lbl_status.setText("Loading PDF...")
        def _run():
            try:
                self._write_tmp()
                res = _call("render", [self._pdf_tmp, 0, self._zoom])
                if not res.get("success"):
                    SwingUtilities.invokeLater(lambda: self._canvas.show_error(res.get("error","")))
                    return
                self._total_pages = res.get("total_pages", 0)
                self._meta = res.get("metadata", {})
                self._toc  = res.get("toc", [])
                pages = res.get("pages", [])
                if pages:
                    jimg = _jimg(pages[0]["image_b64"])
                    SwingUtilities.invokeLater(lambda: self._show_page_image(jimg, 0))
                # UI updates from this background thread must go through the EDT
                SwingUtilities.invokeLater(lambda m=self._meta, t=self._toc, tp=self._total_pages:
                                           self._meta_panel.set_meta(m, t, tp))
                # load thumbnails in background
                _t = threading.Thread(target=self._load_thumbs)
                _t.daemon = True
                _t.start()
            except Exception as ex:
                SwingUtilities.invokeLater(lambda: self._canvas.show_error(str(ex)))
            finally:
                self._loading = False
        _th = threading.Thread(target=_run)
        _th.daemon = True
        _th.start()

    def _load_thumbs(self):
        try:
            res = _call("thumbs", [self._pdf_tmp, THMB_ZOOM])
            if res.get("success"):
                thumbs = res.get("thumbnails",[])
                SwingUtilities.invokeLater(lambda: self._thumb_panel.load(thumbs))
                SwingUtilities.invokeLater(lambda: self._thumb_panel.select(0))
        except Exception: pass

    def _show_page_image(self, jimg, page_num):
        self._current_page = page_num
        self._canvas.show_image(jimg)
        self._lbl_pg.setText("  %d / %d  " % (page_num+1, self._total_pages))
        self._thumb_panel.select(page_num)
        self._lbl_status.setText("Page %d of %d  |  Zoom: %d%%" % (page_num+1, self._total_pages, int(self._zoom*100)))

    def _goto_page(self, n):
        if not _READY or self._pdf_tmp is None: return
        if n < 0 or n >= self._total_pages: return
        self._canvas.show_loading()
        def _run():
            res = _call("render", [self._pdf_tmp, n, self._zoom])
            if res.get("success") and res.get("pages"):
                pg = res["pages"][0]
                jimg = _jimg(pg["image_b64"])
                SwingUtilities.invokeLater(lambda: self._show_page_image(jimg, n))
            else:
                SwingUtilities.invokeLater(lambda: self._canvas.show_error(res.get("error","")))
        _tg = threading.Thread(target=_run)
        _tg.daemon = True
        _tg.start()

    def _page_delta(self, d):
        self._goto_page(self._current_page + d)

    def _zoom_in(self):
        idx = ZOOMS.index(self._zoom) if self._zoom in ZOOMS else 4
        if idx < len(ZOOMS)-1:
            self._zoom = ZOOMS[idx+1]; self._lbl_zm.setText(" %d%% "%int(self._zoom*100))
            self._goto_page(self._current_page)

    def _zoom_out(self):
        idx = ZOOMS.index(self._zoom) if self._zoom in ZOOMS else 4
        if idx > 0:
            self._zoom = ZOOMS[idx-1]; self._lbl_zm.setText(" %d%% "%int(self._zoom*100))
            self._goto_page(self._current_page)

    def _toggle_side(self):
        # Show/hide the metadata side panel.
        vis = not self._side_tabs.isVisible()
        self._side_tabs.setVisible(vis)
        self._split.setDividerLocation(0.72 if vis else 1.0)
        self._split.revalidate()

    def _download(self):
        if not self._pdf_bytes:
            JOptionPane.showMessageDialog(self._root,"No PDF available.","Warning",JOptionPane.WARNING_MESSAGE)
            return
        fc = JFileChooser(); fc.setDialogTitle("Save PDF")
        if fc.showSaveDialog(self._root) == JFileChooser.APPROVE_OPTION:
            path = fc.getSelectedFile().getAbsolutePath()
            if not path.lower().endswith(".pdf"): path += ".pdf"
            try:
                with open(path,"wb") as f: f.write(self._pdf_bytes)
                JOptionPane.showMessageDialog(self._root,"PDF saved to:\n"+path,"Saved",JOptionPane.INFORMATION_MESSAGE)
            except Exception as ex:
                JOptionPane.showMessageDialog(self._root,"Error saving:\n"+str(ex),"Error",JOptionPane.ERROR_MESSAGE)

class BurpExtender(IBurpExtender, IMessageEditorTabFactory, IExtensionStateListener):
    """Burp Suite extension entry point."""

    def extensionUnloaded(self):
        """Clean up temp directory on extension unload."""
        import shutil
        try:
            if _HDIR and os.path.isdir(_HDIR):
                shutil.rmtree(_HDIR, ignore_errors=True)
        except Exception:
            pass

    def registerExtenderCallbacks(self, callbacks):
        global _CB, _PY3, _READY

        _CB = callbacks
        callbacks.setExtensionName(EXT_NAME)
        out = callbacks.getStdout()

        def log(msg):
            out.write(("[%s] %s\n" % (EXT_NAME, msg)).encode("utf-8"))

        log("Version %s starting..." % EXT_VER)

        # 1. Extract helper to %TEMP%
        try:
            _extract()
            log("Helper extracted to: " + _HPATH)
        except Exception as ex:
            log("ERROR extracting helper: " + str(ex))
            return

        # 2. Locate Python 3
        _PY3 = _find_py3()
        if not _PY3:
            log("ERROR: Python 3 not found.")
            log("Install from https://www.python.org/downloads/ and restart Burp.")
            callbacks.registerMessageEditorTabFactory(self)
            return

        log("Python 3 found: " + _PY3)

        # 3. Detect a working PyMuPDF (never installs anything)
        res = _ensure_pymupdf(log)
        if res.get("success"):
            _READY = True
            log("PyMuPDF OK  (version %s)  [%s]" % (res.get("pymupdf_version","?"), _PY3))
        else:
            log("WARNING: PyMuPDF is not available: " + res.get("error",""))
            log("Install manually with: python3 -m pip install pymupdf")

        # 4. Register the tab in the message editor and unload listener
        callbacks.registerExtensionStateListener(self)
        callbacks.registerMessageEditorTabFactory(self)

        if _READY:
            log("Extension loaded successfully! Open a PDF response to view.")
        else:
            log("Extension loaded WITHOUT rendering. Install PyMuPDF and reload.")

    # IMessageEditorTabFactory
    def createNewInstance(self, controller, editable):
        return PDFViewerTab(controller, editable)
