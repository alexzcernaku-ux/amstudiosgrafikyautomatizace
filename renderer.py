"""
Vezme jméno šablony + data, vyplní je do HTML (Jinja2) a vyrenderuje PNG
přesně stejným postupem, co jsme celou dobu ověřovali ručně (WeasyPrint → PDF → PNG).
"""
import os
import subprocess
import tempfile
from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
_env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))


def render(template_name: str, data: dict, dpi: int = 96) -> bytes:
    """Vrátí PNG bytes. template_name např. 'yt_nahled.html', 'z_nemovitosti_cover.html'."""
    template = _env.get_template(template_name)
    html_content = template.render(**data)
    return render_raw_html(html_content, dpi=dpi)


def render_raw_html(html_content: str, dpi: int = 96) -> bytes:
    """Vyrenderuje přímo hotový HTML string — používá to pilíř Vtipné, kde Claude
    generuje čerstvé HTML pokaždé znovu, ne skrz Jinja2 šablonu."""
    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = os.path.join(tmp, "out.pdf")

        HTML(string=html_content, base_url=TEMPLATES_DIR).write_pdf(pdf_path)

        subprocess.run(
            ["pdftoppm", "-png", "-r", str(dpi), pdf_path, os.path.join(tmp, "out")],
            check=True, timeout=60,
        )
        actual_png = os.path.join(tmp, "out-1.png")
        with open(actual_png, "rb") as f:
            return f.read()
