# Better PDF Viewer — Burp Suite Extension

> **Version 1.0 — first release.**  
> High-quality rendering for PDFs exposed in HTTP responses.  
> **PyMuPDF (libmupdf)** engine — superior to existing alternatives.

---

## Quick Installation

### 1. Python 3 + PyMuPDF
The extension only detects — it **never installs anything**. Install PyMuPDF yourself:
```cmd
pip install pymupdf      # or: pipx install pymupdf
```
It tries every detected Python until one has PyMuPDF: manual venv
(`~/.burp_bpdfv/venv`), pipx venv, Homebrew, python.org framework installs,
pyenv, Conda, `/usr/bin/python3` and the plain `python`/`python3` on PATH.

### 2. Get Jython
Download `jython-standalone-2.7.x.jar` from: https://www.jython.org/download  
_(or via Maven: `org.python:jython-standalone:2.7.4`)_

### 3. Configure Jython in Burp
`Extender → Options → Python Environment → select the .jar file`

### 4. Load the Extension
`Extensions → Add → Type: Python → select BetterPDFViewer.py`

✅ Done! The **"Better PDF Viewer"** tab appears automatically on any PDF response.



---

## Features

| Feature | Description |
|---|---|
| 🖼️ PyMuPDF Rendering | libmupdf engine — pixel-perfect, antialiasing, ClearType |
| 🔍 Zoom 50%–400% | `−` / `+` buttons or `Ctrl + Scroll` |
| 📑 Thumbnails | Sidebar with all pages, clickable for navigation |
| 📋 Metadata | Title, author, subject, creator, producer, dates, ToC (**Metadata** button) |
| 💾 Download | Save the PDF to disk with one click (**Download** button) |
| 🎯 Smart Detection | By `Content-Type: application/pdf` AND/OR `%PDF` magic bytes |
| 📦 Single File | No external dependencies beyond PyMuPDF |

---

## Requirements

| Component | Minimum Version | Where to Get |
|---|---|---|
| Burp Suite | Any version with extensions | [portswigger.net](https://portswigger.net/burp) |
| Jython | 2.7.x | [jython.org/download](https://www.jython.org/download) |
| Python | 3.8+ | [python.org/downloads](https://www.python.org/downloads/) |
| PyMuPDF | 1.x | `pip install pymupdf` |

**Operating systems:** Windows 10/11, Linux, macOS (Intel and Apple Silicon)

---

## Troubleshooting

### Extension loads but Python 3 is not found
```
[Better PDF Viewer] ERROR: Python 3 not found.
```
Install Python 3: https://www.python.org/downloads/ (Windows/macOS/Linux).  
The extension searches: Homebrew, python.org framework installs, pyenv, Conda,
`/usr/bin/python3` and `PATH`. Reload the extension after installing Python.

### PyMuPDF not installed
```
[Better PDF Viewer] PyMuPDF not found.
```
Install it manually:

- Windows: `py -m pip install pymupdf`
- macOS/Linux: `python3 -m pip install pymupdf`
- or via pipx: `pipx install pymupdf`

Then reload the extension in Burp (**Reload**).

### Tab does not appear on PDF response
Check that the response actually contains a PDF (the Raw tab should show `%PDF-` in the body). The extension detects by `Content-Type: application/pdf` or by `%PDF` magic bytes.

### Full logs
Check the **Output** and **Errors** tabs of the extension in Burp for details on any error.

---

## File Structure

```
BetterPDFViewer.py    ← The extension (only file needed for use)
README.md             ← Usage guide
LICENSE               ← MIT License
```

---

## License

MIT — see [LICENSE](LICENSE) for details.

**Dependency:** PyMuPDF uses the AGPL-3.0 license (Artifex/MuPDF).  
For closed commercial use, check the terms of Artifex Software.
